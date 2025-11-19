"""Unit tests for command execution module.

This module tests the secure command execution system including validation,
whitelisting, shell feature detection, and platform-specific execution.

Key Testing Patterns:
    - Mock subprocess calls to avoid executing real commands
    - Test security validation (key validation, shell features)
    - Test command whitelisting and configuration loading
    - Verify proper error handling and logging
    - Test platform-specific behavior

Example Run:
    pytest tests/unit/modules/test_commands.py -v
"""

import configparser
from unittest.mock import MagicMock, patch

import pytest

from modules.commands import (
    COMMAND_KEY_PATTERN,
    MAX_COMMAND_KEY_LENGTH,
    MAX_COMMAND_LENGTH,
    has_shell_features,
    load_commands,
    run_predefined_command,
    safe_split_command,
    validate_command_key,
    validate_command_safe,
)


class TestShellFeatureDetection:
    """Test suite for shell feature detection."""

    def test_has_shell_features_pipe(self):
        """Test detection of pipe operator."""
        assert has_shell_features("ps aux | grep python") is True

    def test_has_shell_features_redirect_output(self):
        """Test detection of output redirection."""
        assert has_shell_features("echo test > file.txt") is True
        assert has_shell_features("cat file >> log.txt") is True

    def test_has_shell_features_redirect_input(self):
        """Test detection of input redirection."""
        assert has_shell_features("sort < input.txt") is True

    def test_has_shell_features_command_chaining(self):
        """Test detection of command chaining operators."""
        assert has_shell_features("make && make install") is True
        assert has_shell_features("cmd1; cmd2") is True

    def test_has_shell_features_variable_expansion(self):
        """Test detection of variable expansion."""
        assert has_shell_features("echo $HOME") is True
        assert has_shell_features("cd ${WORKSPACE}") is True

    def test_has_shell_features_command_substitution(self):
        """Test detection of command substitution."""
        assert has_shell_features("echo `date`") is True
        assert has_shell_features("files=$(ls)") is True

    def test_has_shell_features_subshell(self):
        """Test detection of subshells."""
        assert has_shell_features("(cd dir && make)") is True

    def test_no_shell_features_simple_command(self):
        """Test that simple commands are not flagged."""
        assert has_shell_features("firefox") is False
        assert has_shell_features("python script.py") is False
        assert has_shell_features("ls -la /home") is False

    def test_no_shell_features_quoted_strings(self):
        """Test that quoted strings without metacharacters are safe."""
        assert has_shell_features("echo 'hello world'") is False
        assert has_shell_features('echo "test message"') is False


class TestCommandKeyValidation:
    """Test suite for command key validation."""

    def test_validate_command_key_valid(self):
        """Test validation of valid command keys."""
        valid_keys = [
            "simple",
            "with_underscore",
            "with-dash",
            "CamelCase",
            "mix_of-ALL123",
            "a",  # Single character
            "command123",
        ]

        for key in valid_keys:
            is_valid, msg = validate_command_key(key)
            assert is_valid is True, f"Key '{key}' should be valid"
            assert msg == "OK"

    def test_validate_command_key_empty(self):
        """Test validation of empty command key."""
        is_valid, msg = validate_command_key("")
        assert is_valid is False
        assert "empty" in msg.lower()

    def test_validate_command_key_too_long(self):
        """Test validation of excessively long command key."""
        long_key = "a" * (MAX_COMMAND_KEY_LENGTH + 1)
        is_valid, msg = validate_command_key(long_key)
        assert is_valid is False
        assert "too long" in msg.lower()

    def test_validate_command_key_invalid_characters(self):
        """Test validation rejects special characters."""
        invalid_keys = [
            "has space",
            "has/slash",
            "has\\backslash",
            "has.dot",
            "has@symbol",
            "has#hash",
            "has$dollar",
            "../path/traversal",
        ]

        for key in invalid_keys:
            is_valid, msg = validate_command_key(key)
            assert is_valid is False, f"Key '{key}' should be invalid"

    def test_command_key_pattern_direct(self):
        """Test COMMAND_KEY_PATTERN regex directly."""
        assert COMMAND_KEY_PATTERN.match("valid_key") is not None
        assert COMMAND_KEY_PATTERN.match("also-valid") is not None
        assert COMMAND_KEY_PATTERN.match("invalid key") is None
        assert COMMAND_KEY_PATTERN.match("invalid/key") is None


