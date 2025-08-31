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

# ----------------------------
# Load configuration
# ----------------------------
config = configparser.ConfigParser()
config.read("config.ini")

DEVICE_NAME = config["device"]["name"]

MQTT_BROKER = config["mqtt"]["broker"]
MQTT_PORT = int(config["mqtt"]["port"])
MQTT_USER = config["mqtt"]["username"]
MQTT_PASS = config["mqtt"]["password"]

API_PORT = int(config["api"]["port"])
PUBLISH_INTERVAL = int(config["device"].get("interval", 30))  # seconds

# Base MQTT topics
base_topic = f"home/desktop/{DEVICE_NAME}"
discovery_prefix = "homeassistant"

# ----------------------------
# Device Definition
# ----------------------------
device_info = {
    "identifiers": [DEVICE_NAME.lower().replace(" ", "_")],
    "name": DEVICE_NAME,
    "manufacturer": "Rigo Sotomayor",
    "model": "Desktop Agent",
    "sw_version": "1.0"
}

# ----------------------------
# Get System Information
# ----------------------------
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
    
def get_gpu_info_flat():
    """
    Returns GPU info as a flat dictionary for Home Assistant.
    Keys are like: gpu0_name, gpu0_load_percent, gpu0_memory_used_gb, gpu0_temperature_c
    """
    flat_gpus = {}
    try:
        gpus = GPUtil.getGPUs()
        for i, gpu in enumerate(gpus):
            prefix = f"gpu{i}_"
            flat_gpus[f"{prefix}name"] = gpu.name
            flat_gpus[f"{prefix}load_percent"] = round(gpu.load * 100, 2)
            flat_gpus[f"{prefix}memory_total_gb"] = round(gpu.memoryTotal, 2)
            flat_gpus[f"{prefix}memory_used_gb"] = round(gpu.memoryUsed, 2)
            flat_gpus[f"{prefix}temperature_c"] = gpu.temperature
        if not gpus:
            flat_gpus["gpu0_name"] = "No GPU detected"
            flat_gpus["gpu0_load_percent"] = 0
            flat_gpus["gpu0_memory_total_gb"] = 0
            flat_gpus["gpu0_memory_used_gb"] = 0
            flat_gpus["gpu0_temperature_c"] = 0
    except Exception:
        # fallback if GPUtil fails
        flat_gpus["gpu0_name"] = "GPU info unavailable"
        flat_gpus["gpu0_load_percent"] = 0
        flat_gpus["gpu0_memory_total_gb"] = 0
        flat_gpus["gpu0_memory_used_gb"] = 0
        flat_gpus["gpu0_temperature_c"] = 0
    return flat_gpus

def get_temperatures_flat():
    temps = {}
    if hasattr(psutil, "sensors_temperatures"):
        raw_temps = psutil.sensors_temperatures()
        for label, entries in raw_temps.items():
            for entry in entries:
                # Only include actual temperature readings
                if entry.current is not None:
                    key = f"{label}_{entry.label}" if entry.label else f"{label}"
                    temps[key] = entry.current  # °C
    return temps

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
    
# ----------------------------
# Flask API
# ----------------------------
app = Flask(__name__)

@app.route("/status")
def status():
    return jsonify(get_system_info())

