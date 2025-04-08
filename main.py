# main.py
import json
import sys
import os
import tempfile
import importlib
import textwrap
import time

import markdown
from PyQt5.QtGui import QIcon, QFont, QMouseEvent
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
)
from PyQt5.QtCore import QTimer, QObject, QEvent, Qt, QSize

from file_thread import FileHandlerThread
from nfc_thread import NFCHandlerThread, resource_path, DEFAULT_KEY

APP_TITLE = "GlobalPlatformPro App Manager"

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


width_height = [800, 600]
if os.name == "nt":
    width_height = [2 * x for x in width_height]


class GPManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(resource_path("favicon.ico")))

        self.layout = QVBoxLayout()

        # Status label at the top
        self.status_label = QLabel("Checking for readers...")
        self.layout.addWidget(self.status_label)
        self.message_queue = MessageQueue(self.status_label)

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
        self.installed_list.currentItemChanged.connect(self.show_details_pane)
        self.available_list.currentItemChanged.connect(self.show_details_pane)

        self.layout.addLayout(self.apps_grid_layout)

        # Progress bar for downloads
        self.download_bar = QProgressBar()
        self.download_bar.hide()
        self.layout.addWidget(self.download_bar)

        self.setLayout(self.layout)

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
        for plugin_name, plugin_cls in self.plugin_map.items():
            plugin_instance = plugin_cls()
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

        #
        # 3) Populate the "Available Apps" list from self.available_apps_info,
        #    skipping unsupported apps
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

        is_installed_apps = False
        is_showing_details = False

        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(True)
        viewer.setHtml(
            markdown.markdown(textwrap.dedent(self.app_descriptions[selected_app]))
        )

        if (
            not self.apps_grid_layout.itemAtPosition(1, 0).widget()
            == self.installed_list
            and not is_installed_apps
        ) or (
            not self.apps_grid_layout.itemAtPosition(1, 1).widget()
            == self.available_list
            and is_installed_apps
        ):
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

    def update_plugin_releases(self):
        self.message_queue.add_message("Fetching latest plugin releases...")
        updated = False
        for plugin_name, plugin_cls in self.plugin_map.items():
            plugin_instance = plugin_cls()
            caps = plugin_instance.fetch_available_caps()

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
                if self.nfc_thread.key is not None:
                    self.install_button.setEnabled(True)
                    self.uninstall_button.setEnabled(True)
                    installed = self.nfc_thread.get_installed_apps()
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
        # Is the details pane open?
        if (
            not self.apps_grid_layout.itemAtPosition(1, 1).widget()
            == self.installed_list
        ):
            self.handle_details_pane_back()  # close it if so

        selected = self.available_list.selectedItems()
        if not selected:
            return
        cap_name = selected[0].text()

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
        if cap_name.startswith("Unknown: "):
            raw_aid = cap_name.split("Unknown: ", 1)[1]
            self.nfc_thread.uninstall_app(raw_aid)
            return

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
        self.nfc_thread.stop()
        self.nfc_thread.wait()
        event.accept()

    def show_error_dialog(self, message: str):
        QMessageBox.critical(self, "Error", message, QMessageBox.Ok)

    def get_key(self, uid):
        is_default_key = self.config["known_tags"].get(uid, None)
        if is_default_key:
            self.nfc_thread.key_setter_signal.emit(DEFAULT_KEY)
            self.nfc_thread.status_update_signal.emit("Key set.")
            self.update_card_presence(True)

        else:
            if is_default_key is None:
                res = self.prompt_for_key(uid)
            else:
                # TODO: check secure storage for key
                res = self.prompt_for_key(uid, "sds")

            if res and res.get("key", False) is False:
                self.show_error_dialog("No key found.")
            elif res is None:
                return
            else:
                self.nfc_thread.key_setter_signal.emit(res["key"])
                self.update_card_presence(True)
                self.nfc_thread.status_update_signal.emit("Key set.")

    def prompt_for_key(self, uid: str, existing_key: str = None):
        dialog = KeyDialog(uid=uid, exiting_key=existing_key)  # No existing key
        if dialog.exec_():  # Show dialog and wait for user action
            res = dialog.get_results()

            if not self.config["known_tags"].get(res["uid"]):
                self.config["known_tags"][res["uid"]] = None
            self.update_known_tags(res["uid"], res["key"] == DEFAULT_KEY)

            return res

    def update_title_bar(self, message: str):
        if not "None" in message and len(message) > 0:
            self.setWindowTitle(f"{message}")
        else:
            self.setWindowTitle(APP_TITLE)

    def load_config(self):
        """
        [dict[str, bool]] known_keys:
            [bool] uid:str - if the UID uses a default key, true, else false
        [bool] cache_latest_release=False
        """
        default_config = {
            "cache_latest_release": False,
            # [app]: epoch time
            "last_checked": {},
            "known_tags": {},
            "window": {
                "height": width_height[1],
                "width": width_height[0],
                # "font_size": ""
            },
        }
        if os.path.exists("config.json"):
            with open("config.json", "r") as fh:
                config = json.load(fh)

                fh.close()
                # todo: validate

            # Did I update something? Let's make sure the config is updated.
            key_added = False
            for key in default_config.keys():
                if config.get(key) is None:
                    config[key] = default_config[key]
                    key_added = True

            return config
        else:
            # create default
            with open("config.json", "w") as fh:
                json.dump(default_config, fh, indent=4)

            return default_config

    def write_config(self):
        with open("config.json", "w") as fh:
            json.dump(self.config, fh, indent=4)
            fh.close()

    def update_known_tags(self, uid: str, default_key: bool):
        if self.config["known_tags"].get(uid) is None:
            self.config["known_tags"][uid] = default_key
            self.message_queue.add_message(
                f"Added {uid} to known tags. Default key: {default_key}"
            )
        else:
            if self.config["known_tags"][uid] != default_key:
                self.config["known_tags"][uid] = default_key
                self.message_queue.add_message(
                    f"Updated {uid}. Default key: {default_key}"
                )
        self.write_config()

    def query_known_tags(self, uid: str) -> bool:
        """
        Returns a bool if the tag is known
        - The bool indicates whether it has a default key
        Returns None when the tag is not known
        """
        default_key = self.config["known_tags"].get(uid, False)
        return default_key

    def resizeEvent(self, event):
        new_size = event.size()

        self.on_resize(new_size)
        super().resizeEvent(event)

    def on_resize(self, size: QSize):
        self.config["window"]["width"] = size.width()
        self.config["window"]["height"] = size.height()

        self.write_config()


class KeyDialog(QDialog):
    def __init__(self, uid: str, exiting_key=None):
        super().__init__()
        if exiting_key is None or exiting_key != "None":
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


def horizontal_rule():
    h_line = QFrame()
    h_line.setFrameShape(QFrame.HLine)
    h_line.setFrameShadow(QFrame.Sunken)

    return h_line


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(resource_path("favicon.ico")))

    font = QFont("Courier New", 10)
    app.setFont(font)

    window = GPManagerApp()
    window.show()
    sys.exit(app.exec_())
