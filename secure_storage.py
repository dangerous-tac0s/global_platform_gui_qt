from __future__ import annotations

import binascii
import json
import logging
import os
import base64
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import keyring
import gnupg
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from secrets import token_bytes

logger = logging.getLogger(__name__)

# GPG timeout in seconds (5 minutes)
GPG_TIMEOUT_SECONDS = 300


# Key wrapping method constants
class KeyMethod:
    KEYRING = "keyring"
    GPG = "gpg"


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


def _zero_bytearray(buf: bytearray) -> None:
    """Zero out a bytearray in place for secure memory clearing."""
    for i in range(len(buf)):
        buf[i] = 0


def _validate_storage_path(path: str, allow_any: bool = False) -> None:
    """
    Validate that storage path is within expected directories.

    Args:
        path: Path to validate
        allow_any: If True, skip validation (for testing)

    Raises:
        ValueError: If path is outside app data directory
    """
    if allow_any:
        return

    app_dir = get_app_data_dir()
    resolved = Path(path).resolve()

    # Allow paths within app data directory
    try:
        resolved.relative_to(app_dir)
        return
    except ValueError:
        pass

    # Also allow paths in current working directory (for backwards compat)
    try:
        resolved.relative_to(Path.cwd())
        return
    except ValueError:
        pass

    raise ValueError(
        f"Storage path must be within app data directory ({app_dir}) "
        f"or current working directory. Got: {resolved}"
    )


def _safe_b64decode(data: str, field_name: str) -> bytes:
    """
    Safely decode base64 with validation.

    Args:
        data: Base64 encoded string
        field_name: Name of field for error messages

    Returns:
        Decoded bytes

    Raises:
        RuntimeError: If base64 is invalid
    """
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as e:
        raise RuntimeError(f"Invalid base64 in {field_name}: {e}")


