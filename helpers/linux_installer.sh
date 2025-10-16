#!/usr/bin/env bash
set -e

echo "=== Desktop Agent dependency installer ==="

# Default: don’t install GPU extras
INSTALL_AMD=false
INSTALL_INTEL=false

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-amd) INSTALL_AMD=true ;;
    --with-intel) INSTALL_INTEL=true ;;
    --with-all-gpus) INSTALL_AMD=true; INSTALL_INTEL=true ;;
    -h|--help)
      echo "Usage: $0 [--with-amd] [--with-intel] [--with-all-gpus]"
      exit 0
      ;;
  esac
  shift
done

# Detect OS
if [ -f /etc/debian_version ]; then
    DISTRO="debian"
    PKG_MANAGER="apt"
elif [ -f /etc/fedora-release ]; then
    DISTRO="fedora"
    if command -v rpm-ostree >/dev/null 2>&1; then
        IMMUTABLE=true
    else
        IMMUTABLE=false
    fi
else
    echo "Unsupported distro. Please install dependencies manually."
    exit 1
fi

echo "Detected distro: $DISTRO"
$IMMUTABLE && echo "⚠️ Immutable OS detected: $DISTRO"

# Base packages
if [ "$DISTRO" = "debian" ]; then
    BASE_PKGS="
    python3 python3-pip python3-venv python3-dev
    build-essential pkg-config
    libffi-dev libssl-dev zlib1g-dev
    libxml2-dev libxslt1-dev
    libpq-dev curl
    "
elif [ "$DISTRO" = "fedora" ]; then
    BASE_PKGS="
    python3 python3-pip python3-virtualenv python3-devel
    gcc gcc-c++ make pkg-config
    libffi-devel openssl-devel zlib-devel
    libxml2-devel libxslt-devel
    libpq-devel curl
    "
fi

# Optional GPU packages
GPU_PKGS=""
$INSTALL_AMD && GPU_PKGS="$GPU_PKGS radeontop"
$INSTALL_INTEL && GPU_PKGS="$GPU_PKGS intel-gpu-tools"

# Install dependencies
if [ "$DISTRO" = "debian" ]; then
    sudo apt update
    sudo apt install -y $BASE_PKGS $GPU_PKGS
elif [ "$DISTRO" = "fedora" ]; then
    if [ "$IMMUTABLE" = true ]; then
        echo "⚠️ Immutable Fedora detected. You can layer packages with rpm-ostree or use toolbox."
        echo "It's recommended to layer the packages. Running in a toolbox requires some workarounds."
        read -p "Do you want to layer packages into the system? (Y/n): " choice
        if [[ "$choice" =~ ^[Nn]$ ]]; then
            echo "Skipping layering. Use toolbox for installation instead."
            echo "Example:"
            echo "  toolbox create desktop-agent"
            echo "  toolbox enter desktop-agent"
            echo "  sudo dnf install -y $BASE_PKGS"
            $INSTALL_AMD && echo "  sudo dnf install -y radeontop"
            $INSTALL_INTEL && echo "  sudo dnf install -y intel-gpu-tools"
        else
            sudo rpm-ostree install $BASE_PKGS $GPU_PKGS
            echo "Reboot required to apply changes."
        fi
    else
        sudo dnf install -y $BASE_PKGS $GPU_PKGS
    fi
fi

echo "✅ All dependencies installed."
