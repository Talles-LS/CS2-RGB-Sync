"""
Servidor HTTP local para recepção de eventos do CS2 Game State Integration (GSI).

Garantias de segurança e desempenho:
- Escuta exclusivamente em `127.0.0.1` (rejeita qualquer outro endereço de bind).
- Autentica requisições POST via token compartilhado usando `hmac.compare_digest`.
- Nunca executa comandos RGB dentro da requisição HTTP.
- Enfileira o payload válido em uma fila thread-safe e responde HTTP 200 imediatamente.
- Nunca armazena ou registra o token em claro nos logs ou no diagnóstico.
"""

from __future__ import annotations

import copy
import hmac
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from flask import Flask, jsonify, request
from werkzeug.serving import ThreadedWSGIServer, make_server

from app.logger import get_logger, register_sensitive_token, sanitize_payload

LOOPBACK_HOST = "127.0.0.1"
MAX_PAYLOAD_BYTES = 512 * 1024


@dataclass(frozen=True)
class GSIRawMessage:
    """Mensagem GSI bruta recebida e enfileirada pelo servidor HTTP."""

    received_at_ns: int
    received_at_wall: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class GSIServerStats:
    """Snapshot de estatísticas do servidor GSI para diagnóstico e interface."""

    running: bool
    host: str
    port: int
    requests_received: int
    requests_accepted: int
    auth_failures: int
    parse_errors: int
    dropped_events: int
    queue_size: int
    last_received_at: Optional[float]
    last_error: str


