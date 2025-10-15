import json, threading, time, os
import paho.mqtt.client as mqtt
from modules.api import start_api
from modules.updater import update_repo
from modules.commands import run_predefined_command
from modules.desktop_agent import get_system_info, clean_value, get_temperatures_flat
from modules.lutris_agent import get_game_info
from modules.config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, PUBLISH_INT, \
                    API_MOD, API_PORT, MEDIA_AGENT, UPDATES_MOD, UPDATES_INT, \
                    device_id, base_topic, discovery_prefix, device_info


# ----------------------------
# MQTT Client
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
        client.publish(f"{base_topic}/status", json.dumps(cleaned), retain=True)
        client.publish(f"{base_topic}/availability", "online", retain=True)
        time.sleep(PUBLISH_INT)

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        command_key = payload.get("command")
        if not command_key:
            return
        result = run_predefined_command(command_key)
        client.publish(f"{base_topic}/run_result", json.dumps(result), qos=1)
    except Exception as e:
        print(f"[MQTT] Error handling run command: {e}")


# ----------------------------
# Media Agent Handler
# ----------------------------

def is_user_session_active():
    sysinfo = get_system_info()
    if sysinfo["os"] == "Windows":
        return "explorer.exe" in os.popen('tasklist').read()
    else: return True

def wait_for_user_session(timeout=3600):
    start_time = time.time()
    while not is_user_session_active():
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            raise TimeoutError("Waiting for user session timed out.")
        time.sleep(3)  # Check every 3 seconds

def media_agent(client):
    sysinfo = get_system_info()
    try:
        if sysinfo["os"] == "Linux":
            from modules.media_agent_linux import start_media_agent
            start_media_agent(client)
        elif sysinfo["os"] == "Windows":
            wait_for_user_session()  # Ensure user session is ready before starting agent
            from modules.media_agent import start_media_agent
            start_media_agent(client)
    except TimeoutError as e:
        print(f"Media Agent Error: {e}")


# ----------------------------
# Updater
# ----------------------------

def updater():
    while True:
        update_repo()
        time.sleep(UPDATES_INT)

# ----------------------------
# Main
# ----------------------------

def main():
    # Connect to MQTT Broker
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    # Listen for commands called via MQTT
    client.subscribe(f"{base_topic}/run")
    client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

    # Start MQTT loop
    threading.Thread(target=client.loop_forever, daemon=True).start()

    # Start desktop agent status publisher
    threading.Thread(target=publish_status, daemon=True).start()

    # Start API
    if API_MOD: threading.Thread(target=start_api, args=(API_PORT,), daemon=True).start()

    # Start media agent
    if MEDIA_AGENT: threading.Thread(target=media_agent, args=(client,), daemon=True).start()

    # Start lutris agent
    #if LUTRIS_AGENT: threading.Thread(target=get_game_info, args=("Apex Legends",), daemon=True).start()

    # Start updater
    if UPDATES_MOD: threading.Thread(target=updater, daemon=True).start()

    # Keep main thread alive
    print("[Main] Agent running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Main] Shutting down...")

if __name__ == "__main__":
    main()