# -*- mode: python ; coding: utf-8 -*-
# macOS PyInstaller spec file for GlobalPlatform GUI
# Creates a .app bundle for macOS distribution

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
        ('gp.jar', '.'),                     # Java-based GP tool for macOS
        ('plugins', 'plugins'),              # YAML plugin definitions
        ('favicon.ico', '.'),                # Fallback icon
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
        'keyring.backends.macOS',
        'keyring.backends.OS_X',
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
    exclude_binaries=True,  # Required for BUNDLE
    name='gp_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # Universal binary: set to 'universal2' if needed
    codesign_identity=None,  # Set to your Apple Developer ID for signing
    entitlements_file=None,  # Set to entitlements.plist if needed
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

app = BUNDLE(
    coll,
    name='GlobalPlatform GUI.app',
    icon='build_scripts/macos/gp_gui.icns',  # macOS icon (create from favicon.ico)
    bundle_identifier='com.globalplatform.gui',
    info_plist={
        'CFBundleName': 'GlobalPlatform GUI',
        'CFBundleDisplayName': 'GlobalPlatform GUI',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleIdentifier': 'com.globalplatform.gui',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': 'GPGUI',
        'LSMinimumSystemVersion': '10.13.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # Support Dark Mode
        'CFBundleDocumentTypes': [],
        'LSEnvironment': {
            'LANG': 'en_US.UTF-8',
        },
        # Smart card access entitlement description
        'NSAppleEventsUsageDescription': 'This app needs to communicate with smart card readers.',
    },
)
