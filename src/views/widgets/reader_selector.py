"""
ReaderSelectorWidget - Dropdown for selecting smart card readers.

Subscribes to reader list changes and emits selection changes.
"""

from typing import Optional, List, Callable

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox
from PyQt5.QtCore import pyqtSignal


class ReaderSelectorWidget(QWidget):
    """
    Widget for selecting a smart card reader from available readers.

    Provides:
    - Dropdown with reader names
    - Auto-select first reader when list changes
    - Preservation of selection when possible
    - Disabled state when no readers available

    Signals:
        reader_selected: Emitted when user selects a reader (reader_name: str)

    Example:
        selector = ReaderSelectorWidget()
        selector.reader_selected.connect(on_reader_changed)
        selector.update_readers(["Reader A", "Reader B"])
    """

    # Signal emitted when user selects a reader
    reader_selected = pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        label_text: str = "Reader:",
        show_label: bool = True,
    ):
        """
        Initialize the reader selector.

        Args:
            parent: Parent widget
            label_text: Text for the label (default: "Reader:")
            show_label: Whether to show the label
        """
        super().__init__(parent)

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create label
        if show_label:
            self._label = QLabel(label_text)
            layout.addWidget(self._label)
        else:
            self._label = None

        # Create dropdown
        self._dropdown = QComboBox()
        self._dropdown.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self._dropdown)

        # Track current readers
        self._readers: List[str] = []
        self._selected_reader: Optional[str] = None

    def _on_selection_changed(self, index: int) -> None:
        """Handle dropdown selection change."""
        if index >= 0 and index < len(self._readers):
            reader_name = self._readers[index]
            self._selected_reader = reader_name
            self.reader_selected.emit(reader_name)

    def update_readers(self, readers: List[str]) -> None:
        """
        Update the list of available readers.

        Preserves current selection if the reader is still available.
        Auto-selects first reader if current selection is not available.

        Args:
            readers: List of reader names
        """
        # Block signals during update
        self._dropdown.blockSignals(True)
        self._dropdown.clear()
        self._readers = list(readers)

        if not readers:
            self._dropdown.setDisabled(True)
            self._selected_reader = None
            self._dropdown.blockSignals(False)
            return

        self._dropdown.setEnabled(True)
        self._dropdown.addItems(readers)

        # Try to preserve selection
        if self._selected_reader and self._selected_reader in readers:
            idx = readers.index(self._selected_reader)
            self._dropdown.setCurrentIndex(idx)
        else:
            # Select first reader
            self._dropdown.setCurrentIndex(0)
            self._selected_reader = readers[0]
            # Emit signal for new selection
            self._dropdown.blockSignals(False)
            self.reader_selected.emit(readers[0])
            return

        self._dropdown.blockSignals(False)

    @property
    def selected_reader(self) -> Optional[str]:
        """Get the currently selected reader name."""
        return self._selected_reader

    @selected_reader.setter
    def selected_reader(self, reader_name: str) -> None:
        """
        Set the selected reader.

        Args:
            reader_name: Name of reader to select
        """
        if reader_name in self._readers:
            idx = self._readers.index(reader_name)
            self._dropdown.setCurrentIndex(idx)
            self._selected_reader = reader_name

    @property
    def readers(self) -> List[str]:
        """Get the list of available readers."""
        return list(self._readers)

    @property
    def has_readers(self) -> bool:
        """Check if any readers are available."""
        return len(self._readers) > 0

    @property
    def dropdown(self) -> QComboBox:
        """Get the underlying QComboBox."""
        return self._dropdown

    def setEnabled(self, enabled: bool) -> None:
        """Enable or disable the widget."""
        super().setEnabled(enabled)
        self._dropdown.setEnabled(enabled)
        if self._label:
            self._label.setEnabled(enabled)

    def count(self) -> int:
        """Get the number of readers."""
        return len(self._readers)
