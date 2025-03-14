# main.py
import sys
import os
import tempfile
import importlib

from PyQt5.QtGui import QFontMetrics
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
    QPlainTextEdit,
)
from PyQt5.QtCore import Qt, QTimer, QSize, QObject, QEvent

from file_thread import FileHandlerThread
from nfc_thread import NFCHandlerThread

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
    E.g. { "flexsecure-applets": <class FlexsecureAppletsPlugin>, ... }
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


class GPManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlobalPlatformPro App Manager")
        self.resize(800, 600)
        self.layout = QVBoxLayout()

        # Status label at the top
        self.status_label = QLabel("Checking for readers...")
        self.layout.addWidget(self.status_label)
        self.message_queue = MessageQueue(self.status_label)

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

        self.layout.addLayout(grid_layout)

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
        for plugin_name, plugin_cls in self.plugin_map.items():
            plugin_instance = plugin_cls()
            caps = plugin_instance.fetch_available_caps()  # e.g. {cap_name: url}
            for cap_n, url in caps.items():
                # If there's a conflict, you can decide whether to overwrite or skip
                self.available_apps_info[cap_n] = (plugin_name, url)

        #
        # 3) Populate the "Available Apps" list from self.available_apps_info,
        #    skipping unsupported apps
        #
        self.populate_available_list()

        #
        # 4) Start NFC handler
        #
        self.nfc_thread = NFCHandlerThread()
        self.nfc_thread.readers_updated.connect(self.update_readers)
        self.nfc_thread.card_present.connect(self.update_card_presence)
        self.nfc_thread.status_update.connect(self.process_nfc_status)
        self.nfc_thread.operation_complete.connect(self.on_operation_complete)
        self.nfc_thread.installed_apps_updated.connect(self.on_installed_apps_updated)
        self.nfc_thread.start()

        # Initially disable install/uninstall
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)
        self.current_plugin = None

    def populate_available_list(self):
        self.available_list.clear()
        for cap_name, (plugin_name, url) in self.available_apps_info.items():
            if cap_name in unsupported_apps or cap_name in self.installed_app_names:
                continue
            self.available_list.addItem(cap_name)

    def on_reader_select(self, index):
        reader_name = self.reader_dropdown.itemText(index)
        self.nfc_thread.selected_reader_name = reader_name

    def update_readers(self, readers_list):
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
                self.install_button.setEnabled(True)
                self.uninstall_button.setEnabled(True)
                self.message_queue.add_message("Compatible card detected.")
                installed = self.nfc_thread.get_installed_apps()
                self.on_installed_apps_updated(installed)
            else:
                self.install_button.setEnabled(False)
                self.uninstall_button.setEnabled(False)
                self.message_queue.add_message("Unsupported card detected.")
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
            self.message_queue.add_message(f"Using cached: {local_path}")
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
        self.message_queue.add_message(err_msg)

    #
    #  Install Flow
    #
    def install_app(self):
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
            # No plugin found => unexpected in this design, but we handle gracefully
            self.current_plugin = None
            self.fetch_file(cap_name, self.on_install_download_complete)

    def on_install_download_complete(self, file_path, params=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.message_queue.add_message(f"Installing: {file_path}")
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
            self.message_queue.add_message(f"No plugin found for {cap_name}")

    def on_uninstall_download_complete(self, file_path, params=None):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.message_queue.add_message(f"Uninstalling with {file_path}")

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
    def on_operation_complete(self, success, message):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.install_button.setEnabled(True)
        self.uninstall_button.setEnabled(True)

        self.message_queue.add_message(message)
        if success and self.current_plugin:
            try:
                self.current_plugin.post_install()
            except Exception as e:
                self.message_queue.add_message(f"Post-install error: {e}")

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
            # You might want version = installed_aids[raw_aid] if you need it
            version = installed_aids[raw_aid]

            norm = raw_aid.replace(" ", "").upper()
            matched_plugin_name = None
            matched_cap = None

            # The rest of your logic, same as before
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

    #
    #  Utility
    #
    def closeEvent(self, event):
        self.nfc_thread.stop()
        self.nfc_thread.wait()
        event.accept()


def horizontal_rule():
    h_line = QFrame()
    h_line.setFrameShape(QFrame.HLine)
    h_line.setFrameShadow(QFrame.Sunken)

    return h_line


class FocusFilter(QObject):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        print("event filter")
        print(event.type())
        if event.type() == QEvent.FocusOut:
            self.callback()
        return super().eventFilter(obj, event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GPManagerApp()
    window.show()
    sys.exit(app.exec_())
