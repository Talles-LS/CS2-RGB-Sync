"""Testes automatizados para o servidor HTTP local GSIServer."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app.gsi_server import GSIServer
from app.logger import (
    REDACTED_PLACEHOLDER,
    configure_logging,
    get_ring_buffer_handler,
    get_token_filter,
)


def _http_post(url: str, data: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_gsi_server_rejects_non_loopback_host() -> None:
    with pytest.raises(ValueError):
        GSIServer(host="0.0.0.0", port=0, auth_token="token_valido_12345")
    with pytest.raises(ValueError):
        GSIServer(host="192.168.1.10", port=0, auth_token="token_valido_12345")


def test_gsi_server_accepts_valid_payload_and_redacts_token(tmp_path: Path) -> None:
    token = "test_secret_token_abcdef"
    get_token_filter().clear_secrets()
    configure_logging(log_dir=tmp_path / "logs", level=logging.INFO, enable_file=False)
    ring = get_ring_buffer_handler()
    ring.clear()

    server = GSIServer(host="127.0.0.1", port=0, auth_token=token)
    port = server.start()
    try:
        payload = {
            "provider": {"name": "Counter-Strike 2", "appid": 730},
            "round": {"phase": "live", "bomb": "planted"},
            "player": {"team": "T", "state": {"health": 45, "flashed": 120}},
            "auth": {"token": token},
        }
        status, body = _http_post(
            f"http://127.0.0.1:{port}/",
            json.dumps(payload).encode("utf-8"),
        )
        assert status == 200
        assert body["status"] == "ok"

        msg = server.event_queue.get(timeout=1.0)
        assert msg.received_at_ns > 0
        assert msg.payload["round"]["bomb"] == "planted"
        assert msg.payload["auth"]["token"] == REDACTED_PLACEHOLDER

        last_payload = server.get_last_payload()
        assert last_payload is not None
        assert last_payload["auth"]["token"] == REDACTED_PLACEHOLDER

        stats = server.get_stats()
        assert stats.running is True
        assert stats.requests_received == 1
        assert stats.requests_accepted == 1
        assert stats.auth_failures == 0
        assert stats.parse_errors == 0
        assert token not in ring.get_text()
    finally:
        server.stop()


def test_gsi_server_rejects_invalid_or_missing_token(tmp_path: Path) -> None:
    token = "expected_token_999999"
    wrong_token = "attacker_wrong_token"
    get_token_filter().clear_secrets()
    configure_logging(log_dir=tmp_path / "logs", level=logging.INFO, enable_file=False)
    ring = get_ring_buffer_handler()
    ring.clear()

    server = GSIServer(host="127.0.0.1", port=0, auth_token=token)
    port = server.start()
    try:
        # Token incorreto
        status1, _ = _http_post(
            f"http://127.0.0.1:{port}/",
            json.dumps({"provider": {"appid": 730}, "auth": {"token": wrong_token}}).encode("utf-8"),
        )
        # Sem bloco auth
        status2, _ = _http_post(
            f"http://127.0.0.1:{port}/",
            json.dumps({"provider": {"appid": 730}}).encode("utf-8"),
        )
        assert status1 == 401
        assert status2 == 401
        assert server.event_queue.empty()

        stats = server.get_stats()
        assert stats.auth_failures == 2
        assert stats.requests_accepted == 0
        assert token not in ring.get_text()
    finally:
        server.stop()


def test_gsi_server_handles_invalid_json_and_partial_payloads() -> None:
    token = "token_partial_123456"
    server = GSIServer(host="127.0.0.1", port=0, auth_token=token)
    port = server.start()
    try:
        status_bad, _ = _http_post(f"http://127.0.0.1:{port}/", b"not-json")
        status_arr, _ = _http_post(f"http://127.0.0.1:{port}/", b"[1, 2, 3]")
        assert status_bad == 400
        assert status_arr == 400

        # Payload parcial válido (apenas heartbeat/previously)
        status_ok, _ = _http_post(
            f"http://127.0.0.1:{port}/",
            json.dumps({"previously": {"round": {"phase": "freezetime"}}, "auth": {"token": token}}).encode("utf-8"),
        )
        assert status_ok == 200
        stats = server.get_stats()
        assert stats.parse_errors == 2
        assert stats.requests_accepted == 1
    finally:
        server.stop()


def test_gsi_server_queue_drops_oldest_on_burst_and_restarts() -> None:
    token = "token_burst_123456"
    server = GSIServer(host="127.0.0.1", port=0, auth_token=token, max_queue_size=3)
    port = server.start()
    try:
        for seq in range(5):
            status, _ = _http_post(
                f"http://127.0.0.1:{port}/",
                json.dumps({"seq": seq, "auth": {"token": token}}).encode("utf-8"),
            )
            assert status == 200

        stats = server.get_stats()
        assert stats.requests_accepted == 5
        assert stats.dropped_events == 2
        assert stats.queue_size == 3

        queued = [server.event_queue.get_nowait().payload["seq"] for _ in range(3)]
        assert queued == [2, 3, 4]
    finally:
        server.stop()

    # Reinício limpo
    port2 = server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port2}/health", timeout=3.0) as resp:
            assert resp.status == 200
    finally:
        server.stop()