class TestCommandSafetyValidation:
    """Test suite for command safety validation."""

    def test_validate_command_safe_simple(self):
        """Test validation of simple safe commands."""
        is_valid, msg = validate_command_safe("firefox", allow_shell=False)
        assert is_valid is True
        assert msg == "OK"

    def test_validate_command_safe_empty(self):
        """Test validation of empty command."""
        is_valid, msg = validate_command_safe("", allow_shell=False)
        assert is_valid is False
        assert "empty" in msg.lower()

    def test_validate_command_safe_too_long(self):
        """Test validation of excessively long command."""
        long_cmd = "a" * (MAX_COMMAND_LENGTH + 1)
        is_valid, msg = validate_command_safe(long_cmd, allow_shell=False)
        assert is_valid is False
        assert "too long" in msg.lower()

    def test_validate_command_safe_shell_features_denied(self):
        """Test that shell features are denied without explicit permission."""
        is_valid, msg = validate_command_safe("ps aux | grep python", allow_shell=False)
        assert is_valid is False
        assert "shell features" in msg.lower()
        assert "shell_features=true" in msg

    def test_validate_command_safe_shell_features_allowed(self):
        """Test that shell features are allowed with permission."""
        is_valid, msg = validate_command_safe("ps aux | grep python", allow_shell=True)
        assert is_valid is True
        assert msg == "OK"

    def test_validate_command_safe_multiple_metacharacters(self):
        """Test command with multiple shell metacharacters."""
        cmd = "make && make install > log.txt 2>&1"
        is_valid, msg = validate_command_safe(cmd, allow_shell=False)
        assert is_valid is False

        is_valid, msg = validate_command_safe(cmd, allow_shell=True)
        assert is_valid is True


class TestSafeSplitCommand:
    """Test suite for safe command splitting."""

    def test_safe_split_simple(self):
        """Test splitting simple commands."""
        assert safe_split_command("firefox") == ["firefox"]
        assert safe_split_command("python script.py") == ["python", "script.py"]

    def test_safe_split_with_arguments(self):
        """Test splitting commands with multiple arguments."""
        result = safe_split_command("ls -la /home /var")
        assert result == ["ls", "-la", "/home", "/var"]

    def test_safe_split_quoted_strings(self):
        """Test splitting commands with quoted arguments."""
        result = safe_split_command('echo "hello world"')
        assert result == ["echo", "hello world"]

        result = safe_split_command("echo 'test message'")
        assert result == ["echo", "test message"]

    def test_safe_split_mixed_quotes(self):
        """Test splitting with mixed quote types."""
        result = safe_split_command("""echo "double" 'single' mixed""")
        assert result == ["echo", "double", "single", "mixed"]

    def test_safe_split_escaped_characters(self):
        """Test splitting with escaped characters."""
        result = safe_split_command("echo test\\ file")
        assert result == ["echo", "test file"]

    def test_safe_split_invalid_syntax(self):
        """Test that invalid syntax raises ValueError."""
        with pytest.raises(ValueError, match="Invalid command syntax"):
            safe_split_command('echo "unclosed quote')


