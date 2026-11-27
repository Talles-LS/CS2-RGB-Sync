"""Centralized internationalization (i18n) manager for CS2 RGB Sync."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from app.logger import get_logger

DEFAULT_LANGUAGE = "en_US"
SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en_US", "English"),
    ("pt_BR", "Português (Brasil)"),
    ("es_ES", "Español"),
)
SUPPORTED_LANGUAGE_CODES: frozenset[str] = frozenset(
    code for code, _ in SUPPORTED_LANGUAGES
)
_LANGUAGE_NAMES: dict[str, str] = dict(SUPPORTED_LANGUAGES)

_ALIAS_MAP: dict[str, str] = {
    "en": "en_US",
    "en_us": "en_US",
    "en-us": "en_US",
    "english": "en_US",
    "pt": "pt_BR",
    "pt_br": "pt_BR",
    "pt-br": "pt_BR",
    "portuguese": "pt_BR",
    "es": "es_ES",
    "es_es": "es_ES",
    "es-es": "es_ES",
    "spanish": "es_ES",
}


def get_locales_dir() -> Path:
    """Return directory containing translation JSON catalogs (source & PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / "locales"
    return Path(__file__).resolve().parent.parent / "locales"


def normalize_language(code: Optional[str]) -> str:
    """Normalize a language identifier or return DEFAULT_LANGUAGE when unknown."""
    if not isinstance(code, str):
        return DEFAULT_LANGUAGE
    cleaned = code.strip().lower().replace("-", "_")
    if not cleaned:
        return DEFAULT_LANGUAGE
    if cleaned in _ALIAS_MAP:
        return _ALIAS_MAP[cleaned]
    prefix = cleaned.split("_", 1)[0]
    return _ALIAS_MAP.get(prefix, DEFAULT_LANGUAGE)


def is_valid_language(code: Optional[str]) -> bool:
    """Return True if *code* maps cleanly to a supported language."""
    if not isinstance(code, str) or not code.strip():
        return False
    cleaned = code.strip().lower().replace("-", "_")
    if cleaned in _ALIAS_MAP:
        return True
    prefix = cleaned.split("_", 1)[0]
    return prefix in _ALIAS_MAP


def _flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested JSON translation objects into dotted key -> text maps."""
    flat: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(_flatten_dict(value, full_key))
        elif isinstance(value, str):
            flat[full_key] = value
    return flat


class I18nManager:
    """Thread-safe translation catalog manager with automatic fallback and observers."""

    def __init__(self, locales_dir: Optional[Path] = None) -> None:
        self._logger = get_logger("i18n")
        self._lock = threading.RLock()
        self._locales_dir = Path(locales_dir) if locales_dir else get_locales_dir()
        self._catalogs: dict[str, dict[str, str]] = {}
        self._language: str = DEFAULT_LANGUAGE
        self._warned_missing: set[tuple[str, str]] = set()
        self._subscribers: list[Callable[[str], None]] = []
        self.reload()

    def reload(self) -> None:
        """Load all supported JSON locale catalogs from disk."""
        loaded: dict[str, dict[str, str]] = {}
        for code, _ in SUPPORTED_LANGUAGES:
            path = self._locales_dir / f"{code}.json"
            if not path.is_file():
                self._logger.warning("Locale file missing: %s", path)
                loaded[code] = {}
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                loaded[code] = _flatten_dict(raw) if isinstance(raw, dict) else {}
            except (OSError, json.JSONDecodeError) as exc:
                self._logger.error("Failed to load locale %s: %s", path, exc)
                loaded[code] = {}

        with self._lock:
            self._catalogs = loaded
            self._warned_missing.clear()

    def available_languages(self) -> tuple[tuple[str, str], ...]:
        """Return tuple of ``(code, native_display_name)`` pairs."""
        return SUPPORTED_LANGUAGES

    def get_language(self) -> str:
        with self._lock:
            return self._language

    def get_language_display_name(self, code: Optional[str] = None) -> str:
        lang = normalize_language(code) if code is not None else self.get_language()
        return _LANGUAGE_NAMES.get(lang, _LANGUAGE_NAMES[DEFAULT_LANGUAGE])

    def set_language(self, code: str) -> str:
        """Set active language and notify observers if it changed."""
        canonical = normalize_language(code)
        callbacks: list[Callable[[str], None]] = []
        with self._lock:
            changed = canonical != self._language
            self._language = canonical
            if changed:
                callbacks = list(self._subscribers)

        if changed:
            for cb in callbacks:
                try:
                    cb(canonical)
                except Exception:
                    self._logger.exception("Error notifying language subscriber")
        return canonical

    def subscribe(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            self._subscribers = [cb for cb in self._subscribers if cb is not callback]

    def all_keys(self, language: str = DEFAULT_LANGUAGE) -> set[str]:
        lang = normalize_language(language)
        with self._lock:
            return set(self._catalogs.get(lang, {}).keys())

    def missing_keys(self, language: str) -> set[str]:
        """Return keys present in DEFAULT_LANGUAGE (en_US) missing from *language*."""
        lang = normalize_language(language)
        with self._lock:
            base = set(self._catalogs.get(DEFAULT_LANGUAGE, {}).keys())
            target = set(self._catalogs.get(lang, {}).keys())
            return base - target

    def translate(
        self, key: str, language: Optional[str] = None, **kwargs: Any
    ) -> str:
        """Translate dotted *key* into active/requested language with en_US fallback."""
        with self._lock:
            lang = normalize_language(language) if language is not None else self._language
            template = self._catalogs.get(lang, {}).get(key)
            if template is None and lang != DEFAULT_LANGUAGE:
                warn_key = (lang, key)
                if warn_key not in self._warned_missing:
                    self._warned_missing.add(warn_key)
                    self._logger.warning(
                        "Missing translation key '%s' for '%s'; falling back to %s",
                        key,
                        lang,
                        DEFAULT_LANGUAGE,
                    )
                template = self._catalogs.get(DEFAULT_LANGUAGE, {}).get(key)

            if template is None:
                warn_key = (DEFAULT_LANGUAGE, key)
                if warn_key not in self._warned_missing:
                    self._warned_missing.add(warn_key)
                    self._logger.warning("Unknown translation key '%s'", key)
                tail = key.rsplit(".", 1)[-1].replace("_", " ").strip()
                template = tail.capitalize() if tail else "Text"

        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template


_GLOBAL_I18N: Optional[I18nManager] = None
_GLOBAL_LOCK = threading.Lock()


def get_i18n() -> I18nManager:
    """Return global I18nManager singleton."""
    global _GLOBAL_I18N
    with _GLOBAL_LOCK:
        if _GLOBAL_I18N is None:
            _GLOBAL_I18N = I18nManager()
        return _GLOBAL_I18N


def t(key: str, **kwargs: Any) -> str:
    """Translate dotted *key* using global active language."""
    return get_i18n().translate(key, **kwargs)


def get_language() -> str:
    return get_i18n().get_language()


def set_language(code: str) -> str:
    return get_i18n().set_language(code)


def available_languages() -> tuple[tuple[str, str], ...]:
    return get_i18n().available_languages()


def get_language_display_name(code: Optional[str] = None) -> str:
    return get_i18n().get_language_display_name(code)


def subscribe_language_changed(callback: Callable[[str], None]) -> None:
    get_i18n().subscribe(callback)


def unsubscribe_language_changed(callback: Callable[[str], None]) -> None:
    get_i18n().unsubscribe(callback)