class GSIServer:
    """Servidor HTTP local baseado em Flask + Werkzeug para receber POSTs do CS2 GSI."""

    def __init__(
        self,
        host: str = LOOPBACK_HOST,
        port: int = 3000,
        auth_token: str = "",
        event_queue: Optional[queue.Queue[GSIRawMessage]] = None,
        max_queue_size: int = 256,
    ) -> None:
        if host != LOOPBACK_HOST:
            raise ValueError(
                f"Bind proibido '{host}': o servidor GSI deve escutar somente em {LOOPBACK_HOST}."
            )
        if port != 0 and not (1024 <= port <= 65535):
            raise ValueError(
                f"Porta inválida '{port}': utilize 0 (efêmera) ou 1024..65535."
            )
        if not auth_token or not isinstance(auth_token, str):
            raise ValueError("auth_token é obrigatório para iniciar o GSIServer.")

        self._host = host
        self._configured_port = port
        self._actual_port = port
        self._auth_token = auth_token
        register_sensitive_token(auth_token)

        self._logger = get_logger("gsi_server")
        self._queue: queue.Queue[GSIRawMessage] = event_queue or queue.Queue(
            maxsize=max_queue_size
        )

        self._state_lock = threading.RLock()
        self._running = False
        self._requests_received = 0
        self._requests_accepted = 0
        self._auth_failures = 0
        self._parse_errors = 0
        self._dropped_events = 0
        self._last_received_at: Optional[float] = None
        self._last_error = ""
        self._last_payload: Optional[dict[str, Any]] = None

        self._server: Optional[ThreadedWSGIServer] = None
        self._thread: Optional[threading.Thread] = None

        # Silencia logs padrão do Werkzeug para não poluir nem registrar headers/IPs repetitivos
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        self._app = self._create_flask_app()

    @property
    def host(self) -> str:
        return self._host

    @property
    def actual_port(self) -> int:
        with self._state_lock:
            return self._actual_port

    @property
    def event_queue(self) -> queue.Queue[GSIRawMessage]:
        return self._queue

    def update_token(self, new_token: str) -> None:
        """Atualiza o token esperado em tempo de execução de forma thread-safe."""
        if not new_token or not isinstance(new_token, str):
            raise ValueError("Novo token GSI inválido.")
        register_sensitive_token(new_token)
        with self._state_lock:
            self._auth_token = new_token

    def get_stats(self) -> GSIServerStats:
        with self._state_lock:
            return GSIServerStats(
                running=self._running,
                host=self._host,
                port=self._actual_port,
                requests_received=self._requests_received,
                requests_accepted=self._requests_accepted,
                auth_failures=self._auth_failures,
                parse_errors=self._parse_errors,
                dropped_events=self._dropped_events,
                queue_size=self._queue.qsize(),
                last_received_at=self._last_received_at,
                last_error=self._last_error,
            )

    def get_last_payload(self) -> Optional[dict[str, Any]]:
        """Retorna cópia do último payload válido recebido (com token mascarado)."""
        with self._state_lock:
            return copy.deepcopy(self._last_payload)

    def _enqueue_non_blocking(self, msg: GSIRawMessage) -> None:
        """Enfileira mensagem descartando a mais antiga caso a fila esteja cheia."""
        try:
            self._queue.put_nowait(msg)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            with self._state_lock:
                self._dropped_events += 1
            try:
                self._queue.put_nowait(msg)
            except queue.Full:
                pass

    def _create_flask_app(self) -> Flask:
        app = Flask("cs2_rgb_sync_gsi")
        app.config["MAX_CONTENT_LENGTH"] = MAX_PAYLOAD_BYTES

        @app.get("/health")
        def health() -> Any:
            return jsonify({"status": "ok", "service": "cs2-rgb-sync"}), 200

        @app.post("/")
        def receive_gsi() -> Any:
            received_ns = time.perf_counter_ns()
            received_wall = time.time()

            with self._state_lock:
                self._requests_received += 1
                expected_token = self._auth_token

            payload = request.get_json(force=True, silent=True)
            if not isinstance(payload, dict):
                with self._state_lock:
                    self._parse_errors += 1
                    self._last_error = "Payload JSON inválido ou ausente."
                self._logger.warning("Requisição GSI ignorada: JSON inválido.")
                return jsonify({"status": "error", "reason": "invalid_json"}), 400

            auth_block = payload.get("auth")
            provided_token = (
                auth_block.get("token") if isinstance(auth_block, dict) else None
            )
            if not isinstance(provided_token, str) or not hmac.compare_digest(
                provided_token, expected_token
            ):
                with self._state_lock:
                    self._auth_failures += 1
                    self._last_error = "Falha na validação do token GSI."
                self._logger.warning("Requisição GSI rejeitada: token inválido ou ausente.")
                return jsonify({"status": "error", "reason": "unauthorized"}), 401

            sanitized = sanitize_payload(payload)
            with self._state_lock:
                self._requests_accepted += 1
                self._last_received_at = received_wall
                self._last_payload = sanitized
                self._last_error = ""

            self._enqueue_non_blocking(
                GSIRawMessage(
                    received_at_ns=received_ns,
                    received_at_wall=received_wall,
                    payload=sanitized,
                )
            )
            return jsonify({"status": "ok"}), 200

        @app.errorhandler(413)
        def payload_too_large(_err: Any) -> Any:
            with self._state_lock:
                self._parse_errors += 1
                self._last_error = "Payload excede o limite de 512 KB."
            return jsonify({"status": "error", "reason": "payload_too_large"}), 413

        return app

    def start(self) -> int:
        """Inicia o servidor HTTP em thread dedicada e retorna a porta ativa."""
        with self._state_lock:
            if self._running:
                return self._actual_port

            server = make_server(
                self._host,
                self._configured_port,
                self._app,
                threaded=True,
            )
            if not isinstance(server, ThreadedWSGIServer):
                server.timeout = 0.5
            self._server = server
            self._actual_port = int(server.server_port)
            self._running = True

            self._thread = threading.Thread(
                target=self._serve_forever,
                name="CS2RGBSync-GSIServer",
                daemon=True,
            )
            self._thread.start()
            self._logger.info(
                "Servidor GSI iniciado em http://%s:%d/", self._host, self._actual_port
            )
            return self._actual_port

    def _serve_forever(self) -> None:
        server = self._server
        if server is None:
            return
        try:
            server.serve_forever(poll_interval=0.2)
        except Exception as exc:
            with self._state_lock:
                self._last_error = f"Erro no servidor GSI: {exc}"
            self._logger.exception("Falha inesperada no servidor GSI")
        finally:
            with self._state_lock:
                self._running = False

    def stop(self) -> None:
        """Encerra o servidor HTTP de forma limpa."""
        with self._state_lock:
            server = self._server
            thread = self._thread
            if not self._running and server is None:
                return
            self._running = False

        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass

        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)

        with self._state_lock:
            self._server = None
            self._thread = None
            self._actual_port = self._configured_port
        self._logger.info("Servidor GSI encerrado.")