class TestLoadCommands:
    """Test suite for command configuration loading."""

    def test_load_commands_creates_default(self, tmp_path, monkeypatch):
        """Test that load_commands creates default config if missing."""
        # Create directory structure
        data_dir = tmp_path / "data"
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir(parents=True)

        # Create example config
        example_config = resources_dir / "commands_example.ini"
        example_config.write_text("[example]\ncmd = echo test\nwait = false\n")

        # Create a commands.ini that doesn't exist yet (will be copied)
        config_file = data_dir / "commands.ini"

        # Create a mock module file that Path(__file__) will resolve to
        mock_module_file = tmp_path / "modules" / "commands.py"
        mock_module_file.parent.mkdir(parents=True)
        mock_module_file.touch()

        # Mock Path(__file__) to return our temporary module path
        import modules.commands

        original_file = modules.commands.__file__
        try:
            modules.commands.__file__ = str(mock_module_file)

            commands = load_commands()

            # Verify the data directory and file were created
            assert config_file.exists()
            # Should have loaded the example command
            assert "example" in commands
        finally:
            modules.commands.__file__ = original_file

    def test_load_commands_validation(self, tmp_path):
        """Test that load_commands validates command keys."""
        # Create directory structure
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir(parents=True)

        # Create a test commands file with valid and invalid keys
        config = configparser.ConfigParser()
        config["valid_key"] = {"cmd": "firefox", "wait": "false"}
        config["invalid key"] = {"cmd": "chrome", "wait": "false"}  # Has space
        config["also-valid"] = {"cmd": "code", "wait": "false"}

        config_file = data_dir / "commands.ini"
        with open(config_file, "w") as f:
            config.write(f)

        # Create dummy example file
        example_file = resources_dir / "commands_example.ini"
        example_file.write_text("[example]\ncmd = test\n")

        # Create a mock module file that Path(__file__) will resolve to
        mock_module_file = tmp_path / "modules" / "commands.py"
        mock_module_file.parent.mkdir(parents=True)
        mock_module_file.touch()

        # Mock Path(__file__) to return our temporary module path
        import modules.commands

        original_file = modules.commands.__file__
        try:
            modules.commands.__file__ = str(mock_module_file)

            commands = load_commands()

            # Valid keys should be loaded
            assert "valid_key" in commands
            assert "also-valid" in commands
            # Invalid key should be skipped
            assert "invalid key" not in commands
        finally:
            modules.commands.__file__ = original_file

    def test_load_commands_shell_features_flag(self, tmp_path):
        """Test that shell_features flag is correctly parsed."""
        # Create directory structure
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir(parents=True)

        config = configparser.ConfigParser()
        config["with_shell"] = {
            "cmd": "ps aux | grep python",
            "wait": "true",
            "shell_features": "true",
        }
        config["without_shell"] = {"cmd": "firefox", "wait": "false"}

        config_file = data_dir / "commands.ini"
        with open(config_file, "w") as f:
            config.write(f)

        # Create dummy example file
        example_file = resources_dir / "commands_example.ini"
        example_file.write_text("[example]\ncmd = test\n")

        # Create a mock module file that Path(__file__) will resolve to
        mock_module_file = tmp_path / "modules" / "commands.py"
        mock_module_file.parent.mkdir(parents=True)
        mock_module_file.touch()

        # Mock Path(__file__) to return our temporary module path
        import modules.commands

        original_file = modules.commands.__file__
        try:
            modules.commands.__file__ = str(mock_module_file)

            commands = load_commands()

            assert commands["with_shell"]["shell_features"] is True
            assert commands["without_shell"]["shell_features"] is False
        finally:
            modules.commands.__file__ = original_file


class TestRunPredefinedCommand:
    """Test suite for run_predefined_command function."""

    @patch("modules.commands.COMMANDS_MOD", False)
    def test_run_predefined_command_module_disabled(self):
        """Test behavior when commands module is disabled."""
        result = run_predefined_command("any_command")
        assert result["success"] is False
        assert "not enabled" in result["output"].lower()

    @patch("modules.commands.COMMANDS_MOD", True)
    @patch("modules.commands.ALLOWED_COMMANDS", {})
    def test_run_predefined_command_not_in_whitelist(self):
        """Test that non-whitelisted commands are rejected."""
        result = run_predefined_command("unknown_command")
        assert result["success"] is False
        assert "not allowed" in result["output"]

    @patch("modules.commands.COMMANDS_MOD", True)
    def test_run_predefined_command_invalid_key(self):
        """Test that invalid command keys are rejected."""
        result = run_predefined_command("invalid key")
        assert result["success"] is False
        assert "Invalid command key" in result["output"]

    @patch("modules.commands.COMMANDS_MOD", True)
    @patch(
        "modules.commands.ALLOWED_COMMANDS",
        {
            "test": {
                "cmd": "firefox",
                "wait": False,
                "platforms": ["linux"],
                "shell_features": False,
            }
        },
    )
    @patch("modules.commands.sys.platform", "linux")
    @patch("modules.commands._execute_linux_command")
    def test_run_predefined_command_success_linux(self, mock_exec):
        """Test successful command execution on Linux."""
        mock_exec.return_value = {"success": True, "output": "Command launched"}

        result = run_predefined_command("test")

        assert result["success"] is True
        mock_exec.assert_called_once_with("test", "firefox", False, False)

    @patch("modules.commands.COMMANDS_MOD", True)
    @patch(
        "modules.commands.ALLOWED_COMMANDS",
        {
            "test": {
                "cmd": "notepad.exe",
                "wait": False,
                "platforms": ["win"],
                "shell_features": False,
            }
        },
    )
    @patch("modules.commands.sys.platform", "win32")
    @patch("modules.commands._execute_windows_command")
    def test_run_predefined_command_success_windows(self, mock_exec):
        """Test successful command execution on Windows."""
        mock_exec.return_value = {"success": True, "output": "Command launched"}

        result = run_predefined_command("test")

        assert result["success"] is True
        mock_exec.assert_called_once()

    @patch("modules.commands.COMMANDS_MOD", True)
    @patch(
        "modules.commands.ALLOWED_COMMANDS",
        {
            "test": {
                "cmd": "firefox",
                "wait": False,
                "platforms": ["linux"],
                "shell_features": False,
            }
        },
    )
    @patch("modules.commands.sys.platform", "win32")
    def test_run_predefined_command_wrong_platform(self):
        """Test that platform-specific commands are rejected on wrong platform."""
        result = run_predefined_command("test")

        assert result["success"] is False
        assert "not available on" in result["output"].lower()

    @patch("modules.commands.COMMANDS_MOD", True)
    @patch(
        "modules.commands.ALLOWED_COMMANDS",
        {
            "test": {
                "cmd": "ps aux | grep python",
                "wait": True,
                "platforms": None,
                "shell_features": False,
            }
        },
    )
    def test_run_predefined_command_shell_validation_failure(self):
        """Test that commands with shell features fail without permission."""
        result = run_predefined_command("test")

        assert result["success"] is False
        assert "shell features" in result["output"].lower()


