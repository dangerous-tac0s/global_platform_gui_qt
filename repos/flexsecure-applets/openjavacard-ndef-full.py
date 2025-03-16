# /repos/flexsecure-applets/openjavacard-ndef-full.py
import abc
import os
import re

import ndef
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QTextEdit,
    QStackedWidget,
    QFrame,
    QLineEdit,
)
from PyQt5.QtCore import Qt, QLocale
from babel import Locale
from ndef import TextRecord

from main import horizontal_rule, FocusFilter
from . import override_map
from applet_override_base import AppletOverrideBase

system_locale = QLocale.system()

width_height = [400, 400]
if os.name == "nt":
    width_height = [2 * x for x in width_height]


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

    min_javacard_version = (2, 2, 0)

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
        dlg.resize(*width_height)

        layout = QVBoxLayout(dlg)

        dlg.setWindowTitle(f"NDEF {layout.tr("Configuration")}")

        self.perm_map = {
            layout.tr("open access"): "00",
            layout.tr("no access"): "FF",
            layout.tr("write once"): "F1",
            layout.tr("contact only"): "F0",
        }

        self._result = {"param_string": ""}

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Size Tab
        self.size_tab = QWidget()
        self.build_size_tab()
        self.tab_widget.addTab(self.size_tab, layout.tr("Size"))

        # Record
        self.record_tab = QWidget()
        self.build_record_tab()
        self.tab_widget.addTab(self.record_tab, layout.tr("Record"))

        # Advanced
        self.permissions_tab = QWidget()
        self.build_permissions_tab()
        self.tab_widget.addTab(self.permissions_tab, layout.tr("Permissions"))

        # Raw
        self.raw_tab = QWidget()
        self.build_raw_tab()
        self.tab_widget.addTab(self.raw_tab, layout.tr("Raw"))
        self.tab_widget.currentChanged.connect(self.on_tab_change)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(layout.tr("Okay"))
        ok_btn.clicked.connect(lambda: self.on_ok(dlg))
        cancel_btn = QPushButton(layout.tr("Cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

        dlg.setLayout(layout)
        self._dialog = dlg

        return dlg

    def build_size_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QComboBox, QCheckBox

        layout = QFormLayout(self.size_tab)

        self.size_label = QLabel()
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.size_label.setFont(font)
        self.size_label.setAlignment(Qt.AlignCenter)
        self.size_label.setText(f"")
        layout.addRow(self.size_label)

        layout.addRow(horizontal_rule())
        # Container size combobox
        self.size_combo = QComboBox()
        self.size_combo.addItems(
            [layout.tr("Automatic"), "1kB", "2kB", "4kB", "8kB", "16kB", "32kB"]
        )
        self.size_combo.setCurrentIndex(3)
        self.handle_size_tab_change()

        param_string = self.get_param_string()
        self.size_combo.currentIndexChanged.connect(self.handle_size_tab_change)
        layout.addRow(QLabel(layout.tr("Container Size:")), self.size_combo)

    def handle_size_tab_change(self):
        param_string = self.get_param_string()
        # Used to replace the existing string
        value = ""

        size_str = self.size_combo.currentText()  # e.g. "1kB"
        if self.size_combo.currentIndex() != 0:  # Must use index to detect 'Auto'
            size_kb = int(size_str[:-2])
            size_in_bytes = size_kb * 1024
            if size_kb == 32:
                size_in_bytes -= 1
            size_hex = f"{size_in_bytes:04X}"
            value = f"8202{size_hex}"

            self.size_label.setText(
                f"82 02 {" ".join([size_hex[i:i+2] for i in range(0, len(size_hex), 2)])}"
            )

            if param_string[-8:].startswith("8202"):
                # Replace existing
                self.set_param_string(param_string[:-8] + value)
            else:
                # Add missing
                self.set_param_string(param_string + value)
        else:
            # We're in auto
            self.size_label.setText("")

            # Get rid of the 82 param
            if param_string[-8:].startswith("8202"):
                self.set_param_string(param_string[0:-8])

        print(self.get_param_string())

    def build_record_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QComboBox, QTextEdit

        layout = QFormLayout(self.record_tab)

        self.record_type_combo = QComboBox()
        self.record_type_combo.addItems(
            [
                layout.tr("text"),
                layout.tr("uri"),
                layout.tr("mime"),
                layout.tr("smart poster"),
            ]
        )
        self.record_type_combo.currentIndexChanged.connect(self.change_record_type)
        layout.addRow(QLabel(layout.tr("Record Type:")), self.record_type_combo)

        self.record_stacked_widget = QStackedWidget()
        self.record_stacked_widget.addWidget(TextRecordForm(self.record_stacked_widget))
        self.record_stacked_widget.addWidget(URIRecordForm(self.record_stacked_widget))
        layout.addRow(self.record_stacked_widget)

    def change_record_type(self, index):
        self.record_stacked_widget.setCurrentIndex(index)

    def build_permissions_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QComboBox

        layout = QFormLayout(self.permissions_tab)

        self.rw_label = QLabel()
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        self.rw_label.setFont(font)
        self.rw_label.setAlignment(Qt.AlignCenter)
        self.rw_label.setText(f"81 02 00 00")
        layout.addRow(self.rw_label)

        layout.addRow(horizontal_rule())

        # Read permission
        self.read_perm_combo = QComboBox()
        self.read_perm_combo.addItems(
            [
                layout.tr("open access"),
                layout.tr("no access"),
                layout.tr("contact only"),
            ]
        )
        self.read_perm_combo.currentIndexChanged.connect(self.on_rw_value_change)
        layout.addRow(QLabel("Read Permission:"), self.read_perm_combo)

        # Write permission
        self.write_perm_combo = QComboBox()
        self.write_perm_combo.addItems(
            [
                layout.tr("open access"),
                layout.tr("no access"),
                layout.tr("write once"),
                layout.tr("contact only"),
            ]
        )
        self.write_perm_combo.currentIndexChanged.connect(self.on_rw_value_change)
        layout.addRow(
            QLabel(f"{layout.tr("Write Permission")}:"), self.write_perm_combo
        )

    def on_rw_value_change(self):
        param_string = self.get_param_string()
        re_rw = re.compile(rf"8102{RE_BYTE}{2}")

        formatted_value = f"81 02 {self.perm_map[self.read_perm_combo.currentText()]} {self.perm_map[self.write_perm_combo.currentText()]}"
        value = formatted_value.replace(" ", "")
        self.rw_label.setText(formatted_value)

        if param_string.startswith("81"):
            self.set_param_string(value + param_string[6:])
        elif re_rw.search(param_string):
            # We are replacing an existing string
            self.set_param_string(re_rw.sub(value, param_string))
        elif param_string == "":
            # Nothing set yet
            self.set_param_string(value)
        elif param_string.startswith("82"):
            # Only size set
            self.set_param_string(value + param_string)
        elif param_string.startswith("80"):
            # Data is set
            num_bytes = int(param_string[2:4], base=16) + 2

            self.set_param_string(param_string[0 : num_bytes * 2] + value)

            if len(param_string) > num_bytes:
                if param_string[num_bytes * 2 :].startswith("81"):
                    self.set_param_string(
                        param_string[0 : num_bytes * 2]
                        + value
                        + param_string[num_bytes * 2 + 8 :]
                    )
                elif param_string[num_bytes * 2 :].startswith("82"):
                    self.set_param_string(
                        param_string[0 : num_bytes * 2]
                        + value
                        + param_string[num_bytes * 2 :]
                    )
                else:
                    print("WTF mate? Probably an indexing issue")
                    print(param_string[num_bytes * 2], "\n", param_string)

        print(self.get_param_string())

    def build_raw_tab(self):
        from PyQt5.QtWidgets import QFormLayout, QLabel, QTextEdit

        param_string = self._result["param_string"]
        layout = QFormLayout(self.raw_tab)

        self.raw_text_edit = QTextEdit()
        # self.raw_text_edit.setPlaceholderText("Enter hex param string (optional)")
        if param_string != "":
            self.raw_text_edit.setText(param_string)
        layout.addRow(
            QLabel(layout.tr("Raw parameters:")),
        )
        layout.addRow(self.raw_text_edit)

    def on_tab_change(self, tab):
        """
        This handles:
            - the record tab's setting of param_string
            - the raw tab
                - input validation
                - setting param_string

        """
        param_string = self.get_param_string()

        # Raw Tab is last
        if tab == self.tab_widget.count() - 1:
            # If we are going to the raw tab, update it.
            if self.raw_text_edit.toPlainText() != param_string:
                self.raw_text_edit.setText(param_string)

        else:
            # raw to record
            record_parsed = get_record_from_param_string(param_string)
            record_tab = self.record_stacked_widget.currentWidget()
            record_tab_values = record_tab.getValues()
            record_tab_param = record_tab_values["params"]

            if record_parsed is not None:
                record_parsed_param = record_parsed["param"]
                if record_parsed_param != record_tab_param:
                    # Params don't match current record form
                    # TODO: decode record ->
                    #           matches selected -> do nothing
                    #                       else -> set record type etc
                    self.set_param_string(
                        param_string.replace(record_parsed_param, record_tab_param)
                    )
            else:
                # No record. We'll add it to the beginning.
                self.set_param_string(record_tab_param + param_string)

        # Size
        # Evaluate param string to push updates from raw edits
        size_combo_current = self.size_combo.currentIndex()
        size_combo_bytes = int(self.size_combo.currentText()[:-2]) * 1024
        size_param = param_string[-4:] if param_string[-8:].startswith("8202") else None

        if size_param:
            size_param_bytes = int(size_param, base=16)

            if size_param_bytes != size_combo_bytes:
                self.size_combo.setCurrentIndex(bytes_to_index(size_param_bytes))
        else:
            # Clear our 82 02 bytes
            self.size_combo.setCurrentIndex(0)

    def on_ok(self, dlg):
        """
        Gracefully exit. Kinda legacy.
        """

        print(self.record_stacked_widget.currentWidget().getValues())

        dlg.accept()

    def get_result(self):
        """Return the dictionary of final user-chosen data."""
        res = getattr(self, "_result", {})
        res["param_string"] += " --create D2760000850101"
        return res

    def get_param_string(self) -> str or None:
        return str(self._result["param_string"]) or ""

    def set_param_string(self, param_string: str):
        """Replaces the entire param_string"""
        self._result["param_string"] = str(param_string)

    def post_install(self, plugin, **kwargs):
        """
        Make the params available to NFCHandlerThread's install_app
        """
        result = getattr(self, "_result", {})
        if result and result["source"] == "ui":
            param_string = result["param_string"]


##########################################################################
#
#   Forms
#
##########################################################################


class AbstractRecordForm(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Create a QFrame to serve as a bordered container for the form
        self.frame = QFrame(self)
        self.frame.setFrameShape(QFrame.Box)
        self.frame.setFrameShadow(QFrame.Sunken)

        # Create the form layout that will hold the fields, and attach it to the frame
        self.form_layout = QFormLayout()
        self.form_layout.setLabelAlignment(Qt.AlignTop)
        self.frame.setLayout(self.form_layout)

        # Create the main layout for this widget and add the frame
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.frame)
        self.setLayout(main_layout)

        # Call the subclass's implementation to build the form
        self.buildForm()

    @abc.abstractmethod
    def buildForm(self):
        """
        Subclasses should build their form by adding widgets to self.form_layout.
        For example:
            self.form_layout.addRow(QLabel("Field:"), QLineEdit())
        """
        pass

    @abc.abstractmethod
    def getValues(self):
        """
        Return the values from the form.
        This should be implemented to return a dict (or similar) with the form data.
        """
        pass

    @abc.abstractmethod
    def setValues(self, values):
        """
        Set the form values.
        This should be implemented to take a dict (or similar) and update the form fields.
        """
        pass


class TextRecordForm(AbstractRecordForm):
    def buildForm(self):

        self.language_combo = QComboBox()
        self.language_combo.addItems((iso_to_localized_names.values()))
        lang = system_locale.name().split("_")[0]
        lang_index = ISO_639_1_LANGS.index(lang)
        self.language_combo.setCurrentIndex(lang_index)

        self.form_layout.addRow(QLabel(self.tr("Language:")), self.language_combo)

        self.payload_edit = QTextEdit()
        self.form_layout.addRow(self.payload_edit)

        self.language_combo.currentIndexChanged.connect(self.handleUpdate)
        text_record_focus_filter = FocusFilter(self.handleUpdate)
        # Handle updating param_strig on focus out
        self.payload_edit.installEventFilter(text_record_focus_filter)

    def handleUpdate(self):
        # param_string = self.parent().parent()
        if len(self.payload_edit.toPlainText()) > 0:
            # We've got a payload
            record = ndef.TextRecord(
                self.payload_edit.toPlainText(),
                language=localized_names_to_iso[self.language_combo.currentText()],
            )
            encoded = b"".join(ndef.message_encoder([record]))
            byte_length = len(encoded)
            param = f"80{byte_length:02X}{encoded.hex()}"
        else:
            # No payload. We need to clear the param_string if necessary.
            pass

    def getValues(self):
        record = TextRecord(
            self.payload_edit.toPlainText(),
            language=localized_names_to_iso[self.language_combo.currentText()],
        )
        encoded = b"".join(ndef.message_encoder([record]))
        encoded_length = f"{len(encoded):02X}"
        return {
            "language": localized_names_to_iso[self.language_combo.currentText()],
            "payload": self.payload_edit.toPlainText(),
            "params": f"80{encoded_length}{encoded.hex()}",
        }

    def setValues(self, param_str: str or None):
        lang = system_locale.name().split("_")[0]
        lang_index = ISO_639_1_LANGS.index(lang)

        if not param_str:
            self.language_combo.setCurrentIndex(lang_index)
            self.payload_edit.setText("")
        else:
            values = get_record_from_param_string(param_str)
            print(values)

            self.language_combo.setCurrentIndex(
                values.get("language", values["language"] or 0)
            )
            self.payload_edit.setText(values.get("payload", values["payload"] or ""))


class URIRecordForm(AbstractRecordForm):
    def buildForm(self):

        self.uri_prefix_combo = QComboBox()
        self.uri_prefix_combo.addItems((NFC_URI_PREFIXES.keys()))
        # self.language_combo.setCurrentIndex(lang_index)

        self.form_layout.addRow(QLabel(self.tr("Prefix:")), self.uri_prefix_combo)

        self.uri_payload_edit = QLineEdit()
        self.form_layout.addRow(QLabel(self.tr("Payload:")), self.uri_payload_edit)

        # self.language_combo.currentIndexChanged.connect(self.handleUpdate)
        # text_record_focus_filter = FocusFilter(self.handleUpdate)
        # # Handle updating param_strig on focus out
        # self.uri_payload_edit.installEventFilter(text_record_focus_filter)

    def handleUpdate(self):
        # param_string = self.parent().parent()
        if len(self.uri_payload_edit.toPlainText()) > 0:
            # We've got a payload
            record = ndef.UriRecord(
                self.uri_payload_edit.toPlainText(),
            )
            encoded = b"".join(ndef.message_encoder([record]))
            byte_length = len(encoded)
            param = f"80{byte_length:02X}{encoded.hex()}"
        else:
            # No payload. We need to clear the param_string if necessary.
            pass

    def getValues(self):
        record = TextRecord(
            self.uri_payload_edit.toPlainText(),
        )
        encoded = b"".join(ndef.message_encoder([record]))
        encoded_length = f"{len(encoded):02X}"
        return {
            "payload": self.uri_payload_edit.toPlainText(),
            "params": f"80{encoded_length}{encoded.hex()}",
        }

    def setValues(self, param_str: str or None):
        lang = system_locale.name().split("_")[0]
        lang_index = ISO_639_1_LANGS.index(lang)

        if not param_str:
            # self.language_combo.setCurrentIndex(lang_index)
            self.uri_payload_edit.setText("")
        else:
            values = get_record_from_param_string(param_str)
            print(values)

            # self.language_combo.setCurrentIndex(
            #     values.get("language", values["language"] or 0)
            # )
            self.uri_payload_edit.setText(
                values.get("payload", values["payload"] or "")
            )


##########################################################################
#
#   Resources
#
##########################################################################

NFC_URI_PREFIXES = {
    "": 0x00,
    "http://www.": 0x01,
    "https://www.": 0x02,
    "http://": 0x03,
    "https://": 0x04,
    "tel:": 0x05,
    "mailto:": 0x06,
    "ftp://anonymous:anonymous@": 0x07,
    "ftp://ftp.": 0x08,
    "ftps://": 0x09,
    "sftp://": 0x0A,
    "smb://": 0x0B,
    "nfs://": 0x0C,
    "ftp://": 0x0D,
    "dav://": 0x0E,
    "news:": 0x0F,
    "telnet://": 0x10,
    "imap:": 0x11,
    "rtsp://": 0x12,
    "urn:": 0x13,
    "pop:": 0x14,
    "sip:": 0x15,
    "sips:": 0x16,
    "tftp:": 0x17,
    "btspp://": 0x18,
    "btl2cap://": 0x19,
    "btgoep://": 0x1A,
    "tcpobex://": 0x1B,
    "irdaobex://": 0x1C,
    "file://": 0x1D,
    "urn:epc:id:": 0x1E,
    "urn:epc:tag:": 0x1F,
    "urn:epc:pat:": 0x20,
    "urn:epc:raw:": 0x21,
    "urn:epc:": 0x22,
    "urn:nfc:": 0x23,
}


ISO_639_1_LANGS = [
    "aa",
    "ab",
    "ae",
    "af",
    "ak",
    "am",
    "an",
    "ar",
    "as",
    "av",
    "ay",
    "az",
    "ba",
    "be",
    "bg",
    "bh",
    "bi",
    "bm",
    "bn",
    "bo",
    "br",
    "bs",
    "ca",
    "ce",
    "ch",
    "co",
    "cr",
    "cs",
    "cu",
    "cv",
    "cy",
    "da",
    "de",
    "dv",
    "dz",
    "ee",
    "el",
    "en",
    "eo",
    "es",
    "et",
    "eu",
    "fa",
    "ff",
    "fi",
    "fj",
    "fo",
    "fr",
    "fy",
    "ga",
    "gd",
    "gl",
    "gn",
    "gu",
    "gv",
    "ha",
    "he",
    "hi",
    "ho",
    "hr",
    "ht",
    "hu",
    "hy",
    "hz",
    "ia",
    "id",
    "ie",
    "ig",
    "ii",
    "ik",
    "io",
    "is",
    "it",
    "iu",
    "ja",
    "jv",
    "ka",
    "kg",
    "ki",
    "kj",
    "kk",
    "kl",
    "km",
    "kn",
    "ko",
    "kr",
    "ks",
    "ku",
    "kv",
    "kw",
    "ky",
    "la",
    "lb",
    "lg",
    "li",
    "ln",
    "lo",
    "lt",
    "lu",
    "lv",
    "mg",
    "mh",
    "mi",
    "mk",
    "ml",
    "mn",
    "mr",
    "ms",
    "mt",
    "my",
    "na",
    "nb",
    "nd",
    "ne",
    "ng",
    "nl",
    "nn",
    "no",
    "nr",
    "nv",
    "ny",
    "oc",
    "oj",
    "om",
    "or",
    "os",
    "pa",
    "pi",
    "pl",
    "ps",
    "pt",
    "qu",
    "rm",
    "rn",
    "ro",
    "ru",
    "rw",
    "sa",
    "sc",
    "sd",
    "se",
    "sg",
    "si",
    "sk",
    "sl",
    "sm",
    "sn",
    "so",
    "sq",
    "sr",
    "ss",
    "st",
    "su",
    "sv",
    "sw",
    "ta",
    "te",
    "tg",
    "th",
    "ti",
    "tk",
    "tl",
    "tn",
    "to",
    "tr",
    "ts",
    "tt",
    "tw",
    "ty",
    "ug",
    "uk",
    "ur",
    "uz",
    "ve",
    "vi",
    "vo",
    "wa",
    "wo",
    "xh",
    "yi",
    "yo",
    "za",
    "zh",
    "zu",
]

ISO_639_1_LANGS.sort()

iso_to_localized_names = {}
for code in ISO_639_1_LANGS:
    try:
        # Parse the locale; this creates a Locale object for the language code.
        loc = Locale.parse(code)
        # loc.display_name returns the language name in its own language.
        iso_to_localized_names[code] = loc.display_name
    except Exception as e:
        iso_to_localized_names[code] = code

localized_names_to_iso = {value: key for key, value in iso_to_localized_names.items()}

RE_BYTE = r"[0-9a-fA-F]{2}"
RE_RECORD_LENGTH = rf"^80({RE_BYTE})"
RE_SIZE = rf"8202({RE_BYTE}{2})$"
RE_PERMISSIONS = rf"8102{RE_BYTE}{2}"


def get_record_from_param_string(param_string: str) -> dict[str, str or int] or None:
    """

    :param param_string:
    :return:
        "param": record[0],  # Full 80 string
        "length": length,  # Length in bytes
        "data": data,  # record bytes
    """
    re_length = re.compile(RE_RECORD_LENGTH)
    length_match = re_length.match(param_string)

    if not length_match:
        return None
    print(length_match.groups())

    length = int(length_match.groups()[0], base=16)
    print(f"record length {length}")
    print(rf"^80{length_match.groups()[0]}{RE_BYTE*length}")
    print(param_string)
    record = re.search(rf"^80{length_match.groups()[0]}{RE_BYTE*length}", param_string)
    print(record)
    if not record:
        return None
    print(record[0])

    data = record[0][4:]

    return {
        "param": record[0],  # Full 80 string
        "length": length,  # Length in bytes
        "data": data,  # record bytes
    }


def get_permissions_from_param_string(
    param_string: str,
) -> dict[str, str] or None:
    param = None

    # Are permissions set or is it noise in a record?
    if "8102" in param_string and param_string.startswith("80"):
        parsed_record = get_record_from_param_string(param_string)
        if not param_string[parsed_record["length"] * 2 + 4 :].startswith("8102"):
            # No permissions data after the record
            return None
        else:
            # We know the next record is permissions and it's
            param = param_string[parsed_record["length"] + 4 : 12]

    # Since there's not data
    if param_string.startswith("8102"):
        param = param_string[0:8]

    if param:
        return {"param": param, "read": param[4:6], "write": param[-2:]}

    return None


def bytes_to_index(decimal_bytes: int) -> int:
    """
    Finds the closest selection to the input bytes
    for the size combo box
    :param decimal_bytes:
    :return:
    """
    if decimal_bytes < 512:
        return 0
    elif decimal_bytes < 1024 + 512:
        return 1
    elif decimal_bytes < 1024 * 3:
        return 2
    elif decimal_bytes < 1024 * 6:
        return 3
    elif decimal_bytes < 1024 * 12:
        return 4
    elif decimal_bytes < 1024 * 24:
        return 5
    else:
        return 6


##########################################################################

register_override("openjavacard-ndef-full.cap", OpenJavaCardNDEFOverride)
