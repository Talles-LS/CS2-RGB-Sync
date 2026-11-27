"""
Gerenciamento da inicialização automática com o Windows via Registro do usuário atual.

Utiliza exclusivamente `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`,
não exigindo privilégios de administrador.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_APP_KEY = "CS2RGBSync"


def build_startup_command() -> str:
    """Monta o comando executável adequado (PyInstaller .exe ou Python + main.py)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_script = Path(__file__).resolve().parent.parent / "main.py"
    python_exe = Path(sys.executable)
    pythonw = python_exe.with_name("pythonw.exe")
    launcher = pythonw if pythonw.is_file() else python_exe
    return f'"{launcher}" "{main_script}"'


def is_windows_startup_enabled(app_name: str = DEFAULT_APP_KEY) -> bool:
    """Verifica se há entrada registrada para iniciar com o Windows."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, app_name)
            return bool(isinstance(val, str) and val.strip())
    except OSError:
        return False


def set_windows_startup(
    enabled: bool,
    command: Optional[str] = None,
    app_name: str = DEFAULT_APP_KEY,
) -> bool:
    """Ativa ou remove a inicialização com o Windows no registro do usuário."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                cmd = command or build_startup_command()
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
