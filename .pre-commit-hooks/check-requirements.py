#!/usr/bin/env python3
"""Pre-commit hook to check for missing requirements in requirements files.

This hook scans Python source files for import statements and verifies that
all imported third-party packages are listed in requirements files.

Exit Codes:
    0: All imports are accounted for
    1: Missing requirements detected

Usage:
    Called automatically by pre-commit framework, or manually:
    python .pre-commit-hooks/check-requirements.py
"""

import ast
import sys
from pathlib import Path
from typing import Set

# Standard library modules to exclude from requirement checks
# These are built-in to Python and don't need to be in requirements.txt
STDLIB_MODULES = {
    # Built-in modules
    "abc",
    "argparse",
    "array",
    "ast",
    "asyncio",
    "base64",
    "binascii",
    "bisect",
    "builtins",
    "bz2",
    "calendar",
    "cgi",
    "cgitb",
    "chunk",
    "cmath",
    "cmd",
    "code",
    "codecs",
    "codeop",
    "collections",
    "colorsys",
    "compileall",
    "concurrent",
    "configparser",
    "contextlib",
    "contextvars",
    "copy",
    "copyreg",
    "crypt",
    "csv",
    "ctypes",
    "curses",
    "dataclasses",
    "datetime",
    "dbm",
    "decimal",
    "difflib",
    "dis",
    "distutils",
    "doctest",
    "email",
    "encodings",
    "enum",
    "errno",
    "faulthandler",
    "fcntl",
    "filecmp",
    "fileinput",
    "fnmatch",
    "formatter",
    "fractions",
    "ftplib",
    "functools",
    "gc",
    "getopt",
    "getpass",
    "gettext",
    "glob",
    "graphlib",
    "grp",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html",
    "http",
    "imaplib",
    "imghdr",
    "imp",
    "importlib",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "keyword",
    "lib2to3",
    "linecache",
    "locale",
    "logging",
    "lzma",
    "mailbox",
    "mailcap",
    "marshal",
    "math",
    "mimetypes",
    "mmap",
    "modulefinder",
    "multiprocessing",
    "netrc",
    "nis",
    "nntplib",
    "numbers",
    "operator",
    "optparse",
    "os",
    "ossaudiodev",
    "parser",
    "pathlib",
    "pdb",
    "pickle",
    "pickletools",
    "pipes",
    "pkgutil",
    "platform",
    "plistlib",
    "poplib",
    "posix",
    "posixpath",
    "pprint",
    "profile",
    "pstats",
    "pty",
    "pwd",
    "py_compile",
    "pyclbr",
    "pydoc",
    "queue",
    "quopri",
    "random",
    "re",
    "readline",
    "reprlib",
    "resource",
    "rlcompleter",
    "runpy",
    "sched",
    "secrets",
    "select",
    "selectors",
    "shelve",
    "shlex",
    "shutil",
    "signal",
    "site",
    "smtpd",
    "smtplib",
    "sndhdr",
    "socket",
    "socketserver",
    "spwd",
    "sqlite3",
    "ssl",
    "stat",
    "statistics",
    "string",
    "stringprep",
    "struct",
    "subprocess",
    "sunau",
    "symtable",
    "sys",
    "sysconfig",
    "syslog",
    "tabnanny",
    "tarfile",
    "telnetlib",
    "tempfile",
    "termios",
    "test",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "tkinter",
    "token",
    "tokenize",
    "trace",
    "traceback",
    "tracemalloc",
    "tty",
    "turtle",
    "types",
    "typing",
    "unicodedata",
    "unittest",
    "urllib",
    "uu",
    "uuid",
    "venv",
    "warnings",
    "wave",
    "weakref",
    "webbrowser",
    "winreg",
    "winsound",
    "wsgiref",
    "xdrlib",
    "xml",
    "xmlrpc",
    "zipapp",
    "zipfile",
    "zipimport",
    "zlib",
    # Python 3.9+ additions
    "graphlib",
    "zoneinfo",
    # Python 3.10+ additions
    "tomllib",
}

# Local project modules to exclude
LOCAL_MODULES = {
    "modules",
    "helpers",
}


