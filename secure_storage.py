from __future__ import annotations

import ctypes
import os
import json
import base64
import subprocess
import uuid
import time
from pathlib import Path
from typing import Optional

import keyring
import gnupg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from secrets import token_bytes


# Cache timeout values in seconds (None = never cache, 0 = session/forever)
CACHE_TIMEOUT_OPTIONS = {
    "never": None,  # Always unlock
    "30_seconds": 30,
    "1_minute": 60,
    "5_minutes": 300,
    "15_minutes": 900,
    "30_minutes": 1800,
    "1_hour": 3600,
    "session": 0,  # Never expire during session
}


def get_app_data_dir() -> Path:
    """
    Get the application data directory for storing config and secure storage.

    - Windows: %APPDATA%/GlobalPlatformGUI
    - macOS: ~/Library/Application Support/GlobalPlatformGUI
    - Linux: ~/.local/share/GlobalPlatformGUI
    """
    if os.name == "nt":
        # Windows
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        app_dir = Path(base) / "GlobalPlatformGUI"
    elif sys.platform == "darwin":
        # macOS
        app_dir = Path.home() / "Library" / "Application Support" / "GlobalPlatformGUI"
    else:
        # Linux/Unix
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        app_dir = Path(xdg_data) / "GlobalPlatformGUI"

    # Ensure directory exists
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_default_storage_path() -> str:
    """Get the default path for the secure storage file."""
    return str(get_app_data_dir() / "data.enc.json")


def get_default_config_path() -> str:
    """Get the default path for the config file."""
    return str(get_app_data_dir() / "config.json")


def migrate_legacy_files(legacy_dir: str = ".") -> dict:
    """
    Migrate legacy files from old location to app data directory.

    Returns dict with migration results.
    """
    app_dir = get_app_data_dir()
    results = {"migrated": [], "skipped": [], "errors": []}

    files_to_migrate = [
        ("data.enc.json", "data.enc.json"),
        ("config.json", "config.json"),
    ]

    for old_name, new_name in files_to_migrate:
        old_path = Path(legacy_dir) / old_name
        new_path = app_dir / new_name

        if old_path.exists() and not new_path.exists():
            try:
                import shutil
                shutil.copy2(old_path, new_path)
                results["migrated"].append(old_name)
            except Exception as e:
                results["errors"].append((old_name, str(e)))
        elif old_path.exists() and new_path.exists():
            results["skipped"].append(old_name)

    return results


# Need sys for platform detection
import sys


