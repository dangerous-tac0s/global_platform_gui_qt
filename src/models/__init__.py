"""
Models - Pure Python dataclasses representing application state.

No Qt dependencies in this package.
"""

from .card import CardState, CardInfo, CardMemory, CardConnectionState
from .applet import AppletInfo, InstalledApplet, InstallResult
from .config import ConfigData, WindowConfig, PluginCache

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
]