def get_imports_from_file(filepath: Path) -> Set[str]:
    """Extract all import statements from a Python file.

    Args:
        filepath: Path to Python file

    Returns:
        Set of top-level package names imported

    Example:
        >>> get_imports_from_file(Path("test.py"))
        {'flask', 'pytest', 'requests'}
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {filepath}: {e}", file=sys.stderr)
        return set()

    imports = set()

    for node in ast.walk(tree):
        # Handle "import module" and "import module.submodule"
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Extract top-level package name
                package = alias.name.split(".")[0]
                imports.add(package)

        # Handle "from module import something"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Extract top-level package name
                package = node.module.split(".")[0]
                imports.add(package)

    return imports


def get_all_project_imports(base_dir: Path) -> Set[str]:
    """Get all third-party imports used in the project.

    Args:
        base_dir: Project root directory

    Returns:
        Set of third-party package names

    Example:
        >>> get_all_project_imports(Path("."))
        {'flask', 'pytest', 'requests', 'psutil'}
    """
    all_imports = set()

    # Scan main.py
    main_file = base_dir / "main.py"
    if main_file.exists():
        all_imports.update(get_imports_from_file(main_file))

    # Scan modules directory
    modules_dir = base_dir / "modules"
    if modules_dir.exists():
        for py_file in modules_dir.rglob("*.py"):
            all_imports.update(get_imports_from_file(py_file))

    # Filter out standard library and local modules
    third_party = all_imports - STDLIB_MODULES - LOCAL_MODULES

    return third_party


def get_requirements_packages(requirements_dir: Path) -> Set[str]:
    """Parse all requirements files to get declared packages.

    Args:
        requirements_dir: Directory containing requirements files

    Returns:
        Set of package names from requirements

    Example:
        >>> get_requirements_packages(Path("requirements"))
        {'flask', 'pytest', 'requests'}
    """
    packages = set()

    if not requirements_dir.exists():
        print(
            f"Warning: Requirements directory not found: {requirements_dir}",
            file=sys.stderr,
        )
        return packages

    # Read all .txt files in requirements directory
    for req_file in requirements_dir.glob("*.txt"):
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Skip -r includes (those are handled by reading all files)
                    if line.startswith("-r "):
                        continue

                    # Extract package name (before version specifiers)
                    # Handle: package>=1.0.0, package==1.0.0, package, package[extra]>=1.0
                    package = (
                        line.split(">=")[0]
                        .split("==")[0]
                        .split("<")[0]
                        .split(">")[0]
                        .split("[")[0]
                        .strip()
                    )

                    if package:
                        # Convert package name to lowercase for comparison
                        # (pip is case-insensitive for package names)
                        packages.add(package.lower())

        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {req_file}: {e}", file=sys.stderr)

    return packages


def normalize_package_name(name: str) -> str:
    """Normalize package name for comparison.

    PyPI package names often differ from import names:
    - paho-mqtt (package) -> paho.mqtt (import)
    - scikit-learn (package) -> sklearn (import)
    - Pillow (package) -> PIL (import)

    Args:
        name: Package or import name

    Returns:
        Normalized name for comparison
    """
    # Common mappings from import name to package name
    import_to_package = {
        "PIL": "pillow",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "yaml": "pyyaml",
    }

    # Check if it's a known mapping
    if name in import_to_package:
        return import_to_package[name].lower()

    # Default: just lowercase it
    return name.lower()


def main() -> int:
    """Main function to check for missing requirements.

    Returns:
        0 if all requirements are satisfied, 1 otherwise
    """
    base_dir = Path.cwd()
    requirements_dir = base_dir / "requirements"

    print("Checking for missing requirements...")

    # Get all third-party imports used in code
    project_imports = get_all_project_imports(base_dir)

    # Get all packages declared in requirements
    requirements_packages = get_requirements_packages(requirements_dir)

    # Normalize both sets for comparison
    normalized_imports = {normalize_package_name(pkg) for pkg in project_imports}
    normalized_requirements = {
        normalize_package_name(pkg) for pkg in requirements_packages
    }

    # Find missing packages
    missing = normalized_imports - normalized_requirements

    if missing:
        print(
            "\n❌ FAILED: The following packages are imported but not in requirements files:"
        )
        for package in sorted(missing):
            print(f"  - {package}")
        print("\nPlease add these packages to the appropriate requirements file:")
        print("  - Base dependencies: requirements/base.txt")
        print("  - Platform-specific: requirements/linux.txt or requirements/windows.txt")
        print("  - Development/testing: requirements/test.txt")
        return 1

    print("✅ PASSED: All imports are accounted for in requirements files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
