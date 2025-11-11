# Standard library imports
import glob
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

# Third-party imports
import GPUtil
import psutil

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

    total, used, free, percent = get_disk_info()

    return {
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
        "disk_usage": round(percent),
        "disk_total_gb": round(total / (1024 ** 3), 1),
        "disk_used_gb": round(used / (1024 ** 3), 1),
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
    if platform.system() == "Windows":
        if shutil.which("wmic"):
            try:
                output = subprocess.check_output("wmic cpu get Name", shell=True)
                lines = [line.strip() for line in output.decode().splitlines() if line.strip()]
                if len(lines) >= 2:
                    return lines[1]
            except:
                pass
        # fallback to registry
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return cpu
        except:
            return "Unknown CPU"
    elif platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except:
            return "Unknown CPU"
    else:
        return platform.processor() or "Unknown CPU"



def get_disk_info():
    # For Windows systems, get the disk info of the root directory
    if sys.platform.startswith("win"):
        usage = psutil.disk_usage('C:\\')
        return usage.total, usage.used, usage.free, usage.percent

    # For Linux systems, focus on /var/home partition
    else:
        total = used = free = 0
        target_partitions = ['/var/home', '/home', '/run/host/var/home', '/']
        for partition in psutil.disk_partitions(all=False):
            if partition.mountpoint in target_partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total = usage.total
                    used = usage.used
                    free = usage.free
                    # Once we find a match, we don't need to check other partitions
                    break
                except PermissionError:
                    # Skip partitions that cannot be accessed
                    continue
                except OSError:
                    # Skip invalid mount points
                    continue
                
        # Calculate the percentage of disk used
        percent = (used / total) * 100 if total > 0 else 0
        return total, used, free, percent

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
# Desktop Agent
# ----------------------------

def build_discovery_payloads(device_id, base_topic, discovery_prefix, device_info):
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

    # Dynamically add all temperature sensors
    for key in get_temperatures_flat().keys():
        discovery_payloads[key] = {
            "name": f"{key.replace('_', ' ').title()}",
            "state_topic": f"{base_topic}/status",
            "unit_of_measurement": "°C",
            "value_template": f"{{{{ value_json.{key} }}}}",
            "icon": "mdi:thermometer",
            "unique_id": f"{device_id}_{key.lower()}"
        }

    # Dynamically add all GPU sensors
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

    # Attach device metadata
    for payload in discovery_payloads.values():
        payload["device"] = device_info
        payload["availability_topic"] = f"{base_topic}/availability"

    return discovery_payloads


def publish_discovery(client, device_id, base_topic, discovery_prefix, device_info):
    payloads = build_discovery_payloads(device_id, base_topic, discovery_prefix, device_info)
    for sensor, payload in payloads.items():
        topic = f"{discovery_prefix}/sensor/{device_id}/{sensor}/config"
        client.publish(topic, json.dumps(payload), retain=True)
        print(f"[DesktopAgent] Published discovery for {sensor}")


def start_desktop_agent(client, base_topic, publish_int):
    def _publisher():
        print("[DesktopAgent] Desktop Agent thread started")
        while True:
            raw_info = get_system_info()
            cleaned = {k: clean_value(v) for k, v in raw_info.items()}
            client.publish(f"{base_topic}/status", json.dumps(cleaned), retain=True)
            client.publish(f"{base_topic}/availability", "online", retain=True)
            time.sleep(publish_int)

    threading.Thread(target=_publisher, daemon=True).start()