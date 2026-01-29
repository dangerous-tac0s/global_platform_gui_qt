"""
Views - Qt widgets and UI components.

Views handle presentation only - no business logic.
"""

from .widgets import StatusBar, MessageQueue, ReaderSelectorWidget, AppletListWidget
from .dialogs import KeyPromptDialog, ComboDialog, DEFAULT_KEY

__all__ = [
    # Widgets
    "StatusBar",
    "MessageQueue",
    "ReaderSelectorWidget",
    "AppletListWidget",
    # Dialogs
    "KeyPromptDialog",
    "ComboDialog",
    "DEFAULT_KEY",
]
