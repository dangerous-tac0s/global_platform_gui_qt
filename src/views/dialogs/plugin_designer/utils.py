"""
Plugin Designer Utilities

Helper functions for file dialogs and CAP file parsing.
"""

import os
import re
import zipfile
import tempfile
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass
from typing import Optional, Callable

from PyQt5.QtCore import QTimer, QCoreApplication
from PyQt5.QtWidgets import QWidget


@dataclass
class CapMetadata:
    """Metadata extracted from a CAP file."""
    aid: str = ""
    package_name: str = ""
    version: str = ""
    applet_aids: list = None

    def __post_init__(self):
        if self.applet_aids is None:
            self.applet_aids = []


def parse_github_url(url: str) -> tuple[str, str, str]:
    """
    Parse a GitHub URL to extract owner, repo, and optional release tag.

    Supports formats:
    - https://github.com/owner/repo
    - https://github.com/owner/repo/releases
    - https://github.com/owner/repo/releases/tag/v1.0.0
    - github.com/owner/repo

    Returns: (owner, repo, tag) - tag may be empty string
    """
    # Remove protocol and www
    url = url.strip()
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'^www\.', '', url)

    # Match github.com/owner/repo pattern
    match = re.match(r'github\.com/([^/]+)/([^/]+)(?:/releases(?:/tag/([^/]+))?)?', url)
    if match:
        owner = match.group(1)
        repo = match.group(2)
        # Remove .git suffix if present (can't use rstrip as it removes characters, not strings)
        if repo.endswith('.git'):
            repo = repo[:-4]
        tag = match.group(3) or ""
        return owner, repo, tag

    return "", "", ""


def parse_cap_file(cap_path: str) -> Optional[CapMetadata]:
    """
    Parse a CAP file to extract metadata.

    CAP files are ZIP archives containing JavaCard components.
    The Header.cap contains package AID and version info.
    The Applet.cap contains applet AIDs.
    """
    try:
        with zipfile.ZipFile(cap_path, 'r') as zf:
            metadata = CapMetadata()

            # Find component files
            header_file = None
            applet_file = None

            for name in zf.namelist():
                lower_name = name.lower()
                if lower_name.endswith('header.cap'):
                    header_file = name
                elif lower_name.endswith('applet.cap'):
                    applet_file = name

            # Parse Header.cap for package AID
            if header_file:
                header_data = zf.read(header_file)
                metadata.aid, metadata.package_name, metadata.version = _parse_header_cap(header_data)

            # Parse Applet.cap for applet AIDs
            if applet_file:
                applet_data = zf.read(applet_file)
                metadata.applet_aids = _parse_applet_cap(applet_data, metadata.aid)

            return metadata

    except (zipfile.BadZipFile, IOError, Exception) as e:
        print(f"Error parsing CAP file: {e}")
        return None


def _parse_header_cap(data: bytes) -> tuple[str, str, str]:
    """
    Parse Header.cap component.

    Structure (simplified):
    - tag (1 byte): 0x01
    - size (2 bytes)
    - magic (4 bytes)
    - minor_version (1 byte)
    - major_version (1 byte)
    - flags (1 byte)
    - package info...
    """
    try:
        if len(data) < 12 or data[0] != 0x01:
            return "", "", ""

        # Skip to package info (offset varies, search for AID length pattern)
        # Package AID is typically after the magic and version bytes
        idx = 7  # Skip tag(1) + size(2) + magic(4)

        # Read minor/major version
        if idx + 2 <= len(data):
            minor = data[idx]
            major = data[idx + 1]
            version = f"{major}.{minor}"
            idx += 2
        else:
            version = ""

        # Skip flags
        idx += 1

        # Read package info
        # package_info contains: minor(1), major(1), aid_length(1), aid(n), name...
        if idx + 3 <= len(data):
            pkg_minor = data[idx]
            pkg_major = data[idx + 1]
            aid_length = data[idx + 2]
            idx += 3

            if aid_length > 0 and aid_length <= 16 and idx + aid_length <= len(data):
                aid_bytes = data[idx:idx + aid_length]
                aid = aid_bytes.hex().upper()
                idx += aid_length

                # Try to read package name (null-terminated string after AID)
                name_bytes = []
                while idx < len(data) and data[idx] != 0:
                    if data[idx] >= 32 and data[idx] < 127:
                        name_bytes.append(data[idx])
                    idx += 1
                package_name = bytes(name_bytes).decode('ascii', errors='ignore')

                return aid, package_name, version

    except Exception as e:
        print(f"Error parsing header: {e}")

    return "", "", ""


