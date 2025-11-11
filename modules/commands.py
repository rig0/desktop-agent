# Standard library imports
import configparser
import copy
import glob
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

# Local imports
from .config import COMMANDS_MOD

# Configure logger
logger = logging.getLogger(__name__)

# ----------------------------
# Security and Validation
# ----------------------------

# Maximum allowed lengths for security
MAX_COMMAND_KEY_LENGTH = 100
MAX_COMMAND_LENGTH = 1000

# Shell metacharacters that indicate shell features are needed
SHELL_METACHARACTERS = frozenset(['|', '>', '<', '&', ';', '$', '`', '\n', '(', ')'])

# Pattern for validating command keys (alphanumeric, underscore, dash only)
COMMAND_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def has_shell_features(cmd: str) -> bool:
    """
    Detect if a command string contains shell-specific features.

    Shell features include pipes, redirects, command chaining, variable expansion, etc.
    Commands with these features require shell=True but pose security risks.

    Args:
        cmd: The command string to check

    Returns:
        True if the command contains shell metacharacters, False otherwise

    Examples:
        >>> has_shell_features("echo hello")
        False
        >>> has_shell_features("ps aux | grep python")
        True
        >>> has_shell_features("echo $HOME")
        True
    """
    return any(char in cmd for char in SHELL_METACHARACTERS)


def validate_command_key(key: str) -> Tuple[bool, str]:
    """
    Validate that a command key is safe and well-formed.

    Command keys should only contain alphanumeric characters, underscores, and dashes
    to prevent any potential injection through configuration parsing.

    Args:
        key: The command key to validate

    Returns:
        Tuple of (is_valid, error_message)
        - (True, "OK") if valid
        - (False, reason) if invalid

    Security rationale:
        - Prevents Unicode attacks and encoding issues
        - Prevents path traversal attempts
        - Keeps keys simple and predictable
    """
    if not key:
        return False, "Command key cannot be empty"

    if len(key) > MAX_COMMAND_KEY_LENGTH:
        return False, f"Command key too long (max {MAX_COMMAND_KEY_LENGTH} characters)"

    if not COMMAND_KEY_PATTERN.match(key):
        return False, "Command key must contain only letters, numbers, underscores, and dashes"

    return True, "OK"


def validate_command_safe(cmd: str, allow_shell: bool) -> Tuple[bool, str]:
    """
    Validate that a command is safe to execute.

    This is a defense-in-depth check that ensures:
    1. The command is not empty or excessively long
    2. If shell features are detected, shell_features flag must be enabled
    3. Commands requiring shell are logged for audit purposes

    Args:
        cmd: The command string to validate
        allow_shell: Whether shell_features=true is set in config

    Returns:
        Tuple of (is_valid, error_message)
        - (True, "OK") if valid
        - (False, reason) if invalid

    Security rationale:
        - Fail-secure: deny by default when shell features detected
        - Require explicit opt-in for dangerous operations
        - Provide clear feedback on why commands are rejected
    """
    if not cmd:
        return False, "Command cannot be empty"

    if len(cmd) > MAX_COMMAND_LENGTH:
        return False, f"Command too long (max {MAX_COMMAND_LENGTH} characters)"

    # Check for shell features
    if has_shell_features(cmd):
        if not allow_shell:
            return False, (
                "Command contains shell features (pipes, redirects, etc.) but "
                "'shell_features=true' is not set in configuration. "
                "Add 'shell_features = true' to the command configuration if these features are required."
            )
        # Log warning for audit trail
        logger.warning(
            f"Executing command with shell features enabled: {cmd[:100]}... "
            "(this increases security risk - ensure command source is trusted)"
        )

    return True, "OK"


def safe_split_command(cmd: str) -> List[str]:
    """
    Safely split a command string into arguments using shell-like parsing.

    Uses shlex.split() which properly handles:
    - Quoted strings (both single and double quotes)
    - Escaped characters
    - Whitespace preservation within quotes

    Args:
        cmd: Command string to split

    Returns:
        List of command arguments

    Raises:
        ValueError: If the command has unmatched quotes or invalid syntax

    Examples:
        >>> safe_split_command("firefox")
        ['firefox']
        >>> safe_split_command('echo "hello world"')
        ['echo', 'hello world']
    """
    try:
        return shlex.split(cmd)
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")


