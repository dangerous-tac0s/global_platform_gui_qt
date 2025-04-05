import os
import re
import subprocess
import sys
import zipfile

import chardet
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QMetaObject, Q_ARG, pyqtSlot
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
    readers_updated_signal = pyqtSignal(list)

    # Emitted True/False when a card transitions from absent -> present or vice versa
    card_present_signal = pyqtSignal(bool)

    # Emitted with status text you can show in your UI
    status_update_signal = pyqtSignal(str)

    # Emitted upon successful or failed install/uninstall
    #   success (bool), message (str)
    operation_complete_signal = pyqtSignal(bool, str)

    # Emitted with the updated list of AIDs after a successful install/uninstall
    installed_apps_updated_signal = pyqtSignal(dict)

    # Emitted upon any errors. Pipes it to a dialog.
    error_signal = pyqtSignal(str)

    # Emitted whenever we have a good card scanned.
    title_bar_signal = pyqtSignal(str)

    # Key prompt dialog
    show_key_prompt_signal = pyqtSignal(str, str)

    # Known tag handling
    # known_tags_query = pyqtSignal(str)
    known_tags_update_signal = pyqtSignal(str, bool)

    get_key_signal = pyqtSignal(str)
    key_setter_signal = pyqtSignal(str)

    def __init__(self, app, selected_reader_name=None, parent=None):
        """
        :param selected_reader_name: The currently chosen reader (or None at start).
        """
        super().__init__(parent)
        self.app = app
        self.selected_reader_name = selected_reader_name
        self.key = None

        # Thread run loop control
        self.running = True

        # Track card state
        self.card_detected = False
        self.valid_card_detected = False
        self.current_uid = None

        # OS-specific gp command
        self.gp = {
            "nt": [
                resource_path("gp.exe"),
            ],
            "posix": [
                "java",
                "-jar",
                resource_path("gp.jar"),
            ],
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
                    self.readers_updated_signal.emit(reader_names)
                    last_readers = reader_names

                if not reader_names:
                    if self.card_detected:
                        self.card_detected = False
                        self.valid_card_detected = False
                        self.current_uid = None
                        self.card_present_signal.emit(False)
                    self.status_update_signal.emit("No readers found.")
                    self.msleep(timeout_duration)
                    continue

                if self.selected_reader_name in reader_names:
                    idx = reader_names.index(self.selected_reader_name)
                    reader = available_readers[idx]
                    uid = self.get_card_uid(reader)
                    if uid:
                        if not self.card_detected or uid != self.current_uid:
                            jcop3 = self.is_jcop()
                            self.valid_card_detected = jcop3
                            self.card_detected = True
                            self.current_uid = uid
                            self.card_present_signal.emit(True)
                            if jcop3:
                                mem = self.get_memory_status()
                                self.title_bar_signal.emit(
                                    f"UID: {self.current_uid} > {mem}"
                                )

                                self.get_key_signal.emit(self.current_uid)

                            else:
                                self.status_update_signal.emit(
                                    "Unsupported card detected."
                                )
                    else:
                        if self.card_detected:
                            self.card_detected = False
                            self.valid_card_detected = False
                            self.current_uid = None
                            self.card_present_signal.emit(False)
                            self.status_update_signal.emit("No card present.")
                else:
                    if self.card_detected:
                        self.card_detected = False
                        self.valid_card_detected = False
                        self.current_uid = None
                        self.card_present_signal.emit(False)
                        self.status_update_signal.emit("No card present.")

                self.msleep(timeout_duration)

            except Exception as e:
                self.error_signal.emit(f"Loop error: {e}")
                # self.status_update.emit(f"Loop error: {e}")

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

    def is_jcop(self):
        """Send SELECT APDUs"""
        SELECT = [0x00, 0xA4, 0x04, 0x00, 0x00]
        try:
            reader = next(x for x in readers() if self.selected_reader_name in str(x))
            connection = reader.createConnection()
            connection.connect()
            data, sw1, sw2 = connection.transmit(SELECT)
            return hex(sw1) == "0x90" and sw2 == 0
        except Exception as e:
            print(e)
            return False

    def is_jcop3(self, reader_name):
        """Use gp --info to see if 'JavaCard v3' is in the output."""
        try:
            cmd = [*self.gp[os.name][0], "-k", self.key, "--info", "-r", reader_name]
            result = subprocess.run(cmd, capture_output=True, text=True)

            return "JavaCard v3" in result.stdout
        except Exception as e:
            return False

    def get_memory_status(self):
        """Call measure.get_memory()."""
        try:
            memory = get_memory()
            if memory and memory != -1:
                free = memory["persistent"]["free"] / 1024
                percent = memory["persistent"]["percent_free"] * 100
                t_free = (
                    memory["transient"]["reset_free"]
                    + memory["transient"]["deselect_free"]
                ) / 1024
                return f"Free Memory > Persistent: {free:.0f}kB / Transient: {t_free:.1f}kB"
            elif memory == -1:
                return "Javacard Memory not installed"
        except Exception as e:
            return f"Memory Error: {e}"

    def get_installed_apps(self):
        """
        Parse gp --list for both PKG blocks (which contain 'Version: X' + 'Applet: Y')
        and APP lines (which show truly installed apps).
        Returns a dict: { AID_uppercase: version_string_or_None, ... }
        """
        if not self.selected_reader_name:
            self.status_update_signal.emit("No reader selected for get_installed_apps.")
            return {}

        try:
            cmd = [
                *self.gp[os.name],
                "-k",
                self.key,
                "--list",
                "-r",
                self.selected_reader_name,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.error_signal.emit(f"Unable to list apps: {result.stderr}")
                # self.status_update.emit(f"Error listing apps: {result.stderr}")
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
            self.status_update_signal.emit(f"Exception listing apps: {e}")
            print(e)
            return {}

    # ----------------------------
    #  Installation and Uninstall
    # ----------------------------
    def install_app(self, cap_file_path, params=None):
        if not self.selected_reader_name:
            self.operation_complete_signal.emit(False, "No reader selected.")
            return

        try:
            if self.key is None:
                # TODO: request key with dialog
                self.show_key_prompt_signal.emit(self.current_uid)

            if self.key is None:
                # if we still don't have one, don't do anything
                self.error_signal.emit("No valid key has been provided")
            else:
                cmd = [
                    *self.gp[os.name],
                    "-k",
                    self.key,
                    "--install",
                    cap_file_path,
                    "-r",
                    self.selected_reader_name,
                ]
                if params and "param_string" in params:
                    # Allow a bit more flexibility
                    cmd.extend(["--params", *params["param_string"].split(" ")])

                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0 and len(result.stderr) == 0:
                    installed = self.get_installed_apps()
                    self.installed_apps_updated_signal.emit(installed)
                else:
                    if result.stderr.startswith(
                        "Failed to open secure channel: Card cryptogram invalid!"
                    ):
                        # Wrong key provided--don't do that again!
                        self.key = None
                        self.known_tags_update_signal.emit(self.current_uid, False)
                        self.error_signal.emit(
                            "Invalid key used: further attempts with invalid keys can brick the device!"
                        )
                        self.known_tags_update_signal.emit(self.current_uid, False)
                    else:
                        err_msg = f"Install failed: {result.stderr}"
                        # self.operation_complete.emit(False, err_msg)
                        self.error_signal.emit(err_msg)
                        # Let's try to remove the app now
                        self.uninstall_app_by_cap(cap_file_path)
        except Exception as e:
            err_msg = f"Install error: {e}"
            # self.operation_complete.emit(False, err_msg)
            self.error_signal.emit(err_msg)
        finally:
            if (
                os.path.exists(cap_file_path)
                and not self.app.config["cache_latest_release"]
            ):
                os.remove(cap_file_path)
            mem = self.get_memory_status()
            self.title_bar_signal.emit(f"UID: {self.current_uid} > {mem}")

    def uninstall_app(self, aid, force=False):
        """
        Uninstall by AID:
           gp --uninstall [--force?] <aid> -r <reader>
        """
        if not self.selected_reader_name:
            self.operation_complete_signal.emit(False, "No reader selected.")
            return

        try:
            if self.key is None:
                # TODO: request key with dialog
                pass

            if self.key is None:
                # if we still don't have one, don't do anything
                self.error_signal.emit("No valid key has been provided")
                self.operation_complete_signal(False)
                return

            cmd = [*self.gp[os.name], "-k", self.key, "--uninstall"]
            cmd.extend([aid, "-r", self.selected_reader_name])
            if force:
                cmd.extend("-f")  # or '--force' if gp.jar uses that
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and len(result.stderr) == 0:
                self.operation_complete_signal.emit(True, f"Uninstalled {aid}")
                installed = self.get_installed_apps()
                self.installed_apps_updated_signal.emit(installed)
            else:
                if result.stderr.startswith(
                    "Failed to open secure channel: Card cryptogram invalid!"
                ):
                    # Wrong key provided--don't do that again!
                    self.key = None
                    self.known_tags_update_signal.emit(self.current_uid, False)
                    self.error_signal.emit(
                        "Invalid key used: further attempts with invalid keys can brick the device!"
                    )
                else:
                    pass

        except Exception as e:
            err_msg = f"Uninstall error (AID): {e}"
            self.operation_complete_signal.emit(False, err_msg)
            self.error_signal.emit(err_msg)
        finally:
            mem = self.get_memory_status()
            self.title_bar_signal.emit(f"UID: {self.current_uid} > {mem}")

    def uninstall_app_by_cap(self, cap_file_path, fallback_aid=None, force=False):
        """
        Attempt 'gp --uninstall <cap_file_path>' first.
        If that fails and fallback_aid is provided, try 'uninstall_app(aid=fallback_aid)' next.
        The 'force' param, if True, passes '-f' to gp (applies to both attempts).
        """
        if not self.selected_reader_name:
            self.operation_complete_signal.emit(False, "No reader selected.")
            return

        try:
            # Build the command:
            cmd = [*self.gp[os.name], "-k", self.key, "--uninstall"]
            if force:
                cmd.append("-f")
            cmd.extend([cap_file_path, "-r", self.selected_reader_name])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                # success
                installed = self.get_installed_apps()
                self.installed_apps_updated_signal.emit(installed)
            else:
                # Fail => fallback to AID if provided
                # err_msg = f"Uninstall by CAP file failed: {result.stderr}"
                # self.status_update.emit(err_msg)

                manifest = extract_manifest_from_cap(cap_file_path)

                fallback_aid = get_selected_manifest(manifest)["aid"]

                if fallback_aid:
                    # self.status_update.emit(
                    #     f"Falling back to AID-based uninstall: {fallback_aid}"
                    # )
                    self.uninstall_app(fallback_aid, force=force)
                else:
                    self.operation_complete_signal.emit(False, "Failed to uninstall")

        except Exception as e:
            err_msg = f"Uninstall error (CAP file): {e}"
            # self.status_update.emit(err_msg)
            self.error_signal.emit(err_msg)

            # Attempt fallback if provided
            if fallback_aid:
                self.status_update_signal.emit(
                    f"Falling back to AID-based uninstall: {fallback_aid}"
                )
                self.uninstall_app(fallback_aid, force=force)
            else:
                self.operation_complete_signal.emit(False, err_msg)
        finally:
            # TODO: Support caching
            if os.path.exists(cap_file_path):
                os.remove(cap_file_path)
            mem = self.get_memory_status()
            self.title_bar_signal.emit(f"UID: {self.current_uid} > {mem}")

    def get_key(self):
        self.get_key_signal.emit()

    @pyqtSlot(str)  # This slot is called when the signal is emitted
    def key_setter(self, key):
        self.key = key
        self.get_installed_apps()

    def stop(self):
        """Signal the loop to exit gracefully."""
        self.running = False


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def detect_encoding(file_path):
    """
    Detect the file encoding using chardet.

    Args:
        file_path (str): Path to the file.

    Returns:
        str: Detected encoding.
    """
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result["encoding"]


def extract_manifest_from_cap(cap_file_path, output_dir=None):
    """
    Extract the MANIFEST.MF file from a CAP archive and return a dictionary with all parsed data.

    Args:
        cap_file_path (str): Path to the CAP archive (ZIP file).
        output_dir (str, optional): Directory where the MANIFEST.MF will be saved. Defaults to None.

    Returns:
        dict: A dictionary containing all keys and values parsed from the MANIFEST.MF file.
    """
    try:
        with zipfile.ZipFile(cap_file_path, "r") as zip_ref:
            # List files in the archive to find 'META-INF/MANIFEST.MF'
            file_list = zip_ref.namelist()

            manifest_file = "META-INF/MANIFEST.MF"
            if manifest_file not in file_list:
                print(f"Error: {manifest_file} not found in the CAP archive.")
                return None

            # Extract the MANIFEST.MF content
            with zip_ref.open(manifest_file) as mf_file:
                # Temporarily write to a file to detect encoding
                temp_path = "temp_manifest.MF"
                with open(temp_path, "wb") as temp_file:
                    temp_file.write(mf_file.read())

                # Detect encoding of the MANIFEST.MF file
                encoding = detect_encoding(temp_path)

                # Read the content using the detected encoding
                with open(temp_path, "r", encoding=encoding) as temp_file:
                    manifest_content = temp_file.read()

                if output_dir:
                    # Optionally save the manifest to a file
                    output_file_path = os.path.join(output_dir, "MANIFEST.MF")
                    with open(output_file_path, "w") as output_file:
                        output_file.write(manifest_content)
                    print(f"MANIFEST.MF extracted to {output_file_path}")

                # Debug: Print manifest content to inspect structure
                # print("Manifest Content:\n", manifest_content)

                # Parse the manifest and extract all relevant fields
                return parse_manifest(manifest_content)

    except zipfile.BadZipFile:
        print(f"Error: The file {cap_file_path} is not a valid ZIP archive.")
        return None
    except Exception as e:
        print(cap_file_path)
        print(f"An error occurred while extracting the MANIFEST.MF: {e}")
        print(manifest_content)
        print()
        return None
    finally:
        try:
            os.remove(temp_path)
        except:
            pass


def parse_manifest(manifest_content: str) -> dict:
    """
    Parse the manifest content to extract all fields.

    Args:
        manifest_content (str): The contents of the extracted MANIFEST.MF file.

    Returns:
        dict: A dictionary containing all keys and values parsed from the manifest.
    """
    data = {}

    # Use a regular expression to find all key-value pairs in the manifest
    pattern = r"(?P<key>^[A-Za-z0-9\-]+):\s*(?P<value>.*)"
    matches = re.finditer(pattern, manifest_content, re.MULTILINE)

    for match in matches:
        key = match.group("key").strip()
        value = match.group("value").strip()

        # Parse AID fields (e.g., Java-Card-Applet-1-AID)
        if key == "Java-Card-Applet-AID":
            value = value.replace(":", "")

        # Fallback. VivoKey's OTP app has a mal-formed AID in 'Java-Card-Applet-AID'
        if key == "Classic-Package-AID":
            value = value.replace("aid", "").replace("/", "")

        # Parse version fields (e.g., Runtime-Descriptor-Version)
        elif key == "Java-Card-Package-Version" or key == "Runtime-Descriptor-Version":
            # Convert version to a tuple of integers
            value = value

            if key == "Runtime-Descriptor-Version" and len(value) < 3:
                while len(value) < 3:
                    value = tuple([*value, 0])

        data[key] = value

    return data


def get_selected_manifest(manifest_dict):
    return {
        "name": manifest_dict.get("Name", None),
        "aid": manifest_dict.get("Java-Card-Applet-AID", None)
        or manifest_dict.get("Classic-Package-AID", None),
        "app_version": manifest_dict.get("Java-Card-Package-Version", None),
        "jcop_version": manifest_dict.get("Runtime-Descriptor-Version", None),
    }
