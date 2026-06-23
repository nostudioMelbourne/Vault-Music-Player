# -*- mode: python ; coding: utf-8 -*-

try:
    from PyInstaller.utils.hooks import collect_data_files
    tkinterdnd_datas = collect_data_files('tkinterdnd2')
except Exception:
    tkinterdnd_datas = []


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=tkinterdnd_datas,
    hiddenimports=['tkinterdnd2'],
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
    name='Vault Music',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/app_icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Vault Music',
)
app = BUNDLE(
    coll,
    name='Vault Music.app',
    icon='assets/app_icon.icns',
    bundle_identifier='com.mojo.vaultmusic.beta',
)
