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
STDLIB_MODULES = {
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
    "graphlib",
    "zoneinfo",
    "tomllib",
}


def detect_local_modules(base_dir: Path) -> Set[str]:
    """Detect all local modules and submodules inside the project."""
    local = set()

    # Detect top-level packages
    for path in base_dir.iterdir():
        if path.is_dir() and (path / "__init__.py").exists():
            local.add(path.name)

    # Detect ANYTHING inside modules/*
    modules_dir = base_dir / "modules"
    if modules_dir.exists():
        for py_file in modules_dir.rglob("*.py"):
            # Example: modules/media/playtime/utils.py → "media"
            rel = py_file.relative_to(modules_dir)
            top = rel.parts[0]
            local.add(top)

    return local


def get_imports_from_file(filepath: Path) -> Set[str]:
    """Extract all import statements from a Python file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {filepath}: {e}", file=sys.stderr)
        return set()

    imports = set()

    for node in ast.walk(tree):
        # import foo / import foo.bar
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])

        # from foo import bar
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    return imports


def get_all_project_imports(base_dir: Path) -> Set[str]:
    """Get all imported top-level module names in the project."""
    all_imports = set()

    # main.py
    main_file = base_dir / "main.py"
    if main_file.exists():
        all_imports.update(get_imports_from_file(main_file))

    # modules/*
    modules_dir = base_dir / "modules"
    if modules_dir.exists():
        for py_file in modules_dir.rglob("*.py"):
            all_imports.update(get_imports_from_file(py_file))

    return all_imports


def get_requirements_packages(requirements_dir: Path) -> Set[str]:
    """Get package names declared in all requirements/*.txt files."""
    packages = set()

    if not requirements_dir.exists():
        print(
            f"Warning: Requirements directory not found: {requirements_dir}",
            file=sys.stderr,
        )
        return packages

    for req_file in requirements_dir.glob("*.txt"):
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("-r "):
                        continue

                    # Extract package name before version specifiers
                    pkg = (
                        line.split(">=")[0]
                        .split("==")[0]
                        .split("<")[0]
                        .split(">")[0]
                        .split("[")[0]
                        .strip()
                    )

                    if pkg:
                        packages.add(pkg.lower())
        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {req_file}: {e}", file=sys.stderr)

    return packages


def normalize_package_name(name: str) -> str:
    """Normalize import names to their PyPI package names."""
    mappings = {
        "PIL": "pillow",
        "cv2": "opencv-python",
        "sklearn": "scikit-learn",
        "yaml": "pyyaml",
    }

    if name in mappings:
        return mappings[name].lower()

    return name.lower()


def main() -> int:
    base_dir = Path.cwd()
    requirements_dir = base_dir / "requirements"

    print("Checking for missing requirements...")

    # Local modules detected dynamically
    local_modules = detect_local_modules(base_dir)

    # All imports detected from project
    all_imports = get_all_project_imports(base_dir)

    # Third-party = all imports minus stdlib and local modules
    third_party_imports = {
        pkg
        for pkg in all_imports
        if pkg not in STDLIB_MODULES and pkg not in local_modules
    }

    # Requirements from files
    declared_packages = {
        normalize_package_name(pkg) for pkg in get_requirements_packages(requirements_dir)
    }

    normalized_imports = {normalize_package_name(pkg) for pkg in third_party_imports}

    missing = normalized_imports - declared_packages

    if missing:
        print("\n❌ FAILED: The following packages are imported but NOT in requirements:")
        for pkg in sorted(missing):
            print(f"  - {pkg}")
        print("\nAdd missing packages to the appropriate requirements/*.txt file.")
        return 1

    print("✅ PASSED: All imports are accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
