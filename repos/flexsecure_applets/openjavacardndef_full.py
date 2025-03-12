# /repos/flexsecure_applets/openjavacardndef_full.py

from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QCheckBox, QLineEdit, QHBoxLayout, QPushButton, QTextEdit
)
from PyQt5.QtCore import Qt

from . import FLEXSECURE_AID_MAP  # same folder, relative import
from base_plugin import BaseAppletPlugin


class OpenJavaCardNDEFPlugin(BaseAppletPlugin):
    min_javacard_version = (3, 0, 4)  # e.g. requires JavaCard 3.0.4 or higher

    @property
    def name(self):
        return "openjavacard-ndef-full"

    def pre_install(self, **kwargs):
        # We'll check if the card's OS version is >= min_javacard_version
        nfc_thread = kwargs.get("nfc_thread")
        if not nfc_thread:
            return  # or raise an error if we must have it

        card_ver = getattr(nfc_thread, "card_os_version", None)
        if card_ver is None:
            # nfc_thread might attempt to parse it
            card_ver = nfc_thread.get_javacard_version(nfc_thread.selected_reader_name)
            nfc_thread.card_os_version = card_ver

        if card_ver is None:
            raise Exception("Could not detect JavaCard OS version; cannot proceed.")

        if card_ver < self.min_javacard_version:
            raise Exception(f"Requires JavaCard {self.min_javacard_version}, but card is {card_ver}.")

    def create_dialog(self, parent=None):
        """
        Create and return a QDialog with 4 tabs:
          1) Basic
          2) Record
          3) Advanced
          4) Raw
        We'll store user input in self._result or in the dialog as needed.
        """
        dlg = QDialog(parent)
        dlg.setWindowTitle("NDEF Configuration")

        layout = QVBoxLayout(dlg)
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 1) Basic tab
        self.basic_tab = QWidget()
        self.build_basic_tab()
        self.tab_widget.addTab(self.basic_tab, "Basic")

        # 2) Record tab
        self.record_tab = QWidget()
        self.build_record_tab()
        self.tab_widget.addTab(self.record_tab, "Record")

        # 3) Advanced tab
        self.advanced_tab = QWidget()
        self.build_advanced_tab()
        self.tab_widget.addTab(self.advanced_tab, "Advanced")

        # 4) Raw tab
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
        layout = QFormLayout()
        self.basic_tab.setLayout(layout)

        # Container size combobox
        self.size_combo = QComboBox()
        self.size_combo.addItems(["1kB", "2kB", "4kB", "8kB", "16kB", "32kB"])
        layout.addRow(QLabel("Container Size:"), self.size_combo)

        # "Write Once" checkbox
        self.write_once_check = QCheckBox()
        layout.addRow(QLabel("Write Once:"), self.write_once_check)

    def build_record_tab(self):
        layout = QFormLayout()
        self.record_tab.setLayout(layout)

        self.record_type_combo = QComboBox()
        self.record_type_combo.addItems(["text", "uri", "mime", "smart poster"])
        layout.addRow(QLabel("Record Type:"), self.record_type_combo)

        self.record_payload_edit = QTextEdit()
        layout.addRow(QLabel("Payload:"), self.record_payload_edit)

    def build_advanced_tab(self):
        layout = QFormLayout()
        self.advanced_tab.setLayout(layout)

        # Read permission
        self.read_perm_combo = QComboBox()
        self.read_perm_combo.addItems(["open access", "no access", "write once", "contact only"])
        layout.addRow(QLabel("Read Permission:"), self.read_perm_combo)

        # Write permission
        self.write_perm_combo = QComboBox()
        self.write_perm_combo.addItems(["open access", "no access", "write once", "contact only"])
        layout.addRow(QLabel("Write Permission:"), self.write_perm_combo)

    def build_raw_tab(self):
        layout = QFormLayout()
        self.raw_tab.setLayout(layout)

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
            # Build param from Basic/Record/Advanced
            size_str = self.size_combo.currentText()  # e.g. "1kB"
            size_kb = int(size_str[:-2])
            size_in_bytes = size_kb * 1024
            if size_kb == 32:
                size_in_bytes -= 1
            size_hex = f"{size_in_bytes:04X}"

            # Suppose you have your old “permissions_text_to_hex” map:
            perm_map = {
                "open access": "00",
                "no access": "FF",
                "write once": "F1",
                "contact only": "F0",
            }
            read_val = self.read_perm_combo.currentText()
            write_val = self.write_perm_combo.currentText()
            read_hex = perm_map.get(read_val, "00")
            write_hex = perm_map.get(write_val, "00")

            param_string = f"8102{read_hex}{write_hex}8202{size_hex}"

            record_type = self.record_type_combo.currentText()
            record_payload = self.record_payload_edit.toPlainText()

            self._result = {
                "param_string": param_string,
                "record_type": record_type,
                "record_payload": record_payload,
                "source": "ui"
            }

        dlg.accept()

    def get_result(self):
        """Return the dictionary of final user-chosen data."""
        return self._result

    def pre_install(self, **kwargs):
        """
        If you need to do anything prior to installing, do it here.
        For instance, check if the card meets some condition, generate keys, etc.
        """
        # Example: print("Running pre-install steps for NDEF...")
        pass

    def post_install(self, **kwargs):
        """
        If you need to do additional steps after the standard gp install, do it here.
        E.g. load some data, run gp --params with the param_string, etc.
        """
        # Example:
        result = self._result
        if result and result["source"] == "ui":
            param_string = result["param_string"]
            # Possibly run a second gp command with --params param_string
            pass
