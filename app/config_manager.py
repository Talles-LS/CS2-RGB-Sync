"""
Gerenciador de configurações persistentes em JSON local do CS2 RGB Sync.

Responsabilidades:
- Carregar configurações padrão de `config/default_config.json`.
- Mesclar com configurações persistidas em `%LOCALAPPDATA%\\CS2RGBSync\\config.json`.
- Gerar automaticamente o token local compartilhado na primeira execução.
- Validar invariantes de segurança (host estritamente `127.0.0.1` e porta válida).
- Persistir alterações com escrita atômica.
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from app.logger import get_logger, register_sensitive_token

REQUIRED_LOOPBACK_HOST = "127.0.0.1"
MIN_PORT = 1024
MAX_PORT = 65535


def get_project_root() -> Path:
    """Retorna a raiz do projeto (compatível com execução normal e PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def get_default_config_file_path() -> Path:
    """Retorna o caminho do arquivo `config/default_config.json`."""
    return get_project_root() / "config" / "default_config.json"


def get_default_user_config_path() -> Path:
    """Retorna o caminho padrão de persistência em %LOCALAPPDATA%\\CS2RGBSync\\config.json."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "CS2RGBSync" / "config.json"
    return Path.home() / ".cs2rgbsync" / "config.json"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Mescla recursivamente `override` sobre cópia de `base`."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigManager:
    """Gerencia leitura, validação, geração de token e salvamento de configurações."""

    def __init__(
        self,
        user_config_path: Optional[Path] = None,
        default_config_path: Optional[Path] = None,
    ) -> None:
        self._logger = get_logger("config")
        self._lock = threading.RLock()
        self.user_config_path = Path(
            user_config_path or get_default_user_config_path()
        )
        self.default_config_path = Path(
            default_config_path or get_default_config_file_path()
        )
        self._config: dict[str, Any] = {}
        self.load()

    def _read_default_config(self) -> dict[str, Any]:
        with self.default_config_path.open("r", encoding="utf-8-sig") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            raise ValueError("default_config.json deve conter um objeto JSON raiz.")
        return data

    def load(self) -> dict[str, Any]:
        """Carrega padrões + arquivo do usuário e garante token e invariantes válidas."""
        with self._lock:
            defaults = self._read_default_config()
            user_data: dict[str, Any] = {}
            needs_save = not self.user_config_path.exists()

            if self.user_config_path.exists():
                try:
                    with self.user_config_path.open("r", encoding="utf-8-sig") as fp:
                        loaded = json.load(fp)
                    if isinstance(loaded, dict):
                        user_data = loaded
                    else:
                        self._logger.warning(
                            "Arquivo de configuração inválido; restaurando padrões."
                        )
                        needs_save = True
                except (OSError, json.JSONDecodeError) as exc:
                    self._logger.warning(
                        "Falha ao ler configuração persistida (%s); usando padrões.",
                        exc,
                    )
                    needs_save = True

            merged = _deep_merge(defaults, user_data)
            if self.user_config_path.exists() and "config_version" not in user_data:
                merged["config_version"] = 1
            changed = self._sanitize_and_ensure_token(merged)
            self._config = merged

            if needs_save or changed:
                self.save()
            return self.get_all()

    def _sanitize_and_ensure_token(self, cfg: dict[str, Any]) -> bool:
        changed = False
        server = cfg.setdefault("server", {})

        # Segurança obrigatória: nunca escutar fora de 127.0.0.1
        if server.get("host") != REQUIRED_LOOPBACK_HOST:
            server["host"] = REQUIRED_LOOPBACK_HOST
            changed = True

        port = server.get("port", 3000)
        if not isinstance(port, int) or isinstance(port, bool) or not (
            MIN_PORT <= port <= MAX_PORT
        ):
            server["port"] = 3000
            changed = True

        token = server.get("token")
        if not isinstance(token, str) or len(token.strip()) < 16:
            token = secrets.token_urlsafe(24)
            server["token"] = token
            changed = True

        effects_cfg = cfg.get("effects")
        if isinstance(effects_cfg, dict) and "he_explosion" in effects_cfg:
            effects_cfg.pop("he_explosion", None)
            changed = True

        default_priorities = [
            "flashbang",
            "shot",
            "fire",
            "c4",
            "health_critical",
            "health",
            "team_round",
            "weapon",
        ]
        priorities = cfg.get("priorities")
        if isinstance(priorities, list):
            cleaned: list[str] = []
            for item in priorities:
                item_str = str(item)
                if item_str == "he_explosion":
                    changed = True
                    continue
                if item_str in default_priorities and item_str not in cleaned:
                    cleaned.append(item_str)
            if cleaned != priorities:
                priorities[:] = cleaned
                changed = True

            try:
                cfg_version = int(cfg.get("config_version", 1))
            except (TypeError, ValueError):
                cfg_version = 1

            if cfg_version < 2:
                if "fire" in priorities and "c4" in priorities:
                    fire_idx = priorities.index("fire")
                    c4_idx = priorities.index("c4")
                    if fire_idx > c4_idx:
                        priorities.pop(fire_idx)
                        priorities.insert(priorities.index("c4"), "fire")
                        changed = True
                cfg["config_version"] = 2
                changed = True

            for eff_id in default_priorities:
                if eff_id not in priorities:
                    priorities.append(eff_id)
                    changed = True
        elif cfg.get("config_version", 1) != 2:
            cfg["priorities"] = list(default_priorities)
            cfg["config_version"] = 2
            changed = True

        register_sensitive_token(token)
        return changed

    def save(self) -> None:
        """Persiste as configurações atuais em disco de forma atômica."""
        with self._lock:
            self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.user_config_path.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as fp:
                json.dump(self._config, fp, indent=2, ensure_ascii=False)
                fp.write("\n")
            os.replace(tmp_path, self.user_config_path)

    def get_all(self) -> dict[str, Any]:
        """Retorna uma cópia profunda de toda a árvore de configuração."""
        with self._lock:
            return copy.deepcopy(self._config)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Obtém um valor usando caminho pontuado (ex.: `server.port`)."""
        with self._lock:
            curr: Any = self._config
            for part in dotted_key.split("."):
                if not isinstance(curr, dict) or part not in curr:
                    return copy.deepcopy(default)
                curr = curr[part]
            return copy.deepcopy(curr)

    def set(self, dotted_key: str, value: Any, save_now: bool = True) -> None:
        """Define um valor usando caminho pontuado e opcionalmente salva no disco."""
        with self._lock:
            if dotted_key == "server.host" and value != REQUIRED_LOOPBACK_HOST:
                raise ValueError(
                    "Por segurança, o servidor HTTP deve escutar exclusivamente em 127.0.0.1."
                )
            if dotted_key == "server.port":
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or not (MIN_PORT <= value <= MAX_PORT)
                ):
                    raise ValueError(
                        f"Porta inválida: {value}. Utilize um valor entre {MIN_PORT} e {MAX_PORT}."
                    )
            if dotted_key == "server.token":
                if not isinstance(value, str) or len(value.strip()) < 8:
                    raise ValueError("Token GSI deve ter ao menos 8 caracteres.")
                register_sensitive_token(value)

            parts = dotted_key.split(".")
            curr = self._config
            for part in parts[:-1]:
                if part not in curr or not isinstance(curr[part], dict):
                    curr[part] = {}
                curr = curr[part]
            curr[parts[-1]] = copy.deepcopy(value)
            if save_now:
                self.save()

    def update(self, partial: dict[str, Any], save_now: bool = True) -> dict[str, Any]:
        """Mescla um dicionário parcial na configuração e valida invariantes."""
        with self._lock:
            candidate = _deep_merge(self._config, partial)
            self._sanitize_and_ensure_token(candidate)
            self._config = candidate
            if save_now:
                self.save()
            return self.get_all()

    def regenerate_token(self, save_now: bool = True) -> str:
        """Gera um novo token aleatório seguro e atualiza o filtro de redação."""
        with self._lock:
            new_token = secrets.token_urlsafe(24)
            self._config.setdefault("server", {})["token"] = new_token
            register_sensitive_token(new_token)
            if save_now:
                self.save()
            return new_token
