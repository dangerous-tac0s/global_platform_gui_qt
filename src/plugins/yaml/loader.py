"""
YAML Plugin Loader

Discovers and loads YAML plugin definitions from the file system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .adapter import YamlPluginAdapter
from .parser import YamlParseError


class YamlPluginLoader:
    """
    Discovers and loads YAML plugins from specified directories.

    Scans directories for .yaml and .yml files that contain valid
    plugin definitions.

    Priority order (later overrides earlier):
    1. plugins/ - bundled plugins
    2. repos/ - legacy location (deprecated)
    3. user_plugins/ - user-edited/created plugins (highest priority)
    """

    # Default directories to scan for plugins (order matters - later overrides)
    DEFAULT_PLUGIN_DIRS = [
        "plugins",
        "repos",
    ]

    # User plugins directory (scanned from cwd, always writable)
    USER_PLUGINS_DIR = "user_plugins"

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize the loader.

        Args:
            base_dir: Base directory to search from (defaults to current dir)
        """
        self._base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._loaded_plugins: dict[str, YamlPluginAdapter] = {}
        self._errors: list[tuple[str, str]] = []

    def discover(
        self,
        directories: Optional[list[str]] = None,
        recursive: bool = True,
    ) -> dict[str, YamlPluginAdapter]:
        """
        Discover and load YAML plugins from directories.

        Args:
            directories: List of directory paths to scan (relative to base_dir)
            recursive: Whether to scan subdirectories

        Returns:
            Dict mapping plugin name to adapter instance

        Note:
            User plugins (from user_plugins/ in cwd) are loaded LAST and will
            override bundled plugins with the same name. This allows users to
            customize bundled plugins without modifying the original files.
        """
        if directories is None:
            directories = self.DEFAULT_PLUGIN_DIRS

        self._loaded_plugins.clear()
        self._errors.clear()

        # First, scan bundled plugin directories (from base_dir, may be in PyInstaller temp)
        for dir_name in directories:
            dir_path = self._base_dir / dir_name
            if dir_path.exists() and dir_path.is_dir():
                self._scan_directory(dir_path, recursive)

        # Then, scan user_plugins from cwd (always writable, persists across restarts)
        # User plugins override bundled plugins with the same name
        user_plugins_dir = Path.cwd() / self.USER_PLUGINS_DIR
        if user_plugins_dir.exists() and user_plugins_dir.is_dir():
            self._scan_directory(user_plugins_dir, recursive, allow_override=True)

        return self._loaded_plugins

    def _scan_directory(self, directory: Path, recursive: bool, allow_override: bool = False):
        """Scan a directory for YAML plugin files."""
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.suffix.lower() in ('.yaml', '.yml'):
                    self._try_load_plugin(entry, allow_override)
                elif recursive and entry.is_dir() and not entry.name.startswith('.'):
                    # Skip hidden directories and __pycache__
                    if entry.name != '__pycache__':
                        self._scan_directory(entry, recursive, allow_override)
        except PermissionError:
            self._errors.append((str(directory), "Permission denied"))

    def _try_load_plugin(self, path: Path, allow_override: bool = False):
        """Try to load a YAML file as a plugin."""
        try:
            adapter = YamlPluginAdapter.from_file(path)
            plugin_name = adapter.name

            # Check for duplicate names
            if plugin_name in self._loaded_plugins:
                if allow_override:
                    # User plugin overrides bundled plugin
                    print(f"User plugin '{plugin_name}' overrides bundled version")
                    self._loaded_plugins[plugin_name] = adapter
                    return
                else:
                    existing = self._loaded_plugins[plugin_name]
                    self._errors.append(
                        (str(path), f"Duplicate plugin name '{plugin_name}' "
                         f"(already loaded from {existing._yaml_path})")
                    )
                    return

            self._loaded_plugins[plugin_name] = adapter

        except YamlParseError as e:
            self._errors.append((str(path), str(e)))
        except Exception as e:
            self._errors.append((str(path), f"Unexpected error: {e}"))

    def load_file(self, path: str | Path) -> YamlPluginAdapter:
        """
        Load a single YAML plugin file.

        Args:
            path: Path to the YAML file

        Returns:
            YamlPluginAdapter instance

        Raises:
            YamlParseError: If parsing fails
        """
        path = Path(path)
        if not path.is_absolute():
            path = self._base_dir / path

        return YamlPluginAdapter.from_file(path)

    def get_errors(self) -> list[tuple[str, str]]:
        """
        Get list of errors encountered during discovery.

        Returns:
            List of (path, error_message) tuples
        """
        return self._errors.copy()

    def get_loaded_plugins(self) -> dict[str, YamlPluginAdapter]:
        """Get all loaded plugins."""
        return self._loaded_plugins.copy()


def discover_yaml_plugins(
    base_dir: Optional[str] = None,
    directories: Optional[list[str]] = None,
) -> dict[str, YamlPluginAdapter]:
    """
    Convenience function to discover YAML plugins.

    Args:
        base_dir: Base directory to search from
        directories: Directories to scan

    Returns:
        Dict mapping plugin name to adapter
    """
    loader = YamlPluginLoader(base_dir)
    return loader.discover(directories)


def load_yaml_plugin(path: str | Path) -> YamlPluginAdapter:
    """
    Convenience function to load a single YAML plugin.

    Args:
        path: Path to the YAML plugin file

    Returns:
        YamlPluginAdapter instance
    """
    return YamlPluginAdapter.from_file(path)
