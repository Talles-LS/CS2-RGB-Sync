"""
Detecção da instalação do Counter-Strike 2 e gerenciamento do arquivo GSI.

Garante que apenas o arquivo `gamestate_integration_cs2rgbsync.cfg` seja
criado ou atualizado na pasta `game\\csgo\\cfg` do CS2, sem modificar
quaisquer outros arquivos do jogo.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional

from app.logger import get_logger

GSI_CFG_FILENAME = "gamestate_integration_cs2rgbsync.cfg"
MANAGED_HEADER = "// Managed by CS2 RGB Sync - Do not share auth token"
CS2_APP_ID = "730"

_PATH_LINE_RE = re.compile(r'^\s*"path"\s+"([^"]+)"\s*$')
_APP_LINE_RE = re.compile(r'^\s*"(\d+)"\s+"[^"]+"\s*$')


def normalize_cs2_game_dir(candidate: Path | str) -> Optional[Path]:
    """
    Normaliza um caminho informado pelo usuário ou detectado para a pasta `...\\game\\csgo`.

    Aceita qualquer um dos seguintes formatos se existirem:
    - `<...>/Counter-Strike Global Offensive`
    - `<...>/Counter-Strike Global Offensive/game`
    - `<...>/Counter-Strike Global Offensive/game/csgo`
    - `<...>/Counter-Strike Global Offensive/game/csgo/cfg`
    """
    p = Path(candidate).expanduser()
    candidates = [
        p,
        p / "game" / "csgo",
        p / "csgo",
        p.parent if p.name.lower() == "cfg" else p,
    ]
    for option in candidates:
        cfg_dir = option / "cfg"
        if option.name.lower() == "csgo" and cfg_dir.is_dir():
            return option
    return None


def parse_steam_library_folders(vdf_path: Path) -> list[Path]:
    """
    Analisa o arquivo `libraryfolders.vdf` da Steam e retorna as pastas de biblioteca.
    A biblioteca que contém o AppID `730` (CS2) é colocada primeiro na lista.
    """
    if not vdf_path.is_file():
        return []
    try:
        lines = vdf_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    libraries: list[tuple[bool, Path]] = []
    current_path: Optional[Path] = None
    in_apps = False
    has_cs2 = False
    brace_depth = 0
    apps_depth = -1

    for raw_line in lines:
        line = raw_line.strip()
        if line == "{":
            brace_depth += 1
            continue
        if line == "}":
            if in_apps and brace_depth == apps_depth:
                in_apps = False
                apps_depth = -1
            elif current_path is not None and brace_depth == 2:
                libraries.append((has_cs2, current_path))
                current_path = None
                has_cs2 = False
            brace_depth = max(0, brace_depth - 1)
            continue

        if line == '"apps"':
            in_apps = True
            apps_depth = brace_depth + 1
            continue

        path_match = _PATH_LINE_RE.match(line)
        if path_match:
            raw_path = path_match.group(1).replace("\\\\", "\\")
            current_path = Path(raw_path)
            has_cs2 = False
            continue

        if in_apps:
            app_match = _APP_LINE_RE.match(line)
            if app_match and app_match.group(1) == CS2_APP_ID:
                has_cs2 = True

    if current_path is not None:
        libraries.append((has_cs2, current_path))

    ordered = [lib for flagged, lib in libraries if flagged] + [
        lib for flagged, lib in libraries if not flagged
    ]
    # Deduplica preservando ordem
    seen: set[Path] = set()
    unique: list[Path] = []
    for lib in ordered:
        if lib not in seen:
            seen.add(lib)
            unique.append(lib)
    return unique


def _get_steam_install_paths_windows() -> list[Path]:
    """Consulta o Registro do Windows para localizar a instalação da Steam."""
    paths: list[Path] = []
    if os.name != "nt":
        return paths
    try:
        import winreg
    except ImportError:
        return paths

    registry_targets = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]
    for hive, subkey, value_name in registry_targets:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                val, _ = winreg.QueryValueEx(key, value_name)
                if isinstance(val, str) and val.strip():
                    paths.append(Path(val.strip()))
        except OSError:
            continue
    return paths


def detect_cs2_game_dir(
    preferred_path: Optional[str | Path] = None,
    extra_steam_paths: Optional[Iterable[Path]] = None,
) -> Optional[Path]:
    """
    Detecta automaticamente a pasta `...\\Counter-Strike Global Offensive\\game\\csgo`.

    Ordem de busca:
    1. `preferred_path` configurado manualmente pelo usuário.
    2. Bibliotecas Steam encontradas via Registro do Windows + `libraryfolders.vdf`.
    3. Caminhos padrão conhecidos em `C:` e `D:`.
    """
    if preferred_path:
        normalized = normalize_cs2_game_dir(preferred_path)
        if normalized is not None:
            return normalized

    steam_roots: list[Path] = []
    if extra_steam_paths:
        steam_roots.extend(Path(p) for p in extra_steam_paths)
    steam_roots.extend(_get_steam_install_paths_windows())
    steam_roots.extend(
        [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
            Path(r"D:\Steam"),
            Path(r"D:\SteamLibrary"),
        ]
    )

    candidate_libraries: list[Path] = []
    for root in steam_roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            candidate_libraries.extend(parse_steam_library_folders(vdf))
        candidate_libraries.append(root)

    seen: set[Path] = set()
    for lib in candidate_libraries:
        if lib in seen:
            continue
        seen.add(lib)
        csgo_dir = (
            lib
            / "steamapps"
            / "common"
            / "Counter-Strike Global Offensive"
            / "game"
            / "csgo"
        )
        normalized = normalize_cs2_game_dir(csgo_dir)
        if normalized is not None:
            return normalized

    # Fallback direto caso o usuário tenha biblioteca na raiz
    direct_fallbacks = [
        Path(r"D:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive\game\csgo"),
        Path(
            r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo"
        ),
    ]
    for fb in direct_fallbacks:
        normalized = normalize_cs2_game_dir(fb)
        if normalized is not None:
            return normalized

    return None


def render_gsi_cfg(
    port: int,
    token: str,
    buffer: float = 0.05,
    throttle: float = 0.05,
    timeout: float = 5.0,
    heartbeat: float = 15.0,
) -> str:
    """Gera o conteúdo completo do arquivo `gamestate_integration_cs2rgbsync.cfg`."""
    if not token or not token.strip():
        raise ValueError("Token GSI não pode ser vazio ao gerar o arquivo .cfg.")
    if '"' in token or "\n" in token or "\r" in token:
        raise ValueError("Token GSI contém caracteres inválidos para arquivo .cfg.")
    if not (1024 <= port <= 65535):
        raise ValueError(f"Porta inválida para GSI: {port}.")

    return (
        f"{MANAGED_HEADER}\n"
        '"CS2 RGB Sync"\n'
        "{\n"
        f'\t"uri"\t"http://127.0.0.1:{port}/"\n'
        f'\t"timeout"\t"{timeout:.2f}"\n'
        f'\t"buffer"\t"{buffer:.2f}"\n'
        f'\t"throttle"\t"{throttle:.2f}"\n'
        f'\t"heartbeat"\t"{heartbeat:.1f}"\n'
        '\t"auth"\n'
        "\t{\n"
        f'\t\t"token"\t"{token}"\n'
        "\t}\n"
        '\t"data"\n'
        "\t{\n"
        '\t\t"provider"\t\t\t"1"\n'
        '\t\t"map"\t\t\t\t"1"\n'
        '\t\t"round"\t\t\t\t"1"\n'
        '\t\t"phase_countdowns"\t"1"\n'
        '\t\t"player_id"\t\t\t"1"\n'
        '\t\t"player_state"\t\t"1"\n'
        '\t\t"player_weapons"\t\t"1"\n'
        '\t\t"player_match_stats"\t"1"\n'
        "\t}\n"
        "}\n"
    )


def get_gsi_cfg_path(cs2_game_dir: Path | str) -> Path:
    """Retorna o caminho completo de `gamestate_integration_cs2rgbsync.cfg`."""
    normalized = normalize_cs2_game_dir(cs2_game_dir)
    if normalized is None:
        raise FileNotFoundError(
            f"Pasta válida do CS2 (game/csgo/cfg) não encontrada em: {cs2_game_dir}"
        )
    return normalized / "cfg" / GSI_CFG_FILENAME


def install_gsi_cfg(
    cs2_game_dir: Path | str,
    port: int,
    token: str,
    buffer: float = 0.05,
    throttle: float = 0.05,
    timeout: float = 5.0,
    heartbeat: float = 15.0,
) -> Path:
    """
    Grava `gamestate_integration_cs2rgbsync.cfg` na pasta `cfg` do CS2.
    Não altera nenhum outro arquivo do jogo.
    """
    logger = get_logger("gsi_config")
    target_path = get_gsi_cfg_path(cs2_game_dir)
    content = render_gsi_cfg(
        port=port,
        token=token,
        buffer=buffer,
        throttle=throttle,
        timeout=timeout,
        heartbeat=heartbeat,
    )
    tmp_path = target_path.with_suffix(".cfg.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, target_path)
    logger.info("Arquivo GSI instalado/atualizado em %s (porta=%d)", target_path, port)
    return target_path


def is_managed_gsi_cfg(cfg_path: Path) -> bool:
    """Verifica se o arquivo `.cfg` foi criado pelo CS2 RGB Sync."""
    if not cfg_path.is_file():
        return False
    try:
        header = cfg_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return MANAGED_HEADER in header


def uninstall_gsi_cfg(cfg_path: Path) -> bool:
    """
    Remove o arquivo GSI somente se ele tiver sido criado pelo CS2 RGB Sync.
    Retorna True se o arquivo foi removido.
    """
    if not is_managed_gsi_cfg(cfg_path):
        return False
    cfg_path.unlink()
    get_logger("gsi_config").info("Arquivo GSI gerenciado removido: %s", cfg_path)
    return True
