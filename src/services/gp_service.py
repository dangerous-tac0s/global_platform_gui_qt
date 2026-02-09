"""
GPService - Wrapper for GlobalPlatformPro (gp.jar/gp.exe) operations.

This service handles all subprocess calls to the GP tool for card operations
like listing apps, installing/uninstalling applets, and key management.
"""

import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from pathlib import Path

import chardet


# Default key for new/unlocked cards
DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


@dataclass
class GPResult:
    """Result of a GlobalPlatformPro command."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    command: List[str] = field(default_factory=list)

    @property
    def is_invalid_key_error(self) -> bool:
        """Check if the error indicates an invalid key was used."""
        return "Card cryptogram invalid" in self.stderr


@dataclass
class ManifestInfo:
    """Parsed information from a CAP file manifest."""
    name: Optional[str] = None
    aid: Optional[str] = None
    app_version: Optional[str] = None
    jcop_version: Optional[str] = None


@dataclass
class CPLCData:
    """
    Parsed CPLC (Card Production Life Cycle) data.

    CPLC provides a universal card identifier that works across both contact
    and contactless interfaces, unlike UID which only works contactless.
    """
    raw_hex: str  # Full CPLC hex data for hashing
    ic_fabricator: Optional[str] = None
    ic_type: Optional[str] = None
    os_id: Optional[str] = None
    os_release_date: Optional[str] = None
    os_release_level: Optional[str] = None
    ic_fabrication_date: Optional[str] = None
    ic_serial_number: Optional[str] = None
    ic_batch_id: Optional[str] = None
    ic_module_fabricator: Optional[str] = None
    ic_module_packaging_date: Optional[str] = None
    icc_manufacturer: Optional[str] = None
    ic_embedding_date: Optional[str] = None
    ic_pre_personalizer: Optional[str] = None
    ic_pre_personalization_date: Optional[str] = None
    ic_pre_personalization_equipment_id: Optional[str] = None
    ic_personalizer: Optional[str] = None
    ic_personalization_date: Optional[str] = None
    ic_personalization_equipment_id: Optional[str] = None

    def compute_hash(self) -> str:
        """
        Compute the CPLC-based identifier from raw CPLC hex data.

        Returns format: "CPLC_" + first 16 hex chars of SHA-256 hash.
        """
        import hashlib
        h = hashlib.sha256(self.raw_hex.upper().encode()).hexdigest()
        return f"CPLC_{h[:16].upper()}"


class GPService:
    """
    Service for interacting with GlobalPlatformPro.

    This is a pure Python service with no Qt dependencies,
    making it easy to unit test with mocked subprocess.
    """

    def __init__(
        self,
        gp_path: Optional[str] = None,
        verbose: bool = False,
        working_dir: Optional[str] = None,
    ):
        """
        Initialize the GP service.

        Args:
            gp_path: Path to gp.exe or gp.jar. Auto-detected if None.
            verbose: Enable verbose logging of commands
            working_dir: Working directory for subprocess calls
        """
        self.verbose = verbose
        self.working_dir = working_dir
        self._command_log: List[str] = []

        # Determine GP executable based on OS
        if gp_path:
            self._gp_cmd = self._build_gp_command(gp_path)
        else:
            self._gp_cmd = self._auto_detect_gp()

    def _auto_detect_gp(self) -> List[str]:
        """Auto-detect the GP executable based on OS."""
        if os.name == "nt":
            return [resource_path("gp.exe")]
        else:
            return ["java", "-jar", resource_path("gp.jar")]

    def _build_gp_command(self, gp_path: str) -> List[str]:
        """Build the GP command based on the path."""
        if gp_path.endswith(".jar"):
            return ["java", "-jar", gp_path]
        return [gp_path]

    def _run_command(
        self,
        args: List[str],
        key: Optional[str] = None,
        reader: Optional[str] = None,
        timeout: int = 60,
        key_config=None,
    ) -> GPResult:
        """
        Run a GP command with optional key and reader.

        Args:
            args: Command arguments (e.g., ['--list'])
            key: Card master key (hex string)
            reader: Reader name
            timeout: Command timeout in seconds
            key_config: Optional KeyConfiguration for separate ENC/MAC/DEK keys

        Returns:
            GPResult with command output
        """
        cmd = list(self._gp_cmd)

        # Use separate keys if key_config is in SEPARATE mode
        if key_config and hasattr(key_config, 'mode') and key_config.mode.value == "separate":
            cmd.extend(["--key-enc", key_config.enc_key])
            cmd.extend(["--key-mac", key_config.mac_key])
            cmd.extend(["--key-dek", key_config.dek_key])
        elif key:
            cmd.extend(["-k", key])

        if reader:
            cmd.extend(["-r", reader])

        cmd.extend(args)

        if self.verbose:
            # Redact key in log
            log_cmd = list(cmd)
            if "-k" in log_cmd:
                key_idx = log_cmd.index("-k")
                if key_idx + 1 < len(log_cmd):
                    log_cmd[key_idx + 1] = "***REDACTED***"
            self._command_log.append(" ".join(log_cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
            )
            # Only treat as error if returncode is non-zero or stderr has actual errors
            # (not just WARN messages which are common with GP)
            has_real_error = result.stderr and not all(
                line.strip().startswith("[WARN]") or not line.strip()
                for line in result.stderr.splitlines()
            )
            return GPResult(
                success=result.returncode == 0 and not has_real_error,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                command=cmd,
            )
        except subprocess.TimeoutExpired:
            return GPResult(
                success=False,
                stdout="",
                stderr="Command timed out",
                return_code=-1,
                command=cmd,
            )
        except Exception as e:
            return GPResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=cmd,
            )

    def list_applets(self, reader: str, key: str) -> Dict[str, Optional[str]]:
        """
        List installed applets on the card.

        Args:
            reader: Reader name
            key: Card master key

        Returns:
            Dict mapping AID (uppercase, no spaces) to version string or None
        """
        result = self._run_command(["--list"], key=key, reader=reader)

        if not result.success:
            return {}

        return self._parse_list_output(result.stdout)

    def _parse_list_output(self, output: str) -> Dict[str, Optional[str]]:
        """
        Parse the output of gp --list.

        Extracts PKG blocks (with versions) and APP lines (installed applets).
        """
        lines = output.splitlines()

        pkg_app_versions: Dict[str, Optional[str]] = {}
        current_pkg_version: Optional[str] = None
        parsing_pkg_block = False
        installed_set: set = set()

        for line in lines:
            line = line.strip()

            # Detect start of PKG block
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

            # APP lines indicate installed applets
            if line.startswith("APP:"):
                parts = line.split()
                if len(parts) >= 2:
                    raw_aid = parts[1]
                    norm_aid = raw_aid.replace(" ", "").upper()
                    installed_set.add(norm_aid)

        # Build result with versions for installed applets
        installed_apps: Dict[str, Optional[str]] = {}
        for aid in installed_set:
            installed_apps[aid] = pkg_app_versions.get(aid)

        return installed_apps

    def install_applet(
        self,
        reader: str,
        key: str,
        cap_path: str,
        params: Optional[str] = None,
        create_aid: Optional[str] = None,
    ) -> GPResult:
        """
        Install an applet on the card.

        Args:
            reader: Reader name
            key: Card master key
            cap_path: Path to CAP file
            params: Install parameters (hex string, space-separated)
            create_aid: AID to create during install

        Returns:
            GPResult with operation status
        """
        args = ["--install", cap_path]

        if params:
            # Split params by space for --params argument
            args.extend(["--params", *params.split()])

        if create_aid:
            args.extend(["--create", create_aid])

        return self._run_command(args, key=key, reader=reader)

    def uninstall_applet(
        self,
        reader: str,
        key: str,
        target: str,
        force: bool = False,
    ) -> GPResult:
        """
        Uninstall an applet by AID or CAP file.

        Args:
            reader: Reader name
            key: Card master key
            target: AID or CAP file path
            force: Force uninstall even with dependencies

        Returns:
            GPResult with operation status
        """
        # Use --uninstall for CAP files, --delete for AIDs
        if target.endswith(".cap"):
            args = ["--uninstall", target]
        else:
            args = ["--delete", target]

        if force:
            args.append("-f")

        return self._run_command(args, key=key, reader=reader)

    def change_key(
        self,
        reader: str,
        old_key: str,
        new_key: str,
    ) -> GPResult:
        """
        Change the card master key.

        Args:
            reader: Reader name
            old_key: Current master key
            new_key: New master key

        Returns:
            GPResult with operation status
        """
        if new_key == DEFAULT_KEY:
            # Unlock to default key
            args = ["--unlock-card"]
        else:
            # Lock with new key
            args = ["--lock", new_key]

        return self._run_command(args, key=old_key, reader=reader)

    def change_key_with_config(
        self,
        reader: str,
        old_key: str,
        new_config: "KeyConfiguration",
        old_config: "KeyConfiguration | None" = None,
    ) -> GPResult:
        """
        Change the card key(s) using a KeyConfiguration.

        Supports both single-key (SCP02) and separate-key (SCP03) modes.

        Args:
            reader: Reader name
            old_key: Current master key (for single-key auth)
            new_config: New key configuration
            old_config: Current config if using separate keys for auth

        Returns:
            GPResult with operation status
        """
        from ..models.key_config import KeyMode

        # Build the command arguments
        args = []

        # Check if resetting to default
        if (
            new_config.mode == KeyMode.SINGLE
            and new_config.static_key == DEFAULT_KEY
        ):
            args = ["--unlock-card"]
        elif new_config.mode == KeyMode.SINGLE:
            # Single key mode - use standard --lock
            args = ["--lock", new_config.static_key]
        else:
            # Separate keys mode (SCP03) - use individual lock commands
            args = [
                "--lock-enc", new_config.enc_key,
                "--lock-mac", new_config.mac_key,
                "--lock-dek", new_config.dek_key,
            ]

        # Handle authentication
        if old_config and old_config.mode == KeyMode.SEPARATE:
            # Authenticate with separate keys
            return self._run_command_with_separate_keys(
                args,
                enc_key=old_config.enc_key,
                mac_key=old_config.mac_key,
                dek_key=old_config.dek_key,
                reader=reader,
            )
        else:
            # Authenticate with single key
            return self._run_command(args, key=old_key, reader=reader)

    def _run_command_with_separate_keys(
        self,
        args: List[str],
        enc_key: str,
        mac_key: str,
        dek_key: str,
        reader: Optional[str] = None,
        timeout: int = 60,
    ) -> GPResult:
        """
        Run a GP command with separate ENC/MAC/DEK keys for authentication.

        Args:
            args: Command arguments
            enc_key: ENC key (hex string)
            mac_key: MAC key (hex string)
            dek_key: DEK key (hex string)
            reader: Reader name
            timeout: Command timeout in seconds

        Returns:
            GPResult with command output
        """
        cmd = list(self._gp_cmd)

        # Add separate keys for authentication
        cmd.extend(["--key-enc", enc_key])
        cmd.extend(["--key-mac", mac_key])
        cmd.extend(["--key-dek", dek_key])

        if reader:
            cmd.extend(["-r", reader])

        cmd.extend(args)

        if self.verbose:
            # Redact keys in log
            log_cmd = list(cmd)
            for flag in ["--key-enc", "--key-mac", "--key-dek"]:
                if flag in log_cmd:
                    idx = log_cmd.index(flag)
                    if idx + 1 < len(log_cmd):
                        log_cmd[idx + 1] = "***REDACTED***"
            self._command_log.append(" ".join(log_cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
            )
            has_real_error = result.stderr and not all(
                line.strip().startswith("[WARN]") or not line.strip()
                for line in result.stderr.splitlines()
            )
            return GPResult(
                success=result.returncode == 0 and not has_real_error,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                command=cmd,
            )
        except subprocess.TimeoutExpired:
            return GPResult(
                success=False,
                stdout="",
                stderr="Command timed out",
                return_code=-1,
                command=cmd,
            )
        except Exception as e:
            return GPResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                command=cmd,
            )

    def get_card_info(self, reader: str, key: str) -> GPResult:
        """
        Get card information.

        Args:
            reader: Reader name
            key: Card master key

        Returns:
            GPResult with card info in stdout
        """
        return self._run_command(["--info"], key=key, reader=reader)

    def get_cplc_data(self, reader: str, key: str, key_config=None) -> Optional[CPLCData]:
        """
        Retrieve CPLC (Card Production Life Cycle) data from the card.

        Uses gp --info and parses the CPLC section to extract card
        identification data that works across contact and contactless interfaces.

        Args:
            reader: Reader name
            key: Card master key
            key_config: Optional KeyConfiguration for separate ENC/MAC/DEK keys

        Returns:
            CPLCData if available, None if CPLC retrieval fails
        """
        result = self._run_command(["--info"], key=key, reader=reader, key_config=key_config)
        if not result.success:
            return None

        return self._parse_cplc_from_info(result.stdout)

    def get_cplc_data_no_auth(self, reader: str) -> Optional[CPLCData]:
        """
        Retrieve CPLC data without requiring authentication.

        CPLC is card production data that is typically readable without
        needing the card's master key. GP will use the default key internally.

        Args:
            reader: Reader name

        Returns:
            CPLCData if available, None if CPLC retrieval fails
        """
        # Build command: gp --info -r <reader>
        cmd = list(self._gp_cmd)
        cmd.extend(["-r", reader])
        cmd.append("--info")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.working_dir,
            )
            # Even if auth fails, CPLC might be in the output
            return self._parse_cplc_from_info(result.stdout)
        except Exception:
            return None

    def _parse_cplc_from_info(self, info_output: str) -> Optional[CPLCData]:
        """
        Parse CPLC data from gp --info output.

        GP --info includes CPLC section like:
            CPLC: ICFabricator=4790
                  ICType=D321
                  OperatingSystemID=4700
                  ...

        Note: Uses '=' for field=value pairs, first field on same line as 'CPLC:'

        Args:
            info_output: Raw stdout from gp --info

        Returns:
            CPLCData if CPLC section found, None otherwise
        """
        lines = info_output.splitlines()

        # Find CPLC section and parse fields
        cplc_fields: Dict[str, str] = {}
        raw_hex_parts: List[str] = []
        in_cplc_section = False

        # Mapping from GP output field names to our dataclass fields
        field_mapping = {
            "ICFabricator": "ic_fabricator",
            "ICType": "ic_type",
            "OperatingSystemID": "os_id",
            "OperatingSystemReleaseDate": "os_release_date",
            "OperatingSystemReleaseLevel": "os_release_level",
            "ICFabricationDate": "ic_fabrication_date",
            "ICSerialNumber": "ic_serial_number",
            "ICBatchIdentifier": "ic_batch_id",
            "ICModuleFabricator": "ic_module_fabricator",
            "ICModulePackagingDate": "ic_module_packaging_date",
            "ICCManufacturer": "icc_manufacturer",
            "ICEmbeddingDate": "ic_embedding_date",
            "ICPrePersonalizer": "ic_pre_personalizer",
            "ICPrePersonalizationEquipmentDate": "ic_pre_personalization_date",
            "ICPrePersonalizationEquipmentID": "ic_pre_personalization_equipment_id",
            "ICPersonalizer": "ic_personalizer",
            "ICPersonalizationDate": "ic_personalization_date",
            "ICPersonalizationEquipmentID": "ic_personalization_equipment_id",
        }

        def parse_field(text: str) -> None:
            """Parse a field=value pair and add to cplc_fields."""
            if "=" not in text:
                return
            parts = text.split("=", 1)
            if len(parts) == 2:
                field_name = parts[0].strip()
                field_value = parts[1].strip()
                # Remove any parenthetical annotations like "(2023-06-29)"
                if " (" in field_value:
                    field_value = field_value.split(" (")[0]
                if field_name in field_mapping:
                    cplc_fields[field_mapping[field_name]] = field_value
                    raw_hex_parts.append(field_value)

        for line in lines:
            # Check for CPLC section start: "CPLC: ICFabricator=4790"
            if line.startswith("CPLC:"):
                in_cplc_section = True
                # First field may be on same line
                remainder = line[5:].strip()  # After "CPLC:"
                if remainder:
                    parse_field(remainder)
                continue

            if in_cplc_section:
                stripped = line.strip()

                # End of CPLC section: empty line or new top-level section
                if not stripped:
                    break
                if not line.startswith(" ") and not line.startswith("\t"):
                    # Not indented = new section
                    break

                # Parse continuation line with field=value
                parse_field(stripped)

        if not cplc_fields:
            return None

        # Build raw hex string from all CPLC field values
        raw_hex = "".join(raw_hex_parts)

        return CPLCData(
            raw_hex=raw_hex,
            ic_fabricator=cplc_fields.get("ic_fabricator"),
            ic_type=cplc_fields.get("ic_type"),
            os_id=cplc_fields.get("os_id"),
            os_release_date=cplc_fields.get("os_release_date"),
            os_release_level=cplc_fields.get("os_release_level"),
            ic_fabrication_date=cplc_fields.get("ic_fabrication_date"),
            ic_serial_number=cplc_fields.get("ic_serial_number"),
            ic_batch_id=cplc_fields.get("ic_batch_id"),
            ic_module_fabricator=cplc_fields.get("ic_module_fabricator"),
            ic_module_packaging_date=cplc_fields.get("ic_module_packaging_date"),
            icc_manufacturer=cplc_fields.get("icc_manufacturer"),
            ic_embedding_date=cplc_fields.get("ic_embedding_date"),
            ic_pre_personalizer=cplc_fields.get("ic_pre_personalizer"),
            ic_pre_personalization_date=cplc_fields.get("ic_pre_personalization_date"),
            ic_pre_personalization_equipment_id=cplc_fields.get("ic_pre_personalization_equipment_id"),
            ic_personalizer=cplc_fields.get("ic_personalizer"),
            ic_personalization_date=cplc_fields.get("ic_personalization_date"),
            ic_personalization_equipment_id=cplc_fields.get("ic_personalization_equipment_id"),
        )

    def get_command_log(self) -> List[str]:
        """Get log of executed commands (for verbose/debug mode)."""
        return list(self._command_log)

    def clear_command_log(self) -> None:
        """Clear the command log."""
        self._command_log.clear()


# ============================================================================
# CAP File Utilities
# ============================================================================


def detect_encoding(file_path: str) -> str:
    """Detect file encoding using chardet."""
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result["encoding"] or "utf-8"


def extract_manifest_from_cap(cap_file_path: str) -> Optional[Dict[str, str]]:
    """
    Extract and parse MANIFEST.MF from a CAP file.

    Args:
        cap_file_path: Path to the CAP archive

    Returns:
        Dict with parsed manifest data, or None on error
    """
    temp_path = None
    try:
        with zipfile.ZipFile(cap_file_path, "r") as zip_ref:
            manifest_file = "META-INF/MANIFEST.MF"
            if manifest_file not in zip_ref.namelist():
                return None

            with zip_ref.open(manifest_file) as mf_file:
                temp_path = "temp_manifest.MF"
                with open(temp_path, "wb") as temp_file:
                    temp_file.write(mf_file.read())

                encoding = detect_encoding(temp_path)
                with open(temp_path, "r", encoding=encoding) as temp_file:
                    manifest_content = temp_file.read()

                return parse_manifest(manifest_content)

    except (zipfile.BadZipFile, Exception):
        return None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def parse_manifest(manifest_content: str) -> Dict[str, str]:
    """
    Parse MANIFEST.MF content into a dictionary.

    Args:
        manifest_content: Raw manifest file content

    Returns:
        Dict with parsed key-value pairs
    """
    data: Dict[str, str] = {}

    pattern = r"(?P<key>^[A-Za-z0-9\-]+):\s*(?P<value>.*)"
    matches = re.finditer(pattern, manifest_content, re.MULTILINE)

    for match in matches:
        key = match.group("key").strip()
        value = match.group("value").strip()

        # Normalize AID fields
        if key == "Java-Card-Applet-AID":
            value = value.replace(":", "")
        elif key == "Classic-Package-AID":
            # Fallback for mal-formed AIDs (e.g., VivoKey OTP)
            value = value.replace("aid", "").replace("/", "")

        data[key] = value

    return data


def get_manifest_info(manifest_dict: Dict[str, str]) -> ManifestInfo:
    """
    Extract key information from a parsed manifest.

    Args:
        manifest_dict: Parsed manifest dictionary

    Returns:
        ManifestInfo with extracted fields
    """
    return ManifestInfo(
        name=manifest_dict.get("Name"),
        aid=(
            manifest_dict.get("Java-Card-Applet-AID")
            or manifest_dict.get("Classic-Package-AID")
        ),
        app_version=manifest_dict.get("Java-Card-Package-Version"),
        jcop_version=manifest_dict.get("Runtime-Descriptor-Version"),
    )
