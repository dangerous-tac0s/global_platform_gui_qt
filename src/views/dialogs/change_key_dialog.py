"""
ChangeKeyDialog - Dialog for changing smart card GlobalPlatform keys.

Supports both single-key (SCP02/legacy) and separate-key (SCP03) modes
with real-time key type detection and validation.
"""

import re
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QCheckBox,
    QFrame,
    QDialogButtonBox,
    QToolButton,
    QWidget,
    QSizePolicy,
)

from ...models.key_config import (
    KeyConfiguration,
    KeyType,
    KeyMode,
    detect_key_type,
    is_ambiguous_length,
    get_ambiguous_display,
)


DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"

# Valid key lengths in bytes
VALID_KEY_LENGTHS = [8, 16, 24, 32]


class HexLineEdit(QLineEdit):
    """QLineEdit with automatic hex formatting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self._format_input)
        self.setPlaceholderText("Enter hex bytes...")

    def _format_input(self):
        """Auto-format input as uppercase hex with spaces."""
        text = self.text()
        hex_only = re.sub(r"[^0-9a-fA-F]", "", text)
        spaced = " ".join([hex_only[i : i + 2] for i in range(0, len(hex_only), 2)])
        self.blockSignals(True)
        self.setText(spaced.upper())
        self.blockSignals(False)

    def get_clean_hex(self) -> str:
        """Get hex value without spaces."""
        return self.text().replace(" ", "")

    def get_byte_count(self) -> int:
        """Get number of bytes entered."""
        clean = self.get_clean_hex()
        return len(clean) // 2 if len(clean) % 2 == 0 else 0


class ChangeKeyDialog(QDialog):
    """
    Dialog for changing GlobalPlatform card keys.

    Features:
    - Real-time key type detection based on length
    - AES/3DES selector for ambiguous lengths (16/24 bytes)
    - Collapsible "Advanced" section for SCP03 separate keys
    - "Use same key for all" option for SCP03
    - Warning about irreversible operation
    """

    def __init__(
        self,
        current_key: str = DEFAULT_KEY,
        current_config: Optional[KeyConfiguration] = None,
        scp_info: Optional[dict] = None,
        parent=None,
    ):
        """
        Initialize the change key dialog.

        Args:
            current_key: Current card key (hex string)
            current_config: Existing KeyConfiguration if available
            scp_info: Optional dict with SCP detection results:
                - scp_version: "02", "03", or None
                - supports_scp03: bool
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Change Card Key")
        self.setMinimumWidth(500)

        self._current_key = current_key
        self._current_config = current_config
        self._scp_info = scp_info

        self._setup_ui()
        self._connect_signals()
        self._load_current_config()
        self._update_key_type_display()
        self._apply_scp_info()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # SCP detection info (shown if available)
        self._scp_info_label = QLabel()
        self._scp_info_label.setWordWrap(True)
        self._scp_info_label.hide()  # Hidden until we have SCP info
        layout.addWidget(self._scp_info_label)

        # Main key input section
        main_section = self._create_main_key_section()
        layout.addWidget(main_section)

        # Advanced section (collapsible)
        self._advanced_section = self._create_advanced_section()
        layout.addWidget(self._advanced_section)

        # Warning label
        warning = QLabel(
            "Warning: Changing keys is irreversible. "
            "Losing your keys means permanent loss of card access."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #cc6600; font-style: italic;")
        layout.addWidget(warning)

        # Button box
        button_layout = QHBoxLayout()

        self._reset_button = QPushButton("Reset to Default")
        self._reset_button.setMinimumWidth(120)  # Ensure text is fully visible on Windows
        self._reset_button.clicked.connect(self._reset_to_default)
        button_layout.addWidget(self._reset_button)

        button_layout.addStretch()

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._button_box.accepted.connect(self._validate_and_accept)
        self._button_box.rejected.connect(self.reject)
        button_layout.addWidget(self._button_box)

        layout.addLayout(button_layout)

    def _create_main_key_section(self) -> QWidget:
        """Create the main key input section."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Key input
        self._key_input = HexLineEdit()
        self._key_input.setText(self._current_key)
        layout.addRow("Key:", self._key_input)

        # Detected type label
        self._type_label = QLabel()
        layout.addRow("Detected:", self._type_label)

        # AES/3DES selector (shown only for ambiguous lengths)
        self._type_selector_widget = QWidget()
        type_layout = QHBoxLayout(self._type_selector_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)

        type_layout.addWidget(QLabel("Interpret as:"))

        self._type_group = QButtonGroup(self)
        self._aes_radio = QRadioButton("AES")
        self._des_radio = QRadioButton("3DES")
        self._des_radio.setChecked(True)  # Default to 3DES for legacy compatibility

        self._type_group.addButton(self._aes_radio, 1)
        self._type_group.addButton(self._des_radio, 2)

        type_layout.addWidget(self._aes_radio)
        type_layout.addWidget(self._des_radio)
        type_layout.addStretch()

        layout.addRow("", self._type_selector_widget)
        self._type_selector_widget.hide()  # Hidden by default

        return widget

    def _create_advanced_section(self) -> QWidget:
        """Create the collapsible advanced section for SCP03 keys."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 10, 0, 0)

        # Toggle button
        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setStyleSheet("QToolButton { border: none; }")
        self._advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._advanced_toggle.setArrowType(Qt.RightArrow)
        self._advanced_toggle.setText(" Advanced: Separate SCP03 Keys")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.toggled.connect(self._toggle_advanced)
        container_layout.addWidget(self._advanced_toggle)

        # Advanced content
        self._advanced_content = QGroupBox()
        self._advanced_content.hide()
        content_layout = QVBoxLayout(self._advanced_content)

        # Enable checkbox
        self._use_separate_keys = QCheckBox("Use separate ENC/MAC/DEK keys")
        content_layout.addWidget(self._use_separate_keys)

        # Separate key inputs
        self._separate_keys_widget = QWidget()
        sep_layout = QFormLayout(self._separate_keys_widget)
        sep_layout.setContentsMargins(20, 10, 0, 0)

        self._enc_input = HexLineEdit()
        self._mac_input = HexLineEdit()
        self._dek_input = HexLineEdit()

        sep_layout.addRow("ENC Key:", self._enc_input)
        sep_layout.addRow("MAC Key:", self._mac_input)
        sep_layout.addRow("DEK Key:", self._dek_input)

        # Use same key checkbox
        self._use_same_key = QCheckBox("Use same key for all three")
        self._use_same_key.setChecked(True)
        sep_layout.addRow("", self._use_same_key)

        content_layout.addWidget(self._separate_keys_widget)
        self._separate_keys_widget.setEnabled(False)

        container_layout.addWidget(self._advanced_content)

        return container

    def _connect_signals(self):
        """Connect UI signals."""
        self._key_input.textChanged.connect(self._on_main_key_changed)
        self._type_group.buttonClicked.connect(self._update_key_type_display)
        self._use_separate_keys.toggled.connect(self._on_separate_keys_toggled)
        self._use_same_key.toggled.connect(self._on_use_same_key_toggled)
        self._enc_input.textChanged.connect(self._sync_keys_if_needed)

    def _load_current_config(self):
        """Load existing configuration into the UI."""
        if not self._current_config:
            return

        if self._current_config.mode == KeyMode.SEPARATE:
            # Load separate keys
            self._advanced_toggle.setChecked(True)
            self._use_separate_keys.setChecked(True)

            self._enc_input.setText(self._current_config.enc_key or "")
            self._mac_input.setText(self._current_config.mac_key or "")
            self._dek_input.setText(self._current_config.dek_key or "")

            # Check if all keys are the same
            same = (
                self._current_config.enc_key
                == self._current_config.mac_key
                == self._current_config.dek_key
            )
            self._use_same_key.setChecked(same)

        # Set AES preference based on config
        if self._current_config.uses_aes():
            self._aes_radio.setChecked(True)
        else:
            self._des_radio.setChecked(True)

    def _apply_scp_info(self):
        """Apply SCP detection info to the UI."""
        if not self._scp_info:
            return

        scp_version = self._scp_info.get("scp_version")
        supports_scp03 = self._scp_info.get("supports_scp03", False)

        if scp_version:
            if supports_scp03:
                self._scp_info_label.setText(
                    f"Card uses SCP{scp_version}. "
                    "This card supports AES keys and separate ENC/MAC/DEK keys."
                )
                self._scp_info_label.setStyleSheet(
                    "background-color: #1a3a1a; color: #90EE90; "
                    "padding: 8px; border-radius: 4px; margin-bottom: 8px;"
                )
                # Default to AES for SCP03 cards
                self._aes_radio.setChecked(True)
            else:
                self._scp_info_label.setText(
                    f"Card uses SCP{scp_version}. "
                    "This card uses 3DES keys (legacy mode)."
                )
                self._scp_info_label.setStyleSheet(
                    "background-color: #2a2a1a; color: #FFD700; "
                    "padding: 8px; border-radius: 4px; margin-bottom: 8px;"
                )
                # Default to 3DES for SCP02 cards
                self._des_radio.setChecked(True)

            self._scp_info_label.show()

    def _toggle_advanced(self, expanded: bool):
        """Toggle the advanced section visibility."""
        if expanded:
            self._advanced_toggle.setArrowType(Qt.DownArrow)
            self._advanced_content.show()
        else:
            self._advanced_toggle.setArrowType(Qt.RightArrow)
            self._advanced_content.hide()
        self.adjustSize()

    def _on_main_key_changed(self):
        """Handle main key input change."""
        self._update_key_type_display()

    def _on_separate_keys_toggled(self, checked: bool):
        """Handle separate keys checkbox toggle."""
        self._separate_keys_widget.setEnabled(checked)

        if checked and self._use_same_key.isChecked():
            # Copy main key to all three fields
            key = self._key_input.text()
            self._enc_input.setText(key)
            self._mac_input.setText(key)
            self._dek_input.setText(key)

    def _on_use_same_key_toggled(self, checked: bool):
        """Handle 'use same key' checkbox toggle."""
        self._mac_input.setEnabled(not checked)
        self._dek_input.setEnabled(not checked)

        if checked:
            # Sync all keys to ENC key
            enc_key = self._enc_input.text()
            self._mac_input.setText(enc_key)
            self._dek_input.setText(enc_key)

    def _sync_keys_if_needed(self):
        """Sync MAC/DEK to ENC if 'use same key' is checked."""
        if self._use_same_key.isChecked():
            enc_key = self._enc_input.text()
            self._mac_input.blockSignals(True)
            self._dek_input.blockSignals(True)
            self._mac_input.setText(enc_key)
            self._dek_input.setText(enc_key)
            self._mac_input.blockSignals(False)
            self._dek_input.blockSignals(False)

    def _update_key_type_display(self):
        """Update the key type display based on current input."""
        byte_count = self._key_input.get_byte_count()

        if byte_count == 0:
            self._type_label.setText("Enter a key...")
            self._type_selector_widget.hide()
            return

        if byte_count not in VALID_KEY_LENGTHS:
            self._type_label.setText(
                f"Invalid length ({byte_count} bytes). "
                f"Valid: {', '.join(str(l) for l in VALID_KEY_LENGTHS)}"
            )
            self._type_label.setStyleSheet("color: red;")
            self._type_selector_widget.hide()
            return

        self._type_label.setStyleSheet("")

        if is_ambiguous_length(byte_count):
            # Show ambiguous message and selector
            self._type_label.setText(get_ambiguous_display(byte_count))
            self._type_selector_widget.show()

            # Update radio labels based on length
            if byte_count == 16:
                self._aes_radio.setText("AES-128")
                self._des_radio.setText("3DES")
            else:  # 24 bytes
                self._aes_radio.setText("AES-192")
                self._des_radio.setText("3DES-192")
        else:
            # Unambiguous - show detected type
            prefer_aes = self._aes_radio.isChecked()
            key_type = detect_key_type(self._key_input.get_clean_hex(), prefer_aes)
            self._type_label.setText(key_type.value if key_type else "Unknown")
            self._type_selector_widget.hide()

    def _get_selected_key_type(self) -> Optional[KeyType]:
        """Get the selected key type based on input and selector."""
        byte_count = self._key_input.get_byte_count()

        if byte_count not in VALID_KEY_LENGTHS:
            return None

        prefer_aes = self._aes_radio.isChecked()
        return detect_key_type(self._key_input.get_clean_hex(), prefer_aes)

    def _validate_and_accept(self):
        """Validate input and accept dialog if valid."""
        # Check main key
        byte_count = self._key_input.get_byte_count()
        if byte_count not in VALID_KEY_LENGTHS:
            self._type_label.setText(
                f"Invalid key length: {byte_count} bytes. "
                f"Must be {', '.join(str(l) for l in VALID_KEY_LENGTHS)}."
            )
            self._type_label.setStyleSheet("color: red;")
            return

        # Check separate keys if enabled
        if self._use_separate_keys.isChecked():
            enc_len = self._enc_input.get_byte_count()
            mac_len = self._mac_input.get_byte_count()
            dek_len = self._dek_input.get_byte_count()

            if enc_len not in VALID_KEY_LENGTHS:
                self._type_label.setText("Invalid ENC key length.")
                self._type_label.setStyleSheet("color: red;")
                return

            if not (enc_len == mac_len == dek_len):
                self._type_label.setText("All three keys must have the same length.")
                self._type_label.setStyleSheet("color: red;")
                return

        self.accept()

    def _reset_to_default(self):
        """Reset to default key."""
        self._key_input.setText(DEFAULT_KEY)
        self._use_separate_keys.setChecked(False)
        self._des_radio.setChecked(True)

    def get_configuration(self) -> Optional[KeyConfiguration]:
        """
        Get the configured key settings.

        Returns:
            KeyConfiguration if dialog was accepted, None otherwise
        """
        if self.result() != QDialog.Accepted:
            return None

        key_type = self._get_selected_key_type()
        if not key_type:
            return None

        if self._use_separate_keys.isChecked():
            return KeyConfiguration(
                mode=KeyMode.SEPARATE,
                key_type=key_type,
                enc_key=self._enc_input.get_clean_hex(),
                mac_key=self._mac_input.get_clean_hex(),
                dek_key=self._dek_input.get_clean_hex(),
            )
        else:
            return KeyConfiguration(
                mode=KeyMode.SINGLE,
                key_type=key_type,
                static_key=self._key_input.get_clean_hex(),
            )

    def get_results(self) -> Optional[str]:
        """
        Get the key as a simple string (for backward compatibility).

        Returns:
            Hex key string if accepted, None otherwise
        """
        config = self.get_configuration()
        return config.get_effective_key() if config else None
