"""Automated tests for CS2 RGB Sync internationalization (i18n) and runtime language switching."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config_manager import ConfigManager
from app.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    I18nManager,
    normalize_language,
    set_language,
)
from app.icue_controller import RecordingRGBController
from app.sync_service import SyncService
from ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = PROJECT_ROOT / "locales"


def test_locale_files_exist_valid_and_complete() -> None:
    mgr = I18nManager(locales_dir=LOCALES_DIR)
    base_keys = mgr.all_keys(DEFAULT_LANGUAGE)
    assert len(base_keys) >= 120

    for code, display_name in SUPPORTED_LANGUAGES:
        path = LOCALES_DIR / f"{code}.json"
        assert path.is_file(), f"Missing locale file: {path}"
        raw_text = path.read_text(encoding="utf-8")
        # Ensure UTF-8 valid JSON and zero legacy artifacts
        parsed = json.loads(raw_text)
        assert isinstance(parsed, dict)
        lowered = raw_text.lower()
        assert "katar" not in lowered
        assert "rodinha" not in lowered
        assert "he_explosion" not in lowered
        assert display_name in ("English", "Português (Brasil)", "Español")

        assert mgr.missing_keys(code) == set(), f"Missing keys in {code}"
        extra = mgr.all_keys(code) - base_keys
        assert extra == set(), f"Extra keys in {code}: {extra}"


def test_i18n_fallback_and_normalization(tmp_path: Path) -> None:
    custom_dir = tmp_path / "locales"
    custom_dir.mkdir()
    (custom_dir / "en_US.json").write_text(
        json.dumps({"common": {"ready": "Ready", "greeting": "Hello {name}"}}),
        encoding="utf-8",
    )
    (custom_dir / "pt_BR.json").write_text(
        json.dumps({"common": {"ready": "Pronto"}}),
        encoding="utf-8",
    )
    (custom_dir / "es_ES.json").write_text(
        json.dumps({"common": {"ready": "Listo"}}),
        encoding="utf-8",
    )

    mgr = I18nManager(locales_dir=custom_dir)
    mgr.set_language("pt_BR")
    assert mgr.translate("common.ready") == "Pronto"
    # Missing key in pt_BR falls back cleanly to en_US
    assert mgr.translate("common.greeting", name="CT") == "Hello CT"
    # Completely unknown key never crashes or returns empty
    fallback = mgr.translate("section.nonexistent_item")
    assert isinstance(fallback, str) and len(fallback) > 0

    assert normalize_language("pt-br") == "pt_BR"
    assert normalize_language("ES") == "es_ES"
    assert normalize_language("unknown-xx") == "en_US"


def test_default_language_is_en_us_and_migration_preserves_saved_choice(
    tmp_path: Path,
) -> None:
    # 1. Fresh config -> default language is en_US
    fresh_path = tmp_path / "fresh.json"
    fresh_mgr = ConfigManager(user_config_path=fresh_path)
    assert fresh_mgr.get("ui.language") == "en_US"

    # 2. Existing config without ui.language -> sets en_US while keeping other settings
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "server": {"port": 3122, "token": "user_token_preserved_12345"},
                "effects": {"shot": {"color": "#112233"}},
            }
        ),
        encoding="utf-8",
    )
    legacy_mgr = ConfigManager(user_config_path=legacy_path)
    assert legacy_mgr.get("ui.language") == "en_US"
    assert legacy_mgr.get("server.port") == 3122
    assert legacy_mgr.get("server.token") == "user_token_preserved_12345"
    assert legacy_mgr.get("effects.shot.color") == "#112233"

    # 3. Existing config with saved language ("es_ES") -> preserves saved language & prefs
    saved_es_path = tmp_path / "saved_es.json"
    saved_es_path.write_text(
        json.dumps(
            {
                "server": {"port": 3199, "token": "user_es_token_preserved_123"},
                "ui": {"language": "es_ES", "minimize_to_tray": False},
            }
        ),
        encoding="utf-8",
    )
    es_mgr = ConfigManager(user_config_path=saved_es_path)
    assert es_mgr.get("ui.language") == "es_ES"
    assert es_mgr.get("server.port") == 3199
    assert es_mgr.get("ui.minimize_to_tray") is False


def test_live_runtime_language_switching_across_all_pages_and_tray(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    cfg_path = tmp_path / "ui_i18n_cfg.json"
    cfg_mgr = ConfigManager(user_config_path=cfg_path)
    controller = RecordingRGBController(device_model="CORSAIR TEST")
    service = SyncService(config_manager=cfg_mgr, controller=controller, port_override=0)
    window = MainWindow(service=service)
    window.show()
    app.processEvents()

    try:
        # Starts in default en_US
        assert cfg_mgr.get("ui.language") == "en_US"
        assert [b.text() for b in window.nav_buttons] == [
            "Dashboard",
            "RGB Effects",
            "Settings",
            "Diagnostics",
        ]
        assert window.dashboard_page.toggle_btn.text() == "START INTEGRATION"
        assert "English" in window.settings_page.btn_language.text()
        if hasattr(window, "_tray_quit_action"):
            assert window._tray_quit_action.text() == "Quit"

        # Switch via Settings Language menu action -> pt_BR without restart
        window._select_page(2)
        window.settings_page.language_actions["pt_BR"].trigger()
        app.processEvents()

        assert cfg_mgr.get("ui.language") == "pt_BR"
        assert [b.text() for b in window.nav_buttons] == [
            "Painel",
            "Efeitos RGB",
            "Configurações",
            "Diagnóstico",
        ]
        assert window.dashboard_page.toggle_btn.text() == "INICIAR INTEGRAÇÃO"
        assert "Português (Brasil)" in window.settings_page.btn_language.text()
        assert window.effects_page.btn_save.text() == "Aplicar e Salvar"
        assert window.diagnostics_page.btn_copy_logs.text() == "Copiar Logs"
        assert window.dashboard_page.btn_sim_reset.text() == "Reiniciar"
        if hasattr(window, "_tray_quit_action"):
            assert window._tray_quit_action.text() == "Sair"

        # Switch to es_ES without restart
        window.settings_page.language_actions["es_ES"].trigger()
        app.processEvents()

        assert cfg_mgr.get("ui.language") == "es_ES"
        assert [b.text() for b in window.nav_buttons] == [
            "Panel",
            "Efectos RGB",
            "Configuración",
            "Diagnóstico",
        ]
        assert window.dashboard_page.toggle_btn.text() == "INICIAR INTEGRACIÓN"
        assert "Español" in window.settings_page.btn_language.text()
        assert window.effects_page.btn_save.text() == "Aplicar y Guardar"
        assert window.diagnostics_page.btn_copy_logs.text() == "Copiar Registros"
        assert window.dashboard_page.btn_sim_reset.text() == "Reiniciar"
        if hasattr(window, "_tray_quit_action"):
            assert window._tray_quit_action.text() == "Salir"

        # Verify persisted preference reloads cleanly on restart
        reloaded = ConfigManager(user_config_path=cfg_path)
        assert reloaded.get("ui.language") == "es_ES"

        # Restore defaults preserves selected language
        restored = service.restore_default_settings()
        assert restored["ui"]["language"] == "es_ES"
    finally:
        set_language("en_US")
        window.shutdown_service()
