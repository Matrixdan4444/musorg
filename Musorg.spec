# -*- mode: python ; coding: utf-8 -*-
import json
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Single source of truth for the app version: frontend/package.json.
# Bump it there and the bundle picks it up automatically.
_VERSION = json.loads(Path('frontend/package.json').read_text(encoding='utf-8'))['version']

datas = [('frontend/dist', 'frontend/dist')]
binaries = []
hiddenimports = ['webview.platforms.cocoa']

# Bundle a static ffmpeg (fetched via packaging/fetch_ffmpeg.sh) at the bundle
# root so non-FLAC sources transcode without the user installing ffmpeg. Its
# GPLv3 license/notice travels with the app. The binary is optional at build
# time — without it the app still works for FLAC-only libraries.
if Path('packaging/bin/ffmpeg').exists():
    binaries += [('packaging/bin/ffmpeg', '.')]
else:
    print('Musorg.spec: packaging/bin/ffmpeg not found — run packaging/fetch_ffmpeg.sh to bundle ffmpeg.')
datas += [('packaging/licenses/ffmpeg', 'licenses/ffmpeg')]

for pkg in ('webview', 'uvicorn', 'musicbrainzngs', 'certifi'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules('uvicorn')

a = Analysis(
    ['packaging/musorg_launcher.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Musorg',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Musorg',
)
app = BUNDLE(
    coll,
    name='Musorg.app',
    icon='packaging/Musorg.icns',
    bundle_identifier='com.matrixdan4444.musorg',
    info_plist={
        'CFBundleName': 'Musorg',
        'CFBundleDisplayName': 'Musorg',
        'CFBundleShortVersionString': _VERSION,
        'CFBundleVersion': _VERSION,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
    },
)
