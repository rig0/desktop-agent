# ----------------------------
# Desktop Agent Config Setup
# ----------------------------

Write-Host "=== Desktop Agent Config Setup ==="

$CONFIG_DIR = "..\data"
$CONFIG_FILE = Join-Path $CONFIG_DIR "config.ini"

if (-not (Test-Path $CONFIG_DIR)) { New-Item -ItemType Directory -Path $CONFIG_DIR | Out-Null }

# Device section
$DEFAULT_DEVICE_NAME = $env:COMPUTERNAME
$DEVICE_NAME = Read-Host "Device name [$DEFAULT_DEVICE_NAME]"
if ([string]::IsNullOrWhiteSpace($DEVICE_NAME)) { $DEVICE_NAME = $DEFAULT_DEVICE_NAME }
$DEVICE_NAME = $DEVICE_NAME.Trim()

$UPDATE_INTERVAL = Read-Host "Update interval in seconds [15]"
if ([string]::IsNullOrWhiteSpace($UPDATE_INTERVAL)) { $UPDATE_INTERVAL = 15 }
$UPDATE_INTERVAL = $UPDATE_INTERVAL.Trim()

# MQTT section (mandatory)
do {
    $MQTT_BROKER = Read-Host "MQTT broker IP/hostname"
    $MQTT_BROKER = $MQTT_BROKER.Trim()
} while ([string]::IsNullOrWhiteSpace($MQTT_BROKER))

do {
    $MQTT_PORT = Read-Host "MQTT port [1883]"
    if ([string]::IsNullOrWhiteSpace($MQTT_PORT)) { $MQTT_PORT = 1883 }
} while (-not ($MQTT_PORT -as [int] -and $MQTT_PORT -gt 0))

do {
    $MQTT_USER = Read-Host "MQTT username"
    $MQTT_USER = $MQTT_USER.Trim()
} while ([string]::IsNullOrWhiteSpace($MQTT_USER))

do {
    $MQTT_PASS = Read-Host "MQTT password"
    $MQTT_PASS = $MQTT_PASS.Trim()
} while ([string]::IsNullOrWhiteSpace($MQTT_PASS))

# Modules section
$API_CHOICE = Read-Host "Enable API module? [y/N]"
$API_CHOICE = ($API_CHOICE.Trim()).ToLower()
if ($API_CHOICE -eq "y") {
    $API_ENABLED = $true
    $API_PORT = Read-Host "Override API port? [default 5555]"
    if ([string]::IsNullOrWhiteSpace($API_PORT)) { $API_PORT = 5555 }
} else {
    $API_ENABLED = $false
    $API_PORT = 5555
}

$UPDATES_CHOICE = Read-Host "Enable updates module? [y/N]"
$UPDATES_CHOICE = ($UPDATES_CHOICE.Trim()).ToLower()
if ($UPDATES_CHOICE -eq "y") {
    $UPDATES_ENABLED = $true
    $UPDATES_HOURS = Read-Host "Update interval in hours [default 1h]"
    if ([string]::IsNullOrWhiteSpace($UPDATES_HOURS)) { $UPDATES_HOURS = 1 }
    $UPDATES_INTERVAL = [int]$UPDATES_HOURS * 3600
} else {
    $UPDATES_ENABLED = $false
    $UPDATES_INTERVAL = 3600
}

$MEDIA_CHOICE = Read-Host "Enable media agent module? [y/N]"
$MEDIA_CHOICE = ($MEDIA_CHOICE.Trim()).ToLower()
$MEDIA_ENABLED = $MEDIA_CHOICE -eq "y"

$GAME_CHOICE = Read-Host "Enable game agent module? [y/N]"
$GAME_CHOICE = ($GAME_CHOICE.Trim()).ToLower()
if ($GAME_CHOICE -eq "y") {
    $GAME_ENABLED = $true
    Write-Host ""
    Write-Host "To use the IGDB API, you need a client ID and access token."
    Write-Host "Read more: https://api-docs.igdb.com/#authentication"
    Write-Host "Reminder: access token, not client secret!"
    $IGDB_CLIENT_ID = Read-Host "IGDB Client ID"
    $IGDB_CLIENT_ID = $IGDB_CLIENT_ID.Trim()
    $IGDB_TOKEN = Read-Host "IGDB Access Token"
    $IGDB_TOKEN = $IGDB_TOKEN.Trim()
} else {
    $GAME_ENABLED = $false
    $IGDB_CLIENT_ID = "None"
    $IGDB_TOKEN = "None"
}

# Write config.ini
@"
[device]
name = $DEVICE_NAME
interval = $UPDATE_INTERVAL

