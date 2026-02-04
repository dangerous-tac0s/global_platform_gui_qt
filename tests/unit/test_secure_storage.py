"""
Unit tests for SecureStorage encryption and security features.
"""

import json
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from secure_storage import (
    SecureStorage,
    KeyMethod,
    GPG_TIMEOUT_SECONDS,
    _zero_bytearray,
    _safe_b64decode,
    _validate_storage_path,
    get_app_data_dir,
)


class TestMemoryZeroing:
    """Tests for secure memory zeroing."""

    def test_zero_bytearray_clears_data(self):
        """Verify bytearray is zeroed in place."""
        data = bytearray(b"sensitive_key_data_here!")
        original_id = id(data)

        _zero_bytearray(data)

        # Same object, all zeros
        assert id(data) == original_id
        assert all(b == 0 for b in data)
        assert len(data) == 24  # Length preserved

    def test_zero_bytearray_empty(self):
        """Verify empty bytearray doesn't raise."""
        data = bytearray()
        _zero_bytearray(data)
        assert len(data) == 0


class TestBase64Validation:
    """Tests for safe base64 decoding."""

    def test_valid_base64(self):
        """Verify valid base64 decodes correctly."""
        import base64
        original = b"test data"
        encoded = base64.b64encode(original).decode()

        result = _safe_b64decode(encoded, "test_field")
        assert result == original

    def test_invalid_base64_raises(self):
        """Verify invalid base64 raises RuntimeError with field name."""
        with pytest.raises(RuntimeError) as exc_info:
            _safe_b64decode("not valid base64!!!", "my_field")

        assert "my_field" in str(exc_info.value)
        assert "Invalid base64" in str(exc_info.value)

    def test_empty_base64(self):
        """Verify empty base64 decodes to empty bytes."""
        result = _safe_b64decode("", "empty_field")
        assert result == b""