class SecureStorage:

    def __init__(
        self,
        path: str,
        # gpg_home=os.getcwd(),
        service_name="SecureStorage",
        cache_timeout: Optional[str] = "session",
        allow_any_path: bool = False,
    ):
        _validate_storage_path(path, allow_any=allow_any_path)
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

    def get_method(self) -> Optional[str]:
        """Get the current key wrapping method ('keyring' or 'gpg')."""
        return self.__method

    def get_key_id(self) -> Optional[str]:
        """Get the current key ID used for key wrapping."""
        return self.__key_id

    def set_cache_timeout(self, timeout_key: str):
        """Set the cache timeout. Use keys from CACHE_TIMEOUT_OPTIONS."""
        self._cache_timeout = CACHE_TIMEOUT_OPTIONS.get(timeout_key)
        # Invalidate cache when timeout changes
        self._invalidate_cache()

    def _invalidate_cache(self):
        """Clear the cached data securely."""
        if self._cached_data is not None:
            # Clear sensitive values from cache before dropping reference
            if isinstance(self._cached_data, dict) and "tags" in self._cached_data:
                for tag_data in self._cached_data.get("tags", {}).values():
                    if isinstance(tag_data, dict) and "key" in tag_data:
                        tag_data["key"] = None
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

    def select_key(self) -> bytearray:
        """
        Retrieve the AES key using the configured method.

        Returns:
            bytearray containing the AES key (caller should zero after use)
        """
        if self.__method == KeyMethod.KEYRING:
            b64key = keyring.get_password(self.service_name, self.__key_id)
            if not b64key:
                raise RuntimeError(f"Key not found in keyring for key_id '{self.__key_id}'")
            return bytearray(_safe_b64decode(b64key, "keyring key"))

        elif self.__method == KeyMethod.GPG and self.__gpg:
            if not self.__wrapped_key_b64:
                raise RuntimeError("No wrapped_key available for GPG")
            wrapped = _safe_b64decode(self.__wrapped_key_b64, "wrapped_key_b64")
            try:
                result = gpg_decrypt(wrapped)
                return bytearray(result)
            except (ValueError, RuntimeError) as e:
                raise RuntimeError(f"GPG decryption failed: {e}")

        else:
            raise ValueError(f"Unsupported key selection method: {self.__method}")

    def initialize(self, method, key_id: str = None, initial_data={}):
        if self.meta:
            self.__method = method["keywrapping"]["method"]
        else:
            self.__method = method
            self.__aes_key = bytearray(token_bytes(32))  # Use bytearray for secure zeroing

            # For keyring method, generate a unique key_id if not provided
            if method == KeyMethod.KEYRING and not key_id:
                key_id = f"storage_{uuid.uuid4().hex[:16]}"

            self.__key_id = key_id

        if method == KeyMethod.KEYRING:
            # Check if a key already exists with this key_id to prevent accidental overwrite
            existing = keyring.get_password(self.service_name, self.__key_id)
            if existing:
                raise RuntimeError(
                    f"A keyring entry already exists for '{self.__key_id}'. "
                    "This may indicate an existing storage file. "
                    "Use a different key_id or delete the existing entry."
                )
            keyring.set_password(
                self.service_name, self.__key_id, base64.b64encode(bytes(self.__aes_key)).decode()
            )
        elif not self.__gpg and method == KeyMethod.GPG:
            # They don't have GPG
            return self.initialize(KeyMethod.KEYRING, initial_data=initial_data)
        elif method == KeyMethod.GPG and self.__gpg:
            if not key_id:
                raise ValueError("GPG method requires key_id.")

            result = self.__gpg.encrypt(bytes(self.__aes_key), recipients=key_id, armor=True)

            self.__wrapped_key_b64 = base64.b64encode(result.data).decode()

        else:
            raise ValueError("Unsupported encryption method")

        self.__data = initial_data

        self.save()

    def change_method(self, new_method: str, new_key_id: str):
        if self.__data is None:
            raise RuntimeError("Load or set data before changing encryption method.")

        if self.__aes_key is not None:
            _zero_bytearray(self.__aes_key)
            self.__aes_key = None  # Clear old key reference
        self.initialize(new_method, new_key_id)

    def load(self, retry=False, force_unlock=False):
        """
        Load and decrypt the secure storage.

        Args:
            retry: Internal flag for GPG retry on failure
            force_unlock: If True, bypass cache and force decryption

        Raises:
            FileNotFoundError: If storage file doesn't exist
            RuntimeError: If decryption fails or storage is corrupted
        """
        # Check cache first (unless force_unlock is requested)
        if not force_unlock and self._is_cache_valid():
            self.__data = self._cached_data
            return

        if not os.path.exists(self.__path):
            raise FileNotFoundError(f"Unable to find {self.__path}")

        logger.debug(f"Loading storage from {self.__path}")

        with open(self.__path, "rb") as f:
            obj = json.load(f)

        meta = obj["key_wrapping"]
        self.__method = meta["method"]
        self.__key_id = meta["key_id"]

        # Validate key_id for keyring method
        if self.__method == KeyMethod.KEYRING and not self.__key_id:
            raise RuntimeError(
                "Storage file has null key_id for keyring method - file may be corrupted"
            )

        logger.debug(f"Using {self.__method} method")

        if self.__method == KeyMethod.KEYRING:
            b64key = keyring.get_password(self.service_name, self.__key_id)
            if not b64key:
                raise RuntimeError(f"Key not found in keyring for key_id '{self.__key_id}'")
            self.__aes_key = bytearray(_safe_b64decode(b64key, "keyring key"))

        elif self.__method == KeyMethod.GPG and self.__gpg:
            self.__wrapped_key_b64 = meta["wrapped_key_b64"]
            wrapped = _safe_b64decode(meta["wrapped_key_b64"], "wrapped_key_b64")
            try:
                result = gpg_decrypt(wrapped)
            except Exception as e:
                if not retry:
                    logger.debug("GPG decryption failed, retrying...")
                    self.load(retry=True, force_unlock=force_unlock)
                    return
                else:
                    raise RuntimeError(f"GPG decryption failed after retry: {e}")

            self.__aes_key = bytearray(result)

        else:
            raise ValueError(f"Unsupported encryption method: {self.__method}")

        enc = obj["encryption"]
        iv = _safe_b64decode(enc["iv"], "iv")
        tag = _safe_b64decode(enc["tag"], "tag")
        ciphertext = _safe_b64decode(obj["payload"], "payload")

        try:
            aesgcm = AESGCM(bytes(self.__aes_key))
            self.__data = json.loads(aesgcm.decrypt(iv, ciphertext + tag, None))
        except InvalidTag:
            raise RuntimeError("Decryption failed - data may be corrupted or key is wrong")
        finally:
            # Always zero the key, even on failure
            _zero_bytearray(self.__aes_key)
            self.__aes_key = None

        # Update cache after successful decrypt
        self._update_cache(self.__data)

    def save(self):
        """
        Encrypt and save the storage data.

        Raises:
            RuntimeError: If no data or key is available
        """
        if not self.__aes_key:
            self.__aes_key = self.select_key()

        if self.__data is None or self.__aes_key is None:
            raise RuntimeError("No data or AES key initialized")

        try:
            aesgcm = AESGCM(bytes(self.__aes_key))
            iv = token_bytes(12)
            json_bytes = json.dumps(self.__data).encode()
            encrypted = aesgcm.encrypt(iv, json_bytes, None)
        finally:
            _zero_bytearray(self.__aes_key)
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

        if self.__method == KeyMethod.GPG and self.__gpg:
            metadata["key_wrapping"]["wrapped_key_b64"] = self.__wrapped_key_b64

        logger.debug(f"Saving storage to {self.__path}")

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


