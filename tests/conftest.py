"""
Pytest configuration and shared fixtures.
"""

import pytest
import sys
import os
import tempfile
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False
    ) as f:
        json.dump({
            "_version": 1,
            "cache_latest_release": False,
            "known_tags": {},
            "last_checked": {},
            "window": {"width": 800, "height": 600}
        }, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def temp_config_v0():
    """Create a v0 (unversioned) config file for migration testing."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False
    ) as f:
        # Old format without version
        json.dump({
            "cache_latest_release": True,
            "known_tags": {"04AABBCCDD": True},
            "window": {"width": 1024, "height": 768}
        }, f)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def corrupted_config_file():
    """Create a corrupted config file for error handling testing."""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False
    ) as f:
        f.write("{ invalid json content")
        temp_path = f.name

    yield temp_path

    # Cleanup - also check for backup file
    if os.path.exists(temp_path):
        os.remove(temp_path)
    # Clean up any backup files
    import glob
    for backup in glob.glob("config-*-.broken.json"):
        os.remove(backup)


@pytest.fixture
def sample_gp_list_output():
    """Sample output from gp --list command."""
    return """ISD: A000000151000000 (OP_READY)
     Parent:  A000000151000000
     From:    A0000001515350
     Privs:   SecurityDomain, CardLock, CardTerminate

APP: A0000008466D656D6F727901 (SELECTABLE)
     Parent:  A000000151000000
     From:    A0000008466D656D6F7279
     Privs:

APP: D2760000850101 (SELECTABLE)
     Parent:  A000000151000000
     From:    D276000085
     Privs:

PKG: A0000008466D656D6F7279 (LOADED)
     Parent:  A000000151000000
     Version: 1.0
     Applet:  A0000008466D656D6F727901

PKG: D276000085 (LOADED)
     Parent:  A000000151000000
     Version: 1.0
     Applet:  D2760000850101
"""


@pytest.fixture
def mock_card_service():
    """Create a mock card service for testing."""
    from src.services.card_service import MockCardService

    service = MockCardService()
    service.set_mock_readers(["Test Reader 0", "Test Reader 1"])
    service.set_mock_uid("04AABBCCDD")
    service.set_mock_jcop(True)
    return service


@pytest.fixture
def mock_config_service():
    """Create a mock config service for testing."""
    from src.services.config_service import MockConfigService
    return MockConfigService()


@pytest.fixture
def mock_storage_service():
    """Create a mock storage service for testing."""
    from src.services.storage_service import MockStorageService
    return MockStorageService()
