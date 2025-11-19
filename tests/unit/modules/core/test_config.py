"""Unit tests for configuration management.

This module tests the configuration loading, validation, and helper functions.

Key Testing Patterns:
    - Test configuration validation functions
    - Test helper functions (is_interactive_environment, etc.)
    - Verify version loading
    - Test MQTT validation

Example Run:
    pytest tests/unit/modules/core/test_config.py -v
"""

import os
from unittest.mock import patch


class TestValidationFunctions:
    """Test suite for configuration validation functions."""

    def test_validate_required_mqtt_success(self):
        """Test MQTT validation with valid settings."""
        from modules.core.config import validate_required_mqtt

        is_valid, error = validate_required_mqtt(
            broker="test.broker.com",
            port="1883",
            user="testuser",
            password="testpass",
        )

        assert is_valid is True
        assert error == ""

    def test_validate_required_mqtt_empty_broker(self):
        """Test MQTT validation with empty broker."""
        from modules.core.config import validate_required_mqtt

        is_valid, error = validate_required_mqtt(
            broker="", port="1883", user="testuser", password="testpass"
        )

        assert is_valid is False
        assert "broker" in error.lower()

    def test_validate_required_mqtt_empty_user(self):
        """Test MQTT validation with empty username."""
        from modules.core.config import validate_required_mqtt

        is_valid, error = validate_required_mqtt(
            broker="test.broker.com", port="1883", user="", password="testpass"
        )

        assert is_valid is False
        assert "username" in error.lower()

    def test_validate_required_mqtt_invalid_port_string(self):
        """Test MQTT validation with non-numeric port."""
        from modules.core.config import validate_required_mqtt

        is_valid, error = validate_required_mqtt(
            broker="test.broker.com",
            port="not_a_number",
            user="testuser",
            password="testpass",
        )

        assert is_valid is False
        assert "port" in error.lower()

    def test_validate_required_mqtt_port_out_of_range(self):
        """Test MQTT validation with port out of valid range."""
        from modules.core.config import validate_required_mqtt

        # Port too high
        is_valid, error = validate_required_mqtt(
            broker="test.broker.com", port="99999", user="testuser", password="testpass"
        )
        assert is_valid is False

        # Port too low
        is_valid, error = validate_required_mqtt(
            broker="test.broker.com", port="0", user="testuser", password="testpass"
        )
        assert is_valid is False

    def test_validate_required_mqtt_empty_password_warning(self):
        """Test that empty password logs warning but still validates."""
        from modules.core.config import validate_required_mqtt

        with patch("modules.core.config.logger") as mock_logger:
            is_valid, error = validate_required_mqtt(
                broker="test.broker.com", port="1883", user="testuser", password=""
            )

            # Should still be valid (some brokers allow empty passwords)
            assert is_valid is True
            # But should log a warning
            mock_logger.warning.assert_called_once()