def gpg_decrypt(ciphertext: bytes, timeout: int = GPG_TIMEOUT_SECONDS) -> bytes:
    """
    Decrypt data using GPG via subprocess.

    Uses subprocess because PIN entry doesn't work with the gnupg library.

    Args:
        ciphertext: Encrypted data to decrypt
        timeout: Timeout in seconds (default 5 minutes)

    Returns:
        Decrypted bytes

    Raises:
        RuntimeError: If decryption fails or times out
    """
    try:
        p = subprocess.run(
            ["gpg", "--decrypt"],
            input=ciphertext,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"GPG decryption timed out after {timeout}s - PIN entry may have been cancelled"
        )

    if p.returncode != 0:
        raise RuntimeError(f"GPG decryption failed: {p.stderr.decode()}")

    return p.stdout


# ============================================================================
# Backup Export/Import Functions
# ============================================================================

# PBKDF2 iterations for backup passwords (OWASP 2023 recommendation)
BACKUP_PBKDF2_ITERATIONS = 600000

# Backup file version
BACKUP_VERSION = 1


def _derive_key_from_password(password: str, salt: bytes) -> bytearray:
    """
    Derive AES-256 key from password using PBKDF2-SHA256.

    Args:
        password: User-provided password
        salt: Random salt (should be 16 bytes)

    Returns:
        bytearray containing 32-byte derived key (caller should zero after use)
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=BACKUP_PBKDF2_ITERATIONS,
    )
    return bytearray(kdf.derive(password.encode("utf-8")))


def _encrypt_aes_gcm(plaintext: bytes, key: bytes) -> tuple:
    """
    Encrypt data with AES-256-GCM.

    Args:
        plaintext: Data to encrypt
        key: 32-byte AES key

    Returns:
        Tuple of (ciphertext, iv, tag)
    """
    iv = token_bytes(12)
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(iv, plaintext, None)
    # AES-GCM appends 16-byte tag to ciphertext
    tag = encrypted[-16:]
    ciphertext = encrypted[:-16]
    return ciphertext, iv, tag


def _decrypt_aes_gcm(ciphertext: bytes, key: bytes, iv: bytes, tag: bytes) -> bytes:
    """
    Decrypt data with AES-256-GCM.

    Args:
        ciphertext: Encrypted data (without tag)
        key: 32-byte AES key
        iv: 12-byte initialization vector
        tag: 16-byte authentication tag

    Returns:
        Decrypted plaintext

    Raises:
        InvalidTag: If authentication fails
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext + tag, None)


