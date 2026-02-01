# -*- mode: python ; coding: utf-8 -*-
# Base PyInstaller spec file for GlobalPlatform GUI
# Auto-detects platform and builds appropriately
# For production builds, use: linux.spec, windows.spec, or macos.spec

import sys
import os

block_cipher = None

# Platform detection
IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')

# Platform-specific data files
if IS_WINDOWS:
    platform_datas = [
        ('gp.exe', '.'),
        ('gp.jar', '.'),
    ]
elif IS_MACOS or IS_LINUX:
    platform_datas = [
        ('gp.jar', '.'),
    ]
else:
    platform_datas = [
        ('gp.jar', '.'),
    ]

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

# Platform-specific hidden imports
platform_imports = []
if IS_WINDOWS:
    platform_imports = ['win32api', 'win32con', 'pywintypes', 'keyring.backends.Windows']
elif IS_MACOS:
    platform_imports = ['keyring.backends.macOS', 'keyring.backends.OS_X']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=platform_datas + [
        ('plugins', 'plugins'),
        ('favicon.ico', '.'),
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
    ] + platform_imports + src_imports,
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
    a.binaries,
    a.datas,
    [],
    name='gp_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='favicon.ico',
)
