#!/usr/bin/env bash
set -e

echo "=== Desktop Agent dependency installer ==="

# Default: don’t install GPU extras
INSTALL_AMD=false
INSTALL_INTEL=false

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-amd)
      INSTALL_AMD=true
      ;;
    --with-intel)
      INSTALL_INTEL=true
      ;;
    --with-all-gpus)
      INSTALL_AMD=true
      INSTALL_INTEL=true
      ;;
    -h|--help)
      echo "Usage: $0 [--with-amd] [--with-intel] [--with-all-gpus]"
      echo
      echo "  --with-amd       Install AMD GPU tools (radeontop)"
      echo "  --with-intel     Install Intel GPU tools (intel-gpu-tools)"
      echo "  --with-all-gpus  Install both AMD + Intel tools"
      exit 0
      ;;
  esac
  shift
done

# Detect OS family
if [ -f /etc/debian_version ]; then
    DISTRO="debian"
elif [ -f /etc/fedora-release ]; then
    DISTRO="fedora"
elif grep -qi "bazzite" /etc/os-release 2>/dev/null; then
    DISTRO="bazzite"
else
    echo "Unsupported distro. Please install dependencies manually."
    exit 1
fi

echo "Detected distro: $DISTRO"

# Build list of base packages
BASE_PKGS="
python3 python3-pip python3-venv python3-dev
build-essential pkg-config
libffi-dev libssl-dev zlib1g-dev
libxml2-dev libxslt1-dev
libpq-dev curl
"

if [ "$DISTRO" = "debian" ]; then
    GPU_PKGS=""
    $INSTALL_AMD && GPU_PKGS="$GPU_PKGS radeontop"
    $INSTALL_INTEL && GPU_PKGS="$GPU_PKGS intel-gpu-tools"

    sudo apt update
    sudo apt install -y $BASE_PKGS $GPU_PKGS

elif [ "$DISTRO" = "fedora" ]; then
    BASE_PKGS="
    python3 python3-pip python3-virtualenv python3-devel
    gcc gcc-c++ make pkg-config
    libffi-devel openssl-devel zlib-devel
    libxml2-devel libxslt-devel
    libpq-devel curl
    "

    GPU_PKGS=""
    $INSTALL_AMD && GPU_PKGS="$GPU_PKGS radeontop"
    $INSTALL_INTEL && GPU_PKGS="$GPU_PKGS intel-gpu-tools"

    sudo dnf install -y $BASE_PKGS $GPU_PKGS

elif [ "$DISTRO" = "bazzite" ]; then
    echo "⚠️ Bazzite detected (rpm-ostree)."
    echo "You have two options:"
    echo "  1. Layer dependencies into the host (requires reboot)"
    echo "  2. Use toolbox/distrobox (recommended for dev)"
    echo

    read -p "Do you want to layer packages into the system? (y/N): " choice
    if [[ "$choice" =~ ^[Yy]$ ]]; then
        BASE_PKGS="
        python3 python3-pip python3-virtualenv python3-devel
        gcc gcc-c++ make pkg-config
        libffi-devel openssl-devel zlib-devel
        libxml2-devel libxslt-devel
        libpq-devel curl
        "

        GPU_PKGS=""
        $INSTALL_AMD && GPU_PKGS="$GPU_PKGS radeontop"
        $INSTALL_INTEL && GPU_PKGS="$GPU_PKGS intel-gpu-tools"

        sudo rpm-ostree install $BASE_PKGS $GPU_PKGS
        echo "Reboot required to apply changes."
    else
        echo "Skipping rpm-ostree layering. Run this inside a toolbox instead:"
        echo "  toolbox enter"
        echo "  sudo dnf install -y $BASE_PKGS"
        $INSTALL_AMD && echo "  sudo dnf install -y radeontop"
        $INSTALL_INTEL && echo "  sudo dnf install -y intel-gpu-tools"
    fi
fi

echo "✅ All dependencies installed."
