import os, sys, json, time, socket, math, threading, platform, subprocess, psutil, GPUtil, re, glob, getpass
import paho.mqtt.client as mqtt
from flask import Flask, request, jsonify
from pathlib import Path
from common import DEVICE_NAME, MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, \
                   API_PORT, PUBLISH_INTERVAL, device_id, base_topic, discovery_prefix, device_info

# ----------------------------
# System Info Helpers
# ----------------------------
def get_system_info():
    cpu_freq = psutil.cpu_freq()
    virtual_mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net_io = psutil.net_io_counters()
    
    gpu_flat = get_gpu_info_flat()
    temps_flat = get_temperatures_flat()
    
    return {
        "device": DEVICE_NAME,
        "hostname": socket.gethostname(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": get_os_version(),
        "cpu_model": get_cpu_model(),
        "cpu_usage": round(psutil.cpu_percent(interval=0.5)),
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_frequency_mhz": round(cpu_freq.current) if cpu_freq else None,
        "memory_usage": round(virtual_mem.percent),
        "memory_total_gb": round(virtual_mem.total / (1024 ** 3), 1),
        "memory_used_gb": round(virtual_mem.used / (1024 ** 3), 1),
        "disk_usage": round(disk.percent),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "network_sent_bytes": bytes_to_human(net_io.bytes_sent),
        "network_recv_bytes": bytes_to_human(net_io.bytes_recv),
        **gpu_flat,
        **temps_flat
    }

def get_os_version():
    if sys.platform.startswith("linux"):
        try:
            # Try standard library first
            distro_name = ""
            distro_version = ""
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release") as f:
                    data = {}
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            data[k] = v.strip('"')
                    distro_name = data.get("NAME", "Linux")
                    distro_version = data.get("VERSION_ID", "")
            return f"{distro_name} {distro_version}".strip()
        except:
            return platform.version()
    elif sys.platform.startswith("win"):
        return platform.version()
    else:
        return platform.version()


def get_cpu_model():
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.strip().split(":")[1].strip()
        except:
            return "Unknown CPU"
    elif sys.platform.startswith("win"):
        try:
            output = subprocess.check_output("wmic cpu get Name", shell=True).decode()
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if len(lines) >= 2:
                return lines[1]
        except:
            return "Unknown CPU"
    else:
        return platform.processor() or "Unknown CPU"
    
def safe_number(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    return default

def clean_value(val):
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val

def get_gpu_info_flat():
    gpus = GPUtil.getGPUs()
    gpu_info = {}
    for i, gpu in enumerate(gpus):
        prefix = f"gpu{i}_"
        gpu_info[prefix + "name"] = gpu.name or "Unknown"
        gpu_info[prefix + "load_percent"] = round(safe_number(gpu.load * 100 if gpu.load is not None else None, 0))
        gpu_info[prefix + "memory_total_gb"] = round(safe_number(gpu.memoryTotal, 0))
        gpu_info[prefix + "memory_used_gb"] = round(safe_number(gpu.memoryUsed, 0))
        gpu_info[prefix + "temperature_c"] = round(safe_number(gpu.temperature, 0))
    return gpu_info

def get_temperatures_flat():
    temps = {}
    if hasattr(psutil, "sensors_temperatures"):
        raw_temps = psutil.sensors_temperatures()
        for label, entries in raw_temps.items():
            for entry in entries:
                key = f"{label}_{entry.label}" if entry.label else f"{label}"
                temps[key] = clean_value(entry.current)
    return temps

def bytes_to_human(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    step = 1024.0
    i = 0
    while n >= step and i < len(units) - 1:
        n /= step
        i += 1
    return f"{n:.2f} {units[i]}"


# ----------------------------
# System commands
# ----------------------------

# Load commands from JSON
def load_commands(config_path="commands.json"):
    base_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__)
    config_file = Path(base_dir) / config_path
    if not config_file.exists():
        raise FileNotFoundError(f"{config_file} not found.")
    with open(config_file, "r") as f:
        return json.load(f)

ALLOWED_COMMANDS = load_commands()

def get_linux_gui_env():
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    # Ensure our wrapper is found first (move to config,make dynamic and conditional(in container?))
    env["PATH"] = "/var/home/rambo/Apps/Agent/helpers:" + env.get("PATH", "")

    # Detect display server
    if "WAYLAND_DISPLAY" in env:
        env["DISPLAY"] = ":0"  # Still needed for some apps via XWayland
        env["USE_WAYLAND"] = "1"
    else:
        env.setdefault("DISPLAY", ":0")
        env.pop("USE_WAYLAND", None)

    # Detect DBUS session
    for pid_path in glob.glob("/proc/*/environ"):
        try:
            with open(pid_path, "rb") as f:
                data = f.read().decode(errors="ignore")
                m = re.search(r"DBUS_SESSION_BUS_ADDRESS=([^\x00]+)", data)
                if m:
                    env["DBUS_SESSION_BUS_ADDRESS"] = m.group(1)
                    break
        except Exception:
            continue

    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        # Fallback: only use dbus-launch if no session bus found
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={env['XDG_RUNTIME_DIR']}/bus"

    return env


# Reboot / Shutdown handler
def run_system_power_command(action: str) -> dict:
    try:
        platform_name = "linux" if sys.platform.startswith("linux") else "win" if sys.platform.startswith("win") else None
        if not platform_name:
            return {"success": False, "output": f"Unsupported platform: {sys.platform}"}

        if platform_name == "linux":
            if action == "reboot":
                cmd = "systemctl reboot"
            elif action == "shutdown":
                cmd = "systemctl poweroff"
            else:
                return {"success": False, "output": f"Unknown action '{action}'"}

        elif platform_name == "win":
            if action == "reboot":
                cmd = "shutdown /r /t 0"
            elif action == "shutdown":
                cmd = "shutdown /s /t 0"
            else:
                return {"success": False, "output": f"Unknown action '{action}'"}

        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "output": f"{action.capitalize()} command executed."}

    except Exception as e:
        return {"success": False, "output": str(e)}

# Run predefined commands
def run_predefined_command(command_key: str) -> dict:
    if command_key not in ALLOWED_COMMANDS:
        return {"success": False, "output": f"Command '{command_key}' not allowed."}

    entry = ALLOWED_COMMANDS[command_key]
    if isinstance(entry, dict):
        cmd = entry.get("cmd")
        wait = entry.get("wait", True)
        platforms = entry.get("platforms", None)
    else:
        cmd = entry
        wait = True
        platforms = None

    platform_name = "linux" if sys.platform.startswith("linux") else "win" if sys.platform.startswith("win") else None

    if platforms and platform_name not in platforms:
        return {"success": False, "output": f"Command '{command_key}' not available on {platform_name}."}

    # Special commands
    if cmd in ["reboot", "shutdown"]:
        return run_system_power_command(cmd)

    try:
        if platform_name == "linux":
            env = get_linux_gui_env()
            process_cmd = cmd if isinstance(cmd, list) else cmd.split()

            # Prepend dbus-launch if no running DBUS session detected
            if not env.get("USE_WAYLAND") and "unix:path=" in env.get("DBUS_SESSION_BUS_ADDRESS", ""):
                process_cmd = ["dbus-launch"] + process_cmd

            subprocess.Popen(process_cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "output": f"Command '{command_key}' launched (Linux GUI)."}

        elif platform_name == "win":
            if wait:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout.strip() if result.stdout else result.stderr.strip()
                }
            else:
                subprocess.Popen(cmd, shell=True)
                return {"success": True, "output": f"Command '{command_key}' launched (Windows)."}

        else:
            return {"success": False, "output": f"Unsupported platform '{platform_name}'."}

    except Exception as e:
        return {"success": False, "output": str(e)}


