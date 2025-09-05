# hass-desktop-agent

Desktop agent for your PC that connects to home assistant and feeds live system data via MQTT.

Has built-in API for fetching system info.

Copy config_example.ini to config.ini and fill in values

Supports running pre-defined commands remotely

Copy commands_example.json to commands.json and add your custom commands

Device will automatically be added to home assistant if mqtt discovery is enabled

Made for Windows

Should work on linux limitations (not tested):

- Temeperature sensors

- GPU detection (NVIDIA only)

- Full OS info (Distribution ie. Debian 12)
