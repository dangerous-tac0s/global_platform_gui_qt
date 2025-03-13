
class AppletOverrideBase:
    """
    A base class for any per-app overrides. Each sub-file can define
    a subclass with specialized logic if it wants to override
    the default approach.
    """
    def pre_install(self, plugin, **kwargs):
        pass

    def post_install(self, plugin, **kwargs):
        pass

    def create_dialog(self, plugin, parent=None):
        """Return a QDialog or None."""
        return None

    def get_result(self):
        """Return any final user-chosen data from the dialog."""
        return {}