[mqtt]
broker = $MQTT_BROKER
port = $MQTT_PORT
username = $MQTT_USER
password = $MQTT_PASS

[modules]
api = $API_ENABLED
updates = $UPDATES_ENABLED
media_agent = $MEDIA_ENABLED
game_agent = $GAME_ENABLED

[api]
port = $API_PORT

[updates]
interval = $UPDATES_INTERVAL

[igdb]
client_id = $IGDB_CLIENT_ID
token = $IGDB_TOKEN
"@ | Set-Content -Path $CONFIG_FILE -Encoding UTF8

Write-Host "✅ Config file written to $CONFIG_FILE"


# ----------------------------
# Python Dependencies
# ----------------------------

Write-Host "=== Desktop Agent Python dependency installer ==="

# Change to parent directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location (Join-Path $ScriptDir "..")

# ----------------------------
# Disable Microsoft Store Python Aliases (Alternative)
# ----------------------------
Write-Host "=== Checking Python installation ==="

$aliasDir = "$env:LOCALAPPDATA\Microsoft\WindowsApps"
$aliasPython = Join-Path $aliasDir "python.exe"
$aliasPython3 = Join-Path $aliasDir "python3.exe"

$aliasFound = $false

if (Test-Path $aliasPython) {
    Write-Host "Microsoft Store python.exe alias detected."
    $aliasFound = $true
    Rename-Item -Path $aliasPython -NewName "python_disabled.exe" -ErrorAction SilentlyContinue
}

if (Test-Path $aliasPython3) {
    Write-Host "Microsoft Store python3.exe alias detected."
    $aliasFound = $true
    Rename-Item -Path $aliasPython3 -NewName "python3_disabled.exe" -ErrorAction SilentlyContinue
}

if (-not $aliasFound) {
    Write-Host "No Microsoft Store Python aliases found."
} else {
    Write-Host "Aliases detected. Make sure real Python is installed and in PATH."
}

# ----------------------------
# Locate or Install Python
# ----------------------------
$pythonPaths = @(
    (Get-Command python -ErrorAction SilentlyContinue).Source,
    (Get-Command python3 -ErrorAction SilentlyContinue).Source,
    "$env:ProgramFiles\Python311\python.exe",
    "$env:ProgramFiles\Python312\python.exe",
    "$env:ProgramFiles(x86)\Python311\python.exe",
    "$env:ProgramFiles(x86)\Python312\python.exe"
) | Where-Object { $_ -and (Test-Path $_) }

if ($pythonPaths.Count -gt 0) {
    $PythonExe = $pythonPaths[0]
    Write-Host "Found Python at: $PythonExe"
    $env:PATH = (Split-Path $PythonExe) + ";" + $env:PATH
} else {
    Write-Host "Python not found. Installing Python 3.12..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Python via winget..."
        Start-Process -FilePath "winget" -ArgumentList "install", "--id", "Python.Python.3.12", "-e", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements", "--silent" -Wait
    } else {
        Write-Host "winget not available. Downloading Python installer..."
        $pythonInstaller = "$env:TEMP\python-installer.exe"
        $pythonUrl = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe"
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller
        Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0" -Wait
        Remove-Item $pythonInstaller -Force
    }

    # Refresh PATH and verify
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Error "Python installation failed. Please install manually."
        exit 1
    }

    Write-Host "Python successfully installed and added to PATH."
}

# ----------------------------
# Install Python Packages
# ----------------------------
if (-not (Test-Path "requirements-windows.txt")) {
    Write-Error "requirements-windows.txt not found!"
    exit 1
}

Write-Host "Installing Python dependencies..."
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-windows.txt

# ----------------------------
# Optional: Media Agent Dependencies
# ----------------------------
if ($MEDIA_ENABLED) {
    Write-Host "Media Agent enabled. Installing Windows SDK dependencies..."

    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $buildToolsURL = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
        $installerPath = "$env:TEMP\vs_BuildTools.exe"
        Write-Host "Downloading Microsoft Build Tools..."
        Invoke-WebRequest -Uri $buildToolsURL -OutFile $installerPath
        Start-Process -FilePath $installerPath -ArgumentList "--quiet", "--wait", "--norestart", "--add", "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended" -Wait
        Write-Host "Build tools installed successfully."
    } else {
        Write-Host "Build tools already present."
    }

    python -m pip install winsdk
}

# ----------------------------
# Optional: NVIDIA GPU Support
# ----------------------------
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    python -m pip install GPUtil
} else {
    Write-Host "nvidia-smi not found (NVIDIA driver missing or not loaded). Skipping GPUtil."
}

Write-Host "All Python dependencies installed successfully."
