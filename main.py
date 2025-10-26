import json, threading, time, os, sys, warnings
import paho.mqtt.client as mqtt
from modules.api import start_api
from modules.updater import update_repo
from modules.commands import run_predefined_command
from modules.desktop_agent import get_system_info, publish_discovery, start_desktop_agent
from modules.game_agent import start_game_agent
from modules.config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, PUBLISH_INT, \
                    API_MOD, API_PORT, MEDIA_AGENT, GAME_AGENT, GAME_FILE, UPDATES_MOD, UPDATES_INT, UPDATES_CH, \
                    device_id, base_topic, discovery_prefix, device_info


# ----------------------------
# MQTT Client
# ----------------------------

# Ignore depreceated mqtt callback version
warnings.filterwarnings("ignore", category=DeprecationWarning)

client = mqtt.Client()
exit_flag = threading.Event()

def on_connect(client, userdata, flags, rc):
    messages = {
        0: "[MQTT] Connected successfully.",
        1: "[MQTT] Connection refused - incorrect protocol version.",
        2: "[MQTT] Connection refused - invalid client identifier.",
        3: "[MQTT] Connection refused - server unavailable.",
        4: "[MQTT] Connection refused - bad username or password.",
        5: "[MQTT] Connection refused - not authorized.",
    }
    print(messages.get(rc, f"[MQTT] Connection failed with unknown error (code {rc})."))

    if rc != 0:
        exit_flag.set()  # signal main thread to exit
        client.disconnect()
        return

    publish_discovery(client, device_id, base_topic, discovery_prefix, device_info)


# ----------------------------
# MQTT Command Handler
# ----------------------------

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        command_key = payload.get("command")
        if not command_key:
            return
        result = run_predefined_command(command_key)
        client.publish(f"{base_topic}/run_result", json.dumps(result), qos=1)
    except Exception as e:
        print(f"[Main] MQTT Error handling run command: {e}")


# ----------------------------
# Media Agent Handler
# ----------------------------

def media_agent(client):
    sysinfo = get_system_info()
    if sysinfo["os"] == "Linux":
        from modules.media_agent_linux import start_media_agent
        start_media_agent(client)
    #elif sysinfo["os"] == "Windows":
        #from modules.media_agent import start_media_agent
    

# ----------------------------
# Updater
# ----------------------------

def updater():
    while True:
        update_repo(UPDATES_CH)
        time.sleep(UPDATES_INT)


# ----------------------------
# Main
# ----------------------------

def main():
    # Connect to MQTT Broker
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect

    # Cleanly handle MQTT connection errors
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"[MQTT] Could not connect to broker: {e}")
        sys.exit(1)

    # Start MQTT loop
    threading.Thread(target=client.loop_forever, daemon=True).start()

    # Wait briefly to see if connection fails
    for _ in range(20):  # up to ~2 seconds
        if exit_flag.is_set():
            print("[MQTT] Exiting due to connection failure.")
            sys.exit(1)
        time.sleep(0.1)

    # Listen for commands called via MQTT
    client.subscribe(f"{base_topic}/run")
    client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

    # Start MQTT loop
    threading.Thread(target=client.loop_forever, daemon=True).start()

    # Start desktop agent
    threading.Thread(target=start_desktop_agent, args=(client, base_topic, PUBLISH_INT), daemon=True).start()

    # Start API
    if API_MOD: threading.Thread(target=start_api, args=(API_PORT,), daemon=True).start()

    # Start media agent
    if MEDIA_AGENT: threading.Thread(target=media_agent, args=(client,), daemon=True).start()

    # Start game agent
    if GAME_AGENT: threading.Thread(target=start_game_agent, args=(client, GAME_FILE,), daemon=True).start()

    # Start updater
    if UPDATES_MOD: threading.Thread(target=updater, daemon=True).start()

    # Keep main thread alive
    print("[Main] Agent running. Press Ctrl+C to exit.")
    try:
        while not exit_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Main] Shutting down...")
        client.disconnect()
        sys.exit(0)

if __name__ == "__main__":
    main()