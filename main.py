# main.py
from __future__ import annotations

import datetime
import json
import pprint
import sys
import os
import tempfile
import textwrap
import time

import gnupg

import markdown
from PyQt5.QtGui import QIcon, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QHBoxLayout,
    QGridLayout,
    QProgressBar,
    QMessageBox,
    QFrame,
    QDialog,
    QLineEdit,
    QFormLayout,
    QTextBrowser,
    QInputDialog,
    QAction,
    QActionGroup,
    QMainWindow,
    QDialogButtonBox,
    QSizePolicy,
)
from PyQt5.QtCore import QTimer, Qt, QSize, QEvent
import sip
from cryptography.exceptions import InvalidTag

from dialogs.hex_input_dialog import HexInputDialog
from src.threads import FileHandlerThread, NFCHandlerThread, resource_path, DEFAULT_KEY
from src.threads.plugin_fetch_thread import PluginFetchThread
from secure_storage import (
    SecureStorage,
    get_app_data_dir,
    get_default_storage_path,
    get_default_config_path,
    migrate_legacy_files,
    CACHE_TIMEOUT_OPTIONS,
)

# MVC imports
from src.controllers import CardController
from src.services.storage_service import StorageService
from src.models.card import CardIdentifier
from src.events.event_bus import (
    EventBus,
    KeyPromptEvent,
    KeyValidatedEvent,
    CardStateChangedEvent,
    StatusMessageEvent,
    ErrorEvent,
)
from src.views.widgets.status_bar import MessageQueue
from src.views.widgets.loading_indicator import LoadingIndicator
from src.views.dialogs import KeyPromptDialog, ComboDialog, ChangeKeyDialog, ManageTagsDialog, LoadingDialog
from src.views.dialogs.plugin_designer import PluginDesignerWizard


class ElidingLabel(QLabel):
    """A QLabel that elides text when it doesn't fit the available width."""

    # Vertical padding for cross-platform font rendering compatibility
    VERTICAL_PADDING = 4

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setToolTip(text)
        self._update_minimum_height()

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self._update_elided_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def changeEvent(self, event):
        """Handle font changes to update minimum height and re-elide text."""
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._update_minimum_height()
            self._update_elided_text()

    def _update_minimum_height(self):
        """Update minimum height based on current font metrics."""
        self.ensurePolished()  # Ensure stylesheet font is applied
        fm = QFontMetrics(self.font())
        min_height = fm.height() + self.VERTICAL_PADDING
        self.setMinimumHeight(min_height)

    def sizeHint(self):
        """Return preferred size based on font metrics."""
        self.ensurePolished()  # Ensure stylesheet font is applied
        fm = QFontMetrics(self.font())
        width = fm.horizontalAdvance(self._full_text) if self._full_text else 100
        height = fm.height() + self.VERTICAL_PADDING
        return QSize(min(width, 400), height)

    def _update_elided_text(self):
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self._full_text, Qt.ElideRight, self.width())
        super().setText(elided)


class _StorageServiceAdapter:
    """
    Adapter to bridge existing SecureStorage to ISecureStorageService interface.

    This allows the CardController to work with the existing secure storage
    implementation until we fully migrate to StorageService.
    """

    def __init__(self, storage_instance, data):
        self._instance = storage_instance
        self._data = data or {"tags": {}}

    def is_initialized(self) -> bool:
        return self._data is not None

    def load(self):
        return self._data

    def save(self, data=None):
        if data:
            self._data = data
        if self._instance:
            self._instance.save(self._data)

    def get_key_for_tag(self, uid: str):
        if not self._data:
            return None
        uid_normalized = uid.upper().replace(" ", "")
        tags = self._data.get("tags", {})
        tag_data = tags.get(uid_normalized)
        if tag_data and "key" in tag_data:
            return tag_data["key"]
        return None

    def set_key_for_tag(self, uid: str, key, name=None):
        if not self._data:
            self._data = {"tags": {}}
        uid_normalized = uid.upper().replace(" ", "")
        if "tags" not in self._data:
            self._data["tags"] = {}
        if uid_normalized not in self._data["tags"]:
            self._data["tags"][uid_normalized] = {}
        self._data["tags"][uid_normalized]["key"] = key
        if name:
            self._data["tags"][uid_normalized]["name"] = name

    def get_tag_name(self, uid: str):
        if not self._data:
            return None
        uid_normalized = uid.upper().replace(" ", "")
        tags = self._data.get("tags", {})
        tag_data = tags.get(uid_normalized)
        if tag_data and "name" in tag_data:
            return tag_data["name"]
        return None

    def get_key_for_card(self, identifier: CardIdentifier):
        """CPLC-aware key lookup."""
        if not self._data:
            return None
        tags = self._data.get("tags", {})

        # Try CPLC hash first
        if identifier.cplc_hash:
            cplc_normalized = identifier.cplc_hash.upper()
            if cplc_normalized in tags:
                tag_data = tags[cplc_normalized]
                if tag_data and "key" in tag_data:
                    return tag_data["key"]

        # Fall back to UID
        if identifier.uid:
            uid_normalized = identifier.uid.upper().replace(" ", "")
            if uid_normalized in tags:
                tag_data = tags[uid_normalized]
                if tag_data and "key" in tag_data:
                    return tag_data["key"]

        return None

    def get_name_for_card(self, identifier: CardIdentifier):
        """CPLC-aware name lookup."""
        if not self._data:
            return None
        tags = self._data.get("tags", {})

        # Try CPLC hash first
        if identifier.cplc_hash:
            cplc_normalized = identifier.cplc_hash.upper()
            if cplc_normalized in tags:
                tag_data = tags[cplc_normalized]
                if tag_data and "name" in tag_data:
                    return tag_data["name"]

        # Fall back to UID
        if identifier.uid:
            uid_normalized = identifier.uid.upper().replace(" ", "")
            if uid_normalized in tags:
                tag_data = tags[uid_normalized]
                if tag_data and "name" in tag_data:
                    return tag_data["name"]

        return None

    def set_key_for_card(self, identifier: CardIdentifier, key, name=None):
        """CPLC-aware key storage."""
        if not self._data:
            self._data = {"tags": {}}
        if "tags" not in self._data:
            self._data["tags"] = {}

        # Use CPLC hash as primary key if available
        if identifier.cplc_hash:
            primary_key = identifier.cplc_hash.upper()
        elif identifier.uid:
            primary_key = identifier.uid.upper().replace(" ", "")
        else:
            return

        if primary_key not in self._data["tags"]:
            self._data["tags"][primary_key] = {}

        self._data["tags"][primary_key]["key"] = key

        # Store UID as reference if using CPLC
        if identifier.cplc_hash and identifier.uid:
            self._data["tags"][primary_key]["uid"] = identifier.uid.upper().replace(" ", "")

        if name:
            self._data["tags"][primary_key]["name"] = name

    def upgrade_to_cplc(self, old_uid: str, cplc_hash: str) -> bool:
        """Migrate UID-based entry to CPLC."""
        if not self._data:
            return False
        tags = self._data.get("tags", {})

        uid_normalized = old_uid.upper().replace(" ", "")
        cplc_normalized = cplc_hash.upper()

        if uid_normalized not in tags:
            return False

        # Get existing entry
        old_entry = tags[uid_normalized]

        # Create new CPLC-keyed entry
        new_entry = dict(old_entry)
        new_entry["uid"] = uid_normalized
        new_entry["migrated_from_uid"] = True

        # Add new and remove old
        tags[cplc_normalized] = new_entry
        del tags[uid_normalized]

        return True

try:
    import keyring
except ImportError:
    keyring = None


WIDTH_HEIGHT = [800, 600]

APP_TITLE = "GlobalPlatform GUI"

"""
    [dict[str, bool]] known_keys:
        [bool] uid:str - if the UID uses a default key, true, else false
    [bool] cache_latest_release=False
    """
DEFAULT_CONFIG = {
    "cache_latest_release": False,
    "last_checked": {},
    "known_tags": {},
    "cache_timeout": "never",  # Cache timeout for secure storage unlock
    "window": {
        "height": WIDTH_HEIGHT[1],
        "width": WIDTH_HEIGHT[0],
    },
}

"""
    tags: 
        {
            "name": default is uid,
            "key": default is DEFAULT_KEY
        }
"""

DEFAULT_DATA = {"tags": {}}

DEFAULT_DATA_FILE = {
    "meta": {"version": 1, "encryption": None, "sale": None, "wrapped_key": None},
    "data": DEFAULT_DATA,
}

# Use app data directory for secure storage and config
DATA_FILE = get_default_storage_path()
CONFIG_FILE = get_default_config_path()

# Legacy paths for migration
LEGACY_DATA_FILE = "data.enc.json"
LEGACY_CONFIG_FILE = "config.json"

#
# Folder for caching .cap downloads
#
CAP_DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "gp_caps")
os.makedirs(CAP_DOWNLOAD_DIR, exist_ok=True)

#
# If you still need to skip certain .cap files, keep them here.
#
unsupported_apps = ["FIDO2.cap", "openjavacard-ndef-tiny.cap", "keycard.cap"]

# AID prefix groups - apps sharing a prefix are mutually exclusive
# When an installed AID starts with a group prefix, all available apps
# whose AIDs also start with that prefix will be filtered out
AID_PREFIX_GROUPS = [
    # FIDO2 / U2F family (A0000006472F0002 vs A0000006472F000101)
    "A0000006472F",
]

def get_plugin_instance(plugin):
    """
    Get a plugin instance.

    All plugins are now YAML-based and stored as adapter instances.
    This function is kept for API compatibility.
    """
    return plugin


def load_plugins():
    """
    Discover and load YAML plugins.

    Scans the /plugins folder for .yaml/.yml files with valid plugin schemas.

    Returns a dict plugin_map: { plugin_name: YamlPluginAdapter }.
    E.g. { "smartpgp": <YamlPluginAdapter>, "flexsecure-applets": <YamlPluginAdapter>, ... }

    Note: All plugins are loaded. Use get_enabled_plugins() to filter by disabled list.
    """
    plugin_map = {}

    try:
        from src.plugins.yaml.loader import YamlPluginLoader

        # Use resource_path for PyInstaller compatibility
        base_dir = resource_path(".")
        loader = YamlPluginLoader(base_dir)
        yaml_plugins = loader.discover()

        for plugin_name, adapter in yaml_plugins.items():
            plugin_map[plugin_name] = adapter
            print(f"Loaded plugin: {plugin_name}")

        # Report any loading errors
        for path, error in loader.get_errors():
            print(f"Error loading plugin {path}: {error}")

    except ImportError as e:
        print(f"Plugin system not available: {e}")
    except Exception as e:
        print(f"Error loading plugins: {e}")

    return plugin_map


# MessageQueue is now imported from src.views.widgets.status_bar


if os.name == "nt":
    width_height = [2 * x for x in WIDTH_HEIGHT]


class GPManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.nfc_thread = None
        self.secure_storage = None
        self.secure_storage_instance = SecureStorage(
            DATA_FILE, service_name="GlobalPlatformGUI"
        )

        self.secure_storage_dialog = None
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))

        self.layout = QVBoxLayout()
        self.central_widget = QWidget(self)  # Create the central widget
        self.central_widget.setLayout(
            self.layout
        )  # Set the layout on the central widget
        self.setCentralWidget(self.central_widget)

        # Status message queue at the top (animated conveyor)
        self.message_queue = MessageQueue(self)
        self.layout.addWidget(self.message_queue)
        self.message_queue.add_message("Checking for readers...")

        # Loading indicator (shown during async operations)
        self.loading_indicator = LoadingIndicator(self)
        self.layout.addWidget(self.loading_indicator)

        # Create the menu bar
        self.menu_bar = self.menuBar()

        file_menu = self.menu_bar.addMenu("File")

        create_plugin_action = QAction("Create Plugin...", self)
        create_plugin_action.triggered.connect(self.show_plugin_designer)
        file_menu.addAction(create_plugin_action)

        file_menu.addSeparator()

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        tag_menu = self.menu_bar.addMenu("Tags")
        set_tag_name_action = QAction("Set Name", self)
        set_tag_name_action.triggered.connect(self.set_tag_name)
        set_tag_key_action = QAction("Set Key", self)
        set_tag_key_action.triggered.connect(self.set_tag_key)
        change_tag_key_action = QAction("⚠️ Change Key ⚠️", self)
        change_tag_key_action.triggered.connect(self.change_tag_key)
        manage_tags_action = QAction("Manage Known Tags", self)
        manage_tags_action.triggered.connect(self.manage_tags)

        # Store action references for enabling/disabling
        self._set_tag_name_action = set_tag_name_action
        self._set_tag_key_action = set_tag_key_action
        self._change_tag_key_action = change_tag_key_action
        self._manage_tags_action = manage_tags_action

        tag_menu.addAction(set_tag_name_action)
        tag_menu.addAction(set_tag_key_action)
        tag_menu.addAction(change_tag_key_action)
        tag_menu.addSeparator()
        tag_menu.addAction(manage_tags_action)

        # Initialize actions as disabled - handle_tag_menu will enable appropriately
        set_tag_name_action.setEnabled(False)
        set_tag_key_action.setEnabled(False)
        change_tag_key_action.setEnabled(False)
        manage_tags_action.setEnabled(False)

        self.tag_menu = tag_menu

        # Readers menu
        self.readers_menu = self.menu_bar.addMenu("Readers")
        self._reader_action_group = QActionGroup(self)
        self._reader_action_group.setExclusive(True)
        self._reader_actions = []
        self._no_readers_action = QAction("No readers found", self)
        self._no_readers_action.setEnabled(False)
        self.readers_menu.addAction(self._no_readers_action)

        self.config = self.load_config()
        self.write_config()

        # Apply cache timeout from config to secure storage instance
        cache_timeout = self.config.get("cache_timeout", "never")
        self.secure_storage_instance.set_cache_timeout(cache_timeout)

        # Initialize debug logging from config
        from src.plugins.yaml import set_debug_enabled
        set_debug_enabled(self.config.get("show_debug", False))

        self.resize(self.config["window"]["width"], self.config["window"]["height"])
        self.write_config()
        self.key = None

        self.layout.addWidget(horizontal_rule())

        # Track available readers (selection managed via Readers menu)
        self._available_readers = []

        # Installed / Available lists
        self.installed_app_names = []
        self.installed_aids = {}  # Store raw AIDs for AID-based filtering
        self.installed_list = QListWidget()
        self.available_list = QListWidget()

        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel("Installed Apps"), 0, 0)
        grid_layout.addWidget(self.installed_list, 1, 0)
        grid_layout.addWidget(QLabel("Available Apps"), 0, 1)
        grid_layout.addWidget(self.available_list, 1, 1)

        # No static buttons - contextual buttons appear in details pane
        self._action_buttons_enabled = False
        self._selected_app_name = None
        self._selected_is_installed = False

        self.apps_grid_layout = grid_layout
        # Connect both lists to show details pane with contextual buttons
        self.installed_list.currentItemChanged.connect(
            lambda item: self._on_app_selected(item, is_installed=True)
        )
        self.available_list.currentItemChanged.connect(
            lambda item: self._on_app_selected(item, is_installed=False)
        )

        self.layout.addLayout(self.apps_grid_layout)

        # Progress bar for downloads
        self.download_bar = QProgressBar()
        self.download_bar.hide()
        self.layout.addWidget(self.download_bar)

        self.central_widget.setLayout(self.layout)

        self.nfc_thread = None

        # Load secure storage
        if os.path.exists(DATA_FILE):
            self._load_secure_storage_with_retry()

            if self.secure_storage:
                # Make sure all our tags in secure storage are in config
                updated_config = False
                for tag in self.secure_storage["tags"].keys():
                    if not self.config["known_tags"].get(tag):
                        self.config["known_tags"][tag] = (
                            self.secure_storage["tags"][tag]["key"] == DEFAULT_KEY
                        )
                        updated_config = True
                if updated_config:
                    self.write_config()
                # Enable "Manage Known Tags" action
                if hasattr(self, '_manage_tags_action'):
                    self._manage_tags_action.setEnabled(True)
        else:
            # You can opt out... But I'm gonna ask every time.
            self.prompt_setup()

        # Update menu state based on storage status
        self._update_storage_menu_state()

        #
        # Initialize CardController (MVC)
        #
        self._init_card_controller()

        #
        # 1) Load all plugins
        #
        self.plugin_map = load_plugins()
        if self.plugin_map:
            print("Loaded plugins:", list(self.plugin_map.keys()))
        else:
            print("No plugins found or repos folder missing.")

        #
        # 2) Build a combined {cap_name: (plugin_name, download_url)}
        #    from ALL plugins (needed for management of installed apps)
        #    Filtering for "available for install" happens in populate_available_list()
        #
        self.available_apps_info = {}  # {cap_name: (plugin_name, url)} - active provider
        self.cap_providers = {}  # {cap_name: [(plugin_name, url), ...]} - all providers
        self.app_descriptions = {}
        self.app_display_names = {}  # {cap_name: display_name} - friendly names from metadata
        self.storage = {}
        disabled_plugins = self._get_disabled_plugins()
        for plugin_name, plugin_cls_or_instance in self.plugin_map.items():
            # Handle both class (Python plugins) and instance (YAML plugins)
            if isinstance(plugin_cls_or_instance, type):
                plugin_instance = plugin_cls_or_instance()
            else:
                plugin_instance = plugin_cls_or_instance
            plugin_instance.load_storage()
            # Check if cache needs to be invalidated for YAML plugins with variants
            cache_stale = (
                not self.config["last_checked"].get(plugin_name, False)
                or self.config["last_checked"][plugin_name]["last"]
                <= time.time() - 24 * 60 * 60
            )

            # For YAML plugins with variants, check if cached caps match variants
            if not cache_stale and hasattr(plugin_instance, 'get_variants'):
                variants = plugin_instance.get_variants()
                if variants:
                    variant_filenames = {v['filename'] for v in variants}
                    cached_caps = set(self.config["last_checked"].get(plugin_name, {}).get("apps", {}).keys())
                    # Invalidate cache if it has caps not in variants
                    if cached_caps and not cached_caps.issubset(variant_filenames):
                        cache_stale = True

            if cache_stale:
                caps = plugin_instance.fetch_available_caps()
                if len(caps.keys()) > 0:
                    self.config["last_checked"][plugin_name] = {}
                    self.config["last_checked"][plugin_name]["apps"] = caps
                    self.config["last_checked"][plugin_name]["last"] = time.time()
                    self.config["last_checked"][plugin_name][
                        "release"
                    ] = plugin_instance.release

                    self.write_config()
                else:
                    self.message_queue.add_message(
                        "No apps returned. Check connection and/or url."
                    )
            else:
                caps = self.config["last_checked"][plugin_name]["apps"]

                if self.config["last_checked"][plugin_name].get("release", False):
                    plugin_instance.set_release(
                        self.config["last_checked"][plugin_name]["release"]
                    )

                if len(caps.keys()) == 0:  # Probably a failure in fetching.
                    caps = plugin_instance.fetch_available_caps()
                    if len(caps.keys()) == 0:
                        self.message_queue.add_message(
                            f"Unable to fetch apps for {plugin_name}."
                        )
                        return
                self.config["last_checked"][plugin_name]["apps"] = caps
                self.write_config()

                # For YAML plugins using cached data, set cap names for AID matching
                if hasattr(plugin_instance, 'set_cached_cap_names'):
                    plugin_instance.set_cached_cap_names(list(caps.keys()))

            for cap_n, url in caps.items():
                # Track all providers for this CAP
                if cap_n not in self.cap_providers:
                    self.cap_providers[cap_n] = []
                self.cap_providers[cap_n].append((plugin_name, url))

                # Check for conflict with existing provider
                if cap_n in self.available_apps_info:
                    existing_plugin, _ = self.available_apps_info[cap_n]
                    # Only warn if both plugins are enabled
                    if existing_plugin not in disabled_plugins and plugin_name not in disabled_plugins:
                        self.message_queue.add_message(
                            f"Plugin conflict: '{cap_n}' provided by both "
                            f"'{existing_plugin}' and '{plugin_name}'. "
                            f"Disable one in Settings > Plugins."
                        )
                    # Use the enabled plugin, or prefer YAML plugins (loaded last)
                    if existing_plugin in disabled_plugins:
                        self.available_apps_info[cap_n] = (plugin_name, url)
                    elif plugin_name not in disabled_plugins:
                        # Both enabled - YAML (loaded last) takes precedence
                        self.available_apps_info[cap_n] = (plugin_name, url)
                else:
                    self.available_apps_info[cap_n] = (plugin_name, url)

            descriptions = plugin_instance.get_descriptions()
            for cap_n, description_md in descriptions.items():
                self.app_descriptions[cap_n] = description_md

            # Get display names from metadata
            if hasattr(plugin_instance, 'get_display_names'):
                display_names = plugin_instance.get_display_names()
                for cap_n, display_name in display_names.items():
                    self.app_display_names[cap_n] = display_name

            # Merge for easy access to storage requirements
            self.storage = self.storage | plugin_instance.storage

        #
        # 3) Populate the "Available Apps" list
        #
        self.populate_available_list()

        #
        # 4) Start NFC handler
        #
        self.nfc_thread = NFCHandlerThread(self)
        self.nfc_thread.readers_updated_signal.connect(self.readers_updated)
        self.nfc_thread.card_present_signal.connect(self.update_card_presence)
        self.nfc_thread.status_update_signal.connect(self.process_nfc_status)
        self.nfc_thread.operation_complete_signal.connect(self.on_operation_complete)
        self.nfc_thread.installed_apps_updated_signal.connect(
            self.on_installed_apps_updated
        )
        self.nfc_thread.error_signal.connect(self.show_error_dialog)
        self.nfc_thread.title_bar_signal.connect(self.update_title_bar)
        self.nfc_thread.known_tags_update_signal.connect(self.update_known_tags)
        self.nfc_thread.key_config_update_signal.connect(self.update_key_config)

        self.nfc_thread.show_key_prompt_signal.connect(self.prompt_for_key)
        self.nfc_thread.get_key_signal.connect(self.get_key)
        self.nfc_thread.key_setter_signal.connect(self.nfc_thread.key_setter)
        self.nfc_thread.cplc_retrieved_signal.connect(self.on_cplc_retrieved)

        # Loading dialog for card operations
        self._loading_dialog = LoadingDialog(parent=self)

        # Track last operation for selection behavior
        # "detection", "install", "uninstall", or None
        self._last_operation = None
        self._pending_install_cap = None  # Cap name being installed

        # Key prompt cancellation flag - when True, all PCSC operations are halted
        # This prevents sending wrong keys to cards which could brick them
        self._key_prompt_cancelled = False

        # Initially disable action buttons
        self._update_action_buttons_state(False)
        self.current_plugin = None

        self.nfc_thread.start()

        if self.secure_storage:
            self.handle_tag_menu()

    def changeEvent(self, event):
        """
        This exists because I have messed up twice now, forgetting to
        close the app and doing gp/smart card stuff in another window
        -- scary!
        """
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                self.nfc_thread.resume()
            else:
                self.nfc_thread.pause()
                # No need to sleep - pause is non-blocking

        super().changeEvent(event)

    def _init_card_controller(self):
        """Initialize the CardController and subscribe to EventBus events."""
        # Create a storage service wrapper for the CardController
        # Note: We're using the existing secure_storage_instance for now
        # In the future, this can use StorageService directly
        storage_wrapper = _StorageServiceAdapter(self.secure_storage_instance, self.secure_storage)

        # Create the CardController
        self.card_controller = CardController(
            storage_service=storage_wrapper,
            config_service=None,  # Will be added when ConfigController is ready
        )

        # Get the EventBus singleton
        self._event_bus = EventBus.instance()

        # Subscribe to CardController events
        self._event_bus.key_prompt.connect(self._on_key_prompt_event)
        self._event_bus.key_validated.connect(self._on_key_validated_event)
        self._event_bus.card_state.connect(self._on_card_state_changed_event)
        self._event_bus.status_message.connect(self._on_status_message_event)
        self._event_bus.error.connect(self._on_error_event)

    def _on_key_prompt_event(self, event: KeyPromptEvent):
        """Handle KeyPromptEvent from CardController."""
        # Bridge to existing prompt_for_key method
        self.prompt_for_key(event.uid, "")

    def _on_key_validated_event(self, event: KeyValidatedEvent):
        """Handle KeyValidatedEvent from CardController."""
        if event.valid:
            self.handle_tag_menu()
        # Additional handling can be added here

    def _on_card_state_changed_event(self, event: CardStateChangedEvent):
        """Handle CardStateChangedEvent from CardController."""
        # Update UI based on new card state
        if event.state.is_authenticated:
            self._update_action_buttons_state(True)
        elif not event.state.is_connected:
            self._update_action_buttons_state(False)

    def _on_status_message_event(self, event: StatusMessageEvent):
        """Handle StatusMessageEvent from EventBus."""
        self.message_queue.add_message(event.message)

    def _on_error_event(self, event: ErrorEvent):
        """Handle ErrorEvent from EventBus."""
        if not event.recoverable:
            self.show_error_dialog(event.message)
        else:
            self.message_queue.add_message(f"Error: {event.message}")

    def handle_details_pane_back(self):
        """Remove the details pane and restore installed apps list."""
        # Clear selection state
        self._selected_app_name = None
        self._selected_is_installed = False

        # Clear visual selection in both lists
        self.installed_list.clearSelection()
        self.available_list.clearSelection()

        # Remove the details pane widgets
        for row in range(0, 3):
            item = self.apps_grid_layout.itemAtPosition(row, 0)
            if item:
                widget = item.widget()
                if widget:
                    self.apps_grid_layout.removeWidget(widget)
                    widget.setParent(None)

        # Restore the installed apps list
        self.apps_grid_layout.addWidget(QLabel("Installed Apps"), 0, 0)
        self.apps_grid_layout.addWidget(self.installed_list, 1, 0)
        self.installed_list.show()  # Ensure visible after being hidden
        # Row 2, col 0 stays empty - buttons are in details pane only

    def _on_app_selected(self, item, is_installed: bool):
        """Handle app selection from either installed or available list."""
        if item is None:
            return

        # Clear selection in the other list to avoid confusion
        if is_installed:
            self.available_list.clearSelection()
        else:
            self.installed_list.clearSelection()

        # Get cap_name from UserRole data (for available list) or text (for installed)
        app_name = item.data(Qt.UserRole) or item.text()
        # Strip version suffix if present (e.g., "App.cap (v1.0)" -> "App.cap")
        if " (v" in app_name:
            app_name = app_name.split(" (v")[0]

        self._selected_app_name = app_name
        self._selected_is_installed = is_installed

        # Show details pane with contextual buttons
        self._show_app_details(app_name, is_installed)

    def _show_app_details(self, app_name: str, is_installed: bool):
        """Show details pane with app info and contextual action buttons."""
        # Check if we have a description for this app
        description = self.app_descriptions.get(app_name, "")
        display_name = self.app_display_names.get(app_name, app_name)

        # Create content widget
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 8)  # Add bottom margin

        # Header: App name with version (H1 style)
        app_version = self._get_version_for_cap(app_name) if is_installed else None
        app_title = f"{display_name} (v{app_version})" if app_version else display_name
        app_name_label = ElidingLabel(app_title)
        # Use explicit QFont for reliable cross-platform sizing
        app_font = QFont()
        app_font.setPointSize(14)  # ~18px, using points for DPI independence
        app_font.setBold(True)
        app_name_label.setFont(app_font)
        app_name_label.setMinimumWidth(100)
        app_name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(app_name_label)

        # Header: Plugin name (subtitle style)
        plugin_info = self.available_apps_info.get(app_name)
        if plugin_info:
            plugin_name = plugin_info[0]
            plugin_name_label = QLabel(f"Plugin: {plugin_name}")
            # Use explicit QFont for reliable cross-platform sizing
            plugin_font = QFont()
            plugin_font.setPointSize(10)  # ~13px, using points for DPI independence
            plugin_name_label.setFont(plugin_font)
            plugin_name_label.setStyleSheet("color: #666;")
            plugin_name_label.setWordWrap(False)
            content_layout.addWidget(plugin_name_label)

        # Small spacing before description
        content_layout.addSpacing(8)

        # Markdown viewer for description
        if description:
            viewer = QTextBrowser()
            viewer.setOpenExternalLinks(True)
            viewer.setHtml(markdown.markdown(textwrap.dedent(description)))
            content_layout.addWidget(viewer)
        else:
            # No description - just add stretch
            content_layout.addStretch()

        # Button container - auto-sizes to fit buttons
        button_container = QWidget()
        button_container_layout = QVBoxLayout(button_container)
        button_container_layout.setContentsMargins(0, 8, 0, 8)

        # Action buttons row
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)

        # Main action button (Install or Uninstall)
        if is_installed:
            action_btn = QPushButton("Uninstall")
            action_btn.clicked.connect(self.uninstall_app)
        else:
            action_btn = QPushButton("Install")
            action_btn.clicked.connect(self.install_app)

        action_btn.setEnabled(self._action_buttons_enabled)
        self._current_action_btn = action_btn
        button_row.addWidget(action_btn)

        # Manage button (only if plugin has management UI)
        manage_btn = None
        if is_installed and self._plugin_has_management_ui(app_name):
            manage_btn = QPushButton("Manage")
            # Capture app_name by value using default argument to avoid closure bug
            manage_btn.clicked.connect(lambda checked=False, name=app_name: self._show_management_dialog(name))
            manage_btn.setEnabled(self._action_buttons_enabled)
            self._current_manage_btn = manage_btn
            button_row.addWidget(manage_btn)
        else:
            self._current_manage_btn = None

        button_row.addStretch()

        # Back button
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self.handle_details_pane_back)
        button_row.addWidget(back_btn)

        button_container_layout.addLayout(button_row)

        content_layout.addWidget(button_container)

        # Check if details pane is already showing
        is_showing_details = (
            self.apps_grid_layout.itemAtPosition(1, 0) and
            self.apps_grid_layout.itemAtPosition(1, 0).widget() != self.installed_list
        )

        # Remove existing widgets in column 0
        for row in range(0, 3):
            item = self.apps_grid_layout.itemAtPosition(row, 0)
            if item:
                widget = item.widget()
                if widget:
                    self.apps_grid_layout.removeWidget(widget)
                    # Don't orphan installed_list - we reuse it later
                    # Orphaning a visible widget makes it a top-level window
                    if widget is self.installed_list:
                        widget.hide()  # Hide but keep parented
                    else:
                        widget.setParent(None)

        # Add the new content
        self.apps_grid_layout.addWidget(content_widget, 0, 0, 3, 1)

    def _get_disabled_plugins(self) -> set:
        """Get set of disabled plugin names."""
        return set(self.config.get("disabled_plugins", []))

    def _plugin_has_management_ui(self, app_name: str) -> bool:
        """Check if the plugin for this app has management UI.

        Note: This allows managing apps even from disabled plugins,
        since the app is already installed on the card.
        """
        if app_name not in self.available_apps_info:
            return False

        plugin_name, _ = self.available_apps_info[app_name]
        if plugin_name not in self.plugin_map:
            return False

        plugin = get_plugin_instance(self.plugin_map[plugin_name])

        # Check for YAML plugin with management UI
        if hasattr(plugin, 'has_management_ui'):
            return plugin.has_management_ui()

        # Check for Python plugin with management actions
        if hasattr(plugin, 'get_management_actions'):
            actions = plugin.get_management_actions()
            return len(actions) > 0

        return False

    def _get_version_for_cap(self, cap_name: str) -> str | None:
        """Get the version string for an installed cap by looking up its AID."""
        if not hasattr(self, 'installed_aids') or not self.installed_aids:
            return None

        # Find the AID that maps to this cap_name
        for raw_aid, version in self.installed_aids.items():
            for pname, plugin_cls_or_instance in self.plugin_map.items():
                plugin = get_plugin_instance(plugin_cls_or_instance)
                if hasattr(plugin, 'get_cap_for_aid'):
                    cap = plugin.get_cap_for_aid(raw_aid)
                    if cap == cap_name:
                        return version
        return None

    def _show_management_dialog(self, app_name: str):
        """Show the management dialog for an installed app."""
        if app_name not in self.available_apps_info:
            self.message_queue.add_message(f"No plugin info for {app_name}")
            return

        plugin_name, _ = self.available_apps_info[app_name]
        if plugin_name not in self.plugin_map:
            self.message_queue.add_message(f"Plugin not found: {plugin_name}")
            return

        plugin = get_plugin_instance(self.plugin_map[plugin_name])

        # Find the actual installed AID for this cap
        installed_aid = None
        installed_apps = self.nfc_thread.get_installed_apps()
        if installed_apps:
            for raw_aid in installed_apps.keys():
                # Check if this AID maps to the cap we're managing
                if hasattr(plugin, 'get_cap_for_aid'):
                    cap = plugin.get_cap_for_aid(raw_aid)
                    if cap == app_name:
                        installed_aid = raw_aid.replace(" ", "").upper()
                        break

        # Try to create management dialog
        if hasattr(plugin, 'create_management_dialog'):
            try:
                dialog = plugin.create_management_dialog(
                    nfc_service=self.nfc_thread,
                    parent=self,
                    installed_aid=installed_aid
                )
                if dialog:
                    dialog.exec_()
                else:
                    self.message_queue.add_message("No management options available")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to open management: {e}")
        else:
            self.message_queue.add_message("Management not supported for this plugin")

    def _update_action_buttons_state(self, enabled: bool):
        """Update the enabled state of action buttons."""
        self._action_buttons_enabled = enabled
        # Check if buttons exist and haven't been deleted by Qt
        if hasattr(self, '_current_action_btn') and self._current_action_btn:
            if not sip.isdeleted(self._current_action_btn):
                self._current_action_btn.setEnabled(enabled)
        if hasattr(self, '_current_manage_btn') and self._current_manage_btn:
            if not sip.isdeleted(self._current_manage_btn):
                self._current_manage_btn.setEnabled(enabled)

    def handle_tag_menu(self):
        # Actions requiring a tag present (card connected and authenticated with key)
        tag_present = bool(self.nfc_thread.key and self.secure_storage)

        if hasattr(self, '_set_tag_name_action'):
            self._set_tag_name_action.setEnabled(tag_present)
        if hasattr(self, '_set_tag_key_action'):
            self._set_tag_key_action.setEnabled(tag_present)
        if hasattr(self, '_change_tag_key_action'):
            self._change_tag_key_action.setEnabled(tag_present)

        # "Manage Known Tags" is available when secure storage exists
        # (doesn't require a card to be connected)
        if hasattr(self, '_manage_tags_action'):
            self._manage_tags_action.setEnabled(bool(self.secure_storage))

    def update_plugin_releases(self):
        """Start background fetch of plugin releases (non-blocking)."""
        self.loading_indicator.start("Fetching plugin releases...")

        # Create and start background thread
        self._plugin_fetch_thread = PluginFetchThread(self.plugin_map, self)
        self._plugin_fetch_thread.plugin_fetched.connect(self._on_plugin_fetched)
        self._plugin_fetch_thread.all_complete.connect(self._on_all_plugins_fetched)
        self._plugin_fetch_thread.error.connect(self._on_plugin_fetch_error)
        self._plugin_fetch_thread.start()

    def _on_plugin_fetched(self, plugin_name: str, caps: dict):
        """Handle a single plugin's fetch completion."""
        if len(caps.keys()) > 0:
            self.config["last_checked"][plugin_name] = {}
            self.config["last_checked"][plugin_name]["apps"] = caps
            self.config["last_checked"][plugin_name]["last"] = time.time()
            self.config["last_checked"][plugin_name]["release"] = list(
                caps.values()
            )[0].split("/")[-2]

            # Update the available list (track all providers)
            disabled_plugins = self._get_disabled_plugins()
            for cap_n, url in caps.items():
                # Track provider
                if cap_n not in self.cap_providers:
                    self.cap_providers[cap_n] = []
                # Update existing entry or add new
                provider_entry = (plugin_name, url)
                existing = [(p, u) for p, u in self.cap_providers[cap_n] if p == plugin_name]
                if existing:
                    # Update URL for existing provider
                    self.cap_providers[cap_n] = [
                        (p, url if p == plugin_name else u)
                        for p, u in self.cap_providers[cap_n]
                    ]
                else:
                    self.cap_providers[cap_n].append(provider_entry)

                # Update active provider if this one is enabled
                if plugin_name not in disabled_plugins:
                    self.available_apps_info[cap_n] = (plugin_name, url)

            # Update descriptions and display names
            plugin_instance = get_plugin_instance(self.plugin_map.get(plugin_name))
            if plugin_instance:
                descriptions = plugin_instance.get_descriptions()
                for cap_n, description_md in descriptions.items():
                    self.app_descriptions[cap_n] = description_md

                # Update display names
                if hasattr(plugin_instance, 'get_display_names'):
                    display_names = plugin_instance.get_display_names()
                    for cap_n, display_name in display_names.items():
                        self.app_display_names[cap_n] = display_name

    def _on_all_plugins_fetched(self, results: dict):
        """Handle completion of all plugin fetches."""
        self.loading_indicator.stop()
        updated = any(len(caps) > 0 for caps in results.values())

        if updated:
            self.write_config()  # save state
            self.populate_available_list()  # Push the update
            self.message_queue.add_message("Updated plugin releases.")
        else:
            self.message_queue.add_message("No plugin releases found.")

    def _on_plugin_fetch_error(self, plugin_name: str, error: str):
        """Handle plugin fetch error."""
        self.message_queue.add_message(f"Error fetching {plugin_name}: {error}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F1:
            self.on_f1_pressed(event)
        elif event.key() == Qt.Key_F4:
            self.on_f4_pressed(event)

    def on_f1_pressed(self, event):
        """Show help dialog."""
        help_text = (
            "GlobalPlatform GUI - Smart Card Manager\n\n"
            "Keyboard Shortcuts:\n"
            "  F1 - Show this help\n"
            "  F4 - Force refresh plugins\n\n"
            "For more info, visit the project repository."
        )
        QMessageBox.information(self, "Help", help_text)

    def on_f4_pressed(self, event):
        """
        Force checking plugin resources for updates.
        Mostly, I use this in testing...
        """
        self.message_queue.add_message("Update forced...")
        self.installed_list.clear()
        self.installed_app_names.clear()
        self.available_list.clear()
        self.populate_available_list()
        self.update_plugin_releases()

        self.message_queue.add_message("Checking reader for tags...")
        if self.nfc_thread.isRunning():

            self.nfc_thread.current_uid = None
            self.nfc_thread.key = None
            self.nfc_thread.card_detected = False
            self.update_title_bar(self.nfc_thread.make_title_bar_string())
        else:
            if self.nfc_thread:
                self.nfc_thread.start()
        self.on_operation_complete(True, "Forced update completed.")

    def show_plugin_designer(self):
        """Show the YAML plugin designer wizard."""
        wizard = PluginDesignerWizard(self)
        wizard.plugin_created.connect(self.on_plugin_created)
        wizard.exec_()

    def on_plugin_created(self, yaml_content: str, save_path: str):
        """Handle a new plugin being created."""
        if save_path:
            self.message_queue.add_message(f"Plugin created: {save_path}")
            # Reload plugin map first to pick up the new plugin
            self.plugin_map = load_plugins()
            if self.plugin_map:
                print("Reloaded plugins:", list(self.plugin_map.keys()))
            # Then fetch releases for all plugins including the new one
            self.update_plugin_releases()
        else:
            self.message_queue.add_message("Plugin YAML generated (not saved)")

    def show_settings(self):
        """Show the settings dialog."""
        from src.views.dialogs.settings_dialog import SettingsDialog

        # Gather storage info for the settings dialog
        storage_info = self._get_storage_info()

        dialog = SettingsDialog(self.plugin_map, self.config, storage_info, self)
        dialog.refresh_plugins_requested.connect(self._refresh_plugins_after_settings)
        dialog.reset_storage_requested.connect(self._on_settings_reset_storage)
        dialog.cache_timeout_changed.connect(self._on_cache_timeout_changed)

        if dialog.exec_() == dialog.Accepted:
            # Update config with settings
            self.config = dialog.get_config()
            self.write_config()

            if dialog.needs_restart():
                QMessageBox.information(
                    self,
                    "Restart Required",
                    "Plugin changes will take effect after restarting the application."
                )

    def _get_storage_info(self) -> dict:
        """Get storage information for display in settings."""
        info = {
            "file_path": DATA_FILE,
            "is_loaded": self.secure_storage is not None,
            "method": "Unknown",
            "tag_count": 0,
            "cache_timeout": self.config.get("cache_timeout", "never"),
        }

        if self.secure_storage_instance and self.secure_storage_instance.meta:
            meta = self.secure_storage_instance.meta
            if "keywrapping" in meta and "method" in meta["keywrapping"]:
                info["method"] = meta["keywrapping"]["method"]

        if self.secure_storage:
            tags = self.secure_storage.get("tags", {})
            info["tag_count"] = len(tags)

        return info

    def _on_settings_reset_storage(self):
        """Handle reset storage request from settings dialog."""
        self._backup_and_create_new_storage()
        self._update_storage_menu_state()

    def _on_cache_timeout_changed(self, timeout_key: str):
        """Handle cache timeout change from settings dialog."""
        self.config["cache_timeout"] = timeout_key
        if self.secure_storage_instance:
            self.secure_storage_instance.set_cache_timeout(timeout_key)
        self.write_config()

    def _refresh_plugins_after_settings(self):
        """Reload plugins after settings changes (add/edit/delete)."""
        # Reload plugin map
        self.plugin_map = load_plugins()
        if self.plugin_map:
            print("Reloaded plugins:", list(self.plugin_map.keys()))
        # Refresh available apps info and UI lists
        self.update_plugin_releases()

    def _is_aid_installed(self, cap_name: str, plugin_name: str) -> bool:
        """Check if an available app's AID matches any installed AID.

        Handles:
        1. Same-AID matching (exact or prefix via get_cap_for_aid)
        2. AID prefix group matching (related apps like fido2/u2f)

        Args:
            cap_name: The CAP filename to check
            plugin_name: The plugin that provides this CAP

        Returns:
            True if this app's AID is already installed (should be filtered)
        """
        if not self.installed_aids:
            return False

        plugin_cls = self.plugin_map.get(plugin_name)
        if not plugin_cls:
            return False

        plugin = get_plugin_instance(plugin_cls)
        if not plugin:
            return False

        # Get this available app's AIDs for prefix group matching
        app_aids = []
        if hasattr(plugin, 'get_aid_list'):
            app_aids = [a.upper().replace(" ", "") for a in plugin.get_aid_list()]

        for installed_aid in self.installed_aids.keys():
            norm_installed = installed_aid.upper().replace(" ", "")

            # Check 1: Same-AID matching via plugin's get_cap_for_aid()
            # This handles exact match, variant match, and dynamic AID prefix
            if hasattr(plugin, 'get_cap_for_aid'):
                matched_cap = plugin.get_cap_for_aid(installed_aid)
                if matched_cap == cap_name:
                    return True

            # Check 2: AID prefix group matching
            # If both installed and available AIDs share a prefix group, they conflict
            for prefix in AID_PREFIX_GROUPS:
                if norm_installed.startswith(prefix):
                    for app_aid in app_aids:
                        if app_aid.startswith(prefix):
                            return True

        return False

    def populate_available_list(self):
        # Block signals during list manipulation to prevent spurious selection events
        self.available_list.blockSignals(True)
        self.available_list.clear()
        disabled_plugins = self._get_disabled_plugins()

        for cap_name, (plugin_name, url) in self.available_apps_info.items():
            # Check if current provider is disabled
            if plugin_name in disabled_plugins:
                # Look for an enabled alternative provider
                alternative_found = False
                if cap_name in self.cap_providers:
                    for alt_plugin, alt_url in self.cap_providers[cap_name]:
                        if alt_plugin not in disabled_plugins:
                            # Update to use enabled provider
                            self.available_apps_info[cap_name] = (alt_plugin, alt_url)
                            plugin_name = alt_plugin
                            alternative_found = True
                            break
                if not alternative_found:
                    continue  # All providers disabled, skip this CAP

            if cap_name in unsupported_apps:
                continue
            if cap_name in self.installed_app_names:
                continue
            # AID-based filtering: filter apps whose AID matches installed AIDs
            if self._is_aid_installed(cap_name, plugin_name):
                continue
            # Use display name from metadata, fallback to cap filename
            display_name = self.app_display_names.get(cap_name, cap_name)
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, cap_name)  # Store actual cap_name for lookups
            self.available_list.addItem(item)
        self.available_list.blockSignals(False)
        self.available_list.update()

    def _get_short_reader_name(self, full_name: str) -> str:
        """Extract a short, readable name from the full reader name.

        Reader names often look like:
        - "ACS ACR122U PICC Interface 0"
        - "Identiv uTrust 3700 F CL Reader [CL Interface] 0"

        This extracts just the meaningful part before brackets/interface info.
        """
        import re

        # Remove trailing number (reader index)
        name = full_name.rstrip('0123456789 ')

        # Remove bracketed suffix if present
        if '[' in name:
            name = name[:name.index('[')].strip()

        # Remove common suffixes
        for suffix in ['PICC Interface', 'CL Interface', 'Interface']:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()

        # Remove "Reader" (case insensitive) and its leading whitespace
        name = re.sub(r'\s*reader\b', '', name, flags=re.IGNORECASE).strip()

        return name or full_name  # Fallback to full name if nothing left

    def readers_updated(self, readers_list):
        """Handle reader list updates."""
        readers_list = readers_list or []
        previous_readers = set(self._available_readers)
        current_readers = set(readers_list)

        # Determine what changed
        added_readers = current_readers - previous_readers
        removed_readers = previous_readers - current_readers

        # Update stored list
        self._available_readers = readers_list

        # Update Readers menu
        self._update_readers_menu(readers_list)

        if not readers_list:
            self.key = None
            self.nfc_thread.selected_reader_name = None
            self.message_queue.add_message("No readers found.")
            self._update_action_buttons_state(False)
            return

        # Check if the selected reader is affected
        selected_reader = self.nfc_thread.selected_reader_name
        selected_reader_removed = selected_reader in removed_readers

        # Show specific connect/disconnect messages
        for reader in added_readers:
            is_selected = (reader == selected_reader or
                          (selected_reader_removed and reader == readers_list[0]))
            short_name = self._get_short_reader_name(reader)
            self.message_queue.add_message(
                f"Reader {short_name} is now connected.",
                low_priority=not is_selected
            )

        for reader in removed_readers:
            is_selected = reader == selected_reader
            short_name = self._get_short_reader_name(reader)
            self.message_queue.add_message(
                f"Reader {short_name} is now disconnected.",
                low_priority=not is_selected
            )

        # Auto-select new reader if selected one was removed
        if selected_reader_removed:
            self.nfc_thread.selected_reader_name = readers_list[0]
            self._update_reader_menu_selection(readers_list[0])

        # Show initial card state if no card is present
        # (NFC thread only emits card_present_signal on state changes, not initial state)
        if not self.nfc_thread.card_detected:
            self.message_queue.add_message("No card present.")

    def _update_readers_menu(self, readers_list):
        """Update the Readers menu with current reader list."""
        # Clear existing reader actions
        for action in self._reader_actions:
            self._reader_action_group.removeAction(action)
            self.readers_menu.removeAction(action)
        self._reader_actions.clear()

        if not readers_list:
            if self._no_readers_action not in [a for a in self.readers_menu.actions()]:
                self.readers_menu.addAction(self._no_readers_action)
            return

        # Remove "No readers found" placeholder if present
        self.readers_menu.removeAction(self._no_readers_action)

        # Add reader actions
        selected_reader = self.nfc_thread.selected_reader_name
        for reader_name in readers_list:
            action = QAction(reader_name, self)
            action.setCheckable(True)
            action.setChecked(reader_name == selected_reader)
            action.triggered.connect(lambda checked, name=reader_name: self._on_reader_menu_select(name))
            self._reader_action_group.addAction(action)
            self.readers_menu.addAction(action)
            self._reader_actions.append(action)

    def _on_reader_menu_select(self, reader_name):
        """Handle reader selection from menu."""
        if self.nfc_thread.selected_reader_name == reader_name:
            return  # No change

        self.nfc_thread.selected_reader_name = reader_name
        self._update_reader_menu_selection(reader_name)

        # Trigger card re-detection on the new reader
        # Reset card state so NFC thread will re-check presence
        self.nfc_thread.card_detected = False
        self.nfc_thread.valid_card_detected = False
        self.nfc_thread.current_uid = None
        # Signal the NFC thread to reset its local card_present tracking
        # This allows it to properly detect a card already on the new reader
        self.nfc_thread.signal_reader_changed()

    def _update_reader_menu_selection(self, reader_name):
        """Update checkmark in Readers menu to match selection."""
        for action in self._reader_actions:
            action.setChecked(action.text() == reader_name)

    def update_card_presence(self, present):
        # CRITICAL: If key prompt was cancelled, do NOT process card presence
        # This prevents any PCSC operations or storage writes after cancel
        if self._key_prompt_cancelled:
            return

        if present:
            # Show loading dialog when card is first detected
            # Use 10s timeout - detection operations typically complete in seconds
            if not self._loading_dialog.is_loading():
                # Track as detection operation for selection behavior
                self._last_operation = "detection"
                self._pending_install_cap = None
                self._loading_dialog.show_loading(
                    timeout=10,
                    on_timeout=self._on_loading_timeout
                )

            if self.nfc_thread.valid_card_detected:
                # Note: "Compatible card present." is emitted by NFC thread before key retrieval
                uid = self.nfc_thread.current_uid

                # Only store if we have a valid card ID (not placeholder)
                # AND we have a valid key (not None - user provided a key)
                if (
                    self.secure_storage
                    and self._is_valid_storage_id(uid)
                    and not self.secure_storage["tags"].get(uid)
                    and self.nfc_thread.key is not None  # CRITICAL: Only store if key is set
                ):
                    self.secure_storage["tags"][uid] = {
                        "name": uid,
                        "key": self.nfc_thread.key,
                    }

                if self.nfc_thread.key is not None:
                    if (
                        self.secure_storage
                        and self._is_valid_storage_id(uid)
                        and self.secure_storage["tags"].get(uid)
                        and not self.secure_storage["tags"][uid]["key"]
                    ):
                        self.secure_storage["tags"][uid]["key"] = self.nfc_thread.key

                    self._update_action_buttons_state(True)
                    # Note: NFC thread will emit installed_apps_updated_signal
                    # after key_setter completes - don't block main thread here
            else:
                # Card is incompatible - hide loading dialog
                # Note: "Unsupported card present." is emitted by NFC thread
                self._loading_dialog.hide_loading()
                if self.nfc_thread.current_uid is not None:
                    self._update_action_buttons_state(False)
        else:
            # Card removed - hide loading dialog and clear cancellation flag
            self._loading_dialog.hide_loading()
            self._key_prompt_cancelled = False  # Reset flag when card is removed
            self._update_action_buttons_state(False)
            self.message_queue.add_message("No card present.")

    def _on_loading_timeout(self):
        """Handle loading dialog timeout."""
        self.show_error_dialog(
            "Operation timed out. Please check that your card reader is working properly."
        )

    def process_nfc_status(self, status):
        self.message_queue.add_message(status)

    #
    #  Download or use cached file
    #
    def fetch_file(self, cap_name, on_complete, params=None):
        """
        Check if we've already downloaded the .cap to CAP_DOWNLOAD_DIR.
        If it doesn't exist locally, download it via FileHandlerThread.
        Then call on_complete(file_path) when ready.
        """
        local_path = os.path.join(CAP_DOWNLOAD_DIR, cap_name)
        if os.path.exists(local_path):
            self.message_queue.add_message(
                f"Using cached: {local_path.split(os.path.sep)[-1]}"
            )
            on_complete(local_path)
            return

        if cap_name not in self.available_apps_info:
            self.message_queue.add_message(
                f"No known plugin or download URL for {cap_name}"
            )
            return

        plugin_name, dl_url = self.available_apps_info[cap_name]

        # Get extract_pattern from plugin if available (for ZIP sources)
        extract_pattern = None
        if plugin_name in self.plugin_map:
            plugin = get_plugin_instance(self.plugin_map[plugin_name])
            if hasattr(plugin, 'get_extract_pattern'):
                extract_pattern = plugin.get_extract_pattern()

        self.downloader = FileHandlerThread(
            cap_name, dl_url, output_dir=CAP_DOWNLOAD_DIR,
            extract_pattern=extract_pattern
        )

        self.downloader.download_progress.connect(self.on_download_progress)
        self.downloader.download_complete.connect(
            lambda file_path: on_complete(file_path, params)
        )
        self.downloader.download_error.connect(self.on_download_error)

        self.download_bar.setRange(0, 100)
        self.download_bar.setValue(0)
        self.download_bar.show()

        self._update_action_buttons_state(False)
        self.downloader.start()

    def on_download_progress(self, pct):
        self.download_bar.setValue(pct)

    def on_download_error(self, err_msg):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self._update_action_buttons_state(True)
        self.show_error_dialog(err_msg)

    #
    #  Install Flow
    #
    def install_app(self):
        selected = self.available_list.selectedItems()
        if not selected:
            return

        # Get cap_name from UserRole data (or text() as fallback)
        cap_name = selected[0].data(Qt.UserRole) or selected[0].text()
        display_name = self.app_display_names.get(cap_name, cap_name)

        # Track install operation for selection behavior
        self._last_operation = "install"
        self._pending_install_cap = cap_name

        self.message_queue.add_message(f"Installing: {display_name}")

        # Mutual exclusivity check (also handled by AppletController.validate_install)
        if "U2F" in cap_name and "FIDO2.cap" in self.installed_app_names:
            self.show_error_dialog("FIDO2 falls back to U2F--you do not need both.")
            return

        # Do we have enough storage?
        reqs = self.storage.get(cap_name)
        if (
            reqs is not None
            and self.nfc_thread.storage["persistent"] not in [-1, "-1"]
            and self.nfc_thread.storage["transient"] not in [-1, "-1"]
        ):  # None means we don't have any data for the app
            error_message = "Insufficient Storage\n"
            default_length = len(error_message)

            if self.nfc_thread.storage["persistent"] < reqs["persistent"]:
                error_message += f"\tPersistent Needed: {abs(self.nfc_thread.storage['persistent'] - reqs['persistent'])} bytes"
            if self.nfc_thread.storage["transient"] < reqs["transient"]:
                error_message += f"\tTransient Needed: {abs(self.nfc_thread.storage['transient'] - reqs['transient'])} bytes"
            if len(error_message) > default_length:
                self.show_error_dialog(error_message)
                return

        # Is the details pane open?
        if (
            not self.apps_grid_layout.itemAtPosition(1, 1).widget()
            == self.installed_list
        ):
            self.handle_details_pane_back()  # close it if so

        # See which plugin is responsible for this .cap
        if cap_name not in self.available_apps_info:
            self.message_queue.add_message(f"No plugin or URL for {cap_name}")
            return

        plugin_name, _ = self.available_apps_info[cap_name]
        if plugin_name in self.plugin_map:
            plugin = get_plugin_instance(self.plugin_map[plugin_name])
            plugin.set_cap_name(cap_name)

            dlg = plugin.create_dialog(self)
            if dlg and dlg.exec_() == dlg.Accepted:
                self.current_plugin = plugin
                result_data = plugin.get_result()
                print("Plugin result:", result_data)

                # Run pre_install hook after dialog is accepted (with field values)
                try:
                    plugin.pre_install(nfc_thread=self.nfc_thread)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Pre-install error: {e}")
                    return

                self.fetch_file(
                    cap_name, self.on_install_download_complete, params=result_data
                )
            elif dlg:
                # user canceled
                return
            else:
                # no dialog => simple flow
                self.current_plugin = plugin

                # Run pre_install hook for plugins without dialog
                try:
                    plugin.pre_install(nfc_thread=self.nfc_thread)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Pre-install error: {e}")
                    return

                self.fetch_file(cap_name, self.on_install_download_complete)
        else:
            # No plugin found => but we handle gracefully
            self.current_plugin = None
            self.fetch_file(cap_name, self.on_install_download_complete)

    def on_install_download_complete(self, file_path, params=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        # Show loading dialog for install operation
        self._loading_dialog.show_loading(
            timeout=60,
            on_timeout=self._on_loading_timeout
        )
        self.nfc_thread.install_app(file_path, params)

    #
    #  Uninstall Flow
    #
    def uninstall_app(self):
        selected = self.installed_list.selectedItems()
        if not selected:
            return

        # Track uninstall operation for selection behavior
        self._last_operation = "uninstall"
        self._pending_install_cap = None

        item = selected[0]
        display_text = item.text()

        # Strip version suffix if present (e.g., "App.cap (v1.0)" -> "App.cap")
        if " (v" in display_text:
            display_text = display_text.split(" (v")[0]

        # Get the CAP name from UserRole data (stored during list population)
        # This is more reliable than parsing the display text
        cap_name = item.data(Qt.UserRole)

        # If the entry indicates an unknown app (i.e. no plugin info), fallback to uninstall by AID.
        # Format: "Unknown: <aid>" or "Unknown from <plugin>: <aid>"
        if "Unknown" in display_text:
            # Extract AID - it's always after the last colon followed by space
            if ": " in display_text:
                raw_aid = display_text.split(": ")[-1].strip()
                self.message_queue.add_message(f"Attempting to uninstall by AID: {raw_aid}")
                # Show loading dialog for uninstall operation
                self._loading_dialog.show_loading(
                    timeout=60,
                    on_timeout=self._on_loading_timeout
                )
                return self.nfc_thread.uninstall_app(raw_aid, force=True)

        # No CAP name stored means we can't proceed with normal uninstall
        if not cap_name:
            self.message_queue.add_message(f"No CAP info available for {display_text}.")
            return

        # Look up available info for the selected cap.
        if cap_name not in self.available_apps_info:
            self.message_queue.add_message(f"No available info for {cap_name}.")
            return

        plugin_name, _ = self.available_apps_info[cap_name]
        if plugin_name in self.plugin_map:
            plugin = get_plugin_instance(self.plugin_map[plugin_name])
            plugin.set_cap_name(cap_name)
            try:
                plugin.pre_uninstall()  # Use pre_install (or pre_uninstall, if defined) for checks.
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Pre-uninstall error: {e}")
                return

            self.current_plugin = plugin
            # Fetch (or use cached) the .cap file before uninstalling.
            self.fetch_file(cap_name, self.on_uninstall_download_complete)
        else:
            self.show_error_dialog(f"No plugin found for {cap_name}")

    def on_uninstall_download_complete(self, file_path, params=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.message_queue.add_message(
            f"Uninstalling with {file_path.split(os.path.sep)[-1]}"
        )

        # Show loading dialog for uninstall operation
        self._loading_dialog.show_loading(
            timeout=60,
            on_timeout=self._on_loading_timeout
        )

        if self.current_plugin:
            # Ask the plugin for its fallback AID list for the selected cap.
            aids = (
                self.current_plugin.get_aid_list()
                if hasattr(self.current_plugin, "get_aid_list")
                else []
            )
            fallback_aid = aids[0] if aids else None
            self.nfc_thread.uninstall_app_by_cap(file_path, fallback_aid=fallback_aid)
        else:
            self.nfc_thread.uninstall_app_by_cap(file_path)

    #
    #  Operation Complete
    #
    def on_operation_complete(self, success, message=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        if self.nfc_thread.key is not None:
            self._update_action_buttons_state(True)

        if message is None:
            self.message_queue.add_message("Ready.")

        if success and self.current_plugin:
            try:
                self.current_plugin.post_install()
            except Exception as e:
                self.show_error_dialog(f"Post-install: {e}")
                # self.message_queue.add_message(f"Post-install error: {e}")
        elif not success:
            # This is likely handled already
            print(f"Op Complete Err: {message}")

        self.current_plugin = None

    #
    #  Displaying Installed Apps
    #
    def on_installed_apps_updated(self, installed_aids):
        """
        installed_aids is a dict { AID_uppercase: version_string_or_None }.
        We must iterate installed_aids.keys() or items().
        """
        # Hide loading dialog - card detection/install complete
        self._loading_dialog.hide_loading()

        self.handle_tag_menu()

        # Hide details pane and restore installed apps list view
        # This ensures the UI returns to the list after install/uninstall
        self.handle_details_pane_back()

        # Block signals during list manipulation to prevent spurious selection events
        self.installed_list.blockSignals(True)
        self.installed_list.clear()
        self.installed_app_names = []
        self.installed_aids = dict(installed_aids)  # Store for AID-based filtering

        for raw_aid in installed_aids.keys():
            # e.g. 'A000000308000010000100'
            version = installed_aids[raw_aid]

            norm = raw_aid.replace(" ", "").upper()
            matched_plugin_name = None
            matched_cap = None

            for pname, plugin_cls_or_instance in self.plugin_map.items():
                tmp = get_plugin_instance(plugin_cls_or_instance)
                if hasattr(tmp, "get_cap_for_aid"):
                    cap = tmp.get_cap_for_aid(raw_aid)
                    if cap:
                        matched_plugin_name = pname
                        matched_cap = cap
                        break
                elif hasattr(tmp, "get_aid_list"):
                    # fallback approach
                    for pa in tmp.get_aid_list():
                        if pa.upper().replace(" ", "") == norm:
                            matched_plugin_name = pname
                            break
                    if matched_plugin_name:
                        break

            # Display either the display name or "Unknown"
            if matched_cap:
                self.installed_app_names.append(matched_cap)
                display_name = self.app_display_names.get(matched_cap, matched_cap)
                display_text = display_name
            elif matched_plugin_name:
                display_text = f"Unknown from {matched_plugin_name}: {raw_aid}"
                matched_cap = None  # Ensure no cap stored for unknown apps
            else:
                display_text = f"Unknown: {raw_aid}"
                matched_cap = None

            # Show version if available
            if version:
                display_text += f" (v{version})"

            item = QListWidgetItem(display_text)
            if matched_cap:
                item.setData(Qt.UserRole, matched_cap)  # Store cap_name for lookups
            self.installed_list.addItem(item)
        self.installed_list.blockSignals(False)
        self.populate_available_list()

        # Handle selection based on operation type
        if self._last_operation == "install" and self._pending_install_cap:
            # On successful install: select the newly installed app and show details
            # Block signals to prevent double-triggering, then manually show details
            self.installed_list.blockSignals(True)
            for i in range(self.installed_list.count()):
                item = self.installed_list.item(i)
                if item.data(Qt.UserRole) == self._pending_install_cap:
                    self.installed_list.setCurrentItem(item)
                    # Manually trigger the details pane since signals are blocked
                    self._on_app_selected(item, is_installed=True)
                    break
            self.installed_list.blockSignals(False)
            # Clear available list selection
            self.available_list.clearSelection()
        elif self._last_operation == "uninstall":
            # On uninstall: clear all selections
            self.installed_list.clearSelection()
            self.available_list.clearSelection()
        else:
            # On detection or unknown: clear all selections
            self.installed_list.clearSelection()
            self.available_list.clearSelection()

        # Reset operation tracking
        self._last_operation = None
        self._pending_install_cap = None

        self.on_operation_complete(True)

    #
    #  Utility
    #
    def closeEvent(self, event):
        self.write_config()
        if self.secure_storage:
            try:
                self.write_secure_storage()
            except Exception as e:
                self.show_error_dialog(f"Secure storage not updated: {e}\nRetrying...")
                time.sleep(0.5)
                self.write_secure_storage()

        self.nfc_thread.stop()
        self.nfc_thread.wait()

        event.accept()

    def show_error_dialog(self, message: str):
        # Hide loading dialog if visible
        self._loading_dialog.hide_loading()

        # Was there a bad touch?
        if "Failed to open secure channel" in message:
            # Yup
            uid = self.nfc_thread.current_uid
            self.nfc_thread.key = None

            # Only update storage if we have a valid card ID (not placeholder)
            if self._is_valid_storage_id(uid):
                # Make sure we tell it we don't know the key in the config
                self.config["known_tags"][uid] = False
                self.write_config()
                if self.secure_storage:
                    if self.secure_storage["tags"].get(uid):
                        # Remove the naughty key
                        self.secure_storage["tags"][uid]["key"] = None

            message = "Bad touch! Invalid key! Further attempts without a successful auth will brick the device!"
            QMessageBox.critical(self, "Error", message, QMessageBox.Ok)
            self.prompt_for_key(uid, "")
        else:
            QMessageBox.critical(self, "Error", message, QMessageBox.Ok)

    def get_key(self, card_id):
        """
        Get the key for the user's smart card.
        - Have we seen the tag before?
        - If so, did it have a default key?

        Note: card_id may be None or "__CONTACT_CARD__" for contact cards
        on initial detection. In that case, we prompt for key and store
        it after CPLC retrieval.
        """
        # Clear cancellation flag at start of new detection
        self._key_prompt_cancelled = False

        # Show loading dialog immediately when card is detected
        if not self._loading_dialog.is_loading():
            self._last_operation = "detection"
            self._pending_install_cap = None
            self._loading_dialog.show_loading(
                timeout=10,
                on_timeout=self._on_loading_timeout
            )

        key = None

        # For contact cards without initial ID, still prompt for key
        # __CONTACT_CARD__ is a placeholder for contact interfaces
        is_contact_placeholder = card_id is None or card_id == "__CONTACT_CARD__"
        if is_contact_placeholder:
            res = self.prompt_for_key(None)
            if not res:
                # User cancelled - set flag to halt all PCSC operations
                self._key_prompt_cancelled = True
                self._loading_dialog.hide_loading()
                self.message_queue.add_message("Key entry cancelled.")
                return
            key = res
        else:
            # Normal flow - try to find stored key
            if self.secure_storage is not None:
                if self.secure_storage["tags"].get(card_id):
                    key = self.secure_storage["tags"][card_id]["key"]
            if key is None:
                is_default_key = self.config["known_tags"].get(card_id, None)
                if is_default_key:
                    key = DEFAULT_KEY

            if key is None:
                res = self.prompt_for_key(card_id)

                if not res:
                    # User cancelled - set flag to halt all PCSC operations
                    self._key_prompt_cancelled = True
                    self._loading_dialog.hide_loading()
                    self.message_queue.add_message("Key entry cancelled.")
                    return

                key = res

        self.nfc_thread.key_setter_signal.emit(key)
        self.nfc_thread.status_update_signal.emit("Key set.")

    def prompt_for_key(self, uid: str, existing_key: str = None):
        """
        Prompts the user to enter their smart card's key.

        Note: uid may be None or "__CONTACT_CARD__" for contact cards on
        initial detection. In that case, we just return the key - storage
        will happen after CPLC retrieval via on_cplc_retrieved().
        """
        # Hide loading dialog while key prompt is visible
        was_loading = self._loading_dialog.is_loading()
        self._loading_dialog.hide_loading()

        # Treat __CONTACT_CARD__ placeholder as no UID
        is_contact_placeholder = uid is None or uid == "__CONTACT_CARD__"
        is_new = not is_contact_placeholder and self.config["known_tags"].get(uid, False) != False
        title = ""
        if is_contact_placeholder:
            title = "Contact Card: "
        elif is_new:
            title = "New Tag: "
        if not existing_key:
            existing_key = DEFAULT_KEY
        title += "Enter Hexadecimal Master Key"
        dialog = HexInputDialog(
            title=title,
            fixed_byte_counts=[16, 24],
            parent=self,
            initial_value=existing_key,
        )

        if dialog.exec_():  # Show dialog and wait for user action
            res = dialog.get_results()

            # Only store immediately if we have a valid uid
            # For contact cards (placeholder), storage happens after CPLC retrieval
            if not is_contact_placeholder:
                self.update_known_tags(uid, res)

                if self.secure_storage is not None:
                    if not self.secure_storage["tags"].get(uid):
                        self.secure_storage["tags"][uid] = {"name": uid, "key": res}
                    else:
                        self.secure_storage["tags"][uid]["key"] = res

            # Resume loading dialog after key entry
            if was_loading:
                self._loading_dialog.show_loading(
                    timeout=10,
                    on_timeout=self._on_loading_timeout
                )

            return res
        else:
            # User cancelled - don't resume loading dialog
            return None

    def update_title_bar(self, message: str):
        if not "None" in message and len(message) > 0:
            # Try to replace card_id with user-provided name from secure storage
            display_title = message
            if self.nfc_thread and self.nfc_thread.current_identifier:
                identifier = self.nfc_thread.current_identifier
                card_id = identifier.primary_id

                # Look up user-provided name in secure storage
                # Priority: CPLC hash entry name -> UID entry name
                name = None
                if self.secure_storage:
                    tags = self.secure_storage.get("tags", {})

                    # Try CPLC hash first
                    if identifier.cplc_hash:
                        cplc_key = identifier.cplc_hash.upper()
                        if cplc_key in tags and tags[cplc_key].get("name"):
                            name = tags[cplc_key]["name"]

                    # Fall back to UID
                    if not name and identifier.uid:
                        uid_key = identifier.uid.upper().replace(" ", "")
                        if uid_key in tags and tags[uid_key].get("name"):
                            name = tags[uid_key]["name"]

                # Use name if it's different from the card_id (i.e., user set a custom name)
                if name and name != card_id:
                    display_title = message.replace(card_id, name)

            self.setWindowTitle(display_title)
        else:
            self.setWindowTitle(APP_TITLE)

    def on_cplc_retrieved(self, uid: str, cplc_hash: str):
        """
        Called when CPLC data is retrieved for a card.

        This handles:
        1. Upgrading UID-based storage entries to use CPLC as primary key
        2. For contact cards (uid may be empty), storing key under CPLC identifier
        3. Merging data when both UID and CPLC entries exist
        """
        # CRITICAL: If key prompt was cancelled, do NOT store anything
        if self._key_prompt_cancelled:
            return

        if not cplc_hash:
            return

        # Get the current key from NFC thread (set during authentication)
        key = self.nfc_thread.key

        # CRITICAL: Do NOT store if key is None (user cancelled or no key provided)
        if key is None:
            return
        storage_changed = False

        if self.secure_storage is not None:
            tags = self.secure_storage["tags"]
            existing_cplc_entry = tags.get(cplc_hash)
            existing_uid_entry = tags.get(uid) if uid else None

            # Merge logic: combine UID and CPLC entries, preferring user-set data
            if existing_uid_entry and existing_cplc_entry:
                # Both exist - merge, preferring custom names over default/ID names
                cplc_name = existing_cplc_entry.get("name", "")
                uid_name = existing_uid_entry.get("name", "")

                # Prefer name that's not just an ID (custom user-set name)
                def is_custom_name(name, card_id, uid_val):
                    if not name:
                        return False
                    # Not custom if it equals the CPLC hash, UID, or placeholder
                    return name not in (card_id, uid_val, "__CONTACT_CARD__", "")

                if is_custom_name(cplc_name, cplc_hash, uid):
                    final_name = cplc_name
                elif is_custom_name(uid_name, cplc_hash, uid):
                    final_name = uid_name
                else:
                    final_name = cplc_name or uid_name or cplc_hash

                # Merge into CPLC entry
                tags[cplc_hash] = {
                    "key": existing_cplc_entry.get("key") or existing_uid_entry.get("key") or key,
                    "name": final_name,
                    "uid": uid,
                    "migrated_from_uid": True,
                }
                # Remove the UID entry
                del tags[uid]
                storage_changed = True

            elif existing_uid_entry:
                # Only UID entry exists - migrate to CPLC
                # But check if CPLC entry might have been created since
                tags[cplc_hash] = {
                    "key": existing_uid_entry.get("key") or key,
                    "name": existing_uid_entry.get("name", cplc_hash),
                    "uid": uid,
                    "migrated_from_uid": True,
                }
                del tags[uid]
                storage_changed = True

            elif existing_cplc_entry:
                # Only CPLC entry exists - just ensure UID is recorded
                if uid and not existing_cplc_entry.get("uid"):
                    existing_cplc_entry["uid"] = uid
                    storage_changed = True

            elif key:
                # No entry exists - create new one
                tags[cplc_hash] = {
                    "key": key,
                    "name": cplc_hash,
                }
                if uid:
                    tags[cplc_hash]["uid"] = uid
                storage_changed = True

        if storage_changed:
            self.write_secure_storage()

        # Update known_tags config with CPLC
        if key == DEFAULT_KEY:
            self.config["known_tags"][cplc_hash] = True
        else:
            self.config["known_tags"][cplc_hash] = False
        self.write_config()

        # Update title bar to show CPLC-based name if available
        self.nfc_thread.title_bar_signal.emit(self.nfc_thread.make_title_bar_string())

    def set_tag_name(self):
        # Prompt for the tag name using QInputDialog
        tag_name, ok = QInputDialog.getText(
            self, "Set Tag Name", "Enter the tag name:", QLineEdit.Normal
        )
        if ok and tag_name and self.nfc_thread:
            # Use card_id (CPLC hash preferred, UID fallback) as the storage key
            card_id = self.nfc_thread.card_id
            # Filter out placeholder
            if card_id == "__CONTACT_CARD__":
                card_id = None
            if not card_id:
                self.show_error_dialog("No card identifier available. Cannot save name.")
                return

            if not self.secure_storage["tags"].get(card_id):
                self.secure_storage["tags"][card_id] = {
                    "name": card_id,
                    "key": (
                        DEFAULT_KEY
                        if self.config["known_tags"].get(card_id)
                        else None
                    ),
                }
            # Process the tag name (store it, set it, etc.)
            self.secure_storage["tags"][card_id]["name"] = tag_name
            self.write_secure_storage()
            self.update_title_bar(self.nfc_thread.make_title_bar_string())

    def set_tag_key(self):
        # Prompt for the tag key using QInputDialog
        tag_key, ok = QInputDialog.getText(
            self, "Set Tag Key", "Enter the tag key:", QLineEdit.Normal
        )
        if ok and tag_key:
            if len(tag_key) % 2 != 0:
                self.show_error_dialog("Keys must have an even length")
                while len(tag_key) % 2 != 0:
                    tag_key, ok = QInputDialog.getText(
                        self, "Set Tag Key", "Enter the tag key:", QLineEdit.Normal
                    )
                    if not ok:
                        break
            # Use card_id (CPLC hash preferred, UID fallback) as the storage key
            card_id = self.nfc_thread.card_id
            # Filter out placeholder
            if card_id == "__CONTACT_CARD__":
                card_id = None
            if not card_id:
                self.show_error_dialog("No card identifier available. Cannot save key.")
                return

            if not self.secure_storage["tags"].get(card_id):
                self.secure_storage["tags"][card_id] = {
                    "name": card_id,
                    "key": DEFAULT_KEY if self.config["known_tags"].get(card_id) else None,
                }
            self.secure_storage["tags"][card_id]["key"] = tag_key
            self.config["known_tags"][card_id] = DEFAULT_KEY == tag_key

            self.write_config()
            self.write_secure_storage()
            self.nfc_thread.key = tag_key
            self.on_operation_complete(
                True,
                f"{self.secure_storage['tags'][card_id]['name']}'s saved key is now: {tag_key}",
            )

    def change_tag_key(self):
        # Get current key configuration if available
        current_config = self._get_key_config_for_card(self.nfc_thread.card_id)

        # Detect SCP version from card
        scp_info = None
        if self.nfc_thread.key:
            self.loading_indicator.start("Detecting card protocol...")
            scp_info = self.nfc_thread.get_card_info()
            self.loading_indicator.stop()

        dialog = ChangeKeyDialog(
            current_key=self.nfc_thread.key or DEFAULT_KEY,
            current_config=current_config,
            scp_info=scp_info,
            parent=self,
        )

        if dialog.exec_() == QDialog.Accepted:
            new_config = dialog.get_configuration()
            if new_config:
                self.nfc_thread.change_key_with_config(
                    new_config=new_config,
                    old_config=current_config,
                )

    def _get_key_config_for_card(self, card_id: str):
        """Get the stored KeyConfiguration for a card if available."""
        from src.models.key_config import KeyConfiguration

        if not card_id or card_id == "__CONTACT_CARD__":
            return None

        if not self.secure_storage:
            return None

        tags = self.secure_storage.get("tags", {})
        tag_data = tags.get(card_id)

        if not tag_data:
            return None

        # Check for new key_config format
        if "key_config" in tag_data:
            return KeyConfiguration.from_dict(tag_data["key_config"])

        # Fall back to legacy key format
        if "key" in tag_data and tag_data["key"]:
            return KeyConfiguration.from_legacy_key(tag_data["key"])

        return None

    def _is_valid_storage_id(self, card_id: str | None) -> bool:
        """Check if card_id is valid for storage (not None or placeholder)."""
        return card_id is not None and card_id != "__CONTACT_CARD__"

    def manage_tags(self):
        """Open the manage tags dialog."""
        if not self.secure_storage:
            QMessageBox.information(
                self,
                "Secure Storage Required",
                "Secure storage must be initialized to manage tags.\n\n"
                "Please scan a card first to initialize storage.",
            )
            return

        dialog = ManageTagsDialog(
            secure_storage=self.secure_storage,
            config=self.config,
            parent=self,
        )

        if dialog.exec_() == QDialog.Accepted:
            storage, config, modified = dialog.get_modified_data()
            if modified:
                self.secure_storage = storage
                self.config = config
                self.write_secure_storage()
                self.write_config()
                self.message_queue.add_message("Tag data updated.")

                # If a card is currently present, check if its key was deleted/cleared
                # and invalidate the NFC thread's cached key
                current_id = self.nfc_thread.card_id
                if current_id and current_id != "__CONTACT_CARD__":
                    tag_data = self.secure_storage.get("tags", {}).get(current_id)
                    stored_key = tag_data.get("key") if tag_data else None

                    # If the stored key is gone but NFC thread still has a key, clear it
                    if not stored_key and self.nfc_thread.key:
                        self.nfc_thread.key = None
                        self._update_action_buttons_state(False)  # Disable buttons until key entered
                        self.message_queue.add_message("Card key cleared - please re-enter key.")
                        # Prompt for key again
                        self.get_key(current_id)

    def quit_app(self):

        QApplication.instance().quit()

    def _cleanup_invalid_storage_ids(self):
        """Remove invalid placeholder IDs from storage (e.g., __CONTACT_CARD__)."""
        modified = False

        # Clean up secure_storage tags
        if self.secure_storage and "tags" in self.secure_storage:
            invalid_ids = [
                key for key in self.secure_storage["tags"]
                if not self._is_valid_storage_id(key)
            ]
            for invalid_id in invalid_ids:
                del self.secure_storage["tags"][invalid_id]
                modified = True

        # Clean up config known_tags
        if "known_tags" in self.config:
            invalid_ids = [
                key for key in self.config["known_tags"]
                if not self._is_valid_storage_id(key)
            ]
            for invalid_id in invalid_ids:
                del self.config["known_tags"][invalid_id]
                modified = True

        # Save if we cleaned anything
        if modified:
            self.write_config()
            if self.secure_storage:
                self.write_secure_storage()

    def _load_secure_storage_with_retry(self):
        """
        Attempt to load secure storage with user-friendly error handling.

        If unlock fails, offers options to:
        - Retry (for GPG PIN entry issues)
        - Create new storage (backs up old file)
        - Continue without secure storage
        """
        max_retries = 3
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                self.secure_storage_instance.load()
                self.secure_storage = self.secure_storage_instance.get_data()
                self._cleanup_invalid_storage_ids()
                return  # Success!
            except FileNotFoundError:
                # File was deleted between check and load
                self.secure_storage = None
                return
            except (InvalidTag, RuntimeError) as e:
                last_error = e
                retry_count += 1

                # Determine error type for user message
                error_str = str(e).lower()
                if "key not found" in error_str or "keyring" in error_str:
                    error_type = "keyring"
                    error_msg = (
                        "The encryption key was not found in your system keyring.\n\n"
                        "This can happen if:\n"
                        "• The keyring was cleared or reset\n"
                        "• You're on a different user account\n"
                        "• The system keyring service changed"
                    )
                elif "gpg" in error_str or "decrypt" in error_str:
                    error_type = "gpg"
                    error_msg = (
                        "GPG decryption failed.\n\n"
                        "This can happen if:\n"
                        "• The GPG key is no longer available\n"
                        "• The PIN/passphrase entry was cancelled\n"
                        "• The smart card with the GPG key is not present"
                    )
                else:
                    error_type = "unknown"
                    error_msg = (
                        f"Failed to decrypt secure storage.\n\n"
                        f"Error: {e}"
                    )

                # Show dialog with options
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Secure Storage Unlock Failed")
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setText("Could not unlock your secure storage.")
                msg_box.setInformativeText(error_msg)

                # Add buttons based on context
                retry_btn = msg_box.addButton("Try Again", QMessageBox.ActionRole)
                new_btn = msg_box.addButton("Create New", QMessageBox.AcceptRole)
                skip_btn = msg_box.addButton("Continue Without", QMessageBox.RejectRole)

                # Let buttons size based on their content with padding for platform fonts
                for btn in [retry_btn, new_btn, skip_btn]:
                    text_width = btn.fontMetrics().horizontalAdvance(btn.text())
                    btn.setMinimumWidth(text_width + 30)  # Add padding for margins

                # Add note about data safety
                msg_box.setDetailedText(
                    "Your existing secure storage file will NOT be deleted.\n\n"
                    "If you choose 'Create New':\n"
                    f"• The old file will be backed up as '{DATA_FILE}.backup'\n"
                    "• A new empty secure storage will be created\n"
                    "• Your old data can be recovered if you restore the backup\n\n"
                    "If you choose 'Continue Without':\n"
                    "• Card keys will not be saved between sessions\n"
                    "• You can set up secure storage later from File menu"
                )

                msg_box.exec_()
                clicked = msg_box.clickedButton()

                if clicked == retry_btn:
                    # Try again (loop continues)
                    continue
                elif clicked == new_btn:
                    # Back up old file and create new storage
                    self._backup_and_create_new_storage()
                    return
                else:  # skip_btn or closed
                    self.secure_storage = None
                    return

        # Exhausted retries
        self.secure_storage = None

    def _setup_secure_storage_from_menu(self):
        """Allow user to set up secure storage from the File menu."""
        if self.secure_storage:
            reply = QMessageBox.question(
                self,
                "Secure Storage Exists",
                "Secure storage is already set up.\n\n"
                "Do you want to reset it? This will back up your existing data first.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            # Back up and recreate
            self._backup_and_create_new_storage()
        else:
            # No existing storage - just set it up
            if os.path.exists(DATA_FILE):
                # File exists but couldn't be unlocked
                self._backup_and_create_new_storage()
            else:
                self.prompt_setup()

        # Update menu state
        self._update_storage_menu_state()

    def _update_storage_menu_state(self):
        """Update storage-related UI state. Now a no-op since storage is managed in Settings."""
        pass

    def _backup_and_create_new_storage(self):
        """Back up the existing storage file and prompt for new storage creation."""
        import shutil
        from datetime import datetime

        # Create backup with timestamp
        backup_path = f"{DATA_FILE}.backup"

        # If backup already exists, add timestamp
        if os.path.exists(backup_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{DATA_FILE}.backup.{timestamp}"

        try:
            shutil.copy2(DATA_FILE, backup_path)
            # Remove the old file so prompt_setup creates a new one
            os.remove(DATA_FILE)

            QMessageBox.information(
                self,
                "Backup Created",
                f"Your old secure storage has been backed up to:\n{backup_path}\n\n"
                "Now let's set up a new secure storage.",
            )

            # Trigger new storage setup
            self.prompt_setup()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Backup Failed",
                f"Could not create backup: {e}\n\n"
                "Continuing without secure storage to avoid data loss.",
            )
            self.secure_storage = None

    def prompt_setup(self):
        def initialize_and_accept():
            method_display = self.secure_storage_dialog.method_selector.currentText()
            # Map display name to actual method
            method = "gpg" if "gpg" in method_display.lower() else method_display
            context = {}

            if method == "gpg":
                context = select_gpg_key(context)
                self.secure_storage_instance.initialize(
                    method, key_id=context["keyid"], initial_data=DEFAULT_DATA
                )
            else:
                self.secure_storage_instance.initialize(
                    method, initial_data=DEFAULT_DATA
                )

            if self.secure_storage_instance.get_data():
                self.secure_storage = self.secure_storage_instance.get_data()
            dialog.accept()

        storage_methods = ["keyring", "gpg"]

        try:
            gpg = gnupg.GPG()
        except Exception:
            storage_methods = [x for x in storage_methods if x != "gpg"]

        # Why have them choose one if there's only one choice?
        if len(storage_methods) == 1:
            return storage_methods[0]

        else:

            dialog = QDialog(self)
            layout = QFormLayout()
            layout.addWidget(QLabel("Key storage method:"))
            dialog.method_selector = QComboBox()
            dialog.method_selector.addItems(["keyring", "gpg wrapped"])
            dialog.method_selector.setCurrentIndex(0)
            layout.addWidget(dialog.method_selector)

            btn = QPushButton("Initialize")
            btn.clicked.connect(initialize_and_accept)
            layout.addWidget(btn)

            dialog.setLayout(layout)
            self.secure_storage_dialog = dialog
            dialog.finished.connect(self.on_setup_dialog_finish)

            result = dialog.exec_()

            return dialog.method_selector.currentText()

    def on_setup_dialog_finish(self, result):
        if result == 1:
            if self.secure_storage_dialog.method_selector.currentText() is not None:
                # Load our file to make sure it works...
                if self.nfc_thread:
                    self.nfc_thread.pause()
                    time.sleep(0.15)
                self.secure_storage_instance.load()
                if self.nfc_thread:
                    self.nfc_thread.resume()
            else:
                self.secure_storage = None
        else:
            self.secure_storage = None

    def write_secure_storage(self):
        if not self.secure_storage_instance:
            return
        self.nfc_thread.pause()
        # Wait for NFC thread to acknowledge pause (non-blocking with timeout)
        self.nfc_thread._paused_ack.wait(timeout=0.5)
        # Sync the dict data to the instance before saving
        if self.secure_storage is not None:
            self.secure_storage_instance.set_data(self.secure_storage)
        self.secure_storage_instance.save()
        self.nfc_thread.resume()

    def load_config(self):
        # Future: migrate to ConfigService for automatic versioning/migration
        # from src.services.config_service import ConfigService
        # self._config_service = ConfigService()
        # return self._config_service.load().to_dict()

        # Migrate legacy files from working directory to app data directory
        if os.path.exists(LEGACY_CONFIG_FILE) and not os.path.exists(CONFIG_FILE):
            migration_result = migrate_legacy_files()
            if migration_result["migrated"]:
                self.message_queue.add_message(
                    f"Migrated files to app data: {', '.join(migration_result['migrated'])}"
                )

        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as fh:
                try:
                    config = json.load(fh)
                except Exception as e:
                    self.show_error_dialog("Config file is invalid. Creating new one.")
                    fh.close()
                    # Maybe they want to see about salvaging the config?
                    broken_path = str(get_app_data_dir() / f"config-{int(time.time())}-.broken.json")
                    os.rename(CONFIG_FILE, broken_path)
                    config = DEFAULT_CONFIG

            # Did I update something? Let's make sure the config is updated.
            for key in DEFAULT_CONFIG.keys():
                if config.get(key) is None:
                    config[key] = DEFAULT_CONFIG[key]

            return config
        else:
            # create default
            with open(CONFIG_FILE, "w") as fh:
                json.dump(DEFAULT_CONFIG, fh, indent=4)

            return DEFAULT_CONFIG

    def write_config(self):
        # Future: migrate to ConfigService.save()
        with open(CONFIG_FILE, "w") as fh:
            json.dump(self.config, fh, indent=4)

    def update_known_tags(self, uid: str, default_key: bool | str):
        # Defensive check - don't store placeholder IDs
        if not self._is_valid_storage_id(uid):
            return

        if self.config["known_tags"].get(uid) is None:
            if type(default_key) != type(False):
                self.config["known_tags"][uid] = default_key == DEFAULT_KEY
            else:
                self.config["known_tags"][uid] = default_key

            if self.secure_storage:
                if not self.secure_storage["tags"].get(uid):
                    self.secure_storage["tags"][uid] = {"name": uid, "key": None}
                if default_key == "False":
                    self.secure_storage["tags"][uid]["key"] = None
                else:
                    self.secure_storage["tags"][uid]["key"] = default_key

                self.message_queue.add_message(
                    f"Updated {self.secure_storage['tags'][uid]['name']} to known tags. Default key: {default_key}"
                )
            else:
                self.message_queue.add_message(
                    f"Added {uid} to known tags. Default key: {default_key}"
                )
        else:
            if type(default_key) != type(False):
                # Handle key storage in secure storage
                if self.secure_storage and self.secure_storage["tags"].get(uid):
                    if default_key == "False":
                        self.secure_storage["tags"][uid]["key"] = None
                    else:
                        self.secure_storage["tags"][uid]["key"] = default_key

                default_key = default_key == DEFAULT_KEY
            if self.config["known_tags"][uid] != default_key:
                self.config["known_tags"][uid] = default_key
                self.message_queue.add_message(
                    f"Updated {uid}. Default key: {default_key}"
                )

        self.write_config()

    def update_key_config(self, card_id: str, key_config):
        """
        Update the key configuration for a card.

        Args:
            card_id: Card identifier (CPLC hash or UID)
            key_config: KeyConfiguration object
        """
        if not self.secure_storage:
            return

        # Defensive check - don't store placeholder IDs
        if not self._is_valid_storage_id(card_id):
            return

        tags = self.secure_storage.get("tags", {})

        if card_id not in tags:
            tags[card_id] = {"name": card_id}

        # Store the new key_config format
        tags[card_id]["key_config"] = key_config.to_dict()

        # Also update legacy key field for backward compatibility
        tags[card_id]["key"] = key_config.get_effective_key()

        self.secure_storage["tags"] = tags
        self.write_secure_storage()

        self.message_queue.add_message(f"Updated key configuration for {tags[card_id].get('name', card_id)}")

    def query_known_tags(self, uid: str) -> bool:
        """
        Returns a bool if the tag is known
        - The bool indicates whether it has a default key
        Returns None when the tag is not known
        """
        return self.config["known_tags"].get(uid, False) == True

    def resizeEvent(self, event):
        new_size = event.size()

        self.on_resize(new_size)
        super().resizeEvent(event)

    def on_resize(self, size: QSize):
        self.config["window"]["width"] = size.width()
        self.config["window"]["height"] = size.height()

        self.write_config()


# KeyDialog removed - was unused (prompt_for_key uses HexInputDialog)
# KeyPromptDialog is available in src.views.dialogs if needed


def prompt_for_password(self):
    # Open a dialog to get the password securely
    pw, ok = QInputDialog.getText(
        self, "Set Keyring Password", "Enter your password:", QLineEdit.Password
    )
    if ok and pw:
        return pw
    else:
        self.show_error("Password input failed or was canceled.")
        return None


def select_gpg_key(context):
    gpg = gnupg.GPG()
    gpg_keys = gpg.list_keys()

    gpg_options = {
        f"{x['keyid']} ({x['uids'][0]})": {
            "recipients": x["uids"],
            "keyid": x["keyid"],
        }
        for x in gpg_keys
    }

    def handle_accept(self, x):
        self.choice = x

    choose_gpg_dialog = ComboDialog(
        window_title="GPG",
        combo_label="Choose a key",
        options=list(gpg_options.keys()),
        on_accept=handle_accept,
        on_cancel=lambda x: f"Canceled: {x}",
    )
    choose_gpg_dialog.exec_()

    choice = choose_gpg_dialog.choice
    if choice is None:
        app.show_error_dialog("No choice found")
        return

    gpg_context = gpg_options[choice]
    context = context | gpg_context
    return context


def horizontal_rule():
    h_line = QFrame()
    h_line.setFrameShape(QFrame.HLine)
    h_line.setFrameShadow(QFrame.Sunken)

    return h_line


# ComboDialog removed - now imported from src.views.dialogs


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(resource_path("favicon.ico")))

    # Set application font - use system default with adjusted size for readability
    # Windows often needs larger font sizes than Linux/macOS
    import platform
    if platform.system() == "Windows":
        # Use Segoe UI (Windows default) at readable size
        font = QFont("Segoe UI", 10)
    else:
        # Use system default on other platforms
        font = QFont()
        font.setPointSize(10)
    app.setFont(font)

    window = GPManagerApp()
    window.show()
    sys.exit(app.exec_())
