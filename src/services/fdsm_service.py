"""
FDSMService - Wrapper for Fidesmo CLI tool (fdsm.jar) operations.

This service handles all subprocess calls to the FDSM tool for
Fidesmo device operations like listing apps, installing/uninstalling
applets, and querying the Fidesmo app store.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from .gp_service import GPResult, resource_path

# Minimum Java version required by FDSM
FDSM_MIN_JAVA_VERSION = 21


@dataclass
class JavaInfo:
    """Result of a Java installation check."""
    installed: bool = False
    version: Optional[int] = None  # Major version (e.g., 21)
    version_string: Optional[str] = None  # Full version string (e.g., "21.0.2")
    sufficient_for_fdsm: bool = False
    error: Optional[str] = None


def check_java() -> JavaInfo:
    """Check if Java is installed and meets FDSM's minimum version requirement."""
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # java -version outputs to stderr
        output = result.stderr or result.stdout or ""
        # Parse version from strings like:
        #   openjdk version "21.0.2" 2024-01-16
        #   java version "1.8.0_381"
        match = re.search(r'version "(\d+)(?:\.(\d+))?(?:\.(\d+))?', output)
        if match:
            major = int(match.group(1))
            # Java 1.x convention: "1.8" means Java 8
            if major == 1 and match.group(2):
                major = int(match.group(2))
            version_string = match.group(0).replace('version "', '').rstrip('"')
            return JavaInfo(
                installed=True,
                version=major,
                version_string=version_string,
                sufficient_for_fdsm=major >= FDSM_MIN_JAVA_VERSION,
            )
        # Java found but couldn't parse version
        return JavaInfo(
            installed=True,
            version=None,
            version_string=output.split("\n")[0].strip(),
            sufficient_for_fdsm=False,
            error="Could not parse Java version",
        )
    except FileNotFoundError:
        return JavaInfo(installed=False, error="Java is not installed")
    except subprocess.TimeoutExpired:
        return JavaInfo(installed=False, error="Java version check timed out")
    except Exception as e:
        return JavaInfo(installed=False, error=str(e))


@dataclass
class FidesmoStoreApp:
    """An application available from the Fidesmo app store."""
    name: str
    app_id: str
    description: Optional[str] = None
    version: Optional[str] = None
    state: Optional[str] = None


