# ----------------------------
# Parse Command Line Arguments
# ----------------------------
param(
    [switch]$Silent,
    [switch]$Help
)

# ----------------------------
# Repository Configuration
# ----------------------------
$REPO_OWNER = "rig0"
$REPO_NAME = "desktop-agent"
$REPO_URL = "https://github.com/$REPO_OWNER/$REPO_NAME"
$REPO_WIKI_URL = "$REPO_URL/wiki/Home"

if ($Help) {
    Write-Host "Desktop Agent Windows Installer"
    Write-Host ""
    Write-Host "Usage: .\windows_installer.ps1 [-Silent] [-Help]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Silent    Non-interactive mode: skip config dialogue and use example config"
    Write-Host "  -Help      Show this help message"
    exit 0
}

# ----------------------------
# Self-Elevate to Administrator
# ----------------------------
function Ensure-Admin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "Elevating to Administrator..."
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "powershell.exe"

        # Preserve command line arguments when elevating
        $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        if ($Silent) {
            $arguments += " -Silent"
        }
        $psi.Arguments = $arguments
        $psi.Verb = "runas"
        try {
            [System.Diagnostics.Process]::Start($psi) | Out-Null
        } catch {
            Write-Error "Elevation cancelled. Administrator privileges are required for this step."
            exit 1
        }
        exit 0
    }
}
Ensure-Admin

# ----------------------------
# Desktop Agent Config Setup
# ----------------------------
Write-Host "`n=== Desktop Agent Setup ===`n" -ForegroundColor Cyan

# Paths
$ScriptPath = Resolve-Path $MyInvocation.MyCommand.Definition
$ScriptRoot = Split-Path -Parent $ScriptPath
$ProjectRoot = Split-Path -Parent $ScriptRoot

# Absolute path to data/config.ini (project_root/data/config.ini)
$CONFIG_DIR  = Join-Path $ProjectRoot "data"
$CONFIG_FILE = Join-Path $CONFIG_DIR "config.ini"
$RES_DIR     = Join-Path $ProjectRoot "resources"
$EXAMPLE_CONFIG = Join-Path $RES_DIR "config_example.ini"

# Ensure data directory exists
if (-not (Test-Path $CONFIG_DIR)) {
    New-Item -ItemType Directory -Path $CONFIG_DIR -Force | Out-Null
}

