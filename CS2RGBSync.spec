# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec (onedir) para CS2RGBSync.exe (Windows 11 64 bits)."""

from pathlib import Path
import cuesdk

cuesdk_dir = Path(cuesdk.__file__).resolve().parent
icue_dll = cuesdk_dir / "bin" / "iCUESDK.x64_2019.dll"

datas = [
    ("config/default_config.json", "config"),
    ("gsi/gamestate_integration_cs2rgbsync.cfg", "gsi"),
    ("assets/icons", "assets/icons"),
    ("THIRD_PARTY_LICENSES.txt", "."),
]

binaries = [
    (str(icue_dll), "cuesdk/bin"),
]

excludes = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtCharts",
    "PySide6.QtBluetooth",
    "PySide6.QtSensors",
    "PySide6.QtPositioning",
    "PySide6.QtDesigner",
    "PySide6.QtTest",
    "PySide6.QtSql",
    "PySide6.QtNetwork",
    "tkinter",
    "unittest",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CS2RGBSync",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icons/cs2_rgb_sync.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CS2RGBSync",
)