class FDSMService:
    """
    Service for interacting with Fidesmo CLI (fdsm.jar).

    Pure Python service with no Qt dependencies, mirroring GPService pattern.
    All Fidesmo device operations are routed through this service.
    """

    def __init__(
        self,
        fdsm_path: Optional[str] = None,
        verbose: bool = False,
        working_dir: Optional[str] = None,
    ):
        self.verbose = verbose
        self.working_dir = working_dir
        self._command_log: List[str] = []

        if fdsm_path:
            self._fdsm_cmd = self._build_fdsm_command(fdsm_path)
        else:
            self._fdsm_cmd = self._auto_detect_fdsm()

    def _auto_detect_fdsm(self) -> List[str]:
        """Auto-detect the FDSM executable based on OS."""
        if os.name == "nt":
            # Windows: try fdsm.exe first, fall back to jar
            exe_path = resource_path("fdsm.exe")
            if os.path.exists(exe_path):
                return [exe_path]
        return ["java", "-jar", resource_path("fdsm.jar")]

    def _build_fdsm_command(self, fdsm_path: str) -> List[str]:
        """Build the FDSM command based on the path."""
        if fdsm_path.endswith(".jar"):
            return ["java", "-jar", fdsm_path]
        return [fdsm_path]

    def _build_env(
        self,
        auth_token: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build environment dict with Fidesmo auth credentials."""
        env = os.environ.copy()
        if auth_token:
            env["FIDESMO_AUTH"] = auth_token
        if app_id:
            env["FIDESMO_APPID"] = app_id
        return env

    def _run_command(
        self,
        args: List[str],
        reader: Optional[str] = None,
        timeout: int = 60,
        auth_token: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> GPResult:
        """
        Run an FDSM command with optional reader and auth.

        Args:
            args: Command arguments (e.g., ['--card-apps'])
            reader: Reader name
            timeout: Command timeout in seconds
            auth_token: Fidesmo API auth token
            app_id: Fidesmo application ID

        Returns:
            GPResult with command output
        """
        cmd = list(self._fdsm_cmd)

        if reader:
            cmd.extend(["--reader", reader])

        cmd.extend(args)

        env = self._build_env(auth_token, app_id)

        if self.verbose:
            log_cmd = list(cmd)
            self._command_log.append(" ".join(log_cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
                env=env,
            )
            return GPResult(
                success=result.returncode == 0,
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

    def list_applets(
        self,
        reader: str,
        auth_token: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """
        List installed applets on the card via fdsm --card-apps.

        Args:
            reader: Reader name
            auth_token: Optional Fidesmo auth token

        Returns:
            Dict mapping AID (uppercase, no spaces) to version string or None
        """
        result = self._run_command(
            ["--card-apps"],
            reader=reader,
            auth_token=auth_token,
        )
        if not result.success:
            return {}
        return self._parse_card_apps_output(result.stdout)

    def _parse_card_apps_output(self, output: str) -> Dict[str, Optional[str]]:
        """
        Parse fdsm --card-apps output.

        Expected format (best-effort, will be refined with real output):
        Lines containing AID strings, possibly with version info.
        """
        apps: Dict[str, Optional[str]] = {}
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            # Try to extract AID from line
            # Common formats: "AID: A0000001234..." or just hex AIDs
            parts = line.split()
            for part in parts:
                # Look for hex strings that could be AIDs (at least 10 hex chars)
                clean = part.replace(":", "").replace(" ", "").upper()
                if len(clean) >= 10 and all(c in "0123456789ABCDEF" for c in clean):
                    apps[clean] = None
                    break
        return apps

    def install_applet(
        self,
        reader: str,
        cap_path: str,
        auth_token: Optional[str] = None,
        app_id: Optional[str] = None,
        params: Optional[str] = None,
        create_aid: Optional[str] = None,
    ) -> GPResult:
        """
        Install an applet on the card via fdsm --install.

        Args:
            reader: Reader name
            cap_path: Path to CAP file
            auth_token: Fidesmo API auth token (required)
            app_id: Fidesmo application ID
            params: Install parameters (hex string)
            create_aid: AID to create during install

        Returns:
            GPResult with operation status
        """
        args = ["--install", cap_path]

        if params:
            args.extend(["--params", params])

        if create_aid:
            args.extend(["--create", create_aid])

        return self._run_command(
            args,
            reader=reader,
            auth_token=auth_token,
            app_id=app_id,
        )

    def uninstall_applet(
        self,
        reader: str,
        target: str,
        auth_token: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> GPResult:
        """
        Uninstall an applet via fdsm --uninstall.

        Args:
            reader: Reader name
            target: AID or CAP file path
            auth_token: Fidesmo API auth token
            app_id: Fidesmo application ID

        Returns:
            GPResult with operation status
        """
        args = ["--uninstall", target]
        return self._run_command(
            args,
            reader=reader,
            auth_token=auth_token,
            app_id=app_id,
        )

    def get_card_info(
        self,
        reader: str,
        auth_token: Optional[str] = None,
    ) -> GPResult:
        """
        Get card info via fdsm --card-info.

        Args:
            reader: Reader name
            auth_token: Optional auth token

        Returns:
            GPResult with card info in stdout
        """
        return self._run_command(
            ["--card-info"],
            reader=reader,
            auth_token=auth_token,
        )

    def get_store_apps(
        self,
        auth_token: Optional[str] = None,
        show_all: bool = False,
    ) -> List[FidesmoStoreApp]:
        """
        Query Fidesmo app store via fdsm --store-apps.

        Does NOT require a card to be present.

        Args:
            auth_token: Optional auth token
            show_all: If True, show all states (including unpublished)

        Returns:
            List of FidesmoStoreApp entries
        """
        args = ["--store-apps"]
        if show_all:
            args.append("all")

        result = self._run_command(
            args,
            auth_token=auth_token,
            timeout=30,
        )
        if not result.success:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            if "UnsupportedClassVersionError" in error_msg or "class file version" in error_msg:
                raise RuntimeError("FDSM requires Java 21 or newer. Please update your Java installation.")
            raise RuntimeError(f"FDSM store query failed: {error_msg}")
        return self._parse_store_apps_output(result.stdout)

    def _parse_store_apps_output(self, output: str) -> List[FidesmoStoreApp]:
        """
        Parse fdsm --store-apps output.

        Actual format:
            #  appId - name and vendor
            f374c57e - Fidesmo Pay (by Fidesmo AB)
                       Services: install, activate, ...
        """
        apps: List[FidesmoStoreApp] = []
        current_app: Optional[FidesmoStoreApp] = None

        for line in output.splitlines():
            if line.startswith("#") or not line.strip():
                continue

            # App lines start with hex app_id (no leading whitespace)
            if not line[0].isspace():
                # Parse: "f374c57e - Fidesmo Pay (by Fidesmo AB)"
                match = re.match(r'^([0-9a-fA-F]+)\s*-\s*(.+)$', line.strip())
                if match:
                    current_app = FidesmoStoreApp(
                        app_id=match.group(1),
                        name=match.group(2).strip(),
                    )
                    apps.append(current_app)
            elif current_app and "Services:" in line:
                # Parse: "           Services: install, destroy"
                services = line.split("Services:", 1)[1].strip()
                current_app.description = services

        return apps

    def run_service(
        self,
        reader: str,
        service_id: str,
        auth_token: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> GPResult:
        """
        Execute a Fidesmo service delivery via fdsm --run.

        Args:
            reader: Reader name
            service_id: Service ID to deliver
            auth_token: Fidesmo API auth token (required)
            app_id: Fidesmo application ID

        Returns:
            GPResult with operation status
        """
        return self._run_command(
            ["--run", service_id],
            reader=reader,
            auth_token=auth_token,
            app_id=app_id,
        )

    def get_command_log(self) -> List[str]:
        """Get log of executed commands (for verbose/debug mode)."""
        return list(self._command_log)

    def clear_command_log(self) -> None:
        """Clear the command log."""
        self._command_log.clear()