# In silent mode, skip config dialogue and copy example config
if ($Silent) {
    Write-Host "Silent mode: Copying example config to $CONFIG_FILE"
    Write-Host "Make sure to edit with valid values or app will fail!" -ForegroundColor Yellow

    Copy-Item -Force $EXAMPLE_CONFIG $CONFIG_FILE

    # Set device name to hostname (only in [device] section)
    $SYSTEM_HOSTNAME = $env:COMPUTERNAME
    # Read config as lines
    $lines = Get-Content $CONFIG_FILE
    $inDeviceSection = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match '^\[device\]') {
            $inDeviceSection = $true
            $line
        }
        elseif ($line -match '^\[') {
            $inDeviceSection = $false
            $line
        }
        elseif ($inDeviceSection -and $line -match '^name\s*=') {
            "name = $SYSTEM_HOSTNAME"
        }
        else {
            $line
        }
    }
    $newLines | Set-Content $CONFIG_FILE

    Write-Host "`nConfig file copied successfully." -ForegroundColor Green
    Write-Host "Device name set to: $SYSTEM_HOSTNAME" -ForegroundColor Green
    $CONFIG_SKIPPED = $true
}
else {
    Write-Host "You can configure the app now or manually edit the default config.ini later ($CONFIG_FILE)"
    $CONFIG_CHOICE = Read-Host "Configure now? [Y/n]"
    $CONFIG_CHOICE = ($CONFIG_CHOICE.Trim())
    if ([string]::IsNullOrWhiteSpace($CONFIG_CHOICE)) { $CONFIG_CHOICE = "Y" }

    if ($CONFIG_CHOICE -match '^[Nn]$') {
        $CONFIG_SKIPPED = $true
        Write-Host "`nApp config skipped. Copying example config to $CONFIG_FILE"
        Write-Host "Make sure to edit with valid values or app will fail!" -ForegroundColor Yellow

        Copy-Item -Force $EXAMPLE_CONFIG $CONFIG_FILE

        # Set device name to hostname (only in [device] section)
        $SYSTEM_HOSTNAME = $env:COMPUTERNAME
        # Read config as lines
        $lines = Get-Content $CONFIG_FILE
        $inDeviceSection = $false
        $newLines = foreach ($line in $lines) {
            if ($line -match '^\[device\]') {
                $inDeviceSection = $true
                $line
            }
            elseif ($line -match '^\[') {
                $inDeviceSection = $false
                $line
            }
            elseif ($inDeviceSection -and $line -match '^name\s*=') {
                "name = $SYSTEM_HOSTNAME"
            }
            else {
                $line
            }
        }
        $newLines | Set-Content $CONFIG_FILE

        Write-Host "`nConfig file copied successfully." -ForegroundColor Green
        Write-Host "Device name set to: $SYSTEM_HOSTNAME" -ForegroundColor Green
    }
    else {
    Write-Host "`nCreating config file...`n" -ForegroundColor Cyan

    # Device section
    $DEFAULT_DEVICE_NAME = $env:COMPUTERNAME
    $DEVICE_NAME = Read-Host "Device name [$DEFAULT_DEVICE_NAME]"
    if ([string]::IsNullOrWhiteSpace($DEVICE_NAME)) { $DEVICE_NAME = $DEFAULT_DEVICE_NAME }
    $DEVICE_NAME = $DEVICE_NAME.Trim()

    $UPDATE_INTERVAL = Read-Host "Update interval in seconds [10]"
    if ([string]::IsNullOrWhiteSpace($UPDATE_INTERVAL)) { $UPDATE_INTERVAL = 10 }
    else { $UPDATE_INTERVAL = [int]$UPDATE_INTERVAL }

    # MQTT section (mandatory)
    Write-Host "Enter MQTT settings (mandatory, installer will fail if empty)"
    do {
        $MQTT_BROKER = Read-Host "MQTT broker IP/hostname"
        $MQTT_BROKER = $MQTT_BROKER.Trim()
        if (-not [string]::IsNullOrWhiteSpace($MQTT_BROKER)) { break }
        Write-Host "MQTT broker cannot be empty!" -ForegroundColor Yellow
    } while ($true)

    do {
        $MQTT_PORT = Read-Host "MQTT port [1883]"
        if ([string]::IsNullOrWhiteSpace($MQTT_PORT)) { $MQTT_PORT = 1883 }
        if (($MQTT_PORT -as [int]) -and ($MQTT_PORT -gt 0)) { break }
        Write-Host "MQTT port must be a positive number" -ForegroundColor Yellow
    } while ($true)

    do {
        $MQTT_USER = Read-Host "MQTT username"
        $MQTT_USER = $MQTT_USER.Trim()
        if (-not [string]::IsNullOrWhiteSpace($MQTT_USER)) { break }
        Write-Host "MQTT username cannot be empty!" -ForegroundColor Yellow
    } while ($true)

    do {
        $MQTT_PASS = Read-Host "MQTT password"
        $MQTT_PASS = $MQTT_PASS.Trim()
        if (-not [string]::IsNullOrWhiteSpace($MQTT_PASS)) { break }
        Write-Host "MQTT password cannot be empty!" -ForegroundColor Yellow
    } while ($true)

    # Modules section
    $API_CHOICE = Read-Host "Enable API? [y/N]"
    $API_CHOICE = ($API_CHOICE.Trim()).ToLower()
    if ($API_CHOICE -eq "y") {
        $API_ENABLED = $true
        $API_PORT = Read-Host "Override API port? [default 5555]"
        if ([string]::IsNullOrWhiteSpace($API_PORT)) { $API_PORT = 5555 }
    } else {
        $API_ENABLED = $false
        $API_PORT = 5555
    }

    $COMMANDS_CHOICE = Read-Host "Enable commands? [y/N]"
    $COMMANDS_CHOICE = ($COMMANDS_CHOICE.Trim()).ToLower()
    $COMMANDS_ENABLED = $COMMANDS_CHOICE -eq "y"

    $MEDIA_CHOICE = Read-Host "Enable media agent? [y/N]"
    $MEDIA_CHOICE = ($MEDIA_CHOICE.Trim()).ToLower()
    $MEDIA_ENABLED = $MEDIA_CHOICE -eq "y"

    $GAME_CHOICE = Read-Host "Enable game agent? [y/N]"
    $GAME_CHOICE = ($GAME_CHOICE.Trim()).ToLower()
    if ($GAME_CHOICE -eq "y") {
        $GAME_ENABLED = $true
        Write-Host "`nTo use the IGDB API, you need a client ID and access token."
        Write-Host "Read more: https://api-docs.igdb.com/#authentication"
        Write-Host "Reminder: access token, not client secret!`n"
        $IGDB_CLIENT_ID = Read-Host "IGDB Client ID"
        $IGDB_CLIENT_ID = $IGDB_CLIENT_ID.Trim()
        $IGDB_TOKEN = Read-Host "IGDB Access Token"
        $IGDB_TOKEN = $IGDB_TOKEN.Trim()
    } else {
        $GAME_ENABLED = $false
        $IGDB_CLIENT_ID = "None"
        $IGDB_TOKEN = "None"
    }

    $UPDATES_CHOICE = Read-Host "Enable updates? [y/N]"
    $UPDATES_CHOICE = ($UPDATES_CHOICE.Trim()).ToLower()
    if ($UPDATES_CHOICE -eq "y") {
        $UPDATES_ENABLED = $true
        $UPDATES_HOURS = Read-Host "Update interval in hours [default 1]"
        if ([string]::IsNullOrWhiteSpace($UPDATES_HOURS)) { $UPDATES_HOURS = 1 }
        $UPDATES_INTERVAL = [int]$UPDATES_HOURS * 3600
    } else {
        $UPDATES_ENABLED = $false
        $UPDATES_INTERVAL = 3600
    }

    # Write config.ini
    $content = @"
; ================== DESKTOP AGENT CONFIG ==================
; Documentation: $REPO_WIKI_URL

; Intervals are in seconds. Modules are disabled by default.

; If you enable the game_agent, you need to create a igdb.com account and fill your api credentials.
; Read more https://api-docs.igdb.com/#authentication (Access token, not client secret!)

; Generated by windows_installer.ps1
; ==========================================================

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
commands = $COMMANDS_ENABLED
media_agent = $MEDIA_ENABLED
game_agent = $GAME_ENABLED
updates = $UPDATES_ENABLED

[api]
port = $API_PORT

[updates]
interval = $UPDATES_INTERVAL
channel = beta

[igdb]
client_id = $IGDB_CLIENT_ID
token = $IGDB_TOKEN
"@

        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($CONFIG_FILE, $content, $utf8NoBom)

        Write-Host "`nConfig file written to $CONFIG_FILE`n" -ForegroundColor Green
    }
}


