"""
Unit tests for GPService.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.services.gp_service import (
    GPService,
    GPResult,
    DEFAULT_KEY,
    parse_manifest,
    get_manifest_info,
)


class TestGPService:
    """Tests for GPService."""

    @pytest.fixture
    def gp_service(self):
        """Create a GPService instance for testing."""
        return GPService(gp_path="/mock/gp.jar", verbose=True)

    def test_default_key_constant(self):
        """DEFAULT_KEY should be the standard test key."""
        assert DEFAULT_KEY == "404142434445464748494A4B4C4D4E4F"
        assert len(DEFAULT_KEY) == 32  # 16 bytes as hex

    @patch('subprocess.run')
    def test_list_applets_success(self, mock_run, gp_service, sample_gp_list_output):
        """Should parse installed applets from gp --list output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=sample_gp_list_output,
            stderr="",
        )

        result = gp_service.list_applets("Test Reader", DEFAULT_KEY)

        assert "A0000008466D656D6F727901" in result
        assert "D2760000850101" in result
        assert result["A0000008466D656D6F727901"] == "1.0"
        assert result["D2760000850101"] == "1.0"

    @patch('subprocess.run')
    def test_list_applets_empty_on_error(self, mock_run, gp_service):
        """Should return empty dict on error."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error connecting to card",
        )

        result = gp_service.list_applets("Test Reader", DEFAULT_KEY)
        assert result == {}

    @patch('subprocess.run')
    def test_install_applet_basic(self, mock_run, gp_service):
        """Should call gp with correct install arguments."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Installation complete",
            stderr="",
        )

        result = gp_service.install_applet(
            reader="Test Reader",
            key=DEFAULT_KEY,
            cap_path="/path/to/app.cap",
        )

        assert result.success is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "--install" in call_args
        assert "/path/to/app.cap" in call_args
        assert "-k" in call_args

    @patch('subprocess.run')
    def test_install_applet_with_params(self, mock_run, gp_service):
        """Should include params in install command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        gp_service.install_applet(
            reader="Test Reader",
            key=DEFAULT_KEY,
            cap_path="/path/to/app.cap",
            params="8102FF00 82021000",
        )

        call_args = mock_run.call_args[0][0]
        assert "--params" in call_args
        assert "8102FF00" in call_args
        assert "82021000" in call_args

    @patch('subprocess.run')
    def test_uninstall_by_aid(self, mock_run, gp_service):
        """Should use --delete for AID uninstall."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        gp_service.uninstall_applet(
            reader="Test Reader",
            key=DEFAULT_KEY,
            target="A0000008466D656D6F727901",
        )

        call_args = mock_run.call_args[0][0]
        assert "--delete" in call_args
        assert "A0000008466D656D6F727901" in call_args

    @patch('subprocess.run')
    def test_uninstall_by_cap(self, mock_run, gp_service):
        """Should use --uninstall for CAP file."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        gp_service.uninstall_applet(
            reader="Test Reader",
            key=DEFAULT_KEY,
            target="/path/to/app.cap",
        )

        call_args = mock_run.call_args[0][0]
        assert "--uninstall" in call_args
        assert "/path/to/app.cap" in call_args

    @patch('subprocess.run')
    def test_uninstall_force_flag(self, mock_run, gp_service):
        """Should include -f flag when force=True."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        gp_service.uninstall_applet(
            reader="Test Reader",
            key=DEFAULT_KEY,
            target="A0000008",
            force=True,
        )

        call_args = mock_run.call_args[0][0]
        assert "-f" in call_args

    @patch('subprocess.run')
    def test_change_key_to_custom(self, mock_run, gp_service):
        """Should use --lock for custom key."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        new_key = "11111111111111111111111111111111"
        gp_service.change_key(
            reader="Test Reader",
            old_key=DEFAULT_KEY,
            new_key=new_key,
        )

        call_args = mock_run.call_args[0][0]
        assert "--lock" in call_args
        assert new_key in call_args

    @patch('subprocess.run')
    def test_change_key_to_default(self, mock_run, gp_service):
        """Should use --unlock-card for default key."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        gp_service.change_key(
            reader="Test Reader",
            old_key="11111111111111111111111111111111",
            new_key=DEFAULT_KEY,
        )

        call_args = mock_run.call_args[0][0]
        assert "--unlock-card" in call_args

    @patch('subprocess.run')
    def test_invalid_key_detection(self, mock_run, gp_service):
        """Should detect invalid key errors."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Failed to open secure channel: Card cryptogram invalid!",
        )

        result = gp_service.uninstall_applet(
            reader="Test Reader",
            key="WRONGKEY",
            target="A0000008",
        )

        assert result.success is False
        assert result.is_invalid_key_error is True

    def test_command_log_redacts_key(self, gp_service):
        """Should redact key in command log."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            gp_service.list_applets("Test Reader", "SECRET123")

        log = gp_service.get_command_log()
        assert len(log) == 1
        assert "SECRET123" not in log[0]
        assert "***REDACTED***" in log[0]


class TestManifestParsing:
    """Tests for CAP file manifest parsing."""

    def test_parse_manifest_basic(self):
        """Should parse key-value pairs from manifest."""
        content = """Manifest-Version: 1.0
Java-Card-Applet-AID: A0:00:00:08:46:6D:65:6D:6F:72:79:01
Java-Card-Package-Version: 1.0
"""
        result = parse_manifest(content)

        assert result["Manifest-Version"] == "1.0"
        assert result["Java-Card-Applet-AID"] == "A0000008466D656D6F727901"
        assert result["Java-Card-Package-Version"] == "1.0"

    def test_parse_manifest_classic_aid(self):
        """Should handle Classic-Package-AID format."""
        content = """Name: test
Classic-Package-AID: aid/A0/00/00/05
"""
        result = parse_manifest(content)
        assert result["Classic-Package-AID"] == "A0000005"

    def test_get_manifest_info(self):
        """Should extract key info from parsed manifest."""
        manifest = {
            "Name": "Test App",
            "Java-Card-Applet-AID": "A0000008",
            "Java-Card-Package-Version": "1.0",
        }

        info = get_manifest_info(manifest)

        assert info.name == "Test App"
        assert info.aid == "A0000008"
        assert info.app_version == "1.0"
