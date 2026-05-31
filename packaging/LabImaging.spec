# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve().parent.parent

datas = [
    (str(ROOT / "labcam" / "web" / "templates"), "labcam/web/templates"),
    (str(ROOT / "labcam" / "web" / "static"), "labcam/web/static"),
    (str(ROOT / "config" / "settings.json.example"), "config"),
]

hiddenimports = [
    "labcam.cameras.identify_macos",
    "labcam.cameras.identify_windows",
    "labcam.cameras.probe",
    "pythoncom",
    "win32com.client",
]

a = Analysis(
    [str(ROOT / "labcam" / "portable_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LabImaging",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LabImagingPortable",
    contents_directory="_internal",
)
