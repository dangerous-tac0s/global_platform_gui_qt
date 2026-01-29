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
    ) -> GPResult:
        """
        Run a GP command with optional key and reader.

        Args:
            args: Command arguments (e.g., ['--list'])
            key: Card master key (hex string)
            reader: Reader name
            timeout: Command timeout in seconds

        Returns:
            GPResult with command output
        """
        cmd = list(self._gp_cmd)

        if key:
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
            return GPResult(
                success=result.returncode == 0 and not result.stderr,
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
