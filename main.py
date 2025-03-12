# main.py
import sys
import os
import requests
import importlib

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QComboBox, QHBoxLayout, QGridLayout, QProgressBar,
    QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer

from file_thread import FileHandlerThread
from nfc_thread import NFCHandlerThread

# ---------- Your dictionaries (unchanged) ----------
file_to_aid = {
    "FIDO2.cap": "A0000006472F000101",
    "javacard-memory.cap": "A0000008466D656D6F727901",
    "keycard.cap": "A0000008040001",
    "openjavacard-ndef-full.cap": "D2760000850101",
    "SatoChip.cap": "5361746F4368697000",
    "Satodime.cap": "5361746F44696D6500",
    "SeedKeeper.cap": "536565644B656570657200",
    "SmartPGPApplet-default.cap": "D276000124010304000A000000000000",
    "SmartPGPApplet-large.cap": "D276000124010304000A000000000000",
    "U2FApplet.cap": "A0000006472F0002",
    "vivokey-otp.cap": "A0000005272101014150455801",
    "YkHMACApplet.cap": "A000000527200101",
    "PivApplet.cap": "A000000308000010000100"
}

unsupported_apps = [
    "FIDO2.cap",
    "openjavacard-ndef-tiny.cap",
    "keycard.cap"
]

def fetch_latest_release_assets(owner="DangerousThings", repo="flexsecure-applets"):
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    assets = data.get("assets", [])
    results = {}
    for asset in assets:
        name = asset["name"]
        download_url = asset["browser_download_url"]
        results[name] = download_url
    return results

# ---------- Step 1: A base plugin check (optional) ----------
# We'll assume you have a "base_plugin.py" with a class "BaseAppletPlugin"
# from which each plugin inherits.

try:
    from base_plugin import BaseAppletPlugin
except ImportError:
    # If you haven't created base_plugin.py yet, this is just a placeholder
    class BaseAppletPlugin:  # dummy fallback
        pass

