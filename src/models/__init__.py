"""
Models - Pure Python dataclasses representing application state.

No Qt dependencies in this package.
"""

from .card import CardState, CardInfo, CardMemory, CardConnectionState
from .applet import AppletInfo, InstalledApplet, InstallResult
from .config import ConfigData, WindowConfig, PluginCache
from .key_config import (
    KeyConfiguration,
    KeyType,
    KeyMode,
    detect_key_type,
    is_ambiguous_length,
    get_type_display_name,
    get_ambiguous_display,
)

__all__ = [
    "CardState",
    "CardInfo",
    "CardMemory",
    "CardConnectionState",
    "AppletInfo",
    "InstalledApplet",
    "InstallResult",
    "ConfigData",
    "WindowConfig",
    "PluginCache",
    "KeyConfiguration",
    "KeyType",
    "KeyMode",
    "detect_key_type",
    "is_ambiguous_length",
    "get_type_display_name",
    "get_ambiguous_display",
]