# ----------------------------
# Python Dependencies
# ----------------------------
Write-Host "`n=== Installing python and pip dependencies ===`n" -ForegroundColor Cyan

# Change to parent directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location (Join-Path $ScriptDir "..")

# Disable Microsoft Store Python Aliases
Write-Host "Checking Python installation"

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

$env:PATH = (($env:PATH -split ';') | Where-Object { $_ -notlike '*WindowsApps*' }) -join ';'

if (-not $aliasFound) {
    Write-Host "No Microsoft Store Python aliases found."
} else {
    Write-Host "Aliases detected. Make sure real Python is installed and in PATH."
}

# Locate or Install Python
$pythonPaths = @(
    (Get-Command python -ErrorAction SilentlyContinue).Source,
    (Get-Command python3 -ErrorAction SilentlyContinue).Source,
    "$env:ProgramFiles\Python311\python.exe",
    "$env:ProgramFiles\Python312\python.exe",
    "$env:ProgramFiles(x86)\Python311\python.exe",
    "$env:ProgramFiles(x86)\Python312\python.exe"
) | Where-Object { $_ -and (Test-Path $_) }

if ($pythonPaths.Count -eq 0) {
    Write-Host "`Python not found. Installing Python 3.12..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Start-Process -FilePath "winget" -ArgumentList "install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements --silent" -NoNewWindow -Wait
    } else {
        Write-Host "winget not available. Downloading installer..."
        $pythonInstaller = "$env:TEMP\python-installer.exe"
        $pythonURL = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe"
        #$pythonURL = "https://files.rigslab.com/-dMudDq2xRK/python-3.12.6-amd64.exe"
        Invoke-WebRequest -Uri $pythonURL -OutFile $pythonInstaller
        Write-Host "`Installing python..."
        Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_test=0" -Wait
        Remove-Item $pythonInstaller -Force
    }

    # Refresh PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine")
}

