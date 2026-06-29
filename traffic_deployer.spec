# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — run via scripts/build_exe.ps1 (work-laptop exe)

import os

block_cipher = None
root = os.path.abspath(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[root],
    binaries=[],
    datas=[
        (os.path.join(root, 'web'), 'web'),
        (os.path.join(root, 'demo_data'), 'demo_data'),
    ],
    hiddenimports=[
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'shiboken6',
        'gps_reader',
        'local_server',
        'road_router',
        'bridge',
        'persistence',
        'core.routing',
        'core.ingest',
        'core.export',
        'core.geo',
        'core.state',
        'osmnx',
        'networkx',
        'numpy',
        'pandas',
        # pandas imports its spreadsheet engines lazily at read/write time, so
        # PyInstaller's static analysis misses them. Without these, uploading a
        # .xls (xlrd) or .xlsx (openpyxl) silently fails and exports break.
        'xlrd',
        'openpyxl',
        'xlsxwriter',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TrafficDeployer',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TrafficDeployer',
)