# ----------------------------
# System commands
# ----------------------------

def load_commands(filename="commands.ini"):
    """
    Load and validate command configurations from INI file.

    Parses the commands configuration file and validates all command keys
    for security. Supports the following configuration options per command:
    - cmd: The command to execute (required)
    - wait: Whether to wait for command completion (default: False)
    - platforms: Comma-separated list of platforms (linux, win, etc.)
    - shell_features: Enable shell features like pipes/redirects (default: False)

    Args:
        filename: Name of the configuration file (default: "commands.ini")

    Returns:
        Dictionary mapping command keys to their configuration

    Security notes:
        - Command keys are validated to prevent injection
        - shell_features defaults to False for security
        - Invalid command keys are rejected and logged
    """
    BASE_DIR = Path(__file__).parent.parent
    commands_file = BASE_DIR / "data" / filename
    src = BASE_DIR / "resources" / "commands_example.ini"

    # Create data dir if needed
    commands_file.parent.mkdir(parents=True, exist_ok=True)

    # Create default if missing
    if not commands_file.exists():
        shutil.copy(src, commands_file)
        logger.info(f"Created default commands config at {commands_file}")

    # Parse file
    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve key case
    parser.read(commands_file, encoding="utf-8")

    commands = {}
    for section in parser.sections():
        # Validate command key
        is_valid, error_msg = validate_command_key(section)
        if not is_valid:
            logger.error(f"Invalid command key '{section}': {error_msg} - skipping")
            continue

        cmd = parser.get(section, "cmd", fallback=None)
        if not cmd:
            logger.warning(f"Command '{section}' has no 'cmd' value - skipping")
            continue

        wait = parser.getboolean(section, "wait", fallback=False)
        platforms = parser.get(section, "platforms", fallback=None)
        platforms = [p.strip() for p in platforms.split(",")] if platforms else None

        # Parse shell_features flag (defaults to False for security)
        shell_features = parser.getboolean(section, "shell_features", fallback=False)

        # Log warning if shell features are enabled
        if shell_features:
            logger.warning(
                f"Command '{section}' has shell_features enabled - this allows shell "
                f"metacharacters and increases security risk. Ensure the command source is trusted."
            )

        commands[section] = {
            "cmd": cmd,
            "wait": wait,
            "platforms": platforms,
            "shell_features": shell_features,
        }

    return commands

ALLOWED_COMMANDS = load_commands() if COMMANDS_MOD else {}

def get_linux_gui_env() -> dict:
    # Return environment variables for launching GUI applications on Linux,
    env = copy.deepcopy(os.environ)

    # Detect Wayland
    wayland_display = env.get("WAYLAND_DISPLAY")
    use_wayland = bool(wayland_display)

    # Detect X11
    x11_display = env.get("DISPLAY")
    use_x11 = bool(x11_display)

    env["USE_WAYLAND"] = str(use_wayland)

    # If Wayland, ensure DISPLAY is also set for apps that require X11 fallback
    if use_wayland and not x11_display:
        env["DISPLAY"] = ":0"

    # DBUS_SESSION_BUS_ADDRESS
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        # Fallback to launching dbus-session if missing
        try:
            from subprocess import check_output
            dbus_address = check_output(["dbus-launch"], text=True).splitlines()
            for line in dbus_address:
                if line.startswith("DBUS_SESSION_BUS_ADDRESS="):
                    env["DBUS_SESSION_BUS_ADDRESS"] = line.split("=", 1)[1].strip()
                elif line.startswith("DBUS_SESSION_BUS_PID="):
                    env["DBUS_SESSION_BUS_PID"] = line.split("=", 1)[1].strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            logger.debug(f"Could not launch dbus-session: {e}")
            # Ignore failures; some systems may not have dbus-launch

    return env

