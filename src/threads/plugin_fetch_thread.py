"""
PluginFetchThread - Background thread for fetching plugin releases.

Fetches available CAP files from all plugins without blocking the UI.
"""

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal


class PluginFetchThread(QThread):
    """
    Fetches available CAP files from plugins in the background.

    Signals:
    - plugin_fetched: (plugin_name, caps_dict) - Emitted when one plugin completes
    - all_complete: (results_dict) - Emitted when all plugins have been fetched
    - error: (plugin_name, error_message) - Emitted on fetch error
    """

    plugin_fetched = pyqtSignal(str, dict)  # plugin_name, caps
    all_complete = pyqtSignal(dict)  # {plugin_name: caps}
    error = pyqtSignal(str, str)  # plugin_name, error_message

    def __init__(
        self,
        plugin_map: Dict[str, Any],
        parent=None,
    ):
        """
        Initialize the fetch thread.

        Args:
            plugin_map: Dictionary of plugin_name -> plugin class/instance
            parent: Optional QThread parent
        """
        super().__init__(parent)
        self._plugin_map = plugin_map
        self._results: Dict[str, dict] = {}

    def run(self):
        """Execute the fetch in background thread."""
        from main import get_plugin_instance

        for plugin_name, plugin_cls_or_instance in self._plugin_map.items():
            try:
                plugin_instance = get_plugin_instance(plugin_cls_or_instance)
                caps = plugin_instance.fetch_available_caps()
                plugin_instance.load_storage()

                self._results[plugin_name] = caps
                self.plugin_fetched.emit(plugin_name, caps)

            except Exception as e:
                self._results[plugin_name] = {}
                self.error.emit(plugin_name, str(e))

        self.all_complete.emit(self._results)
