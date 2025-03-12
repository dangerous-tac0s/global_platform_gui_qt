# base_plugin.py

from abc import ABC, abstractmethod

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