# Reboot / Shutdown handler
def run_system_power_command(action: str) -> dict:
    """
    Execute system power commands (reboot, shutdown).

    These commands use hardcoded values and list form for safety.
    No shell=True is needed since there are no shell features or dynamic input.

    Args:
        action: Either "reboot" or "shutdown"

    Returns:
        Dictionary with success status and output message

    Security notes:
        - Commands are hardcoded (no user input)
        - Uses list form to avoid shell=True
        - Provides platform-specific implementations
    """
    try:
        platform_name = "linux" if sys.platform.startswith("linux") else "win" if sys.platform.startswith("win") else None
        if not platform_name:
            return {"success": False, "output": f"Unsupported platform: {sys.platform}"}

        # Build command as list (safe from injection)
        if platform_name == "linux":
            if action == "reboot":
                cmd = ["reboot"]
                # Alternative: cmd = ["sudo", "systemctl", "reboot"]
            elif action == "shutdown":
                cmd = ["poweroff"]
                # Alternative: cmd = ["sudo", "systemctl", "poweroff"]
            else:
                return {"success": False, "output": f"Unknown action '{action}'"}

        elif platform_name == "win":
            if action == "reboot":
                cmd = ["shutdown", "/r", "/t", "0"]
            elif action == "shutdown":
                cmd = ["shutdown", "/s", "/t", "0"]
            else:
                return {"success": False, "output": f"Unknown action '{action}'"}

        # Execute without shell (secure)
        logger.info(f"Executing system power command: {action}")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "output": f"{action.capitalize()} command executed."}

    except Exception as e:
        logger.error(f"Failed to execute power command '{action}': {e}", exc_info=True)
        return {"success": False, "output": str(e)}

# Run predefined commands
def run_predefined_command(command_key: str) -> dict:
    """
    Execute a predefined command from the configuration.

    Implements defense-in-depth security:
    1. Validates command key format
    2. Validates command content
    3. Uses list form when possible (no shell)
    4. Requires explicit shell_features flag for shell metacharacters
    5. Logs all command executions for audit trail

    Args:
        command_key: The key identifying the command in configuration

    Returns:
        Dictionary with success status and output message

    Security notes:
        - Commands are validated before execution
        - shell=True only used when shell_features=true in config
        - All executions are logged for audit purposes
        - Fails securely on validation errors
    """
    # Check if module is enabled
    if not COMMANDS_MOD:
        logger.warning("Commands module not enabled")
        return {"success": False, "output": "Module not enabled"}

    # Validate command key format
    is_valid, error_msg = validate_command_key(command_key)
    if not is_valid:
        logger.error(f"Invalid command key '{command_key}': {error_msg}")
        return {"success": False, "output": f"Invalid command key: {error_msg}"}

    # Check if command exists in configuration
    if command_key not in ALLOWED_COMMANDS:
        logger.warning(f"Command '{command_key}' not found in configuration")
        return {"success": False, "output": f"Command '{command_key}' not allowed."}

    entry = ALLOWED_COMMANDS[command_key]

    # Extract configuration
    if isinstance(entry, dict):
        cmd = entry.get("cmd")
        wait = entry.get("wait", False)
        platforms = entry.get("platforms", None)
        shell_features = entry.get("shell_features", False)
    else:
        # Legacy format (string command)
        cmd = entry
        wait = False
        platforms = None
        shell_features = False

    # Validate command content
    is_valid, error_msg = validate_command_safe(cmd, shell_features)
    if not is_valid:
        logger.error(f"Command '{command_key}' failed validation: {error_msg}")
        return {"success": False, "output": f"Command validation failed: {error_msg}"}

    logger.info(f"Executing command '{command_key}': {cmd[:100]}{'...' if len(cmd) > 100 else ''}")

    platform_name = "linux" if sys.platform.startswith("linux") else "win" if sys.platform.startswith("win") else None

    # Check platform compatibility
    if platforms and platform_name not in platforms:
        logger.warning(f"Command '{command_key}' not available on {platform_name}")
        return {"success": False, "output": f"Command '{command_key}' not available on {platform_name}."}

    # Special hardcoded commands
    if cmd in ["reboot", "shutdown"]:
        return run_system_power_command(cmd)

    try:
        if platform_name == "linux":
            return _execute_linux_command(command_key, cmd, wait, shell_features)

        elif platform_name == "win":
            return _execute_windows_command(command_key, cmd, wait, shell_features)

        else:
            logger.error(f"Unsupported platform '{platform_name}'")
            return {"success": False, "output": f"Unsupported platform '{platform_name}'."}

    except subprocess.CalledProcessError as e:
        logger.error(f"Command '{command_key}' execution failed: {e}", exc_info=True)
        return {"success": False, "output": f"Command execution failed: {str(e)}"}
    except OSError as e:
        logger.error(f"OS error executing command '{command_key}': {e}", exc_info=True)
        return {"success": False, "output": f"OS error: {str(e)}"}
    except ValueError as e:
        logger.error(f"Command '{command_key}' has invalid syntax: {e}", exc_info=True)
        return {"success": False, "output": f"Invalid command syntax: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error executing command '{command_key}': {e}", exc_info=True)
        return {"success": False, "output": str(e)}


