"""Testes automatizados para os recursos de distribuição, CLI e segurança de segredos."""

from __future__ import annotations

import os
from pathlib import Path

from app.config_manager import ConfigManager
from app.gsi_config import GSI_CFG_FILENAME, is_managed_gsi_cfg
from main import main as app_main

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_cli_setup_preserves_existing_token_and_other_cs2_files(tmp_path: Path) -> None:
    cs2_dir = tmp_path / "Counter-Strike Global Offensive" / "game" / "csgo"
    cfg_dir = cs2_dir / "cfg"
    cfg_dir.mkdir(parents=True)

    preexisting = cfg_dir / "autoexec.cfg"
    preexisting.write_text("fps_max 400\n", encoding="utf-8")
    third_party_gsi = cfg_dir / "gamestate_integration_other.cfg"
    third_party_gsi.write_text('"Other"{}\n', encoding="utf-8")

    user_cfg = tmp_path / "AppData" / "config.json"

    # Primeira instalação gera token local e cria gamestate_integration_cs2rgbsync.cfg
    rc1 = app_main(["--setup-gsi", str(cs2_dir), "--config-path", str(user_cfg)])
    assert rc1 == 0
    installed_cfg = cfg_dir / GSI_CFG_FILENAME
    assert installed_cfg.is_file()
    assert is_managed_gsi_cfg(installed_cfg) is True

    mgr1 = ConfigManager(user_config_path=user_cfg)
    first_token = mgr1.get("server.token")
    assert len(first_token) >= 16
    assert first_token in installed_cfg.read_text(encoding="utf-8")

    # Simulação de atualização: preserva o mesmo token e configurações do usuário
    mgr1.set("server.port", 3044)
    rc2 = app_main(["--setup-gsi", str(cs2_dir), "--config-path", str(user_cfg)])
    assert rc2 == 0
    mgr2 = ConfigManager(user_config_path=user_cfg)
    assert mgr2.get("server.token") == first_token
    assert mgr2.get("server.port") == 3044
    assert "http://127.0.0.1:3044/" in installed_cfg.read_text(encoding="utf-8")

    # Outros arquivos da pasta cfg intactos
    assert preexisting.read_text(encoding="utf-8") == "fps_max 400\n"
    assert third_party_gsi.read_text(encoding="utf-8") == '"Other"{}\n'

    # Desinstalação remove somente arquivo gerenciado pelo CS2 RGB Sync
    rc3 = app_main(["--uninstall-gsi", str(cs2_dir)])
    assert rc3 == 0
    assert not installed_cfg.exists()
    assert preexisting.exists()
    assert third_party_gsi.exists()


def test_cli_self_check_passes(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    rc = app_main(["--self-check", "--config-path", str(tmp_path / "check_cfg.json")])
    assert rc == 0


def test_distribution_templates_contain_no_real_user_token() -> None:
    user_cfg = Path(os.environ.get("LOCALAPPDATA", "")) / "CS2RGBSync" / "config.json"
    real_token = None
    if user_cfg.is_file():
        mgr = ConfigManager(user_config_path=user_cfg)
        real_token = mgr.get("server.token")

    for rel in (
        "config/default_config.json",
        "gsi/gamestate_integration_cs2rgbsync.cfg",
        "CS2RGBSync.spec",
        "CS2RGBSync_onefile.spec",
        "installer/CS2RGBSync.iss",
    ):
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        if real_token:
            assert real_token not in text, f"Token vazado em {rel}"