class SecureStorage:

    def __init__(
        self,
        path: str,
        # gpg_home=os.getcwd(),
        service_name="SecureStorage",
        cache_timeout: Optional[str] = "never",
    ):
        self.__path = path
        self.__data = None
        self.__aes_key = None
        self.__method = None
        self.__key_id = None
        self.__wrapped_key_b64 = None
        self.service_name = service_name
        self.__meta: None | dict = None
        self.__persist_key = False

        # Cache settings
        self._cache_timeout = CACHE_TIMEOUT_OPTIONS.get(cache_timeout)
        self._cache_timestamp: Optional[float] = None
        self._cached_data: Optional[dict] = None

        try:
            self.__gpg = gnupg.GPG()
        except Exception:
            self.__gpg = None

    @property
    def meta(self):
        return self.__meta

    def set_cache_timeout(self, timeout_key: str):
        """Set the cache timeout. Use keys from CACHE_TIMEOUT_OPTIONS."""
        self._cache_timeout = CACHE_TIMEOUT_OPTIONS.get(timeout_key)
        # Invalidate cache when timeout changes
        self._invalidate_cache()

    def _invalidate_cache(self):
        """Clear the cached data."""
        self._cached_data = None
        self._cache_timestamp = None

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cached_data is None:
            return False
        if self._cache_timeout is None:
            # "never" - always require unlock
            return False
        if self._cache_timeout == 0:
            # "session" - never expires
            return True
        if self._cache_timestamp is None:
            return False
        elapsed = time.time() - self._cache_timestamp
        return elapsed < self._cache_timeout

    def _update_cache(self, data: dict):
        """Update the cache with new data."""
        if self._cache_timeout is not None:
            self._cached_data = data
            self._cache_timestamp = time.time()

    def select_key(self) -> bytes:
        if self.__method == "keyring":
            b64key = keyring.get_password(self.service_name, self.__key_id)
            if not b64key:
                raise RuntimeError("Key not found in keyring")
            return base64.b64decode(b64key)

        elif self.__method == "gpg" and self.__gpg:
            if not self.__wrapped_key_b64:
                raise RuntimeError("No wrapped_key available for GPG")
            wrapped = base64.b64decode(self.__wrapped_key_b64)
            try:
                result = gpg_decrypt(wrapped)
                return result
            except ValueError as e:
                raise RuntimeError(f"GPG decryption failed: {e}")

        else:
            raise ValueError(f"Unsupported key selection method: {self.__method}")

    def initialize(self, method, key_id: str = None, initial_data={}):
        if self.meta:
            self.__method = method["keywrapping"]["method"]
        else:
            self.__method = method
            self.__aes_key = token_bytes(32)

            # For keyring method, generate a unique key_id if not provided
            if method == "keyring" and not key_id:
                key_id = f"storage_{uuid.uuid4().hex[:16]}"

            self.__key_id = key_id

        if method == "keyring":
            # Check if a key already exists with this key_id to prevent accidental overwrite
            existing = keyring.get_password(self.service_name, self.__key_id)
            if existing:
                raise RuntimeError(
                    f"A keyring entry already exists for '{self.__key_id}'. "
                    "This may indicate an existing storage file. "
                    "Use a different key_id or delete the existing entry."
                )
            keyring.set_password(
                self.service_name, self.__key_id, base64.b64encode(self.__aes_key).decode()
            )
        elif not self.__gpg and method == "gpg":
            # They don't have GPG
            return self.initialize("keyring", initial_data=initial_data)
        elif method == "gpg" and self.__gpg:
            if not key_id:
                raise ValueError("GPG method requires key_id.")

            result = self.__gpg.encrypt(self.__aes_key, recipients=key_id, armor=True)

            self.__wrapped_key_b64 = base64.b64encode(result.data).decode()

        else:
            raise ValueError("Unsupported encryption method")

        self.__data = initial_data

        self.save()

    def change_method(self, new_method: str, new_key_id: str):
        if self.__data is None:
            raise RuntimeError("Load or set data before changing encryption method.")

        _zero_bytes(self.__aes_key)
        self.__aes_key = None  # Clear old key reference
        self.initialize(new_method, new_key_id)

    def load(self, retry=False, force_unlock=False):
        """
        Load and decrypt the secure storage.

        Args:
            retry: Internal flag for GPG retry on failure
            force_unlock: If True, bypass cache and force decryption
        """
        # Check cache first (unless force_unlock is requested)
        if not force_unlock and self._is_cache_valid():
            self.__data = self._cached_data
            return

        if not os.path.exists(self.__path):
            raise FileNotFoundError(f"Unable to find {self.__path}")

        with open(self.__path, "rb") as f:
            obj = json.load(f)

        meta = obj["key_wrapping"]
        self.__method = meta["method"]
        self.__key_id = meta["key_id"]

        if self.__method == "keyring":
            b64key = keyring.get_password(self.service_name, self.__key_id)
            if not b64key:
                raise RuntimeError("Key not found in keyring")
            self.__aes_key = base64.b64decode(b64key)

        elif self.__method == "gpg" and self.__gpg:
            self.__wrapped_key_b64 = meta["wrapped_key_b64"]
            wrapped = base64.b64decode(meta["wrapped_key_b64"])
            try:
                result = gpg_decrypt(wrapped)
            except Exception as e:
                if not retry:
                    self.load(retry=True, force_unlock=force_unlock)
                    return
                else:
                    raise RuntimeError(e)

            self.__aes_key = result

        else:
            raise ValueError("Unsupported encryption method")

        enc = obj["encryption"]
        iv = base64.b64decode(enc["iv"])
        tag = base64.b64decode(enc["tag"])
        ciphertext = base64.b64decode(obj["payload"])
        aesgcm = AESGCM(self.__aes_key)
        self.__data = json.loads(aesgcm.decrypt(iv, ciphertext + tag, None))

        # Update cache after successful decrypt
        self._update_cache(self.__data)

        _zero_bytes(self.__aes_key)
        self.__aes_key = None

    def save(self):
        if not self.__aes_key:
            self.__aes_key = self.select_key()

        if self.__data is None or self.__aes_key is None:
            raise RuntimeError("No data or AES key initialized")

        aesgcm = AESGCM(self.__aes_key)
        iv = token_bytes(12)
        json_bytes = json.dumps(self.__data).encode()
        encrypted = aesgcm.encrypt(iv, json_bytes, None)
        _zero_bytes(self.__aes_key)
        self.__aes_key = None

        # Update cache with saved data
        self._update_cache(self.__data)

        tag = encrypted[-16:]
        ciphertext = encrypted[:-16]

        metadata = {
            "version": 1,
            "encryption": {
                "cipher": "AES-256-GCM",
                "iv": base64.b64encode(iv).decode(),
                "tag": base64.b64encode(tag).decode(),
            },
            "key_wrapping": {
                "method": self.__method,
                "key_id": self.__key_id,
            },
        }

        if self.__method == "gpg" and self.__gpg:
            metadata["key_wrapping"]["wrapped_key_b64"] = self.__wrapped_key_b64

        with open(self.__path, "w") as f:
            json.dump(
                {**metadata, "payload": base64.b64encode(ciphertext).decode()},
                f,
                indent=2,
            )

    def set_data(self, data: dict):
        self.__data = data

    def get_data(self) -> dict:
        return self.__data

    def gpg_unwrap_key(self):
        pass


def _zero_bytes(buf: bytes):
    ctypes.memset(
        ctypes.addressof(ctypes.create_string_buffer(buf, len(buf))), 0, len(buf)
    )


def gpg_decrypt(ciphertext: bytes) -> bytes:
    """
    Pin entry doesn't work with the library *sigh*
    """

    p = subprocess.run(["gpg", "--decrypt"], input=ciphertext, capture_output=True)

    if p.returncode != 0:
        raise RuntimeError(f"GPG decryption failed: {p.stderr.decode()}")

    return p.stdout