@app.route("/run", methods=["POST"])
def run_command():
    """Run a system command via REST"""
    data = request.json
    if not data or "command" not in data:
        return jsonify({"error": "No command provided"}), 400
    
    command = data["command"]
    try:
        os.system(command + " &")  # non-blocking
        return jsonify({"status": f"Command '{command}' executed"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        "name": f"{DEVICE_NAME} Hostname",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.hostname }}",
        "icon": "mdi:information",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_hostname"
    },
    "uptime_seconds": {
        "name": f"{DEVICE_NAME} Uptime",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "s",
        "value_template": "{{ value_json.uptime_seconds }}",
        "icon": "mdi:clock-outline",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_uptime"
    },
    "os": {
        "name": f"{DEVICE_NAME} OS",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.os }}",
        "icon": "mdi:desktop-classic",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_os"
    },
    "os_version": {
        "name": f"{DEVICE_NAME} OS Version",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.os_version }}",
        "icon": "mdi:information",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_os_version"
    },

    # CPU
    "cpu_model": {
        "name": f"{DEVICE_NAME} CPU Model",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.cpu_model }}",
        "icon": "mdi:cpu-64-bit",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_cpu_model"
    },
    "cpu_usage": {
        "name": f"{DEVICE_NAME} CPU Usage",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.cpu_usage }}",
        "icon": "mdi:chip",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_cpu_usage"
    },
    "cpu_cores": {
        "name": f"{DEVICE_NAME} CPU Cores",
        "state_topic": f"{base_topic}/status",
        "value_template": "{{ value_json.cpu_cores }}",
        "icon": "mdi:chip",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_cpu_cores"
    },
    "cpu_frequency_mhz": {
        "name": f"{DEVICE_NAME} CPU Frequency",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "MHz",
        "value_template": "{{ value_json.cpu_frequency_mhz }}",
        "icon": "mdi:chip",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_cpu_frequency"
    },

    # Memory
    "memory_usage": {
        "name": f"{DEVICE_NAME} Memory Usage",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.memory_usage }}",
        "icon": "mdi:memory",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_memory_usage"
    },
    "memory_total_gb": {
        "name": f"{DEVICE_NAME} Memory Total",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.memory_total_gb }}",
        "icon": "mdi:memory",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_memory_total"
    },
    "memory_used_gb": {
        "name": f"{DEVICE_NAME} Memory Used",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.memory_used_gb }}",
        "icon": "mdi:memory",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_memory_used"
    },

    # Disk
    "disk_usage": {
        "name": f"{DEVICE_NAME} Disk Usage",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.disk_usage }}",
        "icon": "mdi:harddisk",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_disk_usage"
    },
    "disk_total_gb": {
        "name": f"{DEVICE_NAME} Disk Total",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.disk_total_gb }}",
        "icon": "mdi:harddisk",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_disk_total",
    },
    "disk_used_gb": {
        "name": f"{DEVICE_NAME} Disk Used",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "GB",
        "value_template": "{{ value_json.disk_used_gb }}",
        "icon": "mdi:harddisk",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_disk_used"
    },

    # Network
    "network_sent_bytes": {
        "name": f"{DEVICE_NAME} Network Sent",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "B",
        "value_template": "{{ value_json.network_sent_bytes }}",
        "icon": "mdi:upload-network",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_network_sent"
    },
    "network_recv_bytes": {
        "name": f"{DEVICE_NAME} Network Received",
        "state_topic": f"{base_topic}/status",
        "unit_of_measurement": "B",
        "value_template": "{{ value_json.network_recv_bytes }}",
        "icon": "mdi:download-network",
        "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_network_received"
    }
    }
    
    # Dynamically add all temp sensors
    for key in get_system_info().keys():
        if key in get_temperatures_flat().keys():  # only temperature sensors
            discovery_payloads[key] = {
                "name": f"{DEVICE_NAME} {key.replace('_', ' ').title()}",
                "state_topic": f"{base_topic}/status",
                "unit_of_measurement": "°C",
                "value_template": f"{{{{ value_json.{key} }}}}",
                "icon": "mdi:thermometer",
                "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_{key.lower()}"
            }
            
    # Dynamically add all gpu sensors
    for key in get_system_info().keys():
        if key.startswith("gpu"):
            discovery_payloads[key] = {
                "name": f"{DEVICE_NAME} {key.replace('_', ' ').title()}",
                "state_topic": f"{base_topic}/status",
                "unit_of_measurement": "°C" if "temperature" in key else "%" if "load" in key else "GB" if "memory" in key else None,
                "value_template": f"{{{{ value_json.{key} }}}}",
                "icon": "mdi:expansion-card",
                "unique_id": f"{DEVICE_NAME.lower().replace(' ', '_')}_{key.lower()}"
            }

    for sensor, payload in discovery_payloads.items():
        payload["device"] = device_info
        topic = f"{discovery_prefix}/sensor/{DEVICE_NAME}/{sensor}/config"
        client.publish(topic, json.dumps(payload), retain=True)
        print(f"Published discovery for {sensor}")

def publish_status():
    """Publish system status periodically"""
    while True:
        status_payload = json.dumps(get_system_info())
        client.publish(f"{base_topic}/status", status_payload)
        print("Published status:", status_payload)
        time.sleep(PUBLISH_INTERVAL)

# ----------------------------
# Main
# ----------------------------
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.on_connect = on_connect
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Start MQTT loop
threading.Thread(target=client.loop_forever, daemon=True).start()

# Start status publishing loop
threading.Thread(target=publish_status, daemon=True).start()

# Run Flask API
app.run(host="0.0.0.0", port=API_PORT)
