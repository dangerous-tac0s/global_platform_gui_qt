# /repos/flexsecure_applets/openjavacardndef_full.py

from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QCheckBox, QPushButton, QHBoxLayout, QTextEdit
)
from PyQt5.QtCore import Qt

# Import the 'AppletOverrideBase' and the dictionary or function for registering overrides.
from . import  override_map
from applet_override_base import AppletOverrideBase

def register_override(cap_name, override_cls):
    """
    Helper function to insert an override class into 'override_map'
    so that 'FlexsecureAppletsPlugin' can find it.
    """
    override_map[cap_name] = override_cls


class OpenJavaCardNDEFOverride(AppletOverrideBase):
    """
    An override for the 'openjavacard-ndef-full.cap' applet
    that requires a special multi-tab config UI, plus optional version checks.
    """

    min_javacard_version = (3, 0, 4)  # e.g. requires JavaCard 3.0.4 or higher

    perm_map = {
        "open access": "00",
        "no access": "FF",
        "write once": "F1",
        "contact only": "F0",
    }

    def pre_install(self, plugin, **kwargs):
        """
        We'll check if the card's OS version is >= min_javacard_version
        (Optional logic - depends on how you store the card version).
        """
        nfc_thread = kwargs.get("nfc_thread")
        if not nfc_thread:
            return  # or raise an error if we must have it

        # Example approach - skip if we don't parse version
        card_ver = getattr(nfc_thread, "card_os_version", None)
        if card_ver is None:
            # If there's a method like nfc_thread.get_javacard_version(...), call it
            # or skip if you haven't implemented that
            pass

        # If we wanted to do a compare:
        # if card_ver < self.min_javacard_version:
        #     raise Exception(f"Requires JavaCard {self.min_javacard_version}, but card is {card_ver}.")

    def create_dialog(self, plugin, parent=None):
        """
        Build a multi-tab QDialog for NDEF configuration.
        'plugin' is the parent plugin (FlexsecureAppletsPlugin).
        """
        dlg = QDialog(parent)
        dlg.setWindowTitle("NDEF Configuration")

        layout = QVBoxLayout(dlg)
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Basic
        self.basic_tab = QWidget()
        self.build_basic_tab()
        self.tab_widget.addTab(self.basic_tab, "Basic")

        # Record
        self.record_tab = QWidget()
        self.build_record_tab()
        self.tab_widget.addTab(self.record_tab, "Record")

        # Advanced
        self.advanced_tab = QWidget()
        self.build_advanced_tab()
        self.tab_widget.addTab(self.advanced_tab, "Advanced")

        # Raw
        self.raw_tab = QWidget()
        self.build_raw_tab()
        self.tab_widget.addTab(self.raw_tab, "Raw")

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(lambda: self.on_ok(dlg))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

        dlg.setLayout(layout)
        self._dialog = dlg

        return dlg

    def build_basic_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QComboBox, QCheckBox
        layout = QFormLayout(self.basic_tab)

        # Container size combobox
        self.size_combo = QComboBox()
        self.size_combo.addItems(["1kB", "2kB", "4kB", "8kB", "16kB", "32kB"])
        layout.addRow(QLabel("Container Size:"), self.size_combo)

        # "Write Once" checkbox
        self.write_once_check = QCheckBox()
        layout.addRow(QLabel("Write Once:"), self.write_once_check)

    def build_record_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QComboBox, QTextEdit
        layout = QFormLayout(self.record_tab)

        self.record_type_combo = QComboBox()
        self.record_type_combo.addItems(["text", "uri", "mime", "smart poster"])
        layout.addRow(QLabel("Record Type:"), self.record_type_combo)

        self.record_payload_edit = QTextEdit()
        layout.addRow(QLabel("Payload:"), self.record_payload_edit)

    def build_advanced_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QComboBox
        layout = QFormLayout(self.advanced_tab)

        self.rw_label = QLabel()
        self.rw_label.setText(f"81 00 00")
        layout.addRow(self.rw_label)

        # Read permission
        self.read_perm_combo = QComboBox()
        self.read_perm_combo.addItems(["open access", "no access", "write once", "contact only"])
        self.read_perm_combo.currentIndexChanged.connect(self.on_rw_value_change)
        layout.addRow(QLabel("Read Permission:"), self.read_perm_combo)

        # Write permission
        self.write_perm_combo = QComboBox()
        self.write_perm_combo.addItems(["open access", "no access", "write once", "contact only"])
        self.write_perm_combo.currentIndexChanged.connect(self.on_rw_value_change)
        layout.addRow(QLabel("Write Permission:"), self.write_perm_combo)

    def on_rw_value_change(self):
        self.rw_label.setText(f"81 {self.perm_map[self.read_perm_combo.currentText()]} {self.perm_map[self.write_perm_combo.currentText()]}")

    def build_raw_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QTextEdit
        layout = QFormLayout(self.raw_tab)

        self.raw_text_edit = QTextEdit()
        self.raw_text_edit.setPlaceholderText("Enter hex param string (optional)")
        layout.addRow(QLabel("Raw params:"), self.raw_text_edit)

    def on_ok(self, dlg):
        """
        Gather user input from the 4 tabs into a final structure or param string.
        If user entered something in the 'Raw' tab, we might override everything else.
        """
        raw_str = self.raw_text_edit.toPlainText().strip()

        if raw_str:
            # If the user provided a raw param string, let's use that
            self._result = {
                "param_string": raw_str,
                "source": "raw"
            }
        else:
            # TODO: Need an option to ignore things such as the basic tab
            #   eg, data is set, we don't *need* 82 02 -- but it can be used
            #           override the container size

            # Build param from Basic/Record/Advanced
            size_str = self.size_combo.currentText()  # e.g. "1kB"
            size_kb = int(size_str[:-2])
            size_in_bytes = size_kb * 1024
            if size_kb == 32:
                size_in_bytes -= 1
            size_hex = f"{size_in_bytes:04X}"

            # Suppose you have your old “permissions_text_to_hex” map:
            read_val = self.read_perm_combo.currentText()
            write_val = self.write_perm_combo.currentText()
            read_hex = self.perm_map.get(read_val, "00")
            write_hex = self.perm_map.get(write_val, "00")

            # Build 80 XX <data>
            record_type = self.record_type_combo.currentText()
            record_payload = self.record_payload_edit.toPlainText()

            param_string = f"8102{read_hex}{write_hex}8202{size_hex}"

            self._result = {
                "param_string": param_string,
                "record_type": record_type,
                "record_payload": record_payload,
                "source": "ui"
            }

        dlg.accept()

    def get_result(self):
        """Return the dictionary of final user-chosen data."""
        return getattr(self, "_result", {})

    def post_install(self, plugin, **kwargs):
        """
        If you need to do additional steps after the standard gp install,
        do it here (like loading data, second gp command with param string, etc.)
        """
        result = getattr(self, "_result", {})
        if result and result["source"] == "ui":
            param_string = result["param_string"]
            # Possibly run a second gp command with --params param_string
            # e.g. plugin.call_gp_params(...)

# Finally, register this override
register_override("openjavacard-ndef-full.cap", OpenJavaCardNDEFOverride)
