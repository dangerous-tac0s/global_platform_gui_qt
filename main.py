# main.py
import json
import sys
import os
import tempfile
import importlib
import textwrap
import time

import gnupg

import markdown
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
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
    QMainWindow,
    QDialogButtonBox,
)
from PyQt5.QtCore import QTimer, Qt, QSize, QEvent

from dialogs.hex_input_dialog import HexInputDialog
from file_thread import FileHandlerThread
from nfc_thread import NFCHandlerThread, resource_path, DEFAULT_KEY
from secure_storage import SecureStorage

try:
    import keyring
except ImportError:
    keyring = None


WIDTH_HEIGHT = [800, 600]

APP_TITLE = "GlobalPlatformPro App Manager"

"""
    [dict[str, bool]] known_keys:
        [bool] uid:str - if the UID uses a default key, true, else false
    [bool] cache_latest_release=False
    """
DEFAULT_CONFIG = {
    "cache_latest_release": False,
    # [app]: epoch time
    "last_checked": {},
    "known_tags": {},
    "window": {
        "height": WIDTH_HEIGHT[1],
        "width": WIDTH_HEIGHT[0],
        # "font_size": ""
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

DATA_FILE = "data.enc.json"

#
# Folder for caching .cap downloads
#
CAP_DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "gp_caps")
os.makedirs(CAP_DOWNLOAD_DIR, exist_ok=True)

#
# If you still need to skip certain .cap files, keep them here.
#
unsupported_apps = ["FIDO2.cap", "openjavacard-ndef-tiny.cap", "keycard.cap"]

#
# We'll define our base plugin interface
#
try:
    from base_plugin import BaseAppletPlugin
except ImportError:
    # Fallback if we haven't provided the real base_plugin yet
    class BaseAppletPlugin:
        pass


def load_plugins():
    """
    Scan the /repos folder for subfolders containing __init__.py
    that define a class subclassing BaseAppletPlugin.

    Returns a dict plugin_map: { plugin_name: plugin_class }.
    E.g. { "flexsecure_applets": <class FlexsecureAppletsPlugin>, ... }
    """
    plugin_map = {}
    repos_dir = os.path.join(os.path.dirname(__file__), "repos")
    if not os.path.isdir(repos_dir):
        print("No /repos folder found, skipping plugin load.")
        return plugin_map

    for repo_name in os.listdir(repos_dir):
        repo_path = os.path.join(repos_dir, repo_name)
        if (
            os.path.isdir(repo_path)
            and not repo_name.startswith("__")
            and not repo_name.startswith(".")
        ):
            # We check if there's an __init__.py in that folder
            init_file = os.path.join(repo_path, "__init__.py")
            if os.path.isfile(init_file):
                # Attempt to import the repo as a package
                mod_path = f"repos.{repo_name}"  # e.g. repos.flexsecure_applets
                try:
                    mod = importlib.import_module(mod_path)
                    # find classes implementing BaseAppletPlugin
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseAppletPlugin)
                            and attr is not BaseAppletPlugin
                        ):
                            instance = attr()
                            plugin_map[instance.name] = attr
                except Exception as e:
                    print(f"Error importing {mod_path}: {e}")
    return plugin_map


class MessageQueue:
    def __init__(self, status_label):
        self.status_label = status_label
        self.queue = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.process_queue)

    def add_message(self, message):
        self.queue.append((message, self.calculate_timeout(message)))
        if not self.timer.isActive():
            self.process_queue()

    def calculate_timeout(self, message):
        return max(3000, len(message) * 50)

    def process_queue(self):
        if self.queue:
            message, timeout = self.queue.pop(0)
            self.status_label.setText(message)
            self.timer.start(timeout)
        else:
            self.timer.stop()


if os.name == "nt":
    width_height = [2 * x for x in WIDTH_HEIGHT]


class GPManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
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

        # Status label at the top
        self.status_label = QLabel("Checking for readers...")
        self.layout.addWidget(self.status_label)
        self.message_queue = MessageQueue(self.status_label)

        # Create the menu bar
        self.menu_bar = self.menuBar()

        file_menu = self.menu_bar.addMenu("File")
        settings_action = QAction("Settings", self)
        settings_action.setEnabled(False)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        tag_menu = self.menu_bar.addMenu("Tag")
        set_tag_name_action = QAction("Set Name", self)
        set_tag_name_action.triggered.connect(self.set_tag_name)
        set_tag_key_action = QAction("Set Key", self)
        set_tag_key_action.triggered.connect(self.set_tag_key)
        change_tag_key_action = QAction("⚠️ Change Key ⚠️", self)
        change_tag_key_action.triggered.connect(self.change_tag_key)
        # change_tag_key_action.setEnabled(False)

        tag_menu.addAction(set_tag_name_action)
        tag_menu.addAction(set_tag_key_action)
        tag_menu.addAction(change_tag_key_action)
        tag_menu.setEnabled(False)

        self.tag_menu = tag_menu

        self.config = self.load_config()
        self.resize(self.config["window"]["width"], self.config["window"]["height"])
        self.write_config()
        self.key = None

        self.layout.addWidget(horizontal_rule())

        # Reader selection row
        reader_layout = QHBoxLayout()
        self.reader_dropdown = QComboBox()
        self.reader_dropdown.currentIndexChanged.connect(self.on_reader_select)
        reader_layout.addWidget(QLabel("Reader:"))
        reader_layout.addWidget(self.reader_dropdown)
        self.layout.addLayout(reader_layout)

        # Installed / Available lists
        self.installed_app_names = []
        self.installed_list = QListWidget()
        self.available_list = QListWidget()

        grid_layout = QGridLayout()
        grid_layout.addWidget(QLabel("Installed Apps"), 0, 0)
        grid_layout.addWidget(self.installed_list, 1, 0)
        grid_layout.addWidget(QLabel("Available Apps"), 0, 1)
        grid_layout.addWidget(self.available_list, 1, 1)

        # Buttons
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self.install_app)
        grid_layout.addWidget(self.install_button, 2, 1)

        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.clicked.connect(self.uninstall_app)
        grid_layout.addWidget(self.uninstall_button, 2, 0)

        self.apps_grid_layout = grid_layout
        # TODO: Installed app details/configuration
        # self.installed_list.currentItemChanged.connect(self.show_installed_details_pane) # TODO: So configuration tools and or description
        self.available_list.currentItemChanged.connect(self.show_details_pane)

        self.layout.addLayout(self.apps_grid_layout)

        # Progress bar for downloads
        self.download_bar = QProgressBar()
        self.download_bar.hide()
        self.layout.addWidget(self.download_bar)

        self.central_widget.setLayout(self.layout)

        # Load secure storage
        if os.path.exists(DATA_FILE):
            try:
                self.secure_storage_instance.load()
                self.secure_storage = self.secure_storage_instance.get_data()
            except RuntimeError:
                self.show_error_dialog("Secure storage not decrypted.")
                self.secure_storage = None

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
        else:
            # You can opt out... But I'm gonna ask every time.
            self.prompt_setup()

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
        #    from each plugin
        #
        self.available_apps_info = {}
        self.app_descriptions = {}
        self.storage = {}
        for plugin_name, plugin_cls in self.plugin_map.items():
            plugin_instance = plugin_cls()
            plugin_instance.load_storage()
            if (
                not self.config["last_checked"].get(plugin_name, False)
                or self.config["last_checked"][plugin_name]["last"]
                <= time.time() - 24 * 60 * 60
            ):
                caps = plugin_instance.fetch_available_caps()
                if len(caps.keys()) > 0:
                    self.config["last_checked"][plugin_name] = {}
                    self.config["last_checked"][plugin_name]["apps"] = caps
                    self.config["last_checked"][plugin_name]["last"] = time.time()

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

            for cap_n, url in caps.items():
                self.available_apps_info[cap_n] = (plugin_name, url)

            descriptions = plugin_instance.get_descriptions()

            for cap_n, description_md in descriptions.items():
                self.app_descriptions[cap_n] = description_md

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

        self.nfc_thread.show_key_prompt_signal.connect(self.prompt_for_key)
        self.nfc_thread.get_key_signal.connect(self.get_key)
        self.nfc_thread.key_setter_signal.connect(self.nfc_thread.key_setter)

        # Initially disable install/uninstall
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)
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
                time.sleep(0.15)

        super().changeEvent(event)

    def handle_details_pane_back(self):
        # Remove the details pane
        items = [
            self.apps_grid_layout.itemAtPosition(0, 0),
            self.apps_grid_layout.itemAtPosition(2, 0),
        ]
        for item in items:
            if item:
                widget = item.widget()
                if widget:
                    self.apps_grid_layout.removeWidget(widget)
                    widget.setParent(None)

        # Replace with the appropriate widgets
        self.apps_grid_layout.addWidget(QLabel("Installed Apps"), 0, 0)
        self.apps_grid_layout.addWidget(self.installed_list, 1, 0)
        self.apps_grid_layout.addWidget(self.uninstall_button, 2, 0)

    def show_details_pane(self, changed_list):
        """
        Swaps installed/available columns for details pane
        """
        if changed_list is None:
            return
        selected_app = changed_list.text()

        if self.app_descriptions.get(selected_app) is None:
            return  # description is missing

        is_showing_details = False

        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(True)
        viewer.setHtml(
            markdown.markdown(textwrap.dedent(self.app_descriptions[selected_app]))
        )

        if self.apps_grid_layout.itemAtPosition(1, 0).widget() != self.installed_list:
            is_showing_details = True

        if not is_showing_details:
            for row in range(0, 3):
                item = self.apps_grid_layout.itemAtPosition(row, 0)
                if item:
                    widget = item.widget()
                    if widget:
                        self.apps_grid_layout.removeWidget(widget)
                        widget.setParent(None)

            self.apps_grid_layout.addWidget(viewer, 0, 0, 2, 1)
            back_button = QPushButton("Back")
            back_button.clicked.connect(self.handle_details_pane_back)

            self.apps_grid_layout.addWidget(back_button, 2, 0)
        else:
            self.apps_grid_layout.removeWidget(
                self.apps_grid_layout.itemAtPosition(0, 0).widget()
            )
            self.apps_grid_layout.addWidget(viewer, 0, 0, 2, 1)

    def handle_tag_menu(self):
        if self.secure_storage and not self.tag_menu.isEnabled():
            self.tag_menu.setEnabled(True)
        elif not self.secure_storage and self.tag_menu.isEnabled():
            self.tag_menu.setEnabled(False)

    def update_plugin_releases(self):
        self.message_queue.add_message("Fetching latest plugin releases...")
        updated = False
        for plugin_name, plugin_cls in self.plugin_map.items():
            plugin_instance = plugin_cls()
            caps = plugin_instance.fetch_available_caps()
            plugin_instance.load_storage()

            if len(caps.keys()) > 0:
                updated = True
                self.config["last_checked"][plugin_name] = {}
                self.config["last_checked"][plugin_name]["apps"] = caps
                self.config["last_checked"][plugin_name]["last"] = time.time()
                self.config["last_checked"][plugin_name]["release"] = list(
                    caps.values()
                )[0].split("/")[-2]

                self.write_config()

                # Update the available list
                for cap_n, url in caps.items():
                    self.available_apps_info[cap_n] = (plugin_name, url)

                # Update descriptions
                descriptions = plugin_instance.get_descriptions()

                for cap_n, description_md in descriptions.items():
                    self.app_descriptions[cap_n] = description_md

            else:
                self.message_queue.add_message(
                    "No apps returned. Check connection and/or url."
                )

        if updated:
            self.write_config()  # save state
            self.populate_available_list()  # Push the update
            self.message_queue.add_message("Updated plugin releases.")
        else:
            self.message_queue.add_message("No plugin releases found.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F1:
            self.on_f1_pressed(event)
        elif event.key() == Qt.Key_F4:
            self.on_f4_pressed(event)

    def on_f1_pressed(self, event):
        """
        TODO: HELP! I NEED SOMEBODY! HELP! NOT JUST ANYBODY!
        """
        print("HELP! I NEED SOMEBODY!\nHELP! NOT JUST ANYBODY!")
        pass

    def on_f4_pressed(self, event):
        """
        Force checking plugin resources for updates
        """
        self.message_queue.add_message("Update forced...")
        self.message_queue.add_message("Forcing update on present tag...")
        while self.installed_list.count() > 0:
            self.available_list.addItem(self.installed_list.takeItem(0))
        self.installed_list.update()
        self.available_list.update()
        time.sleep(0.1)
        if self.nfc_thread.isRunning():

            self.nfc_thread.current_uid = None
            self.nfc_thread.key = None
            self.nfc_thread.card_detected = False
            self.update_title_bar(self.nfc_thread.make_title_bar_string())
        else:
            self.nfc_thread.start()
        # else:
        #     print(self.nfc_thread)
        self.update_plugin_releases()

    def populate_available_list(self):
        self.available_list.clear()
        for cap_name, (plugin_name, url) in self.available_apps_info.items():
            if cap_name in unsupported_apps or cap_name in self.installed_app_names:
                continue
            self.available_list.addItem(cap_name)

    def on_reader_select(self, index):
        reader_name = self.reader_dropdown.itemText(index)
        self.nfc_thread.selected_reader_name = reader_name

    def readers_updated(self, readers_list):
        self.reader_dropdown.blockSignals(True)
        self.reader_dropdown.clear()

        if not readers_list:
            self.reader_dropdown.setDisabled(True)
            self.nfc_thread.selected_reader_name = None
            self.message_queue.add_message("No readers found.")
            self.install_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.reader_dropdown.blockSignals(False)
            return

        self.reader_dropdown.setEnabled(True)
        self.reader_dropdown.addItems(readers_list)
        self.status_label.setText(
            f"Found {len(readers_list)} reader{'s' if len(readers_list)>1 else ''}."
        )

        if self.nfc_thread.selected_reader_name not in readers_list:
            self.nfc_thread.selected_reader_name = readers_list[0]
            self.reader_dropdown.setCurrentIndex(0)
        else:
            idx = readers_list.index(self.nfc_thread.selected_reader_name)
            self.reader_dropdown.setCurrentIndex(idx)

        self.reader_dropdown.blockSignals(False)

    def update_card_presence(self, present):
        if present:
            if self.nfc_thread.valid_card_detected:
                self.message_queue.add_message("Compatible card present.")
                uid = self.nfc_thread.current_uid

                if (
                    self.secure_storage
                    and uid
                    and not self.secure_storage["tags"].get(uid)
                ):
                    self.secure_storage["tags"][uid] = {
                        "name": uid,
                        "key": self.nfc_thread.key,
                    }
                    self.write_secure_storage()

                if self.nfc_thread.key is not None:
                    if (
                        self.secure_storage
                        and self.secure_storage["tags"].get(uid)
                        and not self.secure_storage["tags"][uid]["key"]
                    ):
                        self.secure_storage["tags"][uid]["key"] = self.nfc_thread.key
                        self.write_secure_storage()

                    self.install_button.setEnabled(True)
                    self.uninstall_button.setEnabled(True)
                    installed = self.nfc_thread.get_installed_apps()
                    if installed is not None:
                        self.on_installed_apps_updated(installed)
            else:
                self.install_button.setEnabled(False)
                self.uninstall_button.setEnabled(False)
                self.message_queue.add_message("Unsupported card present.")
        else:
            self.install_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.message_queue.add_message("No card present.")

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
        self.downloader = FileHandlerThread(
            cap_name, dl_url, output_dir=CAP_DOWNLOAD_DIR
        )

        self.downloader.download_progress.connect(self.on_download_progress)
        self.downloader.download_complete.connect(
            lambda file_path: on_complete(file_path, params)
        )
        self.downloader.download_error.connect(self.on_download_error)

        self.download_bar.setRange(0, 100)
        self.download_bar.setValue(0)
        self.download_bar.show()

        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)
        self.downloader.start()

    def on_download_progress(self, pct):
        self.download_bar.setValue(pct)

    def on_download_error(self, err_msg):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.install_button.setEnabled(True)
        self.uninstall_button.setEnabled(True)
        self.show_error_dialog(err_msg)
        # self.message_queue.add_message(err_msg)

    #
    #  Install Flow
    #
    def install_app(self):
        selected = self.available_list.selectedItems()
        if not selected:
            return

        cap_name = selected[0].text()

        # TODO: better mutual exclusivity testing. Without this, trying to install U2F
        #   with FIDO2 installed will result in an error and this app trying to do cleanup
        #   from the b0rked install. This will remove the FIDO2 app--and all keys.
        if "U2F" in cap_name and "FIDO2.cap" in self.installed_app_names:
            self.show_error_dialog("FIDO2 falls back to U2F--you do not need both.")
            return

        # Do we have enough storage?
        reqs = self.storage.get(cap_name)
        if (
            reqs is not None
            and self.nfc_thread.storage["persistent"] != "-1"
            and self.nfc_thread.storage["transient"] != -1
        ):  # None means we don't have any data for the app
            error_message = "Insufficient Storage\n"
            default_length = len(error_message)
            if self.nfc_thread.storage["persistent"] < reqs["persistent"]:
                error_message += f"\tPersistent Needed: {abs(self.nfc_thread.storage["persistent"] - reqs["persistent"])} bytes"
            if self.nfc_thread.storage["transient"] < reqs["transient"]:
                error_message += f"\tTransient Needed: {abs(self.nfc_thread.storage["transient"] - reqs["transient"])} bytes"
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
            plugin_cls = self.plugin_map[plugin_name]
            plugin = plugin_cls()
            plugin.set_cap_name(cap_name)

            # Possibly run pre_install
            try:
                plugin.pre_install(nfc_thread=self.nfc_thread)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Pre-install error: {e}")
                return

            dlg = plugin.create_dialog(self)
            if dlg and dlg.exec_() == dlg.Accepted:
                self.current_plugin = plugin
                result_data = plugin.get_result()
                print("Plugin result:", result_data)
                self.fetch_file(
                    cap_name, self.on_install_download_complete, params=result_data
                )
            elif dlg:
                # user canceled
                return
            else:
                # no dialog => simple flow
                self.current_plugin = plugin
                self.fetch_file(cap_name, self.on_install_download_complete)
        else:
            # No plugin found => but we handle gracefully
            self.current_plugin = None
            self.fetch_file(cap_name, self.on_install_download_complete)

    def on_install_download_complete(self, file_path, params=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.message_queue.add_message(
            f"Installing: {file_path.split(os.path.sep)[-1]}"
        )
        self.nfc_thread.install_app(file_path, params)

    #
    #  Uninstall Flow
    #
    def uninstall_app(self):
        selected = self.installed_list.selectedItems()
        if not selected:
            return
        # Assume the installed list displays the .cap filename (or "Unknown: <aid>")
        cap_name = selected[0].text()

        # If the entry indicates an unknown app (i.e. no plugin info), fallback to uninstall by AID.

        if "Unknown" in cap_name:
            raw_aid = cap_name.split(" ", 1)[1]
            self.message_queue.add_message(f"Attempting to uninstall: {raw_aid}")
            return self.nfc_thread.uninstall_app(raw_aid, force=True)

        # Look up available info for the selected cap.
        if cap_name not in self.available_apps_info:
            self.message_queue.add_message(f"No available info for {cap_name}.")
            return

        plugin_name, _ = self.available_apps_info[cap_name]
        if plugin_name in self.plugin_map:
            plugin_cls = self.plugin_map[plugin_name]
            plugin = plugin_cls()
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
            # self.message_queue.add_message(f"No plugin found for {cap_name}")

    def on_uninstall_download_complete(self, file_path, params=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.message_queue.add_message(
            f"Uninstalling with {file_path.split(os.path.sep)[-1]}"
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
            self.install_button.setEnabled(True)
            self.uninstall_button.setEnabled(True)

        if message is not None:
            self.message_queue.add_message("Compatible card present.")

        if success and self.current_plugin:
            try:
                self.current_plugin.post_install()
            except Exception as e:
                self.show_error_dialog(f"Post-install: {e}")
                # self.message_queue.add_message(f"Post-install error: {e}")

        self.current_plugin = None

    #
    #  Displaying Installed Apps
    #
    def on_installed_apps_updated(self, installed_aids):
        """
        installed_aids is a dict { AID_uppercase: version_string_or_None }.
        We must iterate installed_aids.keys() or items().
        """
        self.installed_list.clear()
        self.installed_app_names = []

        for raw_aid in installed_aids.keys():
            # e.g. 'A000000308000010000100'
            version = installed_aids[raw_aid]  # TODO: rendering versions

            norm = raw_aid.replace(" ", "").upper()
            matched_plugin_name = None
            matched_cap = None

            for pname, plugin_cls in self.plugin_map.items():
                tmp = plugin_cls()
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

            # Display either the cap name or "Unknown"
            if matched_cap:
                self.installed_app_names.append(matched_cap)
                display_text = matched_cap
            elif matched_plugin_name:
                display_text = f"Unknown from {matched_plugin_name}: {raw_aid}"
            else:
                display_text = f"Unknown: {raw_aid}"
            # TODO: Handle showing versions.
            # if version:
            #     display_text += f" - v{version}"

            self.installed_list.addItem(display_text)
        self.populate_available_list()
        self.on_operation_complete(True)

    #
    #  Utility
    #
    def closeEvent(self, event):
        self.write_config()
        if self.secure_storage:
            self.write_secure_storage()

        self.nfc_thread.stop()
        self.nfc_thread.wait()

        event.accept()

    def show_error_dialog(self, message: str):
        # Was there a bad touch?
        if "Failed to open secure channel" in message:
            # Yup
            uid = self.nfc_thread.current_uid
            self.nfc_thread.key = None
            # Make sure we tell it we don't know the key in the config
            self.config["known_tags"][uid] = False
            self.write_config()
            if self.secure_storage:
                if self.secure_storage["tags"].get(uid):
                    # Remove the naughty key
                    self.secure_storage["tags"][uid]["key"] = None
                    self.write_secure_storage()
            message = "Bad touch! Invalid key! Further attempts without a successful auth will brick the device!"
            QMessageBox.critical(self, "Error", message, QMessageBox.Ok)
            self.prompt_for_key(uid, "")
        else:
            QMessageBox.critical(self, "Error", message, QMessageBox.Ok)

    def get_key(self, uid):
        """
        Get the key for the user's smart card.
        - Have we seen the tag before?
        - If so, did it have a default key?
        """
        key = None
        if self.secure_storage is not None:
            if self.secure_storage["tags"].get(uid):
                key = self.secure_storage["tags"][uid]["key"]
        if key is None:
            is_default_key = self.config["known_tags"].get(uid, None)
            if is_default_key:
                key = DEFAULT_KEY

        if key is None:
            res = self.prompt_for_key(uid)

            if res and res.get("key", False) is False:
                self.show_error_dialog("No key found.")
                return
            elif res is None:
                return

            key = res["key"]

        self.nfc_thread.key_setter_signal.emit(key)
        self.nfc_thread.status_update_signal.emit("Key set.")
        self.update_card_presence(True)

    def prompt_for_key(self, uid: str, existing_key: str = None):
        """
        Prompts the user to enter their smart card's key
        """
        is_new = self.config["known_tags"].get(uid, False) != False
        title = ""
        if is_new:
            title = "New Tag: "
        if not existing_key:
            existing_key = DEFAULT_KEY
        title += "Enter Hexadecimal Key"
        dialog = HexInputDialog(
            title=title,
            fixed_byte_counts=[16, 24, 2],
            parent=self,
            initial_value=existing_key,
        )
        # dialog = KeyDialog(
        #     uid=uid,
        #     exiting_key=existing_key,
        #     is_new=is_new,
        # )  # No existing key
        if dialog.exec_():  # Show dialog and wait for user action
            res = dialog.get_results()

            # if not self.config["known_tags"].get(res["uid"]):
            #     self.config["known_tags"][uid] = False
            self.update_known_tags(uid, res)

            # if self.secure_storage is not None:
            #     if not self.secure_storage["tags"].get(uid):
            #         self.secure_storage["tags"][uid] = {"name": uid, "key": res["key"]}
            #     else:
            #         self.secure_storage["tags"][uid]["key"] = res["key"]
            #     self.write_secure_storage()

            return res

    def update_title_bar(self, message: str):
        if not "None" in message and len(message) > 0:
            self.setWindowTitle(f"{message}")
        else:
            self.setWindowTitle(APP_TITLE)

    def set_tag_name(self):
        # Prompt for the tag name using QInputDialog
        tag_name, ok = QInputDialog.getText(
            self, "Set Tag Name", "Enter the tag name:", QLineEdit.Normal
        )
        if ok and tag_name:
            if not self.secure_storage["tags"].get(self.nfc_thread.current_uid):
                self.secure_storage["tags"][self.nfc_thread.current_uid] = {
                    "name": self.nfc_thread.current_uid,
                    "key": (
                        DEFAULT_KEY
                        if self.config["known_tags"].get(self.nfc_thread.current_uid)
                        else None
                    ),
                }
            # Process the tag name (store it, set it, etc.)
            self.secure_storage["tags"][self.nfc_thread.current_uid]["name"] = tag_name
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
            uid = self.nfc_thread.current_uid
            if not self.secure_storage["tags"].get(uid):
                self.secure_storage["tags"][uid] = {
                    "name": uid,
                    "key": DEFAULT_KEY if self.config["known_tags"].get(uid) else None,
                }
            self.secure_storage["tags"][uid]["key"] = tag_key
            self.config["known_tags"][uid] = DEFAULT_KEY == tag_key
            self.write_secure_storage()
            self.write_config()
            self.nfc_thread.key = tag_key
            self.on_operation_complete(
                True,
                f"{self.secure_storage["tags"][uid]["name"]}'s saved key is now: {tag_key}",
            )

    def change_tag_key(self):
        dialog = HexInputDialog(
            title="☠️ Change Your Key ☠️",
            initial_value=self.nfc_thread.key,
            fixed_byte_counts=[16, 24],
            parent=self,
        )
        dialog.exec_()

        results = dialog.get_results()
        if results:
            self.nfc_thread.change_key(results)

    def quit_app(self):

        QApplication.instance().quit()

    def prompt_setup(self):
        def initialize_and_accept():
            method = self.secure_storage_dialog.method_selector.currentText()
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

        dialog = QDialog(self)
        layout = QFormLayout()
        layout.addWidget(QLabel("Select encryption method:"))
        dialog.method_selector = QComboBox()
        dialog.method_selector.addItems(["keyring", "gpg"])
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
                self.nfc_thread.pause()
                time.sleep(0.15)
                self.secure_storage_instance.load()
                self.nfc_thread.resume()
            else:
                self.secure_storage = None
        else:
            self.secure_storage = None

    def write_secure_storage(self):
        if not self.secure_storage_instance:
            return
        self.nfc_thread.pause()
        time.sleep(0.15)
        self.secure_storage_instance.save()
        self.nfc_thread.resume()

    def load_config(self):

        if os.path.exists("config.json"):
            with open("config.json", "r") as fh:
                config = json.load(fh)

                fh.close()
                # todo: validate

            # Did I update something? Let's make sure the config is updated.
            key_added = False
            for key in DEFAULT_CONFIG.keys():
                if config.get(key) is None:
                    config[key] = DEFAULT_CONFIG[key]
                    key_added = True

            if key_added:
                self.write_config()

            return config
        else:
            # create default
            with open("config.json", "w") as fh:
                json.dump(DEFAULT_CONFIG, fh, indent=4)

            return DEFAULT_CONFIG

    def write_config(self):
        with open("config.json", "w") as fh:
            json.dump(self.config, fh, indent=4)
            fh.close()

    def update_known_tags(self, uid: str, default_key: bool | str):
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
                self.write_secure_storage()
                self.message_queue.add_message(
                    f"Updated {self.secure_storage["tags"][uid]["name"]} to known tags. Default key: {default_key}"
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

                # # Handle out secure storage.
                # if self.secure_storage is not None:
                #     if self.secure_storage["tags"].get(uid):
                #         if not self.secure_storage["tags"].get(uid):
                #             self.secure_storage["tags"][uid] = {
                #                 "name": uid,
                #                 "key": None,
                #             }
                #         # This is designed to catch key rejections
                #         if (
                #             not default_key
                #             and self.secure_storage["tags"]["key"] == DEFAULT_KEY
                #         ):
                #             self.secure_storage["tags"][uid]["tags"] = None
                # elif default_key and self.secure_storage["tags"]["key"] != DEFAULT_KEY:
                #     self.secure_storage["tags"][uid]["key"] = DEFAULT_KEY

        self.write_config()
        if self.secure_storage:
            self.write_secure_storage()

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


class KeyDialog(QDialog):
    def __init__(self, uid: str, exiting_key=None, is_new=True):
        super().__init__()
        if is_new:
            dialog_title = "New Smart Card Found!"
        else:
            dialog_title = "Update Smart Card Key"

        self.setWindowTitle(dialog_title)
        layout = QFormLayout()

        self.uid = uid

        self.label = QLabel("Enter key:")
        layout.addRow(self.label)

        self.input_field = QLineEdit()

        if exiting_key is None or exiting_key != "None":
            self.input_field.setText(DEFAULT_KEY)
        else:
            self.input_field.setText(exiting_key)
        layout.addRow(self.input_field)

        self.reset = QPushButton("Reset to Default")
        self.reset.clicked.connect(self.set_input_to_default)

        self.submit = QPushButton("OK")
        self.submit.clicked.connect(self.accept)

        layout.addRow(self.reset, self.submit)
        self.setLayout(layout)
        self.setFixedWidth(800)

    def get_input(self):
        return self.input_field.text()

    def get_results(self):
        return {"uid": self.uid, "key": self.input_field.text()}

    def set_input_to_default(self):
        self.input_field.setText(DEFAULT_KEY)


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
        f"{x["keyid"]} ({x["uids"][0]})": {
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


class ComboDialog(QDialog):
    def __init__(
        self,
        options,
        on_accept,
        on_cancel,
        parent=None,
        window_title="Select Option",
        combo_label="Choose an Option",
    ):
        super().__init__(parent)
        self.setWindowTitle(window_title)

        self.on_accept = on_accept
        self.on_cancel = on_cancel

        layout = QVBoxLayout(self)

        self.combo = QComboBox()
        self.combo.addItems(options)
        layout.addWidget(QLabel(combo_label))
        layout.addWidget(self.combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.handle_accept)
        buttons.rejected.connect(self.handle_cancel)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self.setModal(True)  # Halts app while this is open

    def handle_accept(self):
        selected = self.combo.currentText()
        self.on_accept(self, selected)
        self.accept()

    def handle_cancel(self):
        self.on_cancel()
        self.reject()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(resource_path("favicon.ico")))

    font = QFont("Courier New", 10)
    app.setFont(font)

    window = GPManagerApp()
    window.show()
    sys.exit(app.exec_())