# Verify
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python installation failed. Please install manually."
    exit 1
}

Write-Host "`nPython successfully installed and added to PATH.`n" -ForegroundColor Green


# Install Python Packages
if (-not (Test-Path "requirements-windows.txt")) {
    Write-Error "requirements-windows.txt not found!"
    exit 1
}

Write-Host "Installing Python packages...`n"
python -m ensurepip --upgrade
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-windows.txt

# ----------------------------
# Media Agent Dependencies (obsolete)
# ----------------------------
# if ( ($MEDIA_ENABLED) -or ($CONFIG_SKIPPED) ) {
#     if ($MEDIA_ENABLED) { Write-Host "`nMedia Agent enabled. Installing Windows SDK dependencies..." }
#     if ($CONFIG_SKIPPED) { Write-Host "`nInstalling Windows SDK dependencies for media_agent..." }

#     if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
#         $buildToolsURL = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
#         #$buildToolsURL = "https://files.rigslab.com/-ZLKF9UpEm9/vs_BuildTools.exe"
#         $installerPath = "$env:TEMP\vs_BuildTools.exe"
#         Write-Host "`nDownloading Microsoft Build Tools..."
#         Invoke-WebRequest -Uri $buildToolsURL -OutFile $installerPath
#         Write-Host "`nInstalling Microsoft Build Tools. This could take some time..." -ForegroundColor Yellow
#         Start-Process -FilePath $installerPath -ArgumentList "--quiet", "--wait", "--norestart", "--add", "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended" -Wait
#         Write-Host "`nBuild tools installed successfully.`n" -ForegroundColor Green
#     } else {
#         Write-Host "Build tools already present."
#     }

#     python -m pip install winsdk
# }

Write-Host "`nAll Python dependencies installed successfully.`n" -ForegroundColor Green

Write-Host "-------------------------------------------------" -ForegroundColor DarkGray
Write-Host "-------------------------------------------------`n" -ForegroundColor DarkGray

Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "`nTo run the desktop agent:" 
Write-Host "    cd $ProjectRoot"
Write-Host "    python3 main.py"
Write-Host "`nTo run the media agent:"
Write-Host "    cd $ScriptRoot"
Write-Host "    python3 media_agent.py"
Write-Host "`nInstructions for creating services for the agents can be found here:" -ForegroundColor Yellow
Write-Host "$REPO_WIKI_URL" -ForegroundColor Yellow

if (-not $Silent) {
    Write-Host "`nPress any key to exit..."
    $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
}
else {
    Write-Host "`nInstallation completed in silent mode."
}
