import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException
from smartcard.util import toHexString
from measure import get_memory

class NFCHandlerThread(QThread):
    """
    Monitors the chosen reader for card presence.
    Provides methods for installing/uninstalling CAP files
    via GlobalPlatformPro. Can also list installed apps.
    """
    # Emitted whenever the list of readers changes
    readers_updated = pyqtSignal(list)

    # Emitted True/False when a card transitions from absent -> present or vice versa
    card_present = pyqtSignal(bool)

    # Emitted with status text you can show in your UI
    status_update = pyqtSignal(str)

    # Emitted upon successful or failed install/uninstall
    #   success (bool), message (str)
    operation_complete = pyqtSignal(bool, str)

    # Emitted with the updated list of AIDs after a successful install/uninstall
    installed_apps_updated = pyqtSignal(list)

    def __init__(self, selected_reader_name=None, parent=None):
        """
        :param selected_reader_name: The currently chosen reader (or None at start).
        """
        super().__init__(parent)
        self.selected_reader_name = selected_reader_name

        # Thread run loop control
        self.running = True

        # Track card state
        self.card_detected = False
        self.valid_card_detected = False
        self.current_uid = None

        # OS-specific gp command
        self.gp = {
            "nt":   ["gp.exe"],
            "posix": ["java", "-jar", "gp.jar"]
        }

    def run(self):
        """Main loop for detecting readers/cards. (Unchanged from your existing version.)"""
        last_readers = []
        timeout_duration = 3000  # ms

        while self.running:
            try:
                available_readers = readers()
                reader_names = [str(r) for r in available_readers]

                if reader_names != last_readers:
                    self.readers_updated.emit(reader_names)
                    last_readers = reader_names

                if not reader_names:
                    if self.card_detected:
                        self.card_detected = False
                        self.valid_card_detected = False
                        self.current_uid = None
                        self.card_present.emit(False)
                    self.status_update.emit("No readers found.")
                    self.msleep(timeout_duration)
                    continue

                if self.selected_reader_name in reader_names:
                    idx = reader_names.index(self.selected_reader_name)
                    reader = available_readers[idx]
                    uid = self.get_card_uid(reader)
                    if uid:
                        if not self.card_detected or uid != self.current_uid:
                            jcop3 = self.is_jcop3(self.selected_reader_name)
                            self.valid_card_detected = jcop3
                            self.card_detected = True
                            self.current_uid = uid
                            self.card_present.emit(True)
                            if jcop3:
                                mem = self.get_memory_status()
                                self.status_update.emit(f"UID: {uid} | {mem}")
                            else:
                                self.status_update.emit("Unsupported card detected.")
                    else:
                        if self.card_detected:
                            self.card_detected = False
                            self.valid_card_detected = False
                            self.current_uid = None
                            self.card_present.emit(False)
                            self.status_update.emit("No card present.")
                else:
                    if self.card_detected:
                        self.card_detected = False
                        self.valid_card_detected = False
                        self.current_uid = None
                        self.card_present.emit(False)
                        self.status_update.emit("No card present.")

                self.msleep(timeout_duration)

            except Exception as e:
                self.status_update.emit(f"Loop error: {e}")

    def stop(self):
        """Signal the loop to exit gracefully."""
        self.running = False

    # --------------------------
    #  Card / GP utility methods
    # --------------------------
    def get_card_uid(self, reader):
        """Retrieve card UID with [FF CA 00 00 00]."""
        try:
            GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
            connection = reader.createConnection()
            connection.connect()
            response, sw1, sw2 = connection.transmit(GET_UID)
            if (sw1, sw2) == (0x90, 0x00):
                return toHexString(response)
            return None
        except (NoCardException, CardConnectionException):
            return None

    def is_jcop3(self, reader_name):
        """Use gp --info to see if 'JavaCard v3' is in the output."""
        try:
            cmd = [*self.gp[os.name], "--info", "-r", reader_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return "JavaCard v3" in result.stdout
        except Exception as e:
            print(f"is_jcop3 error: {e}", flush=True)
            return False

    def get_memory_status(self):
        """Call measure.get_memory()."""
        try:
            memory = get_memory()
            if memory:
                free = memory['persistent']['free'] / 1024
                percent = memory['persistent']['percent_free'] * 100
                return f"Memory Free: {free:.0f}kB ({percent:.0f}%)"
            else:
                return "Memory Error"
        except Exception as e:
            return f"Memory Error: {e}"

    def get_installed_apps(self):
        """Parse 'APP:' lines from 'gp --list' to find installed AIDs."""
        if not self.selected_reader_name:
            self.status_update.emit("No reader selected for get_installed_apps.")
            return []

        try:
            cmd = [*self.gp[os.name], "--list", "-r", self.selected_reader_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.status_update.emit(f"Error listing apps: {result.stderr}")
                return []

            installed = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("APP:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        raw_aid = parts[1]
                        normalized = raw_aid.replace(" ", "").upper()
                        installed.append(normalized)
            return installed

        except Exception as e:
            self.status_update.emit(f"Exception listing apps: {e}")
            return []

    # ----------------------------
    #  Installation and Uninstall
    # ----------------------------
    def install_app(self, cap_file_path):
        """Install using 'gp --install <cap_file_path>'."""
        if not self.selected_reader_name:
            self.status_update.emit("No reader selected for install.")
            self.operation_complete.emit(False, "No reader selected.")
            return

        try:
            cmd = [*self.gp[os.name], "--install", cap_file_path, "-r", self.selected_reader_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.status_update.emit(f"Installed: {os.path.basename(cap_file_path)}")
                self.operation_complete.emit(True, f"Installed {cap_file_path}")
                installed = self.get_installed_apps()
                self.installed_apps_updated.emit(installed)
                mem = self.get_memory_status()
                uid = self.current_uid()
                self.status_update.emit(f"UID: {uid} | {mem}")
            else:
                err_msg = f"Install failed: {result.stderr}"
                self.status_update.emit(err_msg)
                self.operation_complete.emit(False, err_msg)
        except Exception as e:
            err_msg = f"Install error: {e}"
            self.status_update.emit(err_msg)
            self.operation_complete.emit(False, err_msg)
        finally:
            mem = self.get_memory_status()
            uid = self.current_uid()
            self.status_update.emit(f"UID: {uid} | {mem}")

    def uninstall_app(self, aid, force=False):
        """
        Uninstall by AID:
           gp --uninstall [--force?] <aid> -r <reader>
        """
        if not self.selected_reader_name:
            self.status_update.emit("No reader selected for uninstall.")
            self.operation_complete.emit(False, "No reader selected.")
            return

        try:
            cmd = [*self.gp[os.name], "--uninstall"]
            if force:
                cmd.append("-f")  # or '--force' if gp.jar uses that
            cmd.extend([aid, "-r", self.selected_reader_name])
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self.status_update.emit(f"Uninstalled AID: {aid}")
                self.operation_complete.emit(True, f"Uninstalled {aid}")
                installed = self.get_installed_apps()
                self.installed_apps_updated.emit(installed)
            else:
                err_msg = f"Uninstall by AID failed: {result.stderr}"
                self.status_update.emit(err_msg)
                self.operation_complete.emit(False, err_msg)

        except Exception as e:
            err_msg = f"Uninstall error (AID): {e}"
            self.status_update.emit(err_msg)
            self.operation_complete.emit(False, err_msg)
        finally:
            mem = self.get_memory_status()
            uid = self.current_uid()
            self.status_update.emit(f"UID: {uid} | {mem}")

    def uninstall_app_by_cap(self, cap_file_path, fallback_aid=None, force=False):
        """
        Attempt 'gp --uninstall <cap_file_path>' first.
        If that fails and fallback_aid is provided, try 'uninstall_app(aid=fallback_aid)' next.
        The 'force' param, if True, passes '-f' to gp (applies to both attempts).
        """
        if not self.selected_reader_name:
            self.status_update.emit("No reader selected for uninstall.")
            self.operation_complete.emit(False, "No reader selected.")
            return

        try:
            # Build the command:
            cmd = [*self.gp[os.name], "--uninstall"]
            if force:
                cmd.append("-f")
            cmd.extend([cap_file_path, "-r", self.selected_reader_name])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # success
                self.status_update.emit(f"Uninstalled CAP file: {os.path.basename(cap_file_path)}")
                self.operation_complete.emit(True, f"Uninstalled {cap_file_path}")
                installed = self.get_installed_apps()
                self.installed_apps_updated.emit(installed)
            else:
                # Fail => fallback to AID if provided
                err_msg = f"Uninstall by CAP file failed: {result.stderr}"
                self.status_update.emit(err_msg)

                if fallback_aid:
                    self.status_update.emit(
                        f"Falling back to AID-based uninstall: {fallback_aid}"
                    )
                    self.uninstall_app(fallback_aid, force=force)
                else:
                    self.operation_complete.emit(False, err_msg)

        except Exception as e:
            err_msg = f"Uninstall error (CAP file): {e}"
            self.status_update.emit(err_msg)

            # Attempt fallback if provided
            if fallback_aid:
                self.status_update.emit(f"Falling back to AID-based uninstall: {fallback_aid}")
                self.uninstall_app(fallback_aid, force=force)
            else:
                self.operation_complete.emit(False, err_msg)

    def stop(self):
        """Signal the loop to exit gracefully."""
        self.running = False
