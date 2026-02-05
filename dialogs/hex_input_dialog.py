from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
)
import re


class HexInputDialog(QDialog):
    def __init__(
        self,
        title="Enter Hex Bytes",
        min_bytes=None,
        max_bytes=None,
        fixed_byte_counts=None,
        parent=None,
        initial_value: None | str = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)

        # Validation rules conflict check
        if fixed_byte_counts is not None and (
            min_bytes is not None or max_bytes is not None
        ):
            raise ValueError(
                "You cannot use fixed_byte_counts with min_bytes or max_bytes."
            )

        self.min_bytes = min_bytes
        self.max_bytes = max_bytes
        self.fixed_byte_counts = fixed_byte_counts
        if self.fixed_byte_counts:
            self.fixed_byte_counts.sort()

        layout = QVBoxLayout(self)

        self.label = QLabel("Enter hexadecimal bytes (e.g. `A0 1F B2`):")
        layout.addWidget(self.label)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("AA BB CC ...")
        self.line_edit.textChanged.connect(self._format_input)
        layout.addWidget(self.line_edit)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        if initial_value:
            self.line_edit.setText(initial_value)

    def _format_input(self):
        text = self.line_edit.text()
        # Don't hex-format if user is typing "FIDESMO" keyword
        stripped = text.replace(" ", "").upper()
        if stripped.startswith("FIDE") or stripped == "FIDESMO":
            return
        hex_only = re.sub(r"[^0-9a-fA-F]", "", text)  # remove non-hex chars
        # Insert space every two hex digits
        spaced = " ".join([hex_only[i : i + 2] for i in range(0, len(hex_only), 2)])
        self.line_edit.blockSignals(True)
        self.line_edit.setText(spaced.upper())
        self.line_edit.blockSignals(False)

    def _validate(self, raw_text: str):
        if len(raw_text) % 2 != 0:
            self.label.setText(
                "Hex input must contain full bytes (two hex characters per byte)."
            )
            return False

        byte_count = len(raw_text) // 2

        if self.fixed_byte_counts is not None:
            if byte_count not in self.fixed_byte_counts:
                label_text = f"Input must be exactly {', '.join(map(str, self.fixed_byte_counts))} bytes."
                if len(self.fixed_byte_counts) == 2:
                    label_text = label_text.replace(",", " or")
                elif len(self.fixed_byte_counts) > 2:
                    label_text = re.sub(
                        r", ([0-9]+ bytes\.)$", r", or \g<1>", label_text
                    )
                self.label.setText(label_text)
                return False

        if self.min_bytes is not None and byte_count < self.min_bytes:
            self.label.setText(f"Input must be at least {self.min_bytes} bytes.")
            return False

        if self.max_bytes is not None and byte_count > self.max_bytes:
            self.label.setText(f"Input must be at most {self.max_bytes} bytes.")
            return False

        return True

    def _validate_and_accept(self):
        raw_text = self.line_edit.text().replace(" ", "")

        # Special case: "FIDESMO" keyword bypasses hex validation
        if raw_text.upper() == "FIDESMO":
            self.hex_result = "FIDESMO"
            self.accept()
            return

        if not self._validate(raw_text):
            return

        self.hex_result = raw_text.upper()
        self.accept()

    def get_results(self):
        return getattr(self, "hex_result", None)