class TestInteractiveHelpers:
    """Test suite for interactive environment detection."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("sys.stdin.isatty")
    def test_is_interactive_environment_tty(self, mock_isatty):
        """Test interactive detection when stdin is TTY."""
        from modules.core.config import is_interactive_environment

        mock_isatty.return_value = True

        assert is_interactive_environment() is True

    @patch.dict(os.environ, {}, clear=True)
    @patch("sys.stdin.isatty")
    def test_is_interactive_environment_not_tty(self, mock_isatty):
        """Test interactive detection when stdin is not TTY."""
        from modules.core.config import is_interactive_environment

        mock_isatty.return_value = False

        assert is_interactive_environment() is False

    @patch.dict(os.environ, {"DA_NON_INTERACTIVE": "1"})
    @patch("sys.stdin.isatty")
    def test_is_interactive_environment_override(self, mock_isatty):
        """Test that DA_NON_INTERACTIVE overrides TTY detection."""
        from modules.core.config import is_interactive_environment

        mock_isatty.return_value = True  # TTY present

        # But DA_NON_INTERACTIVE is set, so should return False
        assert is_interactive_environment() is False

    @patch("builtins.input", return_value="y")
    def test_prompt_yes_no_accepts_yes(self, mock_input):
        """Test that prompt_yes_no accepts 'y' as yes."""
        from modules.core.config import prompt_yes_no

        result = prompt_yes_no("Test prompt?")
        assert result is True

    @patch("builtins.input", return_value="yes")
    def test_prompt_yes_no_accepts_yes_full(self, mock_input):
        """Test that prompt_yes_no accepts 'yes'."""
        from modules.core.config import prompt_yes_no

        result = prompt_yes_no("Test prompt?")
        assert result is True

    @patch("builtins.input", return_value="n")
    def test_prompt_yes_no_accepts_no(self, mock_input):
        """Test that prompt_yes_no accepts 'n' as no."""
        from modules.core.config import prompt_yes_no

        result = prompt_yes_no("Test prompt?")
        assert result is False

    @patch("builtins.input", return_value="")
    def test_prompt_yes_no_uses_default(self, mock_input):
        """Test that prompt_yes_no uses default on empty input."""
        from modules.core.config import prompt_yes_no

        # Default True
        result = prompt_yes_no("Test prompt?", default=True)
        assert result is True

        # Default False
        result = prompt_yes_no("Test prompt?", default=False)
        assert result is False

    @patch("builtins.input", side_effect=["invalid", "maybe", "y"])
    @patch("builtins.print")
    def test_prompt_yes_no_retries_on_invalid(self, mock_print, mock_input):
        """Test that prompt_yes_no retries on invalid input."""
        from modules.core.config import prompt_yes_no

        result = prompt_yes_no("Test prompt?")

        # Should eventually return True after retries
        assert result is True
        # Should have called input 3 times
        assert mock_input.call_count == 3


class TestVersionLoading:
    """Test suite for VERSION loading."""

    def test_version_is_loaded(self):
        """Test that VERSION constant is available."""
        from modules.core.config import VERSION

        assert VERSION is not None
        assert isinstance(VERSION, str)
        assert len(VERSION) > 0

    def test_version_format(self):
        """Test that VERSION follows semver-like format."""
        from modules.core.config import VERSION

        # Should have at least major.minor.patch
        parts = VERSION.split(".")
        assert len(parts) >= 3

        # First three parts should be numeric (ignoring build metadata after +)
        major = parts[0]
        minor = parts[1]
        patch = parts[2].split("+")[0]  # Remove build metadata if present

        assert major.isdigit()
        assert minor.isdigit()
        assert patch.isdigit()


class TestPaths:
    """Test suite for path constants."""

    def test_base_dir_exists(self):
        """Test that BASE_DIR is defined."""
        from modules.core.config import BASE_DIR

        assert BASE_DIR is not None
        from pathlib import Path

        assert isinstance(BASE_DIR, Path)

    def test_config_path_structure(self):
        """Test that CONFIG_PATH follows expected structure."""
        from modules.core.config import CONFIG_PATH

        assert CONFIG_PATH.name == "config.ini"
        assert "data" in str(CONFIG_PATH)

    def test_version_path_structure(self):
        """Test that VERSION_PATH follows expected structure."""
        from modules.core.config import VERSION_PATH

        assert VERSION_PATH.name == "VERSION"


class TestRepositoryInfo:
    """Test suite for repository information constants."""

    def test_repo_constants_defined(self):
        """Test that repository constants are defined."""
        from modules.core.config import REPO_NAME, REPO_OWNER, REPO_URL

        assert REPO_OWNER is not None
        assert REPO_NAME is not None
        assert REPO_URL is not None

    def test_repo_url_structure(self):
        """Test that REPO_URL is properly constructed."""
        from modules.core.config import REPO_NAME, REPO_OWNER, REPO_URL

        expected = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
        assert REPO_URL == expected
