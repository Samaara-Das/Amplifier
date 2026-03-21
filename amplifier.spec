# PyInstaller spec file for Amplifier
# Build with: pyinstaller amplifier.spec

import os
from pathlib import Path

block_cipher = None
ROOT = os.path.abspath('.')

a = Analysis(
    ['scripts/app_entry.py'],
    pathex=[ROOT, os.path.join(ROOT, 'scripts')],
    binaries=[],
    datas=[
        ('config/platforms.json', 'config'),
        ('config/.env.example', 'config'),
        ('config/content-templates.md', 'config'),
        ('scripts/generate_campaign.ps1', 'scripts'),
        ('scripts/login_setup.py', 'scripts'),
    ],
    hiddenimports=[
        'flask',
        'playwright',
        'playwright.async_api',
        'dotenv',
        'httpx',
        'PIL',
        'moviepy',
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
    name='Amplifier',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Show console for logs
    icon=None,  # Add icon later: icon='assets/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Amplifier',
)
