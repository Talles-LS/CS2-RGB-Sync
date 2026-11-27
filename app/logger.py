"""
Sistema de logging seguro do CS2 RGB Sync.

Fornece:
- Filtro de redação automática de tokens secretos (`TokenRedactingFilter`).
- Handler em memória em anel (`RingBufferHandler`) para exibição e cópia na UI.
- Handler rotativo em disco (`RotatingFileHandler`).
- Sanitização de payloads GSI (`sanitize_payload`) para mascarar `auth.token`.
"""

from __future__ import annotations

import copy
import logging
import os
import threading
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable, Optional

REDACTED_PLACEHOLDER = "***REDACTED***"


def get_default_log_dir() -> Path:
    """Retorna o diretório padrão de logs em %LOCALAPPDATA%\\CS2RGBSync\\logs."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "CS2RGBSync" / "logs"
    return Path.home() / ".cs2rgbsync" / "logs"


def sanitize_payload(payload: Any) -> Any:
    """
    Retorna uma cópia profunda do payload GSI com o campo `auth.token` mascarado.
    Nunca modifica o dicionário original em memória.
    """
    if not isinstance(payload, dict):
        return copy.deepcopy(payload)
    sanitized = copy.deepcopy(payload)
    auth = sanitized.get("auth")
    if isinstance(auth, dict) and "token" in auth:
        auth["token"] = REDACTED_PLACEHOLDER
    return sanitized


class TokenRedactingFilter(logging.Filter):
    """Filtro de logging que oculta tokens registrados em mensagens e argumentos."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._secrets: set[str] = set()

    def register_secret(self, secret: Optional[str]) -> None:
        """Registra um segredo que nunca deve aparecer em texto claro nos logs."""
        if secret and isinstance(secret, str) and len(secret) >= 4:
            with self._lock:
                self._secrets.add(secret)

    def clear_secrets(self) -> None:
        """Remove todos os segredos registrados (útil em testes)."""
        with self._lock:
            self._secrets.clear()

    def redact_text(self, text: str) -> str:
        """Substitui qualquer segredo conhecido por REDACTED_PLACEHOLDER."""
        with self._lock:
            secrets_snapshot = tuple(self._secrets)
        result = text
        for secret in secrets_snapshot:
            if secret in result:
                result = result.replace(secret, REDACTED_PLACEHOLDER)
        return result

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {
                k: (REDACTED_PLACEHOLDER if k == "token" else self._redact_value(v))
                for k, v in value.items()
            }
        if isinstance(value, tuple):
            return tuple(self._redact_value(item) for item in value)
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact_value(v) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(self._redact_value(arg) for arg in record.args)
            else:
                record.args = self._redact_value(record.args)
        return True


class RingBufferHandler(logging.Handler):
    """Armazena as últimas linhas formatadas de log em memória (thread-safe)."""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._buffer: deque[str] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return
        with self._lock:
            self._buffer.append(msg)

    def get_lines(self) -> list[str]:
        """Retorna cópia das linhas armazenadas no buffer."""
        with self._lock:
            return list(self._buffer)

    def get_text(self) -> str:
        """Retorna todas as linhas concatenadas por quebra de linha."""
        return "\n".join(self.get_lines())

    def clear(self) -> None:
        """Limpa o buffer em memória."""
        with self._lock:
            self._buffer.clear()


_GLOBAL_REDACT_FILTER = TokenRedactingFilter()
_GLOBAL_RING_HANDLER = RingBufferHandler(capacity=500)
_SETUP_LOCK = threading.Lock()
_CONFIGURED = False


def register_sensitive_token(token: Optional[str]) -> None:
    """Registra o token GSI no filtro global de redação de logs."""
    _GLOBAL_REDACT_FILTER.register_secret(token)


def get_ring_buffer_handler() -> RingBufferHandler:
    """Retorna o handler global em memória para leitura na UI/diagnóstico."""
    return _GLOBAL_RING_HANDLER


def get_token_filter() -> TokenRedactingFilter:
    """Retorna a instância global do filtro de redação."""
    return _GLOBAL_REDACT_FILTER


def configure_logging(
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    enable_file: bool = True,
    enable_console: bool = False,
) -> logging.Logger:
    """Configura o logger raiz da aplicação `cs2rgbsync` de forma idempotente."""
    global _CONFIGURED
    logger = logging.getLogger("cs2rgbsync")
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    with _SETUP_LOCK:
        logger.setLevel(level)
        logger.propagate = False

        if _GLOBAL_REDACT_FILTER not in logger.filters:
            logger.addFilter(_GLOBAL_REDACT_FILTER)

        _GLOBAL_RING_HANDLER.setFormatter(formatter)
        if _GLOBAL_REDACT_FILTER not in _GLOBAL_RING_HANDLER.filters:
            _GLOBAL_RING_HANDLER.addFilter(_GLOBAL_REDACT_FILTER)
        if _GLOBAL_RING_HANDLER not in logger.handlers:
            logger.addHandler(_GLOBAL_RING_HANDLER)

        if enable_file and not any(
            isinstance(h, RotatingFileHandler) for h in logger.handlers
        ):
            target_dir = log_dir or get_default_log_dir()
            target_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                target_dir / "cs2rgbsync.log",
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(_GLOBAL_REDACT_FILTER)
            logger.addHandler(file_handler)

        if enable_console and not any(
            type(h) is logging.StreamHandler for h in logger.handlers
        ):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.addFilter(_GLOBAL_REDACT_FILTER)
            logger.addHandler(console_handler)

        _CONFIGURED = True
    return logger


def get_logger(name: str = "cs2rgbsync") -> logging.Logger:
    """Retorna um sub-logger ligado à hierarquia `cs2rgbsync`."""
    if not _CONFIGURED:
        configure_logging(enable_file=False, enable_console=False)
    if name == "cs2rgbsync" or name.startswith("cs2rgbsync."):
        return logging.getLogger(name)
    return logging.getLogger(f"cs2rgbsync.{name}")


def iter_redacted_records(lines: Iterable[str]) -> list[str]:
    """Aplica redação extra sob demanda ao exportar logs."""
    return [_GLOBAL_REDACT_FILTER.redact_text(line) for line in lines]
