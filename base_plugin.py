# base_plugin.py

import os
import importlib
from abc import ABC, abstractmethod

# override_map = {}


class BaseAppletPlugin(ABC):
    """
    Abstract base for each dynamic applet plugin.
    """

    @property
    @abstractmethod
    def name(self):
        """A short identifier for this plugin, e.g. 'openjavacard-ndef-full'."""
        pass

    @abstractmethod
    def create_dialog(self, parent=None):
        """
        Return a QDialog (or None if no dialog needed).
        The app will call dialog.exec_(); if accepted, we can gather final user inputs.
        """
        pass

    @abstractmethod
    def fetch_available_caps(self) -> dict[str, str]:
        """
        Return a dictionary of { "cap_filename.cap": "download_url or local_path" }
        If the plugin has local-only .cap files, it can return local file paths or
        "file://" URLs. If the plugin can’t provide anything, return {}.
        """

    def pre_install(self, **kwargs):
        """
        Optional. If you need to do any steps prior to installing the .cap,
        like generating keys for FIDO2, do it here.
        If something fails, raise an exception or return a dict with error details.
        """
        pass

    def post_install(self, **kwargs):
        """
        Optional. For example, if you want to load data or do additional GP commands
        after the standard install, do it here.
        """
        pass

    def pre_uninstall(self, **kwargs):
        pass

    def post_uninstall(self, **kwargs):
        pass

    def auto_import_plugins(cls, package, override_map):
        base_dir = os.path.dirname(__file__)  # Get directory of the current file
        this_dir = os.path.join(base_dir, "repos", package)
        for fname in os.listdir(this_dir):
            if fname.endswith(".py") and not fname.startswith("__"):
                mod_name = fname[:-3]  # Strip .py
                full_mod_path = f"repos.{package}.{mod_name}"
                try:
                    importlib.import_module(full_mod_path)
                except Exception as e:
                    print(f"Error importing {full_mod_path}: {e}")

    def set_cap_name(self, cap_name: str, override_map):
        """
        Called by main.py when user picks a .cap to install/uninstall.
        If there's a sub-file override for that .cap, we instantiate it.
        """
        self._selected_cap = cap_name
        if cap_name in override_map:
            override_cls = override_map[cap_name]
            self._override_instance = override_cls()
        else:
            self._override_instance = None

    def get_descriptions(self) -> dict[str, str]:
        pass
