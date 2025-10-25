# HASS Desktop Agent

A lightweight desktop agent that integrates your PC with [Home Assistant](https://www.home-assistant.io/) using **MQTT**.  
It publishes live system metrics, exposes a simple API, and lets you run custom commands remotely.

***Fully functional on both windows and linux but still under development. Updates may have breaking changes. Documentation is a WIP***

*Consider the current state and [Tagged](https://github.com/rig0/hass-desktop-agent/tags) versions as nightly builds.*

*Stable builds will be found in [Releases](https://github.com/rig0/hass-desktop-agent/releases)*

---

## Features

- **System monitoring**: CPU, memory, and other stats sent to Home Assistant via MQTT.
- **Media agent**: Now playing info. Title, artist, album and thumbnail via MQTT.
- **Home Assistant auto-discovery**: Device and sensors show up automatically if MQTT discovery is enabled.
- **Built-in API**: Fetch system info over HTTP.
- **Custom commands**: Define and trigger your own scripts/commands remotely.
- **Auto Updater**: Optional auto updates

---
# -------- OUTDATED DOCUMENTATION --------
Updated documentation will be released with 1.0

## Requirements

- [Python 3.10+](https://www.python.org/downloads/windows/)  
- An MQTT broker accessible to both your PC and Home Assistant  

   #### Windows Media Agent Specific 

   1. Install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)  
      - During installation, select **"Desktop development with C++"** workload.
   2. Install `winsdk` Python package:
      ```powershell
      pip install winsdk
      ```

   > This ensures the Media Agent can access Windows SMTC sessions and fetch media info.  
   > Without it, media detection will not function, but the Desktop Agent and Updater will still work.

---

## Setup (Windows)

1. **Download / Clone the repo**  
   ```powershell
   git clone https://github.com/rig0/hass-desktop-agent
   cd hass-desktop-agent
   ```

2. **Install Python dependencies**  
   ```powershell
   pip install -r requirements.txt
   ```

3. **Copy configuration files**  
   ```powershell
   copy config/config_example.ini config/config.ini
   copy config/commands_example.json config/commands.json
   ```

4. **Edit `config.ini`**  
   Open `config/config.ini` in Notepad and fill in your MQTT broker info, device name, and API port.

5. **Run the agent**  
   ```powershell
   python desktop_agent.py
   ```

---

## Setup (Linux)
WIP

## Home Assistant Integration

If you have MQTT discovery enabled in Home Assistant, the desktop agent and its sensors will appear automatically.  
Otherwise, you can manually configure MQTT sensors pointing to topics under:

`desktop/<device_name>/`

Key topics used by the agent:
- `desktop/<device_id>/status` — full JSON payload of system info  
- `desktop/<device_id>/availability` — `online` / `offline`  
- `desktop/<device_id>/run` — accepts run commands (MQTT)  
- `desktop/<device_id>/media/*` — media state/attributes/thumbnail (if media agent is running)  

---

## Example `commands.json` (Windows)
```json
{
  "reboot": {
    "cmd": "reboot",
    "wait": false,
    "platforms": ["linux", "win"]
  },
  "shutdown": {
    "cmd": "shutdown",
    "wait": false,
    "platforms": ["linux", "win"]
  },
  "plexamp_linux": {
    "cmd": "flatpak run com.plexamp.Plexamp",
    "wait": false,
    "platforms": ["linux"]
  },
  "plexamp_windows": {
    "cmd": "C:\\Users\\User\\AppData\\Local\\Programs\\Plexamp\\Plexamp.exe",
    "wait": false,
    "platforms": ["win"]
  }
}

```
Shutdown and Reboot commands work with both linux and windows. Custom commands have to specify OS.
---

## API Usage

The desktop agent includes a lightweight HTTP API that exposes system information and allows interaction outside of MQTT.  
The API runs on the port defined in your `config.ini` (default: `5555`).

### Endpoints

- **`GET /status`**  
  Returns a JSON object with live system stats. Example:
  ```json
  {
    "cpu_usage": 12.5,
    "ram_usage": 43.7,
    "uptime": 123456,
    "hostname": "MyPC"
  }
  ```

- **`POST /run`**  
  Execute a pre-defined command from `commands.json`.  
  Example:
  ```bash
  curl -X POST http://localhost:5555/run \
       -H "Content-Type: application/json" \
       -d '{"command": "notepad"}'
  ```

  Response:
  ```json
  {
      "status": "success",
      "message": "Command executed"
  }
  ```

### Example: Fetch system status

```bash
curl http://localhost:5555/status
```

Output:
```json
{
    "cpu_usage": 15.4,
    "ram_usage": 62.1,
    "uptime": 48200,
    "hostname": "workstation"
}
```

---

## Windows Auto-Start Setup

You can use **Task Scheduler** to have the Desktop Agent, Media Agent, and Updater start automatically.  
Keep in mind:

- **Desktop Agent**: Can run **whether the user is logged in or not**.  
- **Media Agent**: Must run **after login** because it interacts with the user session.  
- **Updater**: Can use same settings as media agent.  

---

### 1. Desktop Agent (Fully Background)

1. Open **Task Scheduler** → **Create Task**.
2. Under **General**:
   - Name: `Desktop Agent`
   - Run whether user is logged in or not
3. Under **Triggers**:
   - New → Begin the task: `At log on`
4. Under **Actions**:
   - New → Action: `Start a program`
   - Program/script: `python`
   - Add arguments: `C:\Path\To\desktop_agent.py`
   - Start in: `C:\Path\To\`
5. Save and provide your Windows password if prompted.

---

### 2. Media Agent (User Session Only)

1. Open **Task Scheduler** → **Create Task**.
2. Under **General**:
   - Name: `Media Agent`
   - Run only when user is logged on
3. Under **Triggers**:
   - New → Begin the task: `At log on`
4. Under **Actions**:
   - New → Action: `Start a program`
   - Program/script: `python`
   - Add arguments: `C:\Path\To\media_agent.py`
   - Start in: `C:\Path\To\`
5. Save.

> This ensures it can access the user session and SMTC features.

---

### 3. Updater (Optional)

- You can create a task similar to the Media Agent. Under **Add arguments:** `C:\Path\To\updater.py`

---

### Notes

- Replace `C:\Path\To\` with the actual folder where your scripts reside.  
- Ensure `python` is in your **PATH** or provide the full path, e.g., `C:\Python310\python.exe`.  
- Desktop Agent will run **headless**, Media Agent relies on user session.

---

## License

MIT