def _execute_linux_command(command_key: str, cmd: str, wait: bool, shell_features: bool) -> dict:
    """
    Execute a command on Linux platform.

    Args:
        command_key: Command identifier for logging
        cmd: Command string to execute
        wait: Whether to wait for command completion
        shell_features: Whether shell features are enabled

    Returns:
        Dictionary with success status and output

    Security strategy:
        - For wait=False (GUI apps): Use list form, no shell
        - For wait=True with shell_features: Use shell with validation
        - For wait=True without shell_features: Use list form, no shell
    """
    env = get_linux_gui_env()

    if wait:
        # Script execution - capture output
        if shell_features:
            # Shell features required (pipes, redirects, etc.)
            # Already validated by validate_command_safe()
            logger.info(f"Executing '{command_key}' with shell features")
            result = subprocess.run(
                cmd,
                env=env,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30  # Add timeout for safety
            )
        else:
            # Safe execution without shell
            cmd_list = safe_split_command(cmd)
            logger.info(f"Executing '{command_key}' without shell: {cmd_list}")
            result = subprocess.run(
                cmd_list,
                env=env,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30  # Add timeout for safety
            )

        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip() if result.stdout else result.stderr.strip()
        }

    else:
        # GUI application launch - no output capture
        # Always use list form without shell for security
        cmd_list = safe_split_command(cmd)
        logger.info(f"Launching GUI app '{command_key}': {cmd_list}")

        proc = subprocess.Popen(
            cmd_list,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Verify the process started
        time.sleep(1)
        if proc.poll() is not None:
            logger.error(f"Command '{command_key}' failed to start (exit code: {proc.returncode})")
            return {"success": False, "output": f"Command '{command_key}' failed to start."}

        return {"success": True, "output": f"Command '{command_key}' launched."}


def _execute_windows_command(command_key: str, cmd: str, wait: bool, shell_features: bool) -> dict:
    """
    Execute a command on Windows platform.

    Windows-specific considerations:
    - PATH resolution for .exe, .bat, .cmd files
    - Different quoting and escaping rules
    - GUI applications need special handling

    Args:
        command_key: Command identifier for logging
        cmd: Command string to execute
        wait: Whether to wait for command completion
        shell_features: Whether shell features are enabled

    Returns:
        Dictionary with success status and output

    Security strategy:
        - For wait=True with shell_features: Use shell with validation
        - For wait=True without shell_features: Use list form when possible
        - For wait=False: Try list form first, fall back to shell if needed
    """
    if wait:
        # Script execution - capture output
        if shell_features:
            # Shell features required (pipes, redirects, etc.)
            # Already validated by validate_command_safe()
            logger.info(f"Executing '{command_key}' with shell features (Windows)")
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30  # Add timeout for safety
            )
        else:
            # Try to execute without shell
            try:
                cmd_list = safe_split_command(cmd)
                logger.info(f"Executing '{command_key}' without shell (Windows): {cmd_list}")
                result = subprocess.run(
                    cmd_list,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=30  # Add timeout for safety
                )
            except (OSError, FileNotFoundError) as e:
                # Fall back to shell if direct execution fails (for .bat, PATH issues, etc.)
                logger.info(f"Direct execution failed, retrying with shell: {e}")
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip() if result.stdout else result.stderr.strip()
        }

    else:
        # GUI application launch - no output capture
        # On Windows, try list form first, fall back to shell if needed
        try:
            cmd_list = safe_split_command(cmd)
            logger.info(f"Launching GUI app '{command_key}' (Windows): {cmd_list}")
            subprocess.Popen(
                cmd_list,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except (OSError, FileNotFoundError) as e:
            # Fall back to shell for .bat files, PATH resolution, etc.
            logger.info(f"Direct launch failed, using shell (Windows): {e}")
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        return {"success": True, "output": f"Command '{command_key}' launched (Windows)."}
