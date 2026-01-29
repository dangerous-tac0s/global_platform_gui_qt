"""
AppletListWidget - Displays lists of installed and available applets.

Provides a two-column layout with installed apps on the left and
available apps on the right, with selection handling.
"""

from typing import Optional, List, Dict, Any, Callable

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
)
from PyQt5.QtCore import pyqtSignal

from ...events.event_bus import EventBus, InstalledAppsUpdatedEvent


class AppletListWidget(QWidget):
    """
    Widget displaying installed and available applets in a two-column layout.

    Features:
    - Installed apps list (left column)
    - Available apps list (right column)
    - Install/Uninstall buttons
    - Selection signals for showing app details

    Signals:
        install_requested: Emitted when install button clicked (cap_name: str)
        uninstall_requested: Emitted when uninstall button clicked (cap_name: str)
        available_selected: Emitted when available app selected (cap_name: str)
        installed_selected: Emitted when installed app selected (cap_name: str)

    Example:
        applet_list = AppletListWidget()
        applet_list.install_requested.connect(on_install)
        applet_list.set_available_apps(["App1.cap", "App2.cap"])
    """

    # Signals
    install_requested = pyqtSignal(str)
    uninstall_requested = pyqtSignal(str)
    available_selected = pyqtSignal(str)
    installed_selected = pyqtSignal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        subscribe_to_events: bool = True,
    ):
        """
        Initialize the applet list widget.

        Args:
            parent: Parent widget
            subscribe_to_events: If True, subscribe to EventBus events
        """
        super().__init__(parent)

        # Track app names
        self._installed_app_names: List[str] = []
        self._available_app_names: List[str] = []
        self._installed_aids: Dict[str, Optional[str]] = {}  # AID -> version

        # Create layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create grid for two columns
        self._grid = QGridLayout()

        # Installed apps column (left)
        self._grid.addWidget(QLabel("Installed Apps"), 0, 0)
        self._installed_list = QListWidget()
        self._installed_list.currentItemChanged.connect(self._on_installed_selected)
        self._grid.addWidget(self._installed_list, 1, 0)

        self._uninstall_button = QPushButton("Uninstall")
        self._uninstall_button.setEnabled(False)
        self._uninstall_button.clicked.connect(self._on_uninstall_clicked)
        self._grid.addWidget(self._uninstall_button, 2, 0)

        # Available apps column (right)
        self._grid.addWidget(QLabel("Available Apps"), 0, 1)
        self._available_list = QListWidget()
        self._available_list.currentItemChanged.connect(self._on_available_selected)
        self._grid.addWidget(self._available_list, 1, 1)

        self._install_button = QPushButton("Install")
        self._install_button.setEnabled(False)
        self._install_button.clicked.connect(self._on_install_clicked)
        self._grid.addWidget(self._install_button, 2, 1)

        main_layout.addLayout(self._grid)

        # EventBus subscription
        self._event_bus: Optional[EventBus] = None
        if subscribe_to_events:
            self._subscribe_to_events()

    def _subscribe_to_events(self) -> None:
        """Subscribe to EventBus events."""
        self._event_bus = EventBus.instance()
        self._event_bus.subscribe(
            InstalledAppsUpdatedEvent, self._on_installed_apps_updated
        )

    def _on_installed_apps_updated(self, event: InstalledAppsUpdatedEvent) -> None:
        """Handle InstalledAppsUpdatedEvent."""
        self.update_installed_apps(event.apps)

    # =========================================================================
    # Selection Handlers
    # =========================================================================

    def _on_installed_selected(
        self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]
    ) -> None:
        """Handle installed app selection change."""
        self._uninstall_button.setEnabled(current is not None)
        if current:
            self.installed_selected.emit(current.text())

    def _on_available_selected(
        self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]
    ) -> None:
        """Handle available app selection change."""
        self._install_button.setEnabled(current is not None)
        if current:
            self.available_selected.emit(current.text())

    def _on_install_clicked(self) -> None:
        """Handle install button click."""
        selected = self._available_list.selectedItems()
        if selected:
            cap_name = selected[0].text()
            self.install_requested.emit(cap_name)

    def _on_uninstall_clicked(self) -> None:
        """Handle uninstall button click."""
        selected = self._installed_list.selectedItems()
        if selected:
            cap_name = selected[0].text()
            self.uninstall_requested.emit(cap_name)

    # =========================================================================
    # App List Management
    # =========================================================================

    def set_available_apps(
        self,
        apps: List[str],
        exclude_installed: bool = True,
    ) -> None:
        """
        Set the list of available apps.

        Args:
            apps: List of cap file names
            exclude_installed: If True, exclude already installed apps
        """
        self._available_list.clear()
        self._available_app_names = []

        for cap_name in apps:
            if exclude_installed and cap_name in self._installed_app_names:
                continue
            self._available_app_names.append(cap_name)
            self._available_list.addItem(cap_name)

        self._available_list.update()

    def update_installed_apps(
        self,
        apps: Dict[str, Optional[str]],
        resolve_func: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        """
        Update the installed apps list.

        Args:
            apps: Dict mapping AID to version (or None)
            resolve_func: Optional function to resolve AID to display name
        """
        self._installed_list.clear()
        self._installed_app_names = []
        self._installed_aids = apps

        for aid, version in apps.items():
            # Try to resolve to display name
            if resolve_func:
                display_name = resolve_func(aid)
            else:
                display_name = None

            if display_name:
                text = display_name
                self._installed_app_names.append(display_name)
            else:
                text = f"Unknown: {aid}"
                self._installed_app_names.append(f"Unknown: {aid}")

            # Add version if available
            # if version:
            #     text += f" - v{version}"

            self._installed_list.addItem(text)

        # Refresh available list to exclude newly installed apps
        if self._available_app_names:
            self.set_available_apps(
                self._available_app_names + [
                    name for name in self._installed_app_names
                    if name not in self._available_app_names
                ]
            )

    def clear_installed(self) -> None:
        """Clear the installed apps list."""
        self._installed_list.clear()
        self._installed_app_names = []
        self._installed_aids = {}

    def clear_available(self) -> None:
        """Clear the available apps list."""
        self._available_list.clear()
        self._available_app_names = []

    def clear_all(self) -> None:
        """Clear both lists."""
        self.clear_installed()
        self.clear_available()

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def installed_list(self) -> QListWidget:
        """Get the installed apps QListWidget."""
        return self._installed_list

    @property
    def available_list(self) -> QListWidget:
        """Get the available apps QListWidget."""
        return self._available_list

    @property
    def install_button(self) -> QPushButton:
        """Get the install button."""
        return self._install_button

    @property
    def uninstall_button(self) -> QPushButton:
        """Get the uninstall button."""
        return self._uninstall_button

    @property
    def installed_app_names(self) -> List[str]:
        """Get list of installed app names."""
        return list(self._installed_app_names)

    @property
    def available_app_names(self) -> List[str]:
        """Get list of available app names."""
        return list(self._available_app_names)

    @property
    def grid_layout(self) -> QGridLayout:
        """Get the grid layout for customization."""
        return self._grid

    def set_install_enabled(self, enabled: bool) -> None:
        """Enable or disable the install button."""
        self._install_button.setEnabled(enabled)

    def set_uninstall_enabled(self, enabled: bool) -> None:
        """Enable or disable the uninstall button."""
        self._uninstall_button.setEnabled(enabled)

    def set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable both buttons."""
        self._install_button.setEnabled(enabled)
        self._uninstall_button.setEnabled(enabled)

    def get_selected_available(self) -> Optional[str]:
        """Get the currently selected available app."""
        selected = self._available_list.selectedItems()
        return selected[0].text() if selected else None

    def get_selected_installed(self) -> Optional[str]:
        """Get the currently selected installed app."""
        selected = self._installed_list.selectedItems()
        return selected[0].text() if selected else None

    def unsubscribe(self) -> None:
        """Unsubscribe from EventBus events."""
        if self._event_bus:
            self._event_bus.unsubscribe(
                InstalledAppsUpdatedEvent, self._on_installed_apps_updated
            )
            self._event_bus = None
