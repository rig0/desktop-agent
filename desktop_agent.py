import os
import platform
import subprocess
import sys
import json
import time
import socket
import platform
import psutil
import GPUtil
import paho.mqtt.client as mqtt
from flask import Flask, request, jsonify
import threading
import configparser
from pathlib import Path
import math

# ----------------------------
# Load configuration
# ----------------------------
BASE_DIR = Path(__file__).parent

config = configparser.ConfigParser()
config.read(BASE_DIR / "config.ini")

DEVICE_NAME = config["device"]["name"]
device_id = DEVICE_NAME.lower().replace(" ", "_")

MQTT_BROKER = config["mqtt"]["broker"]
MQTT_PORT = int(config["mqtt"]["port"])
MQTT_USER = config["mqtt"]["username"]
MQTT_PASS = config["mqtt"]["password"]

API_PORT = int(config["api"]["port"])
PUBLISH_INTERVAL = int(config["device"].get("interval", 30))  # seconds

# Base MQTT topics
base_topic = f"desktop/{device_id}"
discovery_prefix = "homeassistant"

# ----------------------------
# Device Definition
# ----------------------------
device_info = {
    "identifiers": [device_id],
    "name": DEVICE_NAME,
    "manufacturer": "Rigo Sotomayor",
    "model": "Desktop Agent",
    "sw_version": "1.0"
}

# ----------------------------
# Get System Information
# ----------------------------
def get_system_info():
    cpu_freq = psutil.cpu_freq()
    virtual_mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net_io = psutil.net_io_counters()
    
    # Flatten GPU info
    gpu_flat = get_gpu_info_flat()
    
    # Flatten temp info
    temps_flat = get_temperatures_flat()
    
    return {
        "device": DEVICE_NAME,
        "hostname": socket.gethostname(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "os": platform.system(),
        "os_version": platform.version(),
        "cpu_model": get_cpu_model(),
        "cpu_usage": psutil.cpu_percent(interval=0.5),
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_frequency_mhz": round(cpu_freq.current, 2) if cpu_freq else None,
        "memory_usage": virtual_mem.percent,
        "memory_total_gb": round(virtual_mem.total / (1024 ** 3), 2),
        "memory_used_gb": round(virtual_mem.used / (1024 ** 3), 2),
        "disk_usage": disk.percent,
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "disk_used_gb": round(disk.used / (1024 ** 3), 2),
        "network_sent_bytes": net_io.bytes_sent,
        "network_recv_bytes": net_io.bytes_recv,
        **gpu_flat,
        **temps_flat
    }

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
    """Return a safe number (no NaN/None/inf)."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    return default

def get_gpu_info_flat():
    """Flattened GPU info with safe numbers"""
    gpus = GPUtil.getGPUs()
    gpu_info = {}
    for i, gpu in enumerate(gpus):
        prefix = f"gpu{i}_"
        gpu_info[prefix + "name"] = gpu.name or "Unknown"
        gpu_info[prefix + "load_percent"] = safe_number(gpu.load * 100 if gpu.load is not None else None, 0)
        gpu_info[prefix + "memory_total_gb"] = safe_number(gpu.memoryTotal, 0)
        gpu_info[prefix + "memory_used_gb"] = safe_number(gpu.memoryUsed, 0)
        gpu_info[prefix + "temperature_c"] = safe_number(gpu.temperature, 0)
    return gpu_info

def get_temperatures_flat():
    temps = {}
    if hasattr(psutil, "sensors_temperatures"):
        raw_temps = psutil.sensors_temperatures()
        for label, entries in raw_temps.items():
            for entry in entries:
                key = f"{label}_{entry.label}" if entry.label else f"{label}"
                temps[key] = clean_value(entry.current)  # Use sanitizer
    return temps


def clean_value(val):
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None  # or 0 if you prefer
    return val

# ----------------------------
# Commands
# ----------------------------
def load_commands(config_path="commands.json"):
    config_file = BASE_DIR / Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"{config_file} not found.")
    with open(config_file, "r") as f:
        return json.load(f)

ALLOWED_COMMANDS = load_commands()

def run_predefined_command(command_key: str) -> dict:
    if command_key not in ALLOWED_COMMANDS:
        return {"success": False, "output": f"Command '{command_key}' not allowed."}

    # Support both simple and advanced command definitions
    entry = ALLOWED_COMMANDS[command_key]
    if isinstance(entry, dict):
        cmd = entry.get("cmd")
        wait = entry.get("wait", True)
    else:
        cmd = entry
        wait = True

    try:
        if wait:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return {
                "success": result.returncode == 0,
                "output": result.stdout.strip() if result.stdout else result.stderr.strip()
            }
        else:
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "output": f"Command '{command_key}' started."}
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
    """Publish Home Assistant MQTT discovery configs with icons"""
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
        "unit_of_measurement": "B",
        "value_template": "{{ value_json.network_sent_bytes }}",
        "icon": "mdi:upload-network",
        "unique_id": f"{device_id}_network_sent"
    },
    "network_recv_bytes": {
        "name": "Network Received",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "B",
        "value_template": "{{ value_json.network_recv_bytes }}",
        "icon": "mdi:download-network",
        "unique_id": f"{device_id}_network_received"
    }
    }
    
    # Dynamically add all temp sensors
    for key in get_system_info().keys():
        if key in get_temperatures_flat().keys():  # only temperature sensors
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
                "unit_of_measurement": "°C" if "temperature" in key else "%" if "load" in key else "GB" if "memory" in key else None,
                "value_template": f"{{{{ value_json.{key} }}}}",
                "icon": "mdi:expansion-card",
                "unique_id": f"{device_id}_{key.lower()}"
            }

    for sensor, payload in discovery_payloads.items():
        payload["device"] = device_info
        topic = f"{discovery_prefix}/sensor/{device_id}/{sensor}/config"
        client.publish(topic, json.dumps(payload), retain=True)
        print(f"Published discovery for {sensor}")

def publish_status():
    """Publish system status periodically"""
    while True:
        raw_info = get_system_info()
        cleaned = {k: clean_value(v) for k, v in raw_info.items()}
        status_payload = json.dumps(cleaned)
        client.publish(f"{base_topic}/status", status_payload, retain=True)
        print("Published status:", status_payload)
        time.sleep(PUBLISH_INTERVAL)


def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        command_key = payload.get("command")
        if not command_key:
            print("[MQTT] No command provided")
            return

        result = run_predefined_command(command_key)
        print(f"[MQTT] Ran command '{command_key}': {result}")

        # Optional: publish a result topic
        client.publish(f"{base_topic}/run_result", json.dumps(result), qos=1)

    except Exception as e:
        print(f"[MQTT] Error handling run command: {e}")

# ----------------------------
# Main
# ----------------------------
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.on_connect = on_connect
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# subscribe to the run command topic
client.subscribe(f"{base_topic}/run")
client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

# Start MQTT loop
threading.Thread(target=client.loop_forever, daemon=True).start()

# Start status publishing loop
threading.Thread(target=publish_status, daemon=True).start()

# Run Flask API
app.run(host="0.0.0.0", port=API_PORT)
