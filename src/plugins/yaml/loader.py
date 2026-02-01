"""
YAML Plugin Loader

Discovers and loads YAML plugin definitions from the file system.
"""

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
    """

    # Default directories to scan for plugins
    DEFAULT_PLUGIN_DIRS = [
        "plugins",
        "repos",
    ]

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
        """
        if directories is None:
            directories = self.DEFAULT_PLUGIN_DIRS

        self._loaded_plugins.clear()
        self._errors.clear()

        for dir_name in directories:
            dir_path = self._base_dir / dir_name
            if dir_path.exists() and dir_path.is_dir():
                self._scan_directory(dir_path, recursive)

        return self._loaded_plugins

    def _scan_directory(self, directory: Path, recursive: bool):
        """Scan a directory for YAML plugin files."""
        try:
            for entry in directory.iterdir():
                if entry.is_file() and entry.suffix.lower() in ('.yaml', '.yml'):
                    self._try_load_plugin(entry)
                elif recursive and entry.is_dir() and not entry.name.startswith('.'):
                    # Skip hidden directories and __pycache__
                    if entry.name != '__pycache__':
                        self._scan_directory(entry, recursive)
        except PermissionError:
            self._errors.append((str(directory), "Permission denied"))

    def _try_load_plugin(self, path: Path):
        """Try to load a YAML file as a plugin."""
        try:
            adapter = YamlPluginAdapter.from_file(path)
            plugin_name = adapter.name

            # Check for duplicate names
            if plugin_name in self._loaded_plugins:
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
