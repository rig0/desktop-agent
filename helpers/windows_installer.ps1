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

Write-Host "=== Desktop Agent python dependency installer ==="

# Change to parent directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location (Join-Path $ScriptDir "..")

# Check python
if (-not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    Write-Error "Python3 is not installed! Aborting."
    exit 1
}

# Check requirements file
if (-not (Test-Path "requirements-windows.txt")) {
    Write-Error "requirements-windows.txt not found!"
    exit 1
}

# Install python packages
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-linux.txt

# Install media agent dependencies
if ($MEDIA_ENABLED) {
    Write-Host "Media Agent enabled. Installing Windows SDK dependencies..."

    # Check if cl.exe (Visual C++ compiler) exists
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $buildToolsURL = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
        $installerPath = "$env:TEMP\vs_BuildTools.exe"

        Write-Host "Downloading Microsoft Build Tools..."
        Invoke-WebRequest -Uri $buildToolsURL -OutFile $installerPath

        Write-Host "Installing minimal C++ build tools silently..."
        Start-Process -FilePath $installerPath -ArgumentList `
          "--quiet", "--wait", "--norestart", `
          "--add", "Microsoft.VisualStudio.Workload.VCTools", `
          "--includeRecommended" `
          -NoNewWindow -Wait

        Write-Host "✅ Build tools installed successfully."
    } else {
        Write-Host "✅ Build tools already present."
    }

    # Install winsdk
    python3 -m pip install winsdk
}


# Check for NVIDIA
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    python3 -m pip install GPUtil
} else {
    Write-Host "❌ nvidia-smi not found (NVIDIA driver missing or not loaded). Skipping GPUtil"
}

Write-Host "✅ Python dependencies installed."
