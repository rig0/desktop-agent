#!/usr/bin/env python3
"""Desktop Agent Universal Installer

Autonomously installs Python dependencies for Desktop Agent.
No user interaction required - this is just a dependency installer.

Usage:
    python install.py

Requirements:
    - Python 3.10 or higher
    - pip package manager
    - Internet connection for package downloads

Note:
    This installer only installs Python packages. System packages must be
    installed separately. Configuration happens on first run of main.py.
    See SYSTEM_REQUIREMENTS.md for platform-specific prerequisites.
"""

import platform
import subprocess
import sys
from pathlib import Path


class Installer:
    """Autonomous installer for Desktop Agent Python dependencies."""

    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.requirements_dir = self.base_dir / "requirements"
        self.platform = self._detect_platform()

    def _detect_platform(self) -> str:
        """Detect operating system."""
        system = platform.system().lower()
        if system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        else:
            raise RuntimeError(
                f"Unsupported platform: {system}\n"
                f"Desktop Agent supports Windows and Linux only."
            )

    def _check_python_version(self):
        """Verify Python version meets requirements."""
        version = sys.version_info
        if version < (3, 10):
            raise RuntimeError(
                f"Python 3.10+ required, found {version.major}.{version.minor}\n"
                f"Please upgrade Python: https://www.python.org/downloads/"
            )
        print(
            f"[Installer] Python {version.major}.{version.minor}.{version.micro} detected"
        )

    def _check_pip(self):
        """Verify pip is available."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"[Installer] {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "pip not found. Please install pip:\n" "  python -m ensurepip --upgrade"
            )

    def _get_requirements_file(self) -> Path:
        """Get platform-specific requirements file."""
        req_file = self.requirements_dir / f"{self.platform}.txt"
        if not req_file.exists():
            print(f"[ERROR] Requirements file not found: {req_file}")
            print(f"[ERROR] Expected location: {self.requirements_dir}/")
            print(
                "[ERROR] Please ensure you have the complete Desktop Agent source code."
            )
            raise FileNotFoundError(f"Requirements file not found: {req_file}")
        return req_file

    def _install_requirements(self, req_file: Path):
        """Install Python packages from requirements file."""
        print(f"[Installer] Installing requirements from {req_file.name}...")
        print("[Installer] This may take a few minutes...")

        cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]

        try:
            subprocess.run(cmd, check=True)
            print("[Installer] Requirements installed successfully")
        except subprocess.CalledProcessError as e:
            print("\n[ERROR] Failed to install requirements")
            print("\nPossible causes:")
            print("  1. Missing system dependencies (see SYSTEM_REQUIREMENTS.md)")
            print("  2. Network connection issues")
            print("  3. Insufficient permissions")
            print("\nFor help:")
            print("  - Check SYSTEM_REQUIREMENTS.md in the project root")
            print("  - Visit: https://github.com/rig0/desktop-agent/wiki")
            print("  - Report issues: https://github.com/rig0/desktop-agent/issues")
            raise RuntimeError(f"Failed to install requirements: {e}")

    def _print_next_steps(self):
        """Print post-installation instructions."""
        print("\n" + "=" * 70)
        print("Installation Complete!")
        print("=" * 70)
        print("\nNext Steps:")
        print("1. Run the application: python main.py")
        print("2. On first run, you'll be guided through interactive configuration")
        print("3. See documentation: https://github.com/rig0/desktop-agent/wiki")
        print("\nNote: All configuration happens on first run, not during install.")
        print("=" * 70 + "\n")

    def install(self):
        """Run the installation process."""
        try:
            print("[Installer] Desktop Agent Installer")
            print(f"[Installer] Platform: {self.platform}")

            self._check_python_version()
            self._check_pip()

            req_file = self._get_requirements_file()
            self._install_requirements(req_file)

            self._print_next_steps()
            return 0

        except Exception as e:
            print(f"\n[ERROR] Installation failed: {e}", file=sys.stderr)
            return 1


def main():
    """Entry point - no arguments needed."""
    installer = Installer()
    sys.exit(installer.install())


if __name__ == "__main__":
    main()