def load_plugins():
    """
    Scan the /repos folder for subfolders, then .py files,
    looking for classes that subclass BaseAppletPlugin.
    Returns a dict plugin_map: { plugin_name: plugin_class }
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
            # Look for .py files
            for fname in os.listdir(repo_path):
                print(fname)
                if fname.endswith(".py") and not fname.startswith("__"):
                    mod_name = fname[:-3]  # strip .py
                    full_mod_path = f"repos.{repo_name}.{mod_name}"
                    try:
                        mod = importlib.import_module(full_mod_path)
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
                        print(f"Error importing {full_mod_path}: {e}")
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

        self.status_label = QLabel("Checking for readers...")
        self.layout.addWidget(self.status_label)
        self.message_queue = MessageQueue(self.status_label)

        h_line = QFrame()
        h_line.setFrameShape(QFrame.HLine)
        h_line.setFrameShadow(QFrame.Sunken)
        self.layout.addWidget(h_line)

        # Reader selection
        reader_layout = QHBoxLayout()
        self.reader_dropdown = QComboBox()
        self.reader_dropdown.currentIndexChanged.connect(self.on_reader_select)
        reader_layout.addWidget(QLabel("Reader:"))
        reader_layout.addWidget(self.reader_dropdown)
        self.layout.addLayout(reader_layout)

        # Lists: Installed / Available
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

        self.download_bar = QProgressBar()
        self.download_bar.setRange(0, 100)
        self.download_bar.setValue(0)
        self.download_bar.hide()
        self.layout.addWidget(self.download_bar)

        self.setLayout(self.layout)

        # ----------------------------
        # Fetch from GitHub
        # ----------------------------
        try:
            self.available_apps_info = fetch_latest_release_assets(
                owner="DangerousThings",
                repo="flexsecure-applets"
            )
        except Exception as e:
            self.available_apps_info = {}
            self.message_queue.add_message(f"Error fetching latest release: {e}")

        # Populate
        self.populate_available_list()

        # Start NFC thread
        self.nfc_thread = NFCHandlerThread()
        self.nfc_thread.readers_updated.connect(self.update_readers)
        self.nfc_thread.card_present.connect(self.update_card_presence)
        self.nfc_thread.status_update.connect(self.process_nfc_status)
        self.nfc_thread.operation_complete.connect(self.on_operation_complete)
        self.nfc_thread.installed_apps_updated.connect(self.on_installed_apps_updated)
        self.nfc_thread.start()

        # No valid card at first
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)

        # ---------- Step 2: Load all plugins ----------
        self.plugin_map = load_plugins()
        if self.plugin_map:
            print("Loaded plugins:", list(self.plugin_map.keys()))
        else:
            print("No plugins found or repos folder missing.")

    def populate_available_list(self):
        self.available_list.clear()
        recognized_filenames = set(file_to_aid.keys())
        for cap_name, download_url in self.available_apps_info.items():
            # Skip unsupported or unknown
            if cap_name in unsupported_apps:
                continue
            if cap_name not in recognized_filenames:
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

    # Shared "fetch file" approach
    def fetch_file(self, app_name, on_complete):
        if app_name not in self.available_apps_info:
            self.message_queue.add_message(f"No download URL for {app_name}")
            return

        download_url = self.available_apps_info[app_name]
        self.downloader = FileHandlerThread(app_name, download_url)
        self.downloader.download_progress.connect(self.on_download_progress)
        self.downloader.download_complete.connect(on_complete)
        self.downloader.download_error.connect(self.on_download_error)

        self.download_bar.setValue(0)
        self.download_bar.show()
        self.downloader.start()

        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)

    # ---------- Step 3: Installing with optional plugin ----------
    def install_app(self):
        selected_items = self.available_list.selectedItems()
        if not selected_items:
            return

        app_name = selected_items[0].text()

        # Check if we have a plugin for this app
        plugin_name = app_name.replace(".cap", "")  # e.g. "openjavacard-ndef-full"
        if plugin_name in self.plugin_map:
            # We have a plugin
            plugin_class = self.plugin_map[plugin_name]
            plugin = plugin_class()

            # Pre-install step if needed
            try:
                plugin.pre_install(nfc_thread=self.nfc_thread)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Pre-install error: {e}")
                return

            # Show the plugin's dialog
            dlg = plugin.create_dialog(self)
            if dlg.exec_() == dlg.Accepted:
                # They pressed OK
                self.plugin_result = plugin.get_result()
                # Now proceed with normal download + gp install
                self.fetch_file(app_name, self.on_install_download_complete)
                # We'll also do plugin.post_install after the gp install
                # inside on_operation_complete or after the install
                self.current_plugin = plugin
            else:
                # User canceled
                return
        else:
            # No plugin => just normal flow
            self.fetch_file(app_name, self.on_install_download_complete)
            self.current_plugin = None

    def on_install_download_complete(self, file_path):
        self.download_bar.setValue(100)
        self.download_bar.hide()
        self.message_queue.add_message(f"Download complete: {file_path}")

        # Kick off install
        self.nfc_thread.install_app(file_path)

    def on_download_progress(self, percent):
        self.download_bar.setValue(percent)

    def on_download_error(self, error_msg):
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.install_button.setEnabled(True)
        self.uninstall_button.setEnabled(True)
        self.message_queue.add_message(error_msg)

    # ---------- Uninstall by CAP approach (with fallback) ----------
    def uninstall_app(self):
        selected_items = self.installed_list.selectedItems()
        if not selected_items:
            return

        app_name = selected_items[0].text()
        # If the user sees "Unknown: ..." we can't do a .cap-based approach
        if app_name.startswith("Unknown: "):
            # fallback just remove by AID
            raw_aid = app_name.split("Unknown: ", 1)[1]
            self.nfc_thread.uninstall_app(raw_aid)
            return

        # If we have a plugin
        plugin_name = app_name.replace(".cap", "")
        if plugin_name in self.plugin_map:
            plugin_class = self.plugin_map[plugin_name]
            plugin = plugin_class()
            try:
                plugin.pre_install()  # or pre_uninstall if you have that
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Pre-uninstall error: {e}")
                return
            # Possibly show a config dialog if needed

            # Then do a .cap-based uninstall
            self.fetch_file(app_name, self.on_uninstall_download_complete)
            self.current_plugin = plugin
        else:
            # no plugin => fallback by AID
            fallback_aid = file_to_aid.get(app_name)
            if fallback_aid:
                self.nfc_thread.uninstall_app(fallback_aid)
            else:
                self.message_queue.add_message(f"No known AID for {app_name}")

    def on_uninstall_download_complete(self, file_path):
        self.download_bar.setValue(100)
        self.download_bar.hide()
        self.message_queue.add_message(f"Download complete: {file_path}")

        # fallback_aid from file_to_aid
        base = os.path.basename(file_path)
        fallback_aid = file_to_aid.get(base)
        self.nfc_thread.uninstall_app_by_cap(file_path, fallback_aid=fallback_aid)

    def on_operation_complete(self, success, message):
        self.message_queue.add_message(message)
        self.install_button.setEnabled(True)
        self.uninstall_button.setEnabled(True)

        # If we have a plugin and success, call post_install
        if success and getattr(self, "current_plugin", None):
            try:
                self.current_plugin.post_install()
            except Exception as e:
                self.message_queue.add_message(f"Post-install error: {e}")

            # Clear
            self.current_plugin = None

    def on_installed_apps_updated(self, installed_aids):
        """
        installed_aids may be a dict or list, depending on your NFC thread implementation.
        If it's a list, we keep the old approach; if it's a dict, adapt accordingly.
        """
        self.installed_list.clear()

        reversed_aid_map = {}
        for filename, aid in file_to_aid.items():
            norm = aid.replace(" ", "").upper()
            reversed_aid_map[norm] = filename

        displayed_filenames = set()

        # if installed_aids is a list of AIDs
        for raw_aid in installed_aids:
            norm_aid = raw_aid.replace(" ", "").upper()
            if norm_aid in reversed_aid_map:
                display_text = reversed_aid_map[norm_aid]
            else:
                display_text = f"Unknown: {raw_aid}"
            self.installed_list.addItem(display_text)
            displayed_filenames.add(display_text)

        # Remove from available if installed
        to_remove = []
        for i in range(self.available_list.count()):
            item_text = self.available_list.item(i).text()
            if item_text in displayed_filenames:
                to_remove.append(item_text)

        for r in to_remove:
            matches = self.available_list.findItems(r, Qt.MatchExactly)
            for m in matches:
                self.available_list.takeItem(self.available_list.row(m))

    def closeEvent(self, event):
        self.nfc_thread.stop()
        self.nfc_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GPManagerApp()
    window.show()
    sys.exit(app.exec_())
