import sys
import os

import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QComboBox, QHBoxLayout, QGridLayout, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer

# Our custom threads
from file_thread import FileHandlerThread
from nfc_thread import NFCHandlerThread

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
    response.raise_for_status()  # Raises an HTTPError for bad responses
    data = response.json()
    assets = data.get("assets", [])
    results = {}
    for asset in assets:
        name = asset["name"]
        download_url = asset["browser_download_url"]
        results[name] = download_url
    return results

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
        # E.g. 3 seconds minimum, scaled by message length
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

        # Reader selection UI setup
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
        # Fetch the single repo's latest release assets from GitHub
        # Wrap in a try/except in case user has no internet or GH is unavailable
        # ----------------------------
        try:
            self.available_apps_info = fetch_latest_release_assets(
                owner="DangerousThings",
                repo="flexsecure-applets"
            )
        except Exception as e:
            self.available_apps_info = {}
            self.message_queue.add_message(f"Error fetching latest release: {e}")

        # Populate the Available list
        self.populate_available_list()

        # Create and start the NFCHandlerThread
        self.nfc_thread = NFCHandlerThread()
        self.nfc_thread.readers_updated.connect(self.update_readers)
        self.nfc_thread.card_present.connect(self.update_card_presence)
        self.nfc_thread.status_update.connect(self.process_nfc_status)
        self.nfc_thread.operation_complete.connect(self.on_operation_complete)
        self.nfc_thread.installed_apps_updated.connect(self.on_installed_apps_updated)
        self.nfc_thread.start()

        # Disable install/uninstall until a valid card is detected
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)

    def populate_available_list(self):
        """Clear and fill the 'Available Apps' list from self.available_apps_info,
           skipping unsupported or unknown apps."""
        self.available_list.clear()

        # For convenience, get the recognized filenames from file_to_aid
        recognized_filenames = set(file_to_aid.keys())

        for cap_name, download_url in self.available_apps_info.items():
            # Skip if in unsupported list:
            if cap_name in unsupported_apps:
                continue

            # Skip if we don't have a mapping in file_to_aid
            # (meaning we won't be able to install/uninstall properly)
            if cap_name not in recognized_filenames:
                continue

            # Otherwise, it's supported and recognized
            self.available_list.addItem(cap_name)

    def on_reader_select(self, index):
        """Called when user picks a reader from the dropdown."""
        reader_name = self.reader_dropdown.itemText(index)
        self.nfc_thread.selected_reader_name = reader_name

    def update_readers(self, readers_list):
        """Called by NFCHandlerThread.readers_updated."""
        self.reader_dropdown.blockSignals(True)
        self.reader_dropdown.clear()

        if not readers_list:
            # No readers
            self.reader_dropdown.setDisabled(True)
            self.nfc_thread.selected_reader_name = None
            self.message_queue.add_message("No readers found.")
            self.install_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.reader_dropdown.blockSignals(False)
            return

        # If we have readers, enable the dropdown
        self.reader_dropdown.setEnabled(True)
        self.reader_dropdown.addItems(readers_list)

        # If our currently selected reader is missing, pick the first
        if self.nfc_thread.selected_reader_name not in readers_list:
            self.nfc_thread.selected_reader_name = readers_list[0]
            self.reader_dropdown.setCurrentIndex(0)
        else:
            idx = readers_list.index(self.nfc_thread.selected_reader_name)
            self.reader_dropdown.setCurrentIndex(idx)

        self.reader_dropdown.blockSignals(False)

    def update_card_presence(self, present):
        """Called by NFCHandlerThread.card_present(True/False)."""
        if present:
            # If the NFC thread says the card is valid, enable install/uninstall
            if self.nfc_thread.valid_card_detected:
                self.install_button.setEnabled(True)
                self.uninstall_button.setEnabled(True)
                self.message_queue.add_message("Compatible card detected.")
                # Optionally, retrieve installed apps as soon as card is inserted
                installed = self.nfc_thread.get_installed_apps()
                self.on_installed_apps_updated(installed)
            else:
                self.install_button.setEnabled(False)
                self.uninstall_button.setEnabled(False)
                self.message_queue.add_message("Unsupported card detected.")
        else:
            # No card
            self.install_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
            self.message_queue.add_message("No card present.")

    def process_nfc_status(self, status):
        """
        Called when the NFC thread wants to display a status update
        (UID, Memory status, errors, etc.).
        """
        self.message_queue.add_message(status)

    def fetch_file(self, on_complete):
        selected_items = self.installed_list.selectedItems()
        if not selected_items:
            return

        app_name = selected_items[0].text()  # e.g. "ExampleApp.cap"
        if app_name not in self.available_apps_info:
            self.message_queue.add_message(f"No download URL for {app_name}")
            return

        download_url = self.available_apps_info[app_name]

        # Create a one-shot FileHandlerThread to download the .cap
        self.downloader = FileHandlerThread(app_name, download_url)
        self.downloader.download_progress.connect(self.on_download_progress)
        self.downloader.download_complete.connect(on_complete)
        self.downloader.download_error.connect(self.on_download_error)

        self.download_bar.setValue(0)
        self.download_bar.show()
        self.downloader.start()

        # Disable install button until the download + install are done
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)

    def install_app(self):
        """User clicked 'Install' for the selected item in 'Available Apps'."""
        # Disable install button until the download + install are done
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)
        self.fetch_file(self.on_download_complete)

    def on_download_progress(self, percent):
        """Update progress bar from FileHandlerThread."""
        self.download_bar.setValue(percent)

    def on_download_complete(self, file_path):
        """
        Called when FileHandlerThread finishes.
        'file_path' is the local path to the downloaded .cap file.
        """
        self.download_bar.setValue(100)
        self.download_bar.hide()
        self.message_queue.add_message(f"Download complete: {file_path}")

        # Now call the NFCHandlerThread install method
        # This does not block the UI, because NFCHandlerThread is a QThread.
        self.nfc_thread.install_app(file_path)

    def on_uninstall_download_complete(self, file_path):
        """
        Called when FileHandlerThread finishes.
        'file_path' is the local path to the downloaded .cap file.
        """
        self.download_bar.setValue(100)
        self.download_bar.hide()
        self.message_queue.add_message(f"Download complete: {file_path}")

        fallback_aid = file_to_aid[file_path.split(os.sep)[-1]]
        # Now call the NFCHandlerThread install method
        self.nfc_thread.uninstall_app_by_cap(file_path, fallback_aid=fallback_aid)

    def on_download_error(self, error_msg):
        """Called if FileHandlerThread fails."""
        self.download_bar.hide()
        self.download_bar.setValue(0)
        self.install_button.setEnabled(True)  # let user try again
        self.message_queue.add_message(error_msg)

    def uninstall_app(self):
        """
        Uninstalls are handled by cap to ensure a clean process--falls back to AID.
        :return:
        """
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)
        self.fetch_file(self.on_uninstall_download_complete)

    def on_operation_complete(self, success, message):
        """Called after an install/uninstall finishes in NFCHandlerThread."""
        self.message_queue.add_message(message)
        if success:
            self.install_button.setEnabled(True)
            self.uninstall_button.setEnabled(True)
        else:
            # Some error occurred
            self.install_button.setEnabled(True)
            self.uninstall_button.setEnabled(True)

    def on_installed_apps_updated(self, installed_aids):
        """
        Called after the NFCHandlerThread updates the installed AIDs
        (e.g. after install/uninstall).
        """
        self.installed_list.clear()

        # Build a reverse dict from AID -> cap filename
        reversed_aid_map = {}
        for filename, aid in file_to_aid.items():
            # Normalize each known AID by removing spaces & making uppercase
            normalized_aid = aid.replace(" ", "").upper()
            reversed_aid_map[normalized_aid] = filename

        # Collect the "human-readable" names we actually put into 'Installed Apps'
        displayed_filenames = set()

        for raw_aid in installed_aids:
            # e.g. "A0000008466D656D6F727901"
            norm_aid = raw_aid.replace(" ", "").upper()

            if norm_aid in reversed_aid_map:
                # We recognize this AID from file_to_aid
                display_text = reversed_aid_map[norm_aid]
            else:
                # Not recognized => show "Unknown: {raw_aid}" so we see it in the list
                display_text = f"Unknown: {raw_aid}"

            self.installed_list.addItem(display_text)
            displayed_filenames.add(display_text)

        # Now remove these displayed filenames from the available list if they exist there
        # For example, if the card has an app "javacard-memory.cap" installed, remove it from
        # the "Available Apps" if present. If the name is "Unknown: ..." it likely won't be in
        # the available list, so nothing will be removed for that line.

        to_remove = []
        for i in range(self.available_list.count()):
            item_text = self.available_list.item(i).text()
            # If the item_text is one we just displayed as installed, remove from available
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