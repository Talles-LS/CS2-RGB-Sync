"""Testes automatizados para ConfigManager, redação de logs e detecção/instalação GSI."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.config_manager import ConfigManager
from app.gsi_config import (
    GSI_CFG_FILENAME,
    detect_cs2_game_dir,
    install_gsi_cfg,
    is_managed_gsi_cfg,
    parse_steam_library_folders,
    render_gsi_cfg,
    uninstall_gsi_cfg,
)
from app.logger import (
    REDACTED_PLACEHOLDER,
    configure_logging,
    get_logger,
    get_ring_buffer_handler,
    get_token_filter,
    sanitize_payload,
)


def test_config_generates_token_and_persists(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    mgr = ConfigManager(user_config_path=cfg_file)

    token = mgr.get("server.token")
    assert isinstance(token, str) and len(token) >= 16
    assert mgr.get("server.host") == "127.0.0.1"
    assert mgr.get("server.port") == 3000

    # Padrões esperados para instalações novas
    assert mgr.get("config_version") == 2
    assert mgr.get("effects.flashbang.enabled") is True
    assert "he_explosion" not in (mgr.get("effects") or {})
    assert mgr.get("effects.shot.enabled") is True
    assert mgr.get("effects.c4.enabled") is True
    assert mgr.get("effects.fire.enabled") is True
    assert mgr.get("effects.health.enabled") is False
    assert mgr.get("effects.team.enabled") is False
    assert mgr.get("effects.weapons.enabled") is False
    assert mgr.get("priorities")[:4] == ["flashbang", "shot", "fire", "c4"]

    mgr.set("server.port", 3123)
    mgr.set("effects.shot.duration_ms", 65)
    mgr.set("effects.health.enabled", True)

    # Recarrega do disco e valida preservação de preferências do usuário
    mgr2 = ConfigManager(user_config_path=cfg_file)
    assert mgr2.get("server.token") == token
    assert mgr2.get("server.port") == 3123
    assert mgr2.get("effects.shot.duration_ms") == 65
    assert mgr2.get("effects.health.enabled") is True


def test_config_upgrade_preserves_user_preferences_and_migrates_priorities(
    tmp_path: Path,
) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "server": {"token": "existing_user_token_123456"},
                "priorities": [
                    "flashbang",
                    "he_explosion",
                    "shot",
                    "c4",
                    "fire",
                    "health_critical",
                    "health",
                    "team_round",
                    "weapon",
                ],
                "effects": {
                    "shot": {"color": "#FF4000", "duration_ms": 61},
                    "he_explosion": {"enabled": True, "color": "#FFF2D6"},
                    "health": {"enabled": True},
                    "team": {"enabled": True, "ct_color": "#112233"},
                },
            }
        ),
        encoding="utf-8",
    )
    mgr = ConfigManager(user_config_path=cfg_file)
    assert mgr.get("server.token") == "existing_user_token_123456"
    assert mgr.get("config_version") == 2
    assert mgr.get("effects.shot.color") == "#FF4000"
    assert mgr.get("effects.shot.duration_ms") == 61
    assert mgr.get("effects.health.enabled") is True
    assert mgr.get("effects.team.enabled") is True
    assert mgr.get("effects.team.ct_color") == "#112233"
    assert "he_explosion" not in (mgr.get("effects") or {})
    assert mgr.get("priorities")[:4] == ["flashbang", "shot", "fire", "c4"]


def test_config_rejects_non_loopback_host_and_invalid_port(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"server": {"host": "0.0.0.0", "port": 80, "token": "short"}}),
        encoding="utf-8",
    )
    mgr = ConfigManager(user_config_path=cfg_file)
    assert mgr.get("server.host") == "127.0.0.1"
    assert mgr.get("server.port") == 3000
    assert len(mgr.get("server.token")) >= 16

    with pytest.raises(ValueError):
        mgr.set("server.host", "0.0.0.0")
    with pytest.raises(ValueError):
        mgr.set("server.port", 80)


def test_token_redaction_in_logs_and_payload(tmp_path: Path) -> None:
    token_filter = get_token_filter()
    token_filter.clear_secrets()
    configure_logging(log_dir=tmp_path / "logs", level=logging.INFO, enable_file=False)
    ring = get_ring_buffer_handler()
    ring.clear()

    secret = "super_secret_gsi_token_987654"
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"server": {"token": secret}}),
        encoding="utf-8",
    )
    ConfigManager(user_config_path=cfg_file)

    log = get_logger("test_redact")
    log.info("Token recebido erroneamente: %s", secret)
    log.warning(f"Falha com token {secret} no corpo")

    text = ring.get_text()
    assert secret not in text
    assert REDACTED_PLACEHOLDER in text

    sanitized = sanitize_payload({"auth": {"token": secret}, "player": {"team": "CT"}})
    assert sanitized["auth"]["token"] == REDACTED_PLACEHOLDER
    assert sanitized["player"]["team"] == "CT"


def test_parse_steam_library_folders_prioritizes_cs2(tmp_path: Path) -> None:
    vdf = tmp_path / "libraryfolders.vdf"
    vdf.write_text(
        '"libraryfolders"\n'
        '{\n'
        '\t"0"\n'
        '\t{\n'
        '\t\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n'
        '\t\t"apps"\n'
        '\t\t{\n'
        '\t\t\t"228980"\t\t"100"\n'
        '\t\t}\n'
        '\t}\n'
        '\t"1"\n'
        '\t{\n'
        '\t\t"path"\t\t"D:\\\\SteamLibrary"\n'
        '\t\t"apps"\n'
        '\t\t{\n'
        '\t\t\t"730"\t\t"70000"\n'
        '\t\t}\n'
        '\t}\n'
        '}\n',
        encoding="utf-8",
    )
    libs = parse_steam_library_folders(vdf)
    assert libs[0] == Path(r"D:\SteamLibrary")
    assert Path(r"C:\Program Files (x86)\Steam") in libs


def test_detect_install_and_conditional_uninstall_gsi_cfg(tmp_path: Path) -> None:
    cs2_root = tmp_path / "Counter-Strike Global Offensive"
    cfg_dir = cs2_root / "game" / "csgo" / "cfg"
    cfg_dir.mkdir(parents=True)

    # Outro arquivo existente no jogo não deve ser alterado nem removido
    other_cfg = cfg_dir / "autoexec.cfg"
    other_cfg.write_text("echo keep_me\n", encoding="utf-8")

    detected = detect_cs2_game_dir(preferred_path=cs2_root)
    assert detected == cs2_root / "game" / "csgo"

    installed = install_gsi_cfg(
        cs2_game_dir=detected,
        port=3055,
        token="local_test_token_123456",
        buffer=0.05,
        throttle=0.05,
    )
    assert installed == cfg_dir / GSI_CFG_FILENAME
    content = installed.read_text(encoding="utf-8")
    assert '"uri"\t"http://127.0.0.1:3055/"' in content
    assert '"token"\t"local_test_token_123456"' in content
    assert '"player_state"' in content
    assert '"player_weapons"' in content
    assert '"allgrenades"' not in content
    assert is_managed_gsi_cfg(installed) is True
    assert other_cfg.read_text(encoding="utf-8") == "echo keep_me\n"

    # Arquivo não criado pelo CS2 RGB Sync não pode ser removido
    third_party = cfg_dir / "gamestate_integration_other.cfg"
    third_party.write_text('"Other"{}\n', encoding="utf-8")
    assert uninstall_gsi_cfg(third_party) is False
    assert third_party.exists()

    # Arquivo gerenciado pelo app pode ser removido
    assert uninstall_gsi_cfg(installed) is True
    assert not installed.exists()


def test_render_gsi_cfg_validates_inputs() -> None:
    with pytest.raises(ValueError):
        render_gsi_cfg(port=3000, token="")
    with pytest.raises(ValueError):
        render_gsi_cfg(port=80, token="valid_token_1234")
    with pytest.raises(ValueError):
        render_gsi_cfg(port=3000, token='bad"quote')