class TestLinuxCommandExecution:
    """Test suite for Linux-specific command execution."""

    @patch("modules.commands.subprocess.Popen")
    @patch("modules.commands.get_linux_gui_env")
    def test_execute_linux_gui_app(self, mock_env, mock_popen):
        """Test launching GUI application on Linux."""
        from modules.commands import _execute_linux_command

        mock_env.return_value = {"DISPLAY": ":0"}
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_popen.return_value = mock_process

        result = _execute_linux_command(
            "test", "firefox", wait=False, shell_features=False
        )

        assert result["success"] is True
        assert "launched" in result["output"].lower()
        mock_popen.assert_called_once()

    @patch("modules.commands.subprocess.run")
    @patch("modules.commands.get_linux_gui_env")
    def test_execute_linux_wait_command(self, mock_env, mock_run):
        """Test executing command with wait on Linux."""
        from modules.commands import _execute_linux_command

        mock_env.return_value = {"DISPLAY": ":0"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = _execute_linux_command(
            "test", "echo hello", wait=True, shell_features=False
        )

        assert result["success"] is True
        assert result["output"] == "Command output"
        mock_run.assert_called_once()


class TestWindowsCommandExecution:
    """Test suite for Windows-specific command execution."""

    @patch("modules.commands.subprocess.Popen")
    def test_execute_windows_gui_app(self, mock_popen):
        """Test launching GUI application on Windows."""
        from modules.commands import _execute_windows_command

        result = _execute_windows_command(
            "test", "notepad.exe", wait=False, shell_features=False
        )

        assert result["success"] is True
        mock_popen.assert_called()

    @patch("modules.commands.subprocess.run")
    def test_execute_windows_wait_command(self, mock_run):
        """Test executing command with wait on Windows."""
        from modules.commands import _execute_windows_command

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = _execute_windows_command(
            "test", "echo hello", wait=True, shell_features=False
        )

        assert result["success"] is True
        assert result["output"] == "Command output"


class TestSystemPowerCommands:
    """Test suite for system power commands (reboot/shutdown)."""

    @patch("modules.commands.subprocess.Popen")
    @patch("modules.commands.sys.platform", "linux")
    def test_reboot_linux(self, mock_popen):
        """Test reboot command on Linux."""
        from modules.commands import run_system_power_command

        result = run_system_power_command("reboot")

        assert result["success"] is True
        assert "reboot" in result["output"].lower()
        # Verify command was called without shell
        call_args = mock_popen.call_args
        assert call_args[0][0] == ["reboot"]

    @patch("modules.commands.subprocess.Popen")
    @patch("modules.commands.sys.platform", "win32")
    def test_shutdown_windows(self, mock_popen):
        """Test shutdown command on Windows."""
        from modules.commands import run_system_power_command

        result = run_system_power_command("shutdown")

        assert result["success"] is True
        # Verify Windows-specific shutdown command
        call_args = mock_popen.call_args
        assert call_args[0][0][0] == "shutdown"
        assert "/s" in call_args[0][0]
