# Complete PyQt5 Refactor of Original main.py with Full Functionality and Correct Card Detection

import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QListWidget,
    QComboBox, QHBoxLayout, QMessageBox, QGridLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
import subprocess
import os
import platform
import requests
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException
from measure import get_memory


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
    "PivApplet": "A000000308000010000100"
}

unsupported_apps = ["FIDO2.cap", "openjavacard-ndef-tiny.cap", "keycard.cap"]

class CardDetectionThread(QThread):
    card_present = pyqtSignal(bool)
    readers_present = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.failure_count = 0
        self.failure_threshold = 3  # Only consider the card absent after 3 failures
        self.last_card_state = None

    def run(self):
        last_card_detected = None
        last_readers = []
        while True:
            try:
                available_readers = readers()
                readers_list = [str(reader) for reader in available_readers]
                if readers_list != last_readers:
                    self.readers_present.emit(readers_list)
                    last_readers = readers_list

                card_detected = False
                for reader in available_readers:
                    try:
                        connection = reader.createConnection()
                        connection.connect()
                        card_detected = True
                        break
                    except (NoCardException, CardConnectionException):
                        continue

                if card_detected:
                    self.failure_count = 0
                    if self.last_card_state != True:
                        self.card_present.emit(True)
                        self.last_card_state = True
                else:
                    self.failure_count += 1
                    if self.failure_count >= self.failure_threshold and self.last_card_state != False:
                        self.card_present.emit(False)
                        self.last_card_state = False

            except Exception:
                self.failure_count += 1
                if self.failure_count >= self.failure_threshold and self.last_card_state != False:
                    self.card_present.emit(False)
                    self.last_card_state = False

            self.msleep(1000)


class GPManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GlobalPlatformPro App Manager")
        self.resize(800, 600)
        self.layout = QVBoxLayout()

        self.os = platform.system()
        self.gp_command = "gp.exe" if self.os == "Windows" else "java -jar gp.jar"

        self.card_thread = CardDetectionThread()
        self.card_thread.card_present.connect(self.handle_card_presence)
        self.card_thread.readers_present.connect(self.update_readers)
        self.card_thread.start()

        reader_layout = QHBoxLayout()
        self.reader_dropdown = QComboBox()
        self.reader_dropdown.currentIndexChanged.connect(self.on_reader_selected)
        reader_layout.addWidget(QLabel("Reader:"))
        reader_layout.addWidget(self.reader_dropdown)
        self.layout.addLayout(reader_layout)

        self.status_label = QLabel("Starting...")
        self.layout.addWidget(self.status_label)

        grid_layout = QGridLayout()

        self.installed_list = QListWidget()
        grid_layout.addWidget(QLabel("Installed Apps"), 0, 0)
        grid_layout.addWidget(self.installed_list, 1, 0)

        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.clicked.connect(self.uninstall_app)
        grid_layout.addWidget(self.uninstall_button, 2, 0)

        self.available_list = QListWidget()
        grid_layout.addWidget(QLabel("Available Apps"), 0, 1)
        grid_layout.addWidget(self.available_list, 1, 1)

        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self.install_app)
        grid_layout.addWidget(self.install_button, 2, 1)

        self.layout.addLayout(grid_layout)
        self.setLayout(self.layout)

        self.fetch_available_apps()
        self.update_buttons(False)

    def update_buttons(self, enabled):
        self.install_button.setEnabled(enabled)
        self.uninstall_button.setEnabled(enabled)

    def is_jcop3(self):
        result = subprocess.run(
            self.gp_command.split() + ["--info"], capture_output=True, text=True
        )
        if len(result.stderr) == 0 or (len(result.stderr) > 0 and "WARN" in result.stderr):
            return any("JavaCard v3" in line for line in result.stdout.splitlines())
        return False

    def on_reader_selected(self):
        self.fetch_installed_apps()
        self.report_memory()

    def update_readers(self, readers_list):
        self.reader_dropdown.clear()
        self.reader_dropdown.addItems(readers_list)
        self.status_label.setText("Readers updated.")
        self.update_buttons(False)

    def handle_card_presence(self, present):
        if present and self.is_jcop3():
            self.status_label.setText("Compatible card detected.")
            self.fetch_installed_apps()
            self.report_memory()
            self.update_buttons(True)
        else:
            if self.card_thread.card_present:
                self.status_label.setText("No compatible card detected.")
            else:
                self.status_label.setText("No card present.")
            # self.installed_list.clear()
            self.update_buttons(False)

    def install_app(self):
        self.update_buttons(False)
        selected_items = self.available_list.selectedItems()
        if selected_items:
            app_name = selected_items[0].text()
            try:
                subprocess.run(self.gp_command.split() + ["--install", app_name], check=True)
                self.status_label.setText(f"{app_name} installed successfully.")
                self.fetch_installed_apps()
                self.available_list.takeItem(self.available_list.row(selected_items[0]))
                self.report_memory()
            except subprocess.CalledProcessError as e:
                self.status_label.setText(f"Error installing {app_name}: {e}")
        self.update_buttons(True)

    def uninstall_app(self):
        self.update_buttons(False)
        selected_items = self.installed_list.selectedItems()
        if selected_items:
            app_name = selected_items[0].text()
            try:
                subprocess.run(self.gp_command.split() + ["--uninstall", app_name], check=True)
                self.status_label.setText(f"{app_name} uninstalled successfully.")
                self.fetch_installed_apps()
                self.available_list.addItem(app_name)
                self.report_memory()
            except subprocess.CalledProcessError as e:
                self.status_label.setText(f"Error uninstalling {app_name}: {e}")
        self.update_buttons(True)

    def fetch_available_apps(self):
        self.available_list.clear()
        repo = "DangerousThings/flexsecure-applets"
        url = f"https://api.github.com/repos/{repo}/releases/latest"

        try:
            response = requests.get(url)
            if response.status_code == 200:
                release_data = response.json()
                cap_files = [
                    asset["browser_download_url"]
                    for asset in release_data.get("assets", [])
                    if asset["name"].endswith(".cap")
                ]

                self.available_apps = [link.split("/")[-1] for link in cap_files]
                self.available_apps = [link for link in self.available_apps if link not in unsupported_apps]

                self.available_list.addItems(self.available_apps)
                self.status_label.setText(f"Available apps fetched: {len(self.available_apps)}")
            else:
                self.status_label.setText("Failed to fetch available apps.")
        except Exception as e:
            self.status_label.setText(f"Error fetching apps: {str(e)}")

    def fetch_installed_apps(self):
        try:
            self.installed_list.clear()
            result = subprocess.run(self.gp_command.split() + ["-l"], capture_output=True, text=True)
            for app in result.stdout.splitlines():
                for file, aid in file_to_aid.items():
                    if aid in app and not self.installed_list.findItems(file, Qt.MatchExactly):
                        self.installed_list.addItem(file)
                        break
            self.status_label.setText("Installed apps updated.")
        except Exception as e:
            self.status_label.setText(f"Error fetching installed apps: {str(e)}")

    def report_memory(self):
        try:
            memory = get_memory()
            if memory:
                free = memory["persistent"]["free"] / 1024
                percent = memory["persistent"]["percent_free"] * 100
                self.status_label.setText(f"Memory Free: {free:.0f}kB ({percent:.0f}%)")
            else:
                self.status_label.setText("Unable to retrieve memory information.")
        except Exception as e:
            self.status_label.setText(f"Error fetching memory info: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GPManagerApp()
    window.show()
    sys.exit(app.exec_())
