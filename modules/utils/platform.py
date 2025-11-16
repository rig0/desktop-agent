"""Platform detection and platform-specific operations.

This module centralizes all platform-specific logic, making it easier
to support multiple operating systems and handle platform differences.
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)


class PlatformUtils:
    """Utilities for platform detection and platform-specific operations.

    This class provides a clean interface for handling differences between
    Linux and Windows platforms, particularly for system information that
    requires platform-specific collection methods.

    Attributes:
        _platform: Cached platform name ("linux", "windows", or "unknown").
        _os_version: Cached OS version string.
        _cpu_model: Cached CPU model string.

    Example:
        >>> utils = PlatformUtils()
        >>> if utils.is_linux():
        ...     cpu_model = utils.get_cpu_model()
        >>> print(f"Running on {utils.get_platform()}")
    """

    def __init__(self):
        """Initialize platform utilities with empty cache."""
        self._platform: Optional[str] = None
        self._os_version: Optional[str] = None
        self._cpu_model: Optional[str] = None

    def get_platform(self) -> str:
        """Get the current platform.

        Determines the operating system platform and caches the result.

        Returns:
            Platform name: "linux", "windows", or "unknown".

        Example:
            >>> utils = PlatformUtils()
            >>> utils.get_platform()
            'linux'
        """
        if self._platform is None:
            if sys.platform.startswith("linux"):
                self._platform = "linux"
            elif sys.platform.startswith("win"):
                self._platform = "windows"
            else:
                self._platform = "unknown"
                logger.warning(f"Unknown platform: {sys.platform}")
        return self._platform

    def is_linux(self) -> bool:
        """Check if running on Linux.

        Returns:
            True if running on Linux, False otherwise.

        Example:
            >>> utils = PlatformUtils()
            >>> if utils.is_linux():
            ...     print("Linux-specific code")
        """
        return self.get_platform() == "linux"

    def is_windows(self) -> bool:
        """Check if running on Windows.

        Returns:
            True if running on Windows, False otherwise.

        Example:
            >>> utils = PlatformUtils()
            >>> if utils.is_windows():
            ...     print("Windows-specific code")
        """
        return self.get_platform() == "windows"

    def get_os_version(self) -> str:
        """Get OS version string.

        Retrieves a human-readable OS version string appropriate for the
        current platform. On Linux, attempts to read from /etc/os-release
        first, then falls back to platform.release().

        Returns:
            OS version string (e.g., "Ubuntu 22.04", "Windows 10").

        Example:
            >>> utils = PlatformUtils()
            >>> utils.get_os_version()
            'Ubuntu 22.04'
        """
        if self._os_version is not None:
            return self._os_version

        try:
            if self.is_linux():
                # Try to read from /etc/os-release for better formatting
                if os.path.exists("/etc/os-release"):
                    try:
                        with open("/etc/os-release", encoding="utf-8") as f:
                            data = {}
                            for line in f:
                                if "=" in line:
                                    key, value = line.strip().split("=", 1)
                                    data[key] = value.strip('"')

                            # Prefer PRETTY_NAME, fall back to NAME + VERSION_ID
                            if "PRETTY_NAME" in data:
                                self._os_version = data["PRETTY_NAME"]
                            else:
                                distro_name = data.get("NAME", "Linux")
                                distro_version = data.get("VERSION_ID", "")
                                self._os_version = (
                                    f"{distro_name} {distro_version}".strip()
                                )

                            return self._os_version
                    except (IOError, OSError, ValueError) as e:
                        logger.debug(f"Could not read /etc/os-release: {e}")

                # Fallback to platform.release()
                self._os_version = f"Linux {platform.release()}"

            elif self.is_windows():
                # Windows version from platform
                self._os_version = f"Windows {platform.release()}"

            else:
                # Unknown platform fallback
                self._os_version = f"{platform.system()} {platform.release()}"

        except Exception as e:
            logger.warning(f"Could not determine OS version: {e}")
            self._os_version = "Unknown"

        return self._os_version

    def get_cpu_model(self) -> str:
        """Get CPU model name (platform-specific).

        Retrieves the CPU model name using platform-specific methods:
        - Windows: Uses wmic or Windows Registry
        - Linux: Reads from /proc/cpuinfo
        - Other: Uses platform.processor()

        Returns:
            CPU model string (e.g., "Intel Core i7-9700K").

        Example:
            >>> utils = PlatformUtils()
            >>> utils.get_cpu_model()
            'Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz'
        """
        if self._cpu_model is not None:
            return self._cpu_model

        try:
            if self.is_windows():
                # Try wmic first (if available)
                if shutil.which("wmic"):
                    try:
                        output = subprocess.check_output(
                            "wmic cpu get Name", shell=True, timeout=5
                        )
                        lines = [
                            line.strip()
                            for line in output.decode().splitlines()
                            if line.strip()
                        ]
                        if len(lines) >= 2:
                            self._cpu_model = lines[1]
                            return self._cpu_model
                    except (
                        subprocess.CalledProcessError,
                        subprocess.TimeoutExpired,
                        OSError,
                        UnicodeDecodeError,
                    ) as e:
                        logger.debug(f"Error getting CPU model via wmic: {e}")

                # Fallback to Windows Registry
                try:
                    import winreg

                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                    )
                    cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                    winreg.CloseKey(key)
                    self._cpu_model = cpu_name
                    return self._cpu_model
                except (ImportError, OSError) as e:
                    logger.debug(f"Error getting CPU model from registry: {e}")

                # Final fallback for Windows
                self._cpu_model = platform.processor() or "Unknown CPU"

            elif self.is_linux():
                # Read from /proc/cpuinfo
                try:
                    with open("/proc/cpuinfo", encoding="utf-8") as f:
                        for line in f:
                            if "model name" in line:
                                self._cpu_model = line.split(":", 1)[1].strip()
                                return self._cpu_model
                except (IOError, OSError) as e:
                    logger.debug(f"Could not read /proc/cpuinfo: {e}")

                # Fallback for Linux
                self._cpu_model = platform.processor() or "Unknown CPU"

            else:
                # Unknown platform
                self._cpu_model = platform.processor() or "Unknown CPU"

        except Exception as e:
            logger.warning(f"Could not determine CPU model: {e}")
            self._cpu_model = "Unknown CPU"

        return self._cpu_model