def export_backup(
    data: dict,
    output_path: str,
    method: str,
    password: str = None,
    gpg_key_id: str = None,
) -> None:
    """
    Export storage data to encrypted backup file.

    Args:
        data: Storage data dictionary to export
        output_path: Path for the backup file (should end in .gpbackup)
        method: "password" or "gpg"
        password: Password for encryption (required if method="password")
        gpg_key_id: GPG key ID (required if method="gpg")

    Raises:
        ValueError: If required parameters are missing
        RuntimeError: If encryption fails
    """
    import datetime

    if method == "password":
        if not password:
            raise ValueError("Password required for password-based backup")

        salt = token_bytes(16)
        key = _derive_key_from_password(password, salt)

        try:
            payload = json.dumps(data).encode("utf-8")
            ciphertext, iv, tag = _encrypt_aes_gcm(payload, bytes(key))
        finally:
            _zero_bytearray(key)

        backup_data = {
            "version": BACKUP_VERSION,
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "encryption": {
                "method": "password",
                "cipher": "AES-256-GCM",
                "kdf": "PBKDF2-SHA256",
                "iterations": BACKUP_PBKDF2_ITERATIONS,
                "salt": base64.b64encode(salt).decode(),
                "iv": base64.b64encode(iv).decode(),
                "tag": base64.b64encode(tag).decode(),
            },
            "payload": base64.b64encode(ciphertext).decode(),
        }

    elif method == "gpg":
        if not gpg_key_id:
            raise ValueError("GPG key ID required for GPG-based backup")

        gpg = gnupg.GPG()
        payload = json.dumps(data).encode("utf-8")

        result = gpg.encrypt(payload, recipients=gpg_key_id, armor=True)
        if not result.ok:
            raise RuntimeError(f"GPG encryption failed: {result.stderr}")

        backup_data = {
            "version": BACKUP_VERSION,
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "encryption": {
                "method": "gpg",
                "gpg_key_id": gpg_key_id,
            },
            "payload": base64.b64encode(result.data).decode(),
        }

    else:
        raise ValueError(f"Unsupported backup method: {method}")

    with open(output_path, "w") as f:
        json.dump(backup_data, f, indent=2)


def import_backup(backup_path: str, password: str = None) -> dict:
    """
    Import and decrypt backup file.

    Args:
        backup_path: Path to the backup file
        password: Password for decryption (required if backup is password-protected)

    Returns:
        Decrypted data dictionary

    Raises:
        FileNotFoundError: If backup file doesn't exist
        ValueError: If backup file is invalid
        RuntimeError: If decryption fails
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    with open(backup_path, "r") as f:
        backup_data = json.load(f)

    # Validate version
    version = backup_data.get("version")
    if version != BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {version}")

    encryption = backup_data.get("encryption", {})
    method = encryption.get("method")

    if method == "password":
        if not password:
            raise ValueError("Password required to decrypt this backup")

        salt = _safe_b64decode(encryption.get("salt", ""), "salt")
        iv = _safe_b64decode(encryption.get("iv", ""), "iv")
        tag = _safe_b64decode(encryption.get("tag", ""), "tag")
        ciphertext = _safe_b64decode(backup_data.get("payload", ""), "payload")

        key = _derive_key_from_password(password, salt)
        try:
            plaintext = _decrypt_aes_gcm(ciphertext, bytes(key), iv, tag)
        except InvalidTag:
            raise RuntimeError("Decryption failed - incorrect password or corrupted backup")
        finally:
            _zero_bytearray(key)

        return json.loads(plaintext.decode("utf-8"))

    elif method == "gpg":
        payload = _safe_b64decode(backup_data.get("payload", ""), "payload")

        try:
            plaintext = gpg_decrypt(payload)
        except RuntimeError as e:
            raise RuntimeError(f"GPG decryption failed: {e}")

        return json.loads(plaintext.decode("utf-8"))

    else:
        raise ValueError(f"Unsupported backup encryption method: {method}")


def get_backup_info(backup_path: str) -> dict:
    """
    Get metadata about a backup file without decrypting it.

    Args:
        backup_path: Path to the backup file

    Returns:
        Dictionary with backup metadata (version, created, method, gpg_key_id if applicable)

    Raises:
        FileNotFoundError: If backup file doesn't exist
        ValueError: If backup file is invalid
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    with open(backup_path, "r") as f:
        backup_data = json.load(f)

    encryption = backup_data.get("encryption", {})

    return {
        "version": backup_data.get("version"),
        "created": backup_data.get("created"),
        "method": encryption.get("method"),
        "gpg_key_id": encryption.get("gpg_key_id"),
    }