def _parse_applet_cap(data: bytes, package_aid: str) -> list[str]:
    """
    Parse Applet.cap component for applet AIDs.

    Structure:
    - tag (1 byte): 0x03
    - size (2 bytes)
    - count (1 byte)
    - applets...
    """
    applet_aids = []

    try:
        if len(data) < 4 or data[0] != 0x03:
            return applet_aids

        # size = (data[1] << 8) | data[2]
        count = data[3]
        idx = 4

        for _ in range(count):
            if idx >= len(data):
                break

            # Each applet: aid_length(1), aid(n), install_method_offset(2)
            aid_length = data[idx]
            idx += 1

            if aid_length > 0 and aid_length <= 16 and idx + aid_length <= len(data):
                aid_bytes = data[idx:idx + aid_length]
                aid = aid_bytes.hex().upper()
                applet_aids.append(aid)
                idx += aid_length

            # Skip install method offset
            idx += 2

    except Exception as e:
        print(f"Error parsing applet component: {e}")

    return applet_aids


class GitHubError(Exception):
    """Error from GitHub API."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


def fetch_github_repo_info(owner: str, repo: str) -> dict:
    """
    Fetch repository information from GitHub.

    Returns: dict with name, description, owner
    Raises: GitHubError on failure
    """
    import json

    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        req = urllib.request.Request(api_url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'GlobalPlatformGUI')

        with urllib.request.urlopen(req, timeout=10) as response:
            repo_data = json.loads(response.read().decode())

        return {
            "name": repo_data.get("name", repo),
            "description": repo_data.get("description", ""),
            "owner": repo_data.get("owner", {}).get("login", owner),
            "full_name": repo_data.get("full_name", f"{owner}/{repo}"),
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise GitHubError(f"Repository '{owner}/{repo}' not found", 404)
        elif e.code == 403:
            raise GitHubError("GitHub API rate limit exceeded. Try again later.", 403)
        else:
            raise GitHubError(f"GitHub API error: {e.code} {e.reason}", e.code)
    except urllib.error.URLError as e:
        raise GitHubError(f"Network error: {e.reason}")
    except Exception as e:
        raise GitHubError(f"Error: {e}")


def fetch_github_release_assets(
    owner: str, repo: str, pattern: str = "*.cap", tag: str = ""
) -> list[tuple[str, str]]:
    """
    Fetch ALL release assets matching pattern from GitHub.

    Args:
        owner: Repository owner
        repo: Repository name
        pattern: Glob pattern for asset filename
        tag: Specific release tag (uses "latest" if empty)

    Returns: List of (download_url, filename) tuples
    Raises: GitHubError on failure
    """
    import json
    import fnmatch

    if tag:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    else:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    try:
        req = urllib.request.Request(api_url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'GlobalPlatformGUI')

        with urllib.request.urlopen(req, timeout=10) as response:
            release_data = json.loads(response.read().decode())

        assets = release_data.get('assets', [])
        matching = []
        for asset in assets:
            name = asset.get('name', '')
            if fnmatch.fnmatch(name, pattern):
                matching.append((asset.get('browser_download_url', ''), name))

        if not matching:
            # No matching asset found
            asset_names = [a.get('name', '') for a in assets]
            if asset_names:
                raise GitHubError(
                    f"No assets matching '{pattern}' in release. "
                    f"Available: {', '.join(asset_names)}"
                )
            else:
                raise GitHubError("Release has no downloadable assets")

        return matching

    except urllib.error.HTTPError as e:
        if e.code == 404:
            if tag:
                raise GitHubError(f"Release tag '{tag}' not found", 404)
            else:
                raise GitHubError(f"No releases found for '{owner}/{repo}'", 404)
        elif e.code == 403:
            raise GitHubError("GitHub API rate limit exceeded. Try again later.", 403)
        else:
            raise GitHubError(f"GitHub API error: {e.code} {e.reason}", e.code)
    except urllib.error.URLError as e:
        raise GitHubError(f"Network error: {e.reason}")
    except GitHubError:
        raise
    except Exception as e:
        raise GitHubError(f"Error: {e}")


def fetch_github_release_asset(
    owner: str, repo: str, pattern: str = "*.cap", tag: str = ""
) -> tuple[str, str]:
    """
    Fetch first release asset matching pattern from GitHub.

    Convenience wrapper around fetch_github_release_assets for single-asset use.
    """
    assets = fetch_github_release_assets(owner, repo, pattern, tag)
    return assets[0] if assets else ("", "")


def download_file(url: str, dest_dir: str = None) -> Optional[str]:
    """
    Download a file from URL to a temporary location.

    Returns: path to downloaded file or None
    """
    if dest_dir is None:
        dest_dir = tempfile.gettempdir()

    try:
        # Extract filename from URL
        filename = url.split('/')[-1].split('?')[0]
        dest_path = os.path.join(dest_dir, filename)

        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'GlobalPlatformGUI')

        with urllib.request.urlopen(req, timeout=30) as response:
            with open(dest_path, 'wb') as f:
                f.write(response.read())

        return dest_path

    except Exception as e:
        print(f"Error downloading file: {e}")
        return None


# Thread pool for async operations
_executor = ThreadPoolExecutor(max_workers=2)


def run_file_dialog_async(
    dialog_type: str,
    title: str,
    filetypes: list,
    initial_file: str = "",
    callback: Callable[[str], None] = None,
) -> None:
    """
    Run a file dialog asynchronously using tkinter in a thread.

    Args:
        dialog_type: "open" or "save"
        title: Dialog title
        filetypes: List of (description, pattern) tuples
        initial_file: Initial filename for save dialog
        callback: Function to call with result path (or empty string if cancelled)
    """
    def run_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()

            # Try to make it appear on top
            root.lift()
            root.attributes('-topmost', True)
            root.after_idle(root.attributes, '-topmost', False)

            if dialog_type == "open":
                path = filedialog.askopenfilename(
                    title=title,
                    filetypes=filetypes,
                )
            else:
                path = filedialog.asksaveasfilename(
                    title=title,
                    filetypes=filetypes,
                    initialfile=initial_file,
                    defaultextension=filetypes[0][1] if filetypes else "",
                )

            root.destroy()
            return path or ""

        except Exception as e:
            print(f"Dialog error: {e}")
            return ""

    def on_complete(future: Future):
        result = future.result()
        if callback:
            # Schedule callback on Qt main thread
            QTimer.singleShot(0, lambda: callback(result))

    future = _executor.submit(run_dialog)
    future.add_done_callback(on_complete)

    # Keep Qt responsive while waiting
    while not future.done():
        QCoreApplication.processEvents()


def show_open_file_dialog(
    parent: QWidget,
    title: str,
    filetypes: list,
    callback: Callable[[str], None],
) -> None:
    """
    Show an open file dialog without blocking the Qt event loop.

    Args:
        parent: Parent widget (unused, for API compatibility)
        title: Dialog title
        filetypes: List of (description, pattern) tuples
        callback: Called with selected path or empty string
    """
    run_file_dialog_async("open", title, filetypes, callback=callback)


def show_save_file_dialog(
    parent: QWidget,
    title: str,
    filetypes: list,
    initial_file: str,
    callback: Callable[[str], None],
) -> None:
    """
    Show a save file dialog without blocking the Qt event loop.

    Args:
        parent: Parent widget (unused, for API compatibility)
        title: Dialog title
        filetypes: List of (description, pattern) tuples
        initial_file: Default filename
        callback: Called with selected path or empty string
    """
    run_file_dialog_async("save", title, filetypes, initial_file, callback)


# Well-known plugin definition filenames (checked in order)
PLUGIN_DEFINITION_FILENAMES = [
    "gp-plugin.yaml",
    "gp-plugin.yml",
    ".gp-plugin.yaml",
    ".gp-plugin.yml",
]


def fetch_github_plugin_definition(owner: str, repo: str, branch: str = "") -> list[tuple[str, dict]]:
    """
    Check if a GitHub repository provides GP GUI plugin definitions.

    Looks for well-known plugin definition files in the repo root:
    - gp-plugin.yaml / gp-plugin.yml
    - .gp-plugin.yaml / .gp-plugin.yml

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch to check (defaults to repo's default branch)

    Returns:
        List of (filename, parsed_yaml_dict) tuples for all found plugin definitions
    """
    import json
    import yaml

    results = []

    # First get the default branch if not specified
    if not branch:
        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            req = urllib.request.Request(api_url)
            req.add_header('Accept', 'application/vnd.github.v3+json')
            req.add_header('User-Agent', 'GlobalPlatformGUI')

            with urllib.request.urlopen(req, timeout=10) as response:
                repo_data = json.loads(response.read().decode())
                branch = repo_data.get("default_branch", "main")
        except Exception:
            branch = "main"  # Fallback

    # Try each well-known filename
    for filename in PLUGIN_DEFINITION_FILENAMES:
        try:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
            req = urllib.request.Request(raw_url)
            req.add_header('User-Agent', 'GlobalPlatformGUI')

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')

            # Parse YAML
            plugin_data = yaml.safe_load(content)

            if isinstance(plugin_data, dict):
                results.append((filename, plugin_data))

        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # File not found, try next
            # Other errors - stop trying
            break
        except Exception:
            continue

    return results


def fetch_github_release_plugin_definition(owner: str, repo: str, tag: str = "") -> list[tuple[str, dict]]:
    """
    Check if a GitHub release contains plugin definition files.

    Looks for *.gp-plugin.yaml or gp-plugin.yaml in release assets.

    Args:
        owner: Repository owner
        repo: Repository name
        tag: Release tag (uses latest if empty)

    Returns:
        List of (filename, parsed_yaml_dict) tuples for all found plugin definitions
    """
    import json
    import yaml

    results = []

    if tag:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    else:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    try:
        req = urllib.request.Request(api_url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'GlobalPlatformGUI')

        with urllib.request.urlopen(req, timeout=10) as response:
            release_data = json.loads(response.read().decode())

        assets = release_data.get('assets', [])

        # Look for plugin definition files
        for asset in assets:
            name = asset.get('name', '')
            if name.endswith('.gp-plugin.yaml') or name.endswith('.gp-plugin.yml') or \
               name == 'gp-plugin.yaml' or name == 'gp-plugin.yml':
                download_url = asset.get('browser_download_url', '')
                if download_url:
                    try:
                        # Download and parse
                        req = urllib.request.Request(download_url)
                        req.add_header('User-Agent', 'GlobalPlatformGUI')

                        with urllib.request.urlopen(req, timeout=30) as response:
                            content = response.read().decode('utf-8')

                        plugin_data = yaml.safe_load(content)
                        if isinstance(plugin_data, dict):
                            results.append((name, plugin_data))
                    except Exception:
                        continue  # Skip this asset, try others

    except Exception:
        pass

    return results