# ----------------------------
# Flask API
# ----------------------------
app = Flask(__name__)

@app.route("/status")
def status():
    return jsonify(get_system_info())

@app.route("/run", methods=["POST"])
def run_command():
    data = request.json
    command_key = data.get("command")
    if not command_key:
        return jsonify({"success": False, "output": "No command provided."}), 400
    result = run_predefined_command(command_key)
    return jsonify(result), 200 if result["success"] else 400

# ----------------------------
# MQTT Setup
# ----------------------------
client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    publish_discovery()

def publish_discovery():
    discovery_payloads = {
    # Host Info
    "hostname": {
        "name": "Hostname",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.hostname }}",
        "icon": "mdi:information",
        "unique_id": f"{device_id}_hostname"
    },
    "uptime_seconds": {
        "name": "Uptime",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "s",
        "value_template": "{{ value_json.uptime_seconds }}",
        "icon": "mdi:clock-outline",
        "unique_id": f"{device_id}_uptime"
    },
    "os": {
        "name": "OS",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.os }}",
        "icon": "mdi:desktop-classic",
        "unique_id": f"{device_id}_os"
    },
    "os_release": {
        "name": "OS Release",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.os_release}}",
        "icon": "mdi:information",
        "unique_id": f"{device_id}_os_release"
    },
    "os_version": {
        "name": "OS Version",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.os_version }}",
        "icon": "mdi:information",
        "unique_id": f"{device_id}_os_version"
    },

    # CPU
    "cpu_model": {
        "name": "CPU Model",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.cpu_model }}",
        "icon": "mdi:cpu-64-bit",
        "unique_id": f"{device_id}_cpu_model"
    },
    "cpu_usage": {
        "name": "CPU Usage",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.cpu_usage }}",
        "icon": "mdi:chip",
        "unique_id": f"{device_id}_cpu_usage"
    },
    "cpu_cores": {
        "name": "CPU Cores",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.cpu_cores }}",
        "icon": "mdi:chip",
        "unique_id": f"{device_id}_cpu_cores"
    },
    "cpu_frequency_mhz": {
        "name": "CPU Frequency",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "MHz",
        "value_template": "{{ value_json.cpu_frequency_mhz }}",
        "icon": "mdi:chip",
        "unique_id": f"{device_id}_cpu_frequency"
    },

    # Memory
    "memory_usage": {
        "name": "Memory Usage",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.memory_usage }}",
        "icon": "mdi:memory",
        "unique_id": f"{device_id}_memory_usage"
    },
    "memory_total_gb": {
        "name": "Memory Total",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.memory_total_gb }}",
        "icon": "mdi:memory",
        "unique_id": f"{device_id}_memory_total"
    },
    "memory_used_gb": {
        "name": "Memory Used",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.memory_used_gb }}",
        "icon": "mdi:memory",
        "unique_id": f"{device_id}_memory_used"
    },

    # Disk
    "disk_usage": {
        "name": "Disk Usage",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.disk_usage }}",
        "icon": "mdi:harddisk",
        "unique_id": f"{device_id}_disk_usage"
    },
    "disk_total_gb": {
        "name": "Disk Total",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.disk_total_gb }}",
        "icon": "mdi:harddisk",
        "unique_id": f"{device_id}_disk_total",
    },
    "disk_used_gb": {
        "name": "Disk Used",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.disk_used_gb }}",
        "icon": "mdi:harddisk",
        "unique_id": f"{device_id}_disk_used"
    },

    # Network
    "network_sent_bytes": {
        "name": "Network Sent",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "",
        "value_template": "{{ value_json.network_sent_bytes }}",
        "icon": "mdi:upload-network",
        "unique_id": f"{device_id}_network_sent"
    },
    "network_recv_bytes": {
        "name": "Network Received",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "",
        "value_template": "{{ value_json.network_recv_bytes }}",
        "icon": "mdi:download-network",
        "unique_id": f"{device_id}_network_received"
    }
    }
    
    # Dynamically add all temp sensors
    for key in get_system_info().keys():
        if key in get_temperatures_flat().keys():
            discovery_payloads[key] = {
                "name": f"{key.replace('_', ' ').title()}",
                "state_topic": f"{base_topic}/status",
                "unit_of_measurement": "°C",
                "value_template": f"{{{{ value_json.{key} }}}}",
                "icon": "mdi:thermometer",
                "unique_id": f"{device_id}_{key.lower()}"
            }
            
    # Dynamically add all gpu sensors
    for key in get_system_info().keys():
        if key.startswith("gpu"):
            discovery_payloads[key] = {
                "name": f"{key.replace('_', ' ').title()}",
                "state_topic": f"{base_topic}/status",
                "unit_of_measurement": "°C" if "temperature" in key else "%" if "load" in key else "MB" if "memory" in key else None,
                "value_template": f"{{{{ value_json.{key} }}}}",
                "icon": "mdi:expansion-card",
                "unique_id": f"{device_id}_{key.lower()}"
            }

    for sensor, payload in discovery_payloads.items():
        payload["device"] = device_info
        payload["availability_topic"] = f"{base_topic}/availability"
        topic = f"{discovery_prefix}/sensor/{device_id}/{sensor}/config"
        client.publish(topic, json.dumps(payload), retain=True)
        print(f"Published discovery for {sensor}")


def publish_status():
    while True:
        raw_info = get_system_info()
        cleaned = {k: clean_value(v) for k, v in raw_info.items()}
        status_payload = json.dumps(cleaned)
        client.publish(f"{base_topic}/status", status_payload, retain=True)
        client.publish(f"{base_topic}/availability", "online", retain=True)
        time.sleep(PUBLISH_INTERVAL)

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        command_key = payload.get("command")
        if not command_key:
            print("[MQTT] No command provided")
            return
        result = run_predefined_command(command_key)
        client.publish(f"{base_topic}/run_result", json.dumps(result), qos=1)
    except Exception as e:
        print(f"[MQTT] Error handling run command: {e}")


# ----------------------------
# Main
# ----------------------------
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.on_connect = on_connect
client.connect(MQTT_BROKER, MQTT_PORT, 60)

client.subscribe(f"{base_topic}/run")
client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

threading.Thread(target=client.loop_forever, daemon=True).start()
threading.Thread(target=publish_status, daemon=True).start()

app.run(host="0.0.0.0", port=API_PORT)
