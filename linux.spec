# -*- mode: python ; coding: utf-8 -*-
# Linux PyInstaller spec file for GlobalPlatform GUI
# Creates a one-folder distribution suitable for AppImage packaging

import sys
from pathlib import Path

block_cipher = None

# Collect all src modules
src_imports = [
    'src',
    'src.models',
    'src.models.key_config',
    'src.models.card',
    'src.models.applet',
    'src.models.config',
    'src.views',
    'src.views.dialogs',
    'src.views.dialogs.change_key_dialog',
    'src.views.dialogs.key_prompt_dialog',
    'src.views.dialogs.combo_dialog',
    'src.views.dialogs.plugin_designer',
    'src.views.widgets',
    'src.services',
    'src.services.gp_service',
    'src.services.storage_service',
    'src.threads',
    'src.threads.nfc_thread',
    'src.threads.file_thread',
    'src.controllers',
    'src.events',
    'src.plugins',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('gp.jar', '.'),                    # Java-based GP tool for Linux
        ('plugins', 'plugins'),              # YAML plugin definitions
        ('favicon.ico', '.'),                # Icon (also used for window)
    ],
    hiddenimports=[
        'ndef',
        'ndeflib',
        'babel',
        'babel.numbers',
        'main',
        'smartcard',
        'smartcard.System',
        'smartcard.CardConnection',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'keyring',
        'keyring.backends',
        'gnupg',
        'markdown',
        'chardet',
        'yaml',
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
    ] + src_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # One-folder mode for AppImage
    name='gp_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI application
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
    name='gp_gui',
)
