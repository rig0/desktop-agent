import json, threading, time, os, sys, warnings
import paho.mqtt.client as mqtt
from modules.api import start_api
from modules.updater import UpdateManager
from modules.commands import run_predefined_command
from modules.deployment import notify_pipeline
from modules.desktop_agent import get_system_info, publish_discovery, start_desktop_agent
from modules.game_agent import start_game_agent
from modules.config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS, PUBLISH_INT, \
                    API_MOD, API_PORT, MEDIA_AGENT, GAME_AGENT, GAME_FILE, UPDATES_MOD, UPDATES_INT, UPDATES_CH, UPDATES_AUTO, \
                    device_id, base_topic, discovery_prefix, device_info


# ----------------------------
# MQTT Client
# ----------------------------

# Ignore deprecated mqtt callback version
warnings.filterwarnings("ignore", category=DeprecationWarning)

client = mqtt.Client()
exit_flag = threading.Event()

def on_connect(client, userdata, flags, rc):
    messages = {
        0: "\n[Main] MQTT connected successfully.",
        1: "\n[Main] MQTT connection refused - incorrect protocol version.",
        2: "\n[Main] MQTT connection refused - invalid client identifier.",
        3: "\n[Main] MQTT connection refused - server unavailable.",
        4: "\n[Main] MQTT connection refused - bad username or password.",
        5: "\n[Main] MQTT connection refused - not authorized.",
    }
    print(messages.get(rc, f"\n[Main] MQTT connection failed with unknown error (code {rc})."))

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
        print(f"[Main] Error handling MQTT command: {e}")


# ----------------------------
# Media Agent Handler
# ----------------------------

def media_agent(client):
    sysinfo = get_system_info()
    if sysinfo["os"] == "Linux":
        from modules.media_agent_linux import start_media_agent
        start_media_agent(client)
    elif sysinfo["os"] == "Windows":
        print("[Main] Media agent is enabled but must be ran standalone on Windows.")
        #from modules.media_agent import start_media_agent
    

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
        print(f"\n[Main] Could not connect to MQTT broker: {e}")
        sys.exit(1)

    # Listen for commands called via MQTT
    client.subscribe(f"{base_topic}/run")
    client.message_callback_add(f"{base_topic}/run", on_mqtt_message)

    # Start MQTT loop
    threading.Thread(target=client.loop_forever, daemon=True).start()

    # Wait briefly to see if connection fails
    for _ in range(20):  # up to ~2 seconds
        if exit_flag.is_set():
            print("[Main] Exiting due to MQTT connection failure.")
            sys.exit(1)
        time.sleep(0.1)


    # Start desktop agent
    threading.Thread(target=start_desktop_agent, args=(client, base_topic, PUBLISH_INT), daemon=True).start()

    # Start API
    if API_MOD: threading.Thread(target=start_api, args=(API_PORT,), daemon=True).start()

    # Start media agent
    if MEDIA_AGENT: threading.Thread(target=media_agent, args=(client,), daemon=True).start()

    # Start game agent
    if GAME_AGENT: threading.Thread(target=start_game_agent, args=(client, GAME_FILE,), daemon=True).start()

    # Start updater monitor
    update_manager = None
    if UPDATES_MOD:
        update_manager = UpdateManager(
            client=client,
            base_topic=base_topic,
            discovery_prefix=discovery_prefix,
            device_id=device_id,
            device_info=device_info,
            channel=UPDATES_CH,
            interval=UPDATES_INT,
            auto_install=UPDATES_AUTO,
        )

        install_topic = f"{base_topic}/update/install"

        def on_update_install(client, userdata, msg):
            update_manager.handle_install_request(msg.payload)

        client.subscribe(install_topic)
        client.message_callback_add(install_topic, on_update_install)
        update_manager.start()

    # Trigger jenkins pipeline if deploying
    if '--deploy' in sys.argv: notify_pipeline("Build Successful")

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
