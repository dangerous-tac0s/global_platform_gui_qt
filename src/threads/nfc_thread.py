"""
NFCHandlerThread - Background thread for NFC card operations.

Monitors for smart card readers and cards, handles card authentication,
and provides install/uninstall functionality. Maintains backward
compatibility with Qt signals while adding EventBus support.
"""

import os
import re
import subprocess
import sys
import time
import zipfile
from threading import Event
from typing import Optional, Dict, Any, List, TYPE_CHECKING

import chardet
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
from smartcard.System import readers

from ..models.card import CardIdentifier, CardType, FIDESMO_PERSISTENT_TOTAL, FIDESMO_KEY_SENTINEL
from ..events.event_bus import (
    EventBus,
    ErrorEvent,
    StatusMessageEvent,
    OperationResultEvent,
    ProgressEvent,
    CardPresenceEvent,
    InstalledAppsUpdatedEvent,
    KeyPromptEvent,
)

if TYPE_CHECKING:
    from ..services.interfaces import IGPService
    from ..models.key_config import KeyConfiguration

# Default key for GlobalPlatform cards
DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"


class NFCHandlerThread(QThread):
    """
    Background thread for monitoring NFC readers and handling card operations.

    Qt Signals (Legacy):
    - error_signal: Error messages
    - status_update_signal: Status messages
    - title_bar_signal: Title bar updates
    - operation_complete_signal: Operation results
    - reader_detected_signal: Reader list updates
    - card_detected_signal: Card UID detected
    - installed_apps_updated_signal: Installed apps changed
    - get_key_signal: Request key from storage
    - show_key_prompt_signal: Show key prompt dialog
    - known_tags_update_signal: Update known tag storage
    - card_removed_signal: Card was removed
    - cplc_retrieved_signal: CPLC data retrieved

    EventBus Events (when enabled):
    - CardPresenceEvent: Card detected/removed
    - StatusMessageEvent: Status updates
    - ErrorEvent: Error notifications
    - OperationResultEvent: Install/uninstall results
    - KeyPromptEvent: Key prompt requests
    - InstalledAppsUpdatedEvent: App list changes
    """

    # Legacy Qt signals (kept for backward compatibility)
    error_signal = pyqtSignal(str)
    status_update_signal = pyqtSignal(str)
    title_bar_signal = pyqtSignal(str)
    operation_complete_signal = pyqtSignal(bool, str)
    reader_detected_signal = pyqtSignal(list)
    readers_updated_signal = pyqtSignal(list)  # Alias for reader_detected_signal
    card_detected_signal = pyqtSignal(str)
    card_present_signal = pyqtSignal(bool)  # Card presence state
    installed_apps_updated_signal = pyqtSignal(dict)
    get_key_signal = pyqtSignal(str)  # arg is card_id (CPLC hash or UID)
    show_key_prompt_signal = pyqtSignal(str)  # arg is card_id
    key_setter_signal = pyqtSignal(str)  # Key value to set
    known_tags_update_signal = pyqtSignal(str, str)  # card_id, key
    key_config_update_signal = pyqtSignal(str, object)  # card_id, KeyConfiguration
    card_removed_signal = pyqtSignal()
    cplc_retrieved_signal = pyqtSignal(str, str)  # uid, cplc_hash
    fidesmo_mode_signal = pyqtSignal(bool)  # True when Fidesmo device detected
    fidesmo_confirm_signal = pyqtSignal()  # Ask user to confirm Fidesmo mode

    def __init__(
        self,
        app,
        gp_service: Optional["IGPService"] = None,
        parent=None,
        use_event_bus: bool = False,
    ):
        """
        Initialize the NFC handler thread.

        Args:
            app: Application instance (for config access during migration)
            gp_service: Service for GlobalPlatformPro operations
            parent: Optional QThread parent
            use_event_bus: If True, emit EventBus events in addition to signals
        """
        super().__init__(parent)
        self.app = app
        self._gp_service = gp_service
        self.use_event_bus = use_event_bus

        # EventBus instance (lazy loaded if enabled)
        self._event_bus = EventBus.instance() if use_event_bus else None

        # Thread control events
        self._stop_event = Event()
        self._pause_event = Event()
        self._pause_event.set()  # Start unpaused
        self._paused_ack = Event()  # Acknowledge pause
        self._reader_changed = Event()  # Signal reader switch to reset card state

        # Reader and card state
        self.known_readers: List[str] = []
        self.selected_reader_name: Optional[str] = None
        self.current_uid: Optional[str] = None
        self.current_identifier: Optional[CardIdentifier] = None
        self.key: Optional[str] = None
        self._key_config = None  # Optional KeyConfiguration for separate ENC/MAC/DEK keys
        self.card_detected: bool = False
        self.valid_card_detected: bool = False
        self._pending_key: Optional[str] = None  # Key waiting to be processed async

        # Fidesmo support
        self._card_type: CardType = CardType.UNKNOWN
        self._fdsm_service = None  # Lazy-loaded FDSMService

        # Storage tracking
        self.storage = {"persistent": -1, "transient": -1, "persistent_total": -1}

        # GlobalPlatformPro command paths
        self.gp = {
            "posix": [resource_path("gp.jar")],
            "nt": ["java", "-jar", resource_path("gp.jar")],
        }

        # Add java for posix if needed
        if os.name == "posix":
            self.gp["posix"] = ["java", "-jar", *self.gp["posix"]]

    @property
    def card_id(self) -> Optional[str]:
        """Get the primary card identifier (CPLC preferred, UID fallback)."""
        if self.current_identifier:
            return self.current_identifier.primary_id
        return self.current_uid

    @property
    def card_type(self) -> CardType:
        """Get the current card type."""
        return self._card_type

    @property
    def is_fidesmo(self) -> bool:
        """Check if the current card is a Fidesmo device."""
        return self._card_type == CardType.FIDESMO

    def _get_fdsm_service(self):
        """Lazy-load FDSMService instance."""
        if self._fdsm_service is None:
            from ..services.fdsm_service import FDSMService
            self._fdsm_service = FDSMService()
        return self._fdsm_service

    def _get_fidesmo_auth(self):
        """Get Fidesmo auth token and app ID from secure storage."""
        auth_token = None
        app_id = None
        try:
            if hasattr(self.app, 'secure_storage') and self.app.secure_storage:
                fidesmo = self.app.secure_storage.get("fidesmo")
                if fidesmo:
                    auth_token = fidesmo.get("auth_token")
            if hasattr(self.app, 'config') and self.app.config:
                app_id = self.app.config.get("fidesmo_app_id")
        except Exception:
            pass
        return auth_token, app_id

    # =========================================================================
    # Thread Control
    # =========================================================================

    def run(self):
        """Main thread loop for monitoring readers and cards."""
        last_reader_list: List[str] = []
        card_present = False

        while not self._stop_event.is_set():
            # Handle pause requests
            if not self._pause_event.is_set():
                self._paused_ack.set()
                self._pause_event.wait()
                self._paused_ack.clear()

            # Handle reader change - reset card state to trigger fresh detection
            if self._reader_changed.is_set():
                self._reader_changed.clear()
                card_present = False
                # Check new reader immediately and emit appropriate status
                if self.selected_reader_name and not self.is_card_present():
                    self._emit_status("No card present.")

            try:
                # Process any pending key setup (runs GP commands async)
                if self._pending_key is not None:
                    self._process_pending_key()

                # Get current readers (filter out SAM readers)
                all_readers = readers()
                filtered_readers = [
                    r for r in all_readers if "SAM" not in str(r).upper()
                ]
                reader_names = [str(r) for r in filtered_readers]

                # Detect reader changes
                if reader_names != last_reader_list:
                    last_reader_list = reader_names
                    self.reader_detected_signal.emit(reader_names)
                    self.readers_updated_signal.emit(reader_names)  # Alias
                    # Note: main.py handles status messaging via readers_updated()

                    # Auto-select first reader if none selected
                    if reader_names and not self.selected_reader_name:
                        self.selected_reader_name = reader_names[0]

                # Check for card presence
                if self.selected_reader_name:
                    is_present = self.is_card_present()

                    if is_present and not card_present:
                        # Card just inserted
                        card_present = True
                        uid = self.get_card_uid()
                        self.current_uid = uid
                        self.card_detected = True


                        # Check if JCOP and get key
                        if self.is_jcop(self.selected_reader_name):
                            self.valid_card_detected = True

                            # Read memory before key prompt — can detect
                            # Fidesmo devices via persistent_total without
                            # any GP authentication.
                            try:
                                reader_idx = self._get_reader_index()
                                self.update_memory(reader_idx)
                            except Exception:
                                pass  # Memory read failed, proceed normally

                            if (
                                FIDESMO_PERSISTENT_TOTAL is not None
                                and self.storage.get("persistent_total") == FIDESMO_PERSISTENT_TOTAL
                                and self._card_type == CardType.UNKNOWN
                            ):
                                # Potential Fidesmo device — ask user before proceeding
                                self._emit_status("Potential Fidesmo device detected.")
                                self.fidesmo_confirm_signal.emit()
                            else:
                                self._emit_status("Compatible card present.")
                                self.get_key()
                        else:
                            self.valid_card_detected = False
                            self._emit_status("Unsupported card present.")

                        self.card_detected_signal.emit(uid)
                        self.card_present_signal.emit(True)
                        self._emit_card_presence(True, uid)


                    elif not is_present and card_present:
                        # Card removed
                        card_present = False
                        self.current_uid = None
                        self.current_identifier = None
                        self.key = None
                        self._key_config = None
                        self._pending_key = None  # Clear any pending key operation
                        self.card_detected = False
                        self.valid_card_detected = False
                        self._card_type = CardType.UNKNOWN

                        self.card_removed_signal.emit()
                        # Don't emit fidesmo_mode_signal(False) here — NFC flicker
                        # during FDSM I/O causes a false "card removed" that would
                        # disable Fidesmo UI.  Fidesmo mode is exited explicitly
                        # when a GP card is processed in _process_pending_key().
                        self.card_present_signal.emit(False)
                        self._emit_card_presence(False, None)
                        self.title_bar_signal.emit(self.make_title_bar_string())

            except Exception as e:
                self._emit_error(f"Thread error: {e}")

            time.sleep(0.5)

    def pause(self):
        """Pause the monitoring thread."""
        self._pause_event.clear()

    def resume(self):
        """Resume the monitoring thread."""
        self._pause_event.set()

    def stop(self):
        """Stop the monitoring thread."""
        self._stop_event.set()
        self.resume()

    def signal_reader_changed(self):
        """Signal that the reader selection has changed.

        This resets the card detection state so the thread will
        check for card presence on the newly selected reader.
        """
        self._reader_changed.set()

    # =========================================================================
    # Card Detection
    # =========================================================================

    def is_card_present(self) -> bool:
        """Check if a card is present in the selected reader."""
        if not self.selected_reader_name:
            return False

        try:
            filtered_readers = [
                r for r in readers() if "SAM" not in str(r).upper()
            ]
            reader = next(
                x for x in filtered_readers
                if self.selected_reader_name in str(x)
            )
            connection = reader.createConnection()
            connection.connect()
            connection.disconnect()
            return True
        except Exception:
            return False

    def get_card_uid(self) -> str:
        """Get the UID of the card in the selected reader."""
        connection = None
        try:
            GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
            filtered_readers = [
                r for r in readers() if "SAM" not in str(r).upper()
            ]
            reader = next(
                x for x in filtered_readers
                if self.selected_reader_name in str(x)
            )
            connection = reader.createConnection()
            connection.connect()
            data, sw1, sw2 = connection.transmit(GET_UID)

            if sw1 == 0x90 and sw2 == 0x00:
                return "".join(f"{b:02X}" for b in data)
            else:
                # Contact cards don't return UID
                return "__CONTACT_CARD__"
        except Exception as e:
            return "__CONTACT_CARD__"
        finally:
            if connection:
                try:
                    connection.disconnect()
                except Exception:
                    pass

    def transmit_apdu(self, apdu: bytes) -> bytes:
        """
        Transmit an APDU to the card and return the response.

        Args:
            apdu: APDU bytes to send

        Returns:
            Response bytes including status word
        """
        connection = None
        try:
            filtered_readers = [
                r for r in readers() if "SAM" not in str(r).upper()
            ]
            reader = next(
                x for x in filtered_readers
                if self.selected_reader_name in str(x)
            )
            connection = reader.createConnection()
            connection.connect()

            # Convert bytes to list of ints for pyscard
            apdu_list = list(apdu)
            data, sw1, sw2 = connection.transmit(apdu_list)

            # Return response data + status word as bytes
            response = bytes(data) + bytes([sw1, sw2])
            return response

        except Exception as e:
            print(f"APDU transmission error: {e}")
            # Return error status word
            return bytes([0x6F, 0x00])
        finally:
            if connection:
                try:
                    connection.disconnect()
                except Exception:
                    pass

    def is_jcop(self, reader_name: str) -> bool:
        """
        Check if the card is a JavaCard (JCOP).

        Uses ISO 7816-4 SELECT to verify JavaCard support.
        """
        SELECT = [0x00, 0xA4, 0x04, 0x00, 0x00]
        connection = None
        try:
            filtered_readers = [
                r for r in readers() if "SAM" not in str(r).upper()
            ]
            reader = next(
                x for x in filtered_readers if self.selected_reader_name in str(x)
            )
            connection = reader.createConnection()
            connection.connect()
            data, sw1, sw2 = connection.transmit(SELECT)
            result = hex(sw1) == "0x90" and sw2 == 0
            return result
        except Exception as e:
            print(f"Unable to perform select: {e}")
            return False
        finally:
            if connection:
                try:
                    connection.disconnect()
                except Exception:
                    pass

    def is_jcop3(self, reader_name: str) -> bool:
        """Check if the card is JavaCard v3."""
        try:
            if self.is_fidesmo:
                return False  # Fidesmo devices don't use GP commands
            if (
                self.key is None
                or self.app.config["known_tags"].get(self.current_uid, None) is None
            ):
                return False  # Protect unknown tags
            cmd = [*self.gp[os.name][0], "-k", self.key, "--info", "-r", reader_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return "JavaCard v3" in result.stdout
        except Exception:
            return False

    # =========================================================================
    # CPLC and Card Identification
    # =========================================================================

    def retrieve_cplc_and_update_identifier(self):
        """
        Retrieve CPLC data and update the current card identifier.

        Called after authentication. Creates a CardIdentifier with both
        CPLC hash (if available) and UID.
        """
        if not self.key or not self.selected_reader_name:
            return

        real_uid = self.current_uid if self.current_uid != "__CONTACT_CARD__" else None

        try:
            # Use GPService to get CPLC data (create instance if needed)
            from ..services.gp_service import GPService

            if self._gp_service:
                gp = self._gp_service
            else:
                gp = GPService()

            cplc_data = gp.get_cplc_data(
                self.selected_reader_name, self.key, key_config=self._key_config
            )

            if cplc_data:
                cplc_hash = cplc_data.compute_hash()
                self.current_identifier = CardIdentifier(
                    cplc_hash=cplc_hash, uid=real_uid
                )
                # Emit signal for storage upgrade
                self.cplc_retrieved_signal.emit(real_uid or "", cplc_hash)
                self.title_bar_signal.emit(self.make_title_bar_string())
            else:
                # CPLC not available, use UID-only identifier
                if real_uid:
                    self.current_identifier = CardIdentifier(uid=real_uid)
                else:
                    self.current_identifier = None

        except Exception:
            # CPLC retrieval failed, fall back to UID-only
            if real_uid:
                self.current_identifier = CardIdentifier(uid=real_uid)
            else:
                self.current_identifier = None

    # =========================================================================
    # Memory and Status
    # =========================================================================

    def make_title_bar_string(self) -> str:
        """Build the title bar string with current card info."""
        base = "GlobalPlatform GUI"

        if not self.selected_reader_name:
            return base

        if not self.current_uid:
            return f"{base} - {self.selected_reader_name}"

        # Use card_id (prefers CPLC hash over UID)
        card_identifier = self.card_id
        if card_identifier == "__CONTACT_CARD__":
            uid_display = "Contact Card"
        elif card_identifier:
            uid_display = card_identifier
        else:
            uid_display = self.current_uid

        fidesmo_tag = " [Fidesmo]" if self.is_fidesmo else ""
        key_status = "🔓" if self.key else "🔒"
        memory_str = self.get_memory_status()

        return f"{base} - {uid_display}{fidesmo_tag} {key_status} {memory_str}"

    def get_memory_status(self) -> str:
        """Get memory status string."""
        if self.storage["persistent"] != -1 and self.storage["transient"] != -1:
            p_kb = self.storage["persistent"] / 1024
            t_kb = self.storage["transient"] / 1024
            return f"> Free Memory > Persistent: {p_kb:.0f}kB / Transient: {t_kb:.1f}kB"
        else:
            return "> Javacard Memory not installed"

    def update_memory(self, reader_idx: int = 0):
        """Update memory info from card."""
        # Import here to avoid circular imports
        from measure import get_memory

        memory = get_memory(reader=reader_idx)
        if memory is None or memory == -1:
            self.storage["persistent"] = -1
            self.storage["transient"] = -1
            self.storage["persistent_total"] = -1
            return

        self.storage["persistent"] = memory["persistent"]["free"]
        self.storage["persistent_total"] = memory["persistent"]["total"]
        self.storage["transient"] = (
            memory["transient"]["reset_free"] + memory["transient"]["deselect_free"]
        )

    def _get_reader_index(self) -> int:
        """Get the index of the selected reader."""
        try:
            all_readers = readers()
            filtered_readers = [r for r in all_readers if "SAM" not in str(r).upper()]
            reader_names = [str(r) for r in filtered_readers]
            if self.selected_reader_name in reader_names:
                return reader_names.index(self.selected_reader_name)
        except Exception:
            pass
        return 0

    # =========================================================================
    # Key Management
    # =========================================================================

    def get_key(self):
        """Request key from storage or prompt user."""
        card_id = self.card_id
        if card_id == "__CONTACT_CARD__":
            card_id = None

        self.get_key_signal.emit(card_id)
        self._emit_key_prompt(card_id, needs_prompt=False)

    @pyqtSlot(str)
    def key_setter(self, key: str):
        """
        Set the key from UI prompt.

        Called from UI when user submits key. Sets a pending flag
        that the NFC thread's polling loop will process asynchronously.
        """
        # Check for Fidesmo mode override
        if key == FIDESMO_KEY_SENTINEL:
            self._card_type = CardType.FIDESMO
            self.key = None  # Fidesmo doesn't use a GP key
        else:
            self.key = key
        # Set flag for async processing by the NFC thread
        self._pending_key = key

    def _process_pending_key(self):
        """
        Process pending key setup asynchronously on the NFC thread.

        Called from the polling loop when _pending_key is set.
        """
        if self._pending_key is None:
            return

        key = self._pending_key
        self._pending_key = None
        installed = {}

        # Emit mode signal BEFORE any card I/O so the UI updates
        # regardless of whether subsequent reads succeed.
        if self.is_fidesmo:
            self.key = None  # Clear any GP key — Fidesmo doesn't use one
            real_uid = (
                self.current_uid if self.current_uid != "__CONTACT_CARD__" else None
            )
            if real_uid:
                self.current_identifier = CardIdentifier(uid=real_uid)
            self.fidesmo_mode_signal.emit(True)
        else:
            # GP card — exit Fidesmo mode if it was active
            self.fidesmo_mode_signal.emit(False)

        try:
            reader_idx = self._get_reader_index()
            self.update_memory(reader_idx)

            if not self.is_fidesmo:
                # Standard GP path - existing logic
                self.retrieve_cplc_and_update_identifier()

                if self.current_identifier and self.current_identifier.cplc_hash:
                    real_uid = (
                        self.current_uid if self.current_uid != "__CONTACT_CARD__" else None
                    )
                    self.cplc_retrieved_signal.emit(
                        real_uid or "", self.current_identifier.cplc_hash
                    )

            self.title_bar_signal.emit(self.make_title_bar_string())
            installed = self.get_installed_apps(_internal=True)  # _internal=True since we're on NFC thread

        except Exception as e:
            self._emit_error(f"Error during key setup: {e}")

        finally:
            # Always emit the installed apps signal so loading dialog hides
            self.installed_apps_updated_signal.emit(installed)

    def change_key(self, new_key: str):
        """Change the card's GlobalPlatform key."""
        storage_key = self.card_id if self.card_id != "__CONTACT_CARD__" else None

        if new_key == DEFAULT_KEY:
            cmd = ["--unlock-card"]
        else:
            cmd = ["--lock", new_key]

        result = self.run_gp(cmd, "Unable to change key:")
        if result == -1:
            return

        if storage_key:
            self.known_tags_update_signal.emit(storage_key, new_key)

    def change_key_with_config(
        self,
        new_config: "KeyConfiguration",
        old_config: "KeyConfiguration | None" = None,
    ):
        """
        Change the card's GlobalPlatform key(s) using a KeyConfiguration.

        Supports both single-key and separate-key (SCP03) modes.

        Args:
            new_config: New key configuration
            old_config: Current config if using separate keys for auth
        """
        from ..models.key_config import KeyMode

        if self.is_fidesmo:
            self._emit_error("Key changes are not supported on Fidesmo devices")
            return

        storage_key = self.card_id if self.card_id != "__CONTACT_CARD__" else None

        if not self.selected_reader_name:
            self._emit_error("No reader selected")
            return

        # Build the lock command based on new config
        # Note: Use --lock even for default key, as --unlock-card fails on some cards
        if new_config.mode == KeyMode.SINGLE:
            lock_args = ["--lock", new_config.static_key]
        else:
            # Separate keys mode (SCP03) - include key version
            lock_args = [
                "--lock-enc", new_config.enc_key,
                "--lock-mac", new_config.mac_key,
                "--lock-dek", new_config.dek_key,
                "--new-keyver", "1",  # Key version for new keys
            ]

        # Run the command with appropriate authentication
        if old_config and old_config.mode == KeyMode.SEPARATE:
            # Authenticate with separate keys - run directly
            result = self._run_gp_with_separate_keys(
                lock_args,
                enc_key=old_config.enc_key,
                mac_key=old_config.mac_key,
                dek_key=old_config.dek_key,
            )
        else:
            # Authenticate with single key - use run_gp
            result = self.run_gp(lock_args, "Unable to change key:")

        if result == -1 or result is None:
            return

        # Update local key reference
        self.key = new_config.get_effective_key()

        # Emit success
        self._emit_operation_complete(True, "Key changed successfully")

        # Notify storage to update
        if storage_key:
            # Emit both signals for compatibility
            self.known_tags_update_signal.emit(storage_key, self.key)
            self.key_config_update_signal.emit(storage_key, new_config)

    def _run_gp_with_separate_keys(
        self,
        command: List[str],
        enc_key: str,
        mac_key: str,
        dek_key: str,
        error_preface: str = "Unable to change key:",
        max_retries: int = 2,
    ):
        """Run a GP command with separate ENC/MAC/DEK keys for authentication.

        Args:
            command: The GP command arguments
            enc_key: ENC key for SCP03
            mac_key: MAC key for SCP03
            dek_key: DEK key for SCP03
            error_preface: Prefix for error messages
            max_retries: Number of retries for transient errors
        """
        if self.is_fidesmo:
            return -1
        if not self.selected_reader_name:
            return -1

        # Transient errors that can be retried
        transient_errors = [
            "SCARD_E_NOT_TRANSACTED",
            "SCARD_W_RESET_CARD",
            "SCARD_E_COMM_DATA_LOST",
            "SCARD_E_NO_SMARTCARD",
        ]

        cmd = [
            *self.gp[os.name],
            "--key-enc", enc_key,
            "--key-mac", mac_key,
            "--key-dek", dek_key,
            "-r", self.selected_reader_name,
            *command,
        ]

        last_stderr = ""
        for attempt in range(max_retries + 1):
            result = subprocess.run(cmd, capture_output=True)

            stdout = result.stdout.decode()
            stderr = result.stderr.decode()
            last_stderr = stderr

            # Check for useful output even if returncode is non-zero
            # (GP often returns non-zero with WARN messages but valid data)
            has_useful_output = stdout and (
                "PKG:" in stdout or "APP:" in stdout or "ISD:" in stdout
            )
            if result.returncode == 0 or has_useful_output:
                return stdout

            # Check if this is a transient error that can be retried
            is_transient = any(err in stderr for err in transient_errors)
            if is_transient and attempt < max_retries:
                time.sleep(0.5)
                continue
            else:
                break

        self._emit_error(f"{error_preface} {last_stderr[:60]}")
        return -1

    # =========================================================================
    # GlobalPlatform Commands
    # =========================================================================

    def run_gp(self, command: List[str], error_preface: str = "Error:", max_retries: int = 2):
        """Run a GlobalPlatformPro command with retry logic for transient errors.

        Automatically uses separate ENC/MAC/DEK keys when a SEPARATE
        KeyConfiguration is active (SCP03), otherwise uses a single key.

        Args:
            command: The GP command arguments
            error_preface: Prefix for error messages
            max_retries: Number of retries for transient errors like SCARD_E_NOT_TRANSACTED
        """
        if not self.key or self.is_fidesmo:
            return None  # Protect unknown tags and Fidesmo devices

        # Route to separate-key path if key config is SEPARATE mode
        if self._key_config and hasattr(self._key_config, 'mode'):
            from ..models.key_config import KeyMode
            if self._key_config.mode == KeyMode.SEPARATE:
                return self._run_gp_with_separate_keys(
                    command,
                    enc_key=self._key_config.enc_key,
                    mac_key=self._key_config.mac_key,
                    dek_key=self._key_config.dek_key,
                    error_preface=error_preface,
                    max_retries=max_retries,
                )

        # Transient errors that can be retried
        transient_errors = [
            "SCARD_E_NOT_TRANSACTED",
            "SCARD_W_RESET_CARD",
            "SCARD_E_COMM_DATA_LOST",
            "SCARD_E_NO_SMARTCARD",
        ]

        last_stderr = ""
        for attempt in range(max_retries + 1):
            result = subprocess.run(
                [
                    *self.gp[os.name],
                    "-k",
                    self.key,
                    "-r",
                    self.selected_reader_name,
                    *command,
                ],
                capture_output=True,
            )

            stdout = result.stdout.decode()
            stderr = result.stderr.decode()
            last_stderr = stderr

            # Check for useful output
            has_useful_output = stdout and (
                "PKG:" in stdout or "APP:" in stdout or "ISD:" in stdout
            )
            if result.returncode == 0 or has_useful_output:
                return stdout

            # Check if this is a transient error that can be retried
            is_transient = any(err in stderr for err in transient_errors)
            if is_transient and attempt < max_retries:
                # Wait briefly before retrying to allow card/reader to stabilize
                time.sleep(0.5)
                continue
            else:
                # Either not transient or out of retries
                break

        self._emit_error(f"{error_preface} {last_stderr[:60]}")
        return -1

    def get_installed_apps(self, _internal: bool = False) -> Dict[str, Optional[str]]:
        """
        Get list of installed apps from the card.

        Returns:
            Dict mapping AID to version (or None if no version)
        """
        if not self.selected_reader_name:
            self._emit_status("No reader selected for get_installed_apps.")
            return {}

        if self.is_fidesmo:
            return self._get_installed_apps_fdsm(_internal)

        if not _internal:
            self.pause()
            self._paused_ack.wait(timeout=1.0)

        try:
            result = self.run_gp(["--list"], "Unable to list apps:")
            if result is None or result == -1:
                return {}

            lines = result.splitlines()
            pkg_app_versions: Dict[str, Optional[str]] = {}
            current_pkg_version: Optional[str] = None
            parsing_pkg_block = False
            installed_set = set()

            for line in lines:
                line = line.strip()

                if line.startswith("PKG:"):
                    parsing_pkg_block = True
                    current_pkg_version = None
                    continue

                if parsing_pkg_block:
                    if not line or line.startswith("PKG:") or line.startswith("APP:"):
                        parsing_pkg_block = False
                    else:
                        if "Version:" in line:
                            parts = line.split("Version:", 1)
                            current_pkg_version = parts[1].strip()
                        elif "Applet:" in line:
                            parts = line.split("Applet:", 1)
                            raw_aid = parts[1].strip()
                            norm_aid = raw_aid.replace(" ", "").upper()
                            pkg_app_versions[norm_aid] = current_pkg_version

                if line.startswith("APP:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        raw_aid = parts[1]
                        norm_aid = raw_aid.replace(" ", "").upper()
                        installed_set.add(norm_aid)

            # Build result dict
            installed_apps: Dict[str, Optional[str]] = {}
            for aid in installed_set:
                installed_apps[aid] = pkg_app_versions.get(aid)

            return installed_apps

        except Exception as e:
            self._emit_error(f"Exception listing apps: {e}")
            return {}
        finally:
            if not _internal:
                self.resume()

    def _get_installed_apps_fdsm(self, _internal=False):
        """Get installed apps from Fidesmo device via FDSM."""
        if not self.selected_reader_name:
            return {}
        if not _internal:
            self.pause()
            self._paused_ack.wait(timeout=1.0)
        try:
            fdsm = self._get_fdsm_service()
            auth_token, _ = self._get_fidesmo_auth()
            return fdsm.list_applets(self.selected_reader_name, auth_token=auth_token)
        except Exception as e:
            self._emit_error(f"FDSM list error: {e}")
            return {}
        finally:
            if not _internal:
                self.resume()

    def get_card_info(self) -> Optional[Dict[str, Any]]:
        """
        Get card information including SCP version.

        Returns:
            Dict with card info including:
            - scp_version: "02", "03", or None if unknown
            - scp_i_param: Implementation parameter (hex)
            - key_version: Current key version
            - card_data: Raw card data if available
            Returns None on error.
        """
        if not self.selected_reader_name:
            return None

        self.pause()
        self._paused_ack.wait(timeout=1.0)

        try:
            result = self.run_gp(["--info"], "Unable to get card info:")
            if result == -1 or not result:
                return None

            info = {
                "scp_version": None,
                "scp_i_param": None,
                "key_version": None,
                "supports_scp03": False,
            }

            for line in result.splitlines():
                line = line.strip()

                # Parse SCP version (e.g., "SCP version: 03 (i=70)")
                if "SCP" in line and "version" in line.lower():
                    import re
                    # Match patterns like "SCP02", "SCP03", "SCP version: 03"
                    scp_match = re.search(r'SCP\s*(\d{2})', line, re.IGNORECASE)
                    if scp_match:
                        info["scp_version"] = scp_match.group(1)
                        info["supports_scp03"] = info["scp_version"] == "03"

                    # Match i-parameter (e.g., "i=70" or "(i=70)")
                    i_match = re.search(r'i\s*=\s*([0-9A-Fa-f]+)', line)
                    if i_match:
                        info["scp_i_param"] = i_match.group(1)

                # Parse key version
                if "key version" in line.lower():
                    import re
                    kv_match = re.search(r'(\d+)', line)
                    if kv_match:
                        info["key_version"] = kv_match.group(1)

            return info

        except Exception as e:
            self._emit_error(f"Exception getting card info: {e}")
            return None
        finally:
            self.resume()

    def supports_scp03(self) -> Optional[bool]:
        """
        Check if the current card supports SCP03.

        Returns:
            True if SCP03 supported, False if not, None if detection failed.
        """
        info = self.get_card_info()
        if info:
            return info.get("supports_scp03", False)
        return None

    # =========================================================================
    # Installation
    # =========================================================================

    def install_app(self, cap_file_path: str, params: Optional[Dict[str, Any]] = None):
        """
        Install an applet from a CAP file.

        Args:
            cap_file_path: Path to the CAP file
            params: Optional installation parameters
        """
        if not self.selected_reader_name:
            self._emit_operation_result(False, "No reader selected.")
            return

        if self.is_fidesmo:
            return self._install_app_fdsm(cap_file_path, params)

        self.pause()
        self._paused_ack.wait(timeout=1.0)

        try:
            if self.key is None or len(self.key) == 0:
                self.show_key_prompt_signal.emit(self.current_uid)
                self._emit_key_prompt(self.current_uid, needs_prompt=True)

            if self.key is None:
                self._emit_error("No valid key has been provided")
                return

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
                cmd.extend(["--params", *params["param_string"].split(" ")])

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                installed = self.get_installed_apps(_internal=True)
                self.installed_apps_updated_signal.emit(installed)
                self._emit_installed_apps_updated(installed)
            else:
                stderr = result.stderr
                if "[WARN]" in stderr:
                    lines = [l for l in stderr.split("\n") if not l.startswith("[WARN]")]
                    stderr = "\n".join(lines).strip()
                err_msg = f"Install failed: {stderr[:100]}"
                self._emit_error(err_msg)
                # Try to remove the app
                self.uninstall_app_by_cap(cap_file_path)

        except Exception as e:
            err_msg = f"Install error: {e}"
            self._emit_error(err_msg)
        finally:
            if os.path.exists(cap_file_path) and not self.app.config.get(
                "cache_latest_release", False
            ):
                os.remove(cap_file_path)
            self.update_memory(self._get_reader_index())
            self.title_bar_signal.emit(self.make_title_bar_string())
            self.resume()

    def _install_app_fdsm(self, cap_file_path, params=None):
        """Install an applet on a Fidesmo device via FDSM."""
        if not self.selected_reader_name:
            self._emit_error("No reader selected")
            return -1

        self.pause()
        self._paused_ack.wait(timeout=1.0)

        try:
            fdsm = self._get_fdsm_service()
            auth_token, app_id = self._get_fidesmo_auth()

            # Extract params string if params is a dict (from plugin dialog)
            params_str = None
            if isinstance(params, dict):
                params_str = params.get("param_string") or params.get("params")
            elif isinstance(params, str):
                params_str = params

            result = fdsm.install_applet(
                reader=self.selected_reader_name,
                cap_path=cap_file_path,
                auth_token=auth_token,
                app_id=app_id,
                params=params_str,
            )

            if result.success:
                installed = self.get_installed_apps(_internal=True)
                self.installed_apps_updated_signal.emit(installed)
                return 0
            else:
                self._emit_error(f"FDSM install failed: {result.stderr}")
                return -1
        except Exception as e:
            self._emit_error(f"FDSM install error: {e}")
            return -1
        finally:
            self.resume()

    # =========================================================================
    # Uninstallation
    # =========================================================================

    def uninstall_app(
        self, aid: str, force: bool = False, _internal: bool = False
    ):
        """
        Uninstall an applet by AID.

        Args:
            aid: Application Identifier
            force: Force deletion
            _internal: Internal call (don't pause)
        """
        if not self.selected_reader_name:
            self._emit_operation_result(False, "No reader selected.")
            return

        if self.is_fidesmo:
            return self._uninstall_app_fdsm(aid, force)

        if not _internal:
            self.pause()
            self._paused_ack.wait(timeout=1.0)

        try:
            if self.key is None:
                self._emit_operation_result(False, "No valid key has been provided")
                return

            cmd = [*self.gp[os.name], "-k", self.key, "--delete"]
            cmd.extend([aid, "-r", self.selected_reader_name])
            if force:
                cmd.append("-f")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if len(result.stderr) == 0:
                self._emit_operation_result(True, f"Uninstalled {aid}")
                installed = self.get_installed_apps(_internal=True)
                self.installed_apps_updated_signal.emit(installed)
                self._emit_installed_apps_updated(installed)
            else:
                if result.stderr.startswith(
                    "Failed to open secure channel: Card cryptogram invalid!"
                ):
                    self.key = None
                    storage_key = (
                        self.card_id if self.card_id != "__CONTACT_CARD__" else None
                    )
                    if storage_key:
                        self.known_tags_update_signal.emit(storage_key, "False")
                    self._emit_error(
                        "Invalid key used: further attempts with invalid keys can brick the device!"
                    )
                else:
                    self._emit_error(result.stderr)

        except Exception as e:
            err_msg = f"Uninstall error (AID): {e}"
            self._emit_operation_result(False, err_msg)
            self._emit_error(err_msg)
        finally:
            self.update_memory(self._get_reader_index())
            self.title_bar_signal.emit(self.make_title_bar_string())
            if not _internal:
                self.resume()

    def _uninstall_app_fdsm(self, aid, force=False):
        """Uninstall an applet from a Fidesmo device via FDSM."""
        if not self.selected_reader_name:
            self._emit_error("No reader selected")
            return -1

        self.pause()
        self._paused_ack.wait(timeout=1.0)

        try:
            fdsm = self._get_fdsm_service()
            auth_token, app_id = self._get_fidesmo_auth()
            result = fdsm.uninstall_applet(
                reader=self.selected_reader_name,
                target=aid,
                auth_token=auth_token,
                app_id=app_id,
            )

            if result.success:
                installed = self.get_installed_apps(_internal=True)
                self.installed_apps_updated_signal.emit(installed)
                return 0
            else:
                self._emit_error(f"FDSM uninstall failed: {result.stderr}")
                return -1
        except Exception as e:
            self._emit_error(f"FDSM uninstall error: {e}")
            return -1
        finally:
            self.resume()

    def uninstall_app_by_cap(
        self,
        cap_file_path: str,
        fallback_aid: Optional[str] = None,
        force: bool = False,
    ):
        """
        Uninstall an applet by CAP file.

        Args:
            cap_file_path: Path to the CAP file
            fallback_aid: AID to use if CAP uninstall fails
            force: Force deletion
        """
        if self.is_fidesmo:
            if fallback_aid:
                return self.uninstall_app(fallback_aid, force=force)
            self._emit_operation_result(False, "CAP-based uninstall not supported on Fidesmo devices")
            return

        if not self.selected_reader_name:
            self._emit_operation_result(False, "No reader selected.")
            return

        if self.key is None:
            self._emit_operation_result(False, "No valid key has been provided")
            return

        self.pause()
        self._paused_ack.wait(timeout=1.0)

        try:
            cmd = [*self.gp[os.name], "-k", self.key, "--uninstall"]
            if force:
                cmd.append("-f")
            cmd.extend([cap_file_path, "-r", self.selected_reader_name])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                installed = self.get_installed_apps(_internal=True)
                self.installed_apps_updated_signal.emit(installed)
                self._emit_installed_apps_updated(installed)
            else:
                manifest = extract_manifest_from_cap(cap_file_path)
                fallback_aid = get_selected_manifest(manifest)["aid"]

                if fallback_aid:
                    self.uninstall_app(fallback_aid, force=force, _internal=True)
                else:
                    self._emit_operation_result(False, "Failed to uninstall")

        except Exception as e:
            err_msg = f"Uninstall error (CAP file): {e}"
            self._emit_error(err_msg)

            if fallback_aid:
                self._emit_status(f"Falling back to AID-based uninstall: {fallback_aid}")
                self.uninstall_app(fallback_aid, force=force, _internal=True)
            else:
                self._emit_operation_result(False, err_msg)
        finally:
            if os.path.exists(cap_file_path):
                os.remove(cap_file_path)
            self.update_memory(self._get_reader_index())
            self.title_bar_signal.emit(self.make_title_bar_string())
            self.resume()

    # =========================================================================
    # EventBus Emission Helpers
    # =========================================================================

    def _emit_error(self, message: str) -> None:
        """Emit error via signal and optionally EventBus."""
        print(message)
        self.error_signal.emit(message)

        if self._event_bus:
            self._event_bus.emit(ErrorEvent(
                message=message,
                recoverable=True,
            ))

    def _emit_status(self, message: str) -> None:
        """Emit status via signal and optionally EventBus."""
        self.status_update_signal.emit(message)

        if self._event_bus:
            self._event_bus.emit(StatusMessageEvent(
                message=message,
                level="info",
            ))

    def _emit_operation_result(self, success: bool, message: str) -> None:
        """Emit operation result via signal and optionally EventBus."""
        self.operation_complete_signal.emit(success, message)

        if self._event_bus:
            self._event_bus.emit(OperationResultEvent(
                success=success,
                message=message,
                operation_type="nfc_operation",
            ))

    def _emit_card_presence(self, present: bool, uid: Optional[str]) -> None:
        """Emit card presence via EventBus."""
        if self._event_bus:
            self._event_bus.emit(CardPresenceEvent(
                present=present,
                uid=uid,
            ))

    def _emit_key_prompt(self, card_id: Optional[str], needs_prompt: bool) -> None:
        """Emit key prompt request via EventBus."""
        if self._event_bus:
            self._event_bus.emit(KeyPromptEvent(
                card_id=card_id or "",
                needs_prompt=needs_prompt,
            ))

    def _emit_installed_apps_updated(self, apps: Dict[str, Optional[str]]) -> None:
        """Emit installed apps updated via EventBus."""
        if self._event_bus:
            self._event_bus.emit(InstalledAppsUpdatedEvent(apps=apps))


# =============================================================================
# Helper Functions
# =============================================================================


def detect_encoding(file_path: str) -> str:
    """Detect the file encoding using chardet."""
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result["encoding"]


def extract_manifest_from_cap(
    cap_file_path: str, output_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extract the MANIFEST.MF file from a CAP archive.

    Args:
        cap_file_path: Path to the CAP archive (ZIP file)
        output_dir: Optional directory to save MANIFEST.MF

    Returns:
        Dictionary with parsed manifest data, or None on error
    """
    temp_path = "temp_manifest.MF"
    manifest_content = ""

    try:
        with zipfile.ZipFile(cap_file_path, "r") as zip_ref:
            file_list = zip_ref.namelist()
            manifest_file = "META-INF/MANIFEST.MF"

            if manifest_file not in file_list:
                print(f"Error: {manifest_file} not found in the CAP archive.")
                return None

            with zip_ref.open(manifest_file) as mf_file:
                with open(temp_path, "wb") as temp_file:
                    temp_file.write(mf_file.read())

                encoding = detect_encoding(temp_path)

                with open(temp_path, "r", encoding=encoding) as temp_file:
                    manifest_content = temp_file.read()

                if output_dir:
                    output_file_path = os.path.join(output_dir, "MANIFEST.MF")
                    with open(output_file_path, "w") as output_file:
                        output_file.write(manifest_content)
                    print(f"MANIFEST.MF extracted to {output_file_path}")

                return parse_manifest(manifest_content)

    except zipfile.BadZipFile:
        print(f"Error: The file {cap_file_path} is not a valid ZIP archive.")
        return None
    except Exception as e:
        print(cap_file_path)
        print(f"An error occurred while extracting the MANIFEST.MF: {e}")
        print(manifest_content)
        return None
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


def parse_manifest(manifest_content: str) -> Dict[str, Any]:
    """
    Parse the manifest content to extract all fields.

    Args:
        manifest_content: The contents of the MANIFEST.MF file

    Returns:
        Dictionary with parsed manifest data
    """
    data: Dict[str, Any] = {}

    pattern = r"(?P<key>^[A-Za-z0-9\-]+):\s*(?P<value>.*)"
    matches = re.finditer(pattern, manifest_content, re.MULTILINE)

    for match in matches:
        key = match.group("key").strip()
        value = match.group("value").strip()

        if key == "Java-Card-Applet-AID":
            value = value.replace(":", "")

        if key == "Classic-Package-AID":
            value = value.replace("aid", "").replace("/", "")

        elif key in ("Java-Card-Package-Version", "Runtime-Descriptor-Version"):
            if key == "Runtime-Descriptor-Version" and len(value) < 3:
                while len(value) < 3:
                    value = tuple([*value, 0])

        data[key] = value

    return data


def get_selected_manifest(manifest_dict: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extract selected fields from manifest."""
    return {
        "name": manifest_dict.get("Name", None),
        "aid": manifest_dict.get("Java-Card-Applet-AID", None)
        or manifest_dict.get("Classic-Package-AID", None),
        "app_version": manifest_dict.get("Java-Card-Package-Version", None),
        "jcop_version": manifest_dict.get("Runtime-Descriptor-Version", None),
    }


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