class TestPathValidation:
    """Tests for storage path validation."""

    def test_app_data_dir_allowed(self):
        """Verify paths in app data directory are allowed."""
        app_dir = get_app_data_dir()
        test_path = str(app_dir / "test.enc.json")

        # Should not raise
        _validate_storage_path(test_path)

    def test_cwd_allowed(self):
        """Verify paths in current working directory are allowed."""
        test_path = os.path.join(os.getcwd(), "test.enc.json")

        # Should not raise
        _validate_storage_path(test_path)

    def test_outside_allowed_dirs_raises(self):
        """Verify paths outside allowed directories raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _validate_storage_path("/etc/passwd")

        assert "must be within app data directory" in str(exc_info.value)

    def test_allow_any_bypasses_validation(self):
        """Verify allow_any=True bypasses path validation."""
        # Should not raise even for invalid path
        _validate_storage_path("/etc/passwd", allow_any=True)


class TestSecureStorageInit:
    """Tests for SecureStorage initialization."""

    def test_path_validation_on_init(self):
        """Verify path is validated on initialization."""
        with pytest.raises(ValueError):
            SecureStorage("/etc/passwd")

    def test_allow_any_path_on_init(self):
        """Verify allow_any_path bypasses validation."""
        # Should not raise
        storage = SecureStorage("/tmp/test.enc.json", allow_any_path=True)
        assert storage is not None


class TestKeyMethod:
    """Tests for KeyMethod constants."""

    def test_keyring_constant(self):
        assert KeyMethod.KEYRING == "keyring"

    def test_gpg_constant(self):
        assert KeyMethod.GPG == "gpg"


class TestGPGTimeout:
    """Tests for GPG timeout configuration."""

    def test_default_timeout_is_5_minutes(self):
        """Verify default GPG timeout is 5 minutes (300 seconds)."""
        assert GPG_TIMEOUT_SECONDS == 300


class TestEncryptionRoundtrip:
    """Integration tests for encryption/decryption."""

    @pytest.fixture
    def temp_storage_path(self):
        """Create a temporary file path for testing."""
        # Use a temp directory that's in CWD for path validation
        fd, path = tempfile.mkstemp(suffix=".enc.json", dir=os.getcwd())
        os.close(fd)
        os.remove(path)  # We just want the path, not the file
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)

    @patch('secure_storage.keyring')
    def test_keyring_roundtrip(self, mock_keyring, temp_storage_path):
        """Test encryption and decryption with keyring method."""
        # Setup mock keyring
        stored_key = {}

        def set_password(service, key_id, value):
            stored_key[key_id] = value

        def get_password(service, key_id):
            return stored_key.get(key_id)

        mock_keyring.set_password = set_password
        mock_keyring.get_password = get_password

        # Initialize and save
        storage = SecureStorage(temp_storage_path, allow_any_path=True)
        test_data = {"tags": {"TEST_UID": {"key": "AABBCCDD", "name": "Test Card"}}}
        storage.initialize(KeyMethod.KEYRING, initial_data=test_data)

        # Load in new instance
        storage2 = SecureStorage(temp_storage_path, allow_any_path=True)
        storage2.load()
        loaded_data = storage2.get_data()

        assert loaded_data == test_data
        assert loaded_data["tags"]["TEST_UID"]["key"] == "AABBCCDD"

    @patch('secure_storage.keyring')
    def test_null_key_id_raises_on_load(self, mock_keyring, temp_storage_path):
        """Verify null key_id in storage file raises RuntimeError."""
        # Create a corrupted storage file with null key_id
        import base64
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from secrets import token_bytes

        key = token_bytes(32)
        iv = token_bytes(12)
        aesgcm = AESGCM(key)
        plaintext = json.dumps({"tags": {}}).encode()
        encrypted = aesgcm.encrypt(iv, plaintext, None)
        tag = encrypted[-16:]
        ciphertext = encrypted[:-16]

        corrupted_data = {
            "version": 1,
            "encryption": {
                "cipher": "AES-256-GCM",
                "iv": base64.b64encode(iv).decode(),
                "tag": base64.b64encode(tag).decode(),
            },
            "key_wrapping": {
                "method": "keyring",
                "key_id": None,  # Corrupted - null key_id
            },
            "payload": base64.b64encode(ciphertext).decode(),
        }

        with open(temp_storage_path, "w") as f:
            json.dump(corrupted_data, f)

        storage = SecureStorage(temp_storage_path, allow_any_path=True)

        with pytest.raises(RuntimeError) as exc_info:
            storage.load()

        assert "null key_id" in str(exc_info.value)
        assert "corrupted" in str(exc_info.value)


class TestCacheInvalidation:
    """Tests for cache invalidation security."""

    @patch('secure_storage.keyring')
    def test_cache_invalidation_clears_keys(self, mock_keyring):
        """Verify cache invalidation clears sensitive key data."""
        storage = SecureStorage(
            get_app_data_dir() / "test.enc.json",
            cache_timeout="session",
            allow_any_path=True,
        )

        # Simulate cached data with keys
        storage._cached_data = {
            "tags": {
                "UID1": {"key": "SECRETKEY1", "name": "Card 1"},
                "UID2": {"key": "SECRETKEY2", "name": "Card 2"},
            }
        }

        # Invalidate cache
        storage._invalidate_cache()

        # Cache should be cleared
        assert storage._cached_data is None
        assert storage._cache_timestamp is None


class TestStorageServiceExceptions:
    """Tests for StorageService exception handling."""

    def test_storage_error_hierarchy(self):
        """Verify exception class hierarchy."""
        from src.services.storage_service import (
            StorageError,
            StorageLoadError,
            StorageDecryptError,
            StorageSaveError,
        )

        assert issubclass(StorageLoadError, StorageError)
        assert issubclass(StorageDecryptError, StorageError)
        assert issubclass(StorageSaveError, StorageError)

    def test_load_raises_on_missing_file(self):
        """Verify StorageService raises StorageLoadError for missing file."""
        from src.services.storage_service import StorageService, StorageLoadError

        service = StorageService("/nonexistent/path/data.enc.json")

        with pytest.raises(StorageLoadError):
            service.load()


class TestBackupFunctions:
    """Tests for backup export/import functions."""

    @pytest.fixture
    def temp_backup_path(self):
        """Create a temporary backup file path."""
        fd, path = tempfile.mkstemp(suffix=".gpbackup", dir=os.getcwd())
        os.close(fd)
        os.remove(path)
        yield path
        if os.path.exists(path):
            os.remove(path)

    def test_export_import_roundtrip_password(self, temp_backup_path):
        """Test export and import with password encryption."""
        from secure_storage import export_backup, import_backup

        test_data = {
            "tags": {
                "04AABBCCDD": {"key": "SECRETKEY123", "name": "Test Card"}
            }
        }
        password = "testpassword123"

        # Export
        export_backup(test_data, temp_backup_path, "password", password=password)
        assert os.path.exists(temp_backup_path)

        # Import
        imported = import_backup(temp_backup_path, password=password)
        assert imported == test_data
        assert imported["tags"]["04AABBCCDD"]["key"] == "SECRETKEY123"

    def test_export_requires_password_for_password_method(self, temp_backup_path):
        """Verify password method requires password."""
        from secure_storage import export_backup

        with pytest.raises(ValueError) as exc_info:
            export_backup({"tags": {}}, temp_backup_path, "password")

        assert "Password required" in str(exc_info.value)

    def test_import_wrong_password_fails(self, temp_backup_path):
        """Verify wrong password fails to decrypt."""
        from secure_storage import export_backup, import_backup

        test_data = {"tags": {"UID1": {"key": "KEY1"}}}
        export_backup(test_data, temp_backup_path, "password", password="correct")

        with pytest.raises(RuntimeError) as exc_info:
            import_backup(temp_backup_path, password="wrong")

        assert "incorrect password" in str(exc_info.value).lower()

    def test_get_backup_info(self, temp_backup_path):
        """Test getting backup metadata."""
        from secure_storage import export_backup, get_backup_info

        export_backup({"tags": {}}, temp_backup_path, "password", password="test123")

        info = get_backup_info(temp_backup_path)
        assert info["version"] == 1
        assert info["method"] == "password"
        assert info["created"] is not None

    def test_backup_version_constant(self):
        """Verify backup version constant."""
        from secure_storage import BACKUP_VERSION
        assert BACKUP_VERSION == 1

    def test_pbkdf2_iterations_constant(self):
        """Verify PBKDF2 iterations meets security requirements."""
        from secure_storage import BACKUP_PBKDF2_ITERATIONS
        # OWASP 2023 recommends 600,000 for PBKDF2-SHA256
        assert BACKUP_PBKDF2_ITERATIONS >= 600000
