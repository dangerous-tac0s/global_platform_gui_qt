import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException
from smartcard.util import toHexString
from measure import get_memory

# TODO: Handle alternative keys
DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"

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
    installed_apps_updated = pyqtSignal(dict)

    def __init__(self, selected_reader_name=None, parent=None):
        """
        :param selected_reader_name: The currently chosen reader (or None at start).
        """
        super().__init__(parent)
        self.key = DEFAULT_KEY
        self.selected_reader_name = selected_reader_name

        # Thread run loop control
        self.running = True

        # Track card state
        self.card_detected = False
        self.valid_card_detected = False
        self.current_uid = None

        # OS-specific gp command
        self.gp = {
            "nt":   ["gp.exe", "-k", self.key],
            "posix": ["java", "-jar", "gp.jar", "-k", self.key]
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
        """
        Parse gp --list for both PKG blocks (which contain 'Version: X' + 'Applet: Y')
        and APP lines (which show truly installed apps).
        Returns a dict: { AID_uppercase: version_string_or_None, ... }
        """
        if not self.selected_reader_name:
            self.status_update.emit("No reader selected for get_installed_apps.")
            return {}

        try:
            cmd = [*self.gp[os.name], "--list", "-r", self.selected_reader_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.status_update.emit(f"Error listing apps: {result.stderr}")
                return {}

            lines = result.stdout.splitlines()

            # Data structures for PKG -> version, applets, etc.
            pkg_app_versions = {}  # Maps "AID-of-Applet" -> "version"
            current_pkg_version = None
            parsing_pkg_block = False

            # We'll also track all "APP: ..." lines, which represent installed applets
            installed_set = set()

            for line in lines:
                line = line.strip()

                # Detect start of a PKG block
                if line.startswith("PKG:"):
                    # "PKG: A000000308000010 (LOADED)" etc.
                    # Reset for a new package
                    parsing_pkg_block = True
                    current_pkg_version = None
                    continue

                if parsing_pkg_block:
                    # Inside a package block until we hit next "PKG:", "APP:", or blank
                    if not line or line.startswith("PKG:") or line.startswith("APP:"):
                        # done with current pkg block
                        parsing_pkg_block = False
                        # If this line starts with APP: or PKG:, re-process it in next iteration
                        if line.startswith("APP:"):
                            # We'll handle the APP line after the loop continues
                            pass
                    else:
                        # Possibly lines like "Version:  1.0" or "Applet:   A000000308000010000100"
                        if "Version:" in line:
                            # e.g. "Version:  1.0"
                            # parse out version number
                            parts = line.split("Version:", 1)
                            version_str = parts[1].strip()  # e.g. "1.0"
                            current_pkg_version = version_str
                        elif "Applet:" in line:
                            # e.g. "Applet:   A000000308000010000100"
                            # parse out applet AID
                            parts = line.split("Applet:", 1)
                            raw_aid = parts[1].strip()
                            # Normalize the AID (uppercase, no spaces)
                            norm_aid = raw_aid.replace(" ", "").upper()
                            pkg_app_versions[norm_aid] = current_pkg_version
                    # If we haven't returned or continued, keep parsing lines in this block
                    if line.startswith("APP:"):
                        # We'll handle "APP:" lines below anyway
                        pass

                # If the line is an "APP:" line:
                if line.startswith("APP:"):
                    # e.g. "APP: A000000308000010000100 (SELECTABLE)"
                    parts = line.split()
                    if len(parts) >= 2:
                        raw_aid = parts[1]
                        norm_aid = raw_aid.replace(" ", "").upper()
                        installed_set.add(norm_aid)

            # Now build a dictionary {aid: version_string or None} for installed apps
            installed_apps = {}
            for aid in installed_set:
                if aid in pkg_app_versions:
                    installed_apps[aid] = pkg_app_versions[aid]
                else:
                    installed_apps[aid] = None

            return installed_apps

        except Exception as e:
            self.status_update.emit(f"Exception listing apps: {e}")
            return {}

    # ----------------------------
    #  Installation and Uninstall
    # ----------------------------
    def install_app(self, cap_file_path, params=None):
        if not self.selected_reader_name:
            # self.status_update.emit("No reader selected for install.")
            self.operation_complete.emit(False, "No reader selected.")
            return

        try:
            cmd = [*self.gp[os.name], "--install", cap_file_path, "-r", self.selected_reader_name]
            if params and "param_string" in params:
                cmd.extend(["--params", params["param_string"]])
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # self.status_update.emit(f"Installed: {os.path.basename(cap_file_path)}")
                self.operation_complete.emit(True, f"Installed {cap_file_path}")
                installed = self.get_installed_apps()
                self.installed_apps_updated.emit(installed)
            else:
                err_msg = f"Install failed: {result.stderr}"
                # self.status_update.emit(err_msg)
                self.operation_complete.emit(False, err_msg)
        except Exception as e:
            err_msg = f"Install error: {e}"
            # self.status_update.emit(err_msg)
            self.operation_complete.emit(False, err_msg)
        finally:
            # TODO: Support caching
            if os.path.exists(cap_file_path):
                os.remove(cap_file_path)
            mem = self.get_memory_status()
            self.status_update.emit(f"UID: {self.current_uid} | {mem}")

    def uninstall_app(self, aid, force=False):
        """
        Uninstall by AID:
           gp --uninstall [--force?] <aid> -r <reader>
        """
        if not self.selected_reader_name:
            # self.status_update.emit("No reader selected for uninstall.")
            self.operation_complete.emit(False, "No reader selected.")
            return

        try:
            cmd = [*self.gp[os.name], "--uninstall"]
            if force:
                cmd.append("-f")  # or '--force' if gp.jar uses that
            cmd.extend([aid, "-r", self.selected_reader_name])
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                # self.status_update.emit(f"Uninstalled AID: {aid}")
                self.operation_complete.emit(True, f"Uninstalled {aid}")
                installed = self.get_installed_apps()
                self.installed_apps_updated.emit(installed)
            else:
                err_msg = f"Uninstall by AID failed: {result.stderr}"
                # self.status_update.emit(err_msg)
                self.operation_complete.emit(False, err_msg)

        except Exception as e:
            err_msg = f"Uninstall error (AID): {e}"
            # self.status_update.emit(err_msg)
            self.operation_complete.emit(False, err_msg)
        finally:
            mem = self.get_memory_status()
            self.status_update.emit(f"UID: {self.current_uid} | {mem}")

    def uninstall_app_by_cap(self, cap_file_path, fallback_aid=None, force=False):
        """
        Attempt 'gp --uninstall <cap_file_path>' first.
        If that fails and fallback_aid is provided, try 'uninstall_app(aid=fallback_aid)' next.
        The 'force' param, if True, passes '-f' to gp (applies to both attempts).
        """
        if not self.selected_reader_name:
            # self.status_update.emit("No reader selected for uninstall.")
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
                # self.status_update.emit(f"Uninstalled CAP file: {os.path.basename(cap_file_path)}")
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
        finally:
            # TODO: Support caching
            if os.path.exists(cap_file_path):
                os.remove(cap_file_path)
            mem = self.get_memory_status()
            self.status_update.emit(f"UID: {self.current_uid} | {mem}")

    def stop(self):
        """Signal the loop to exit gracefully."""
        self.running = False
