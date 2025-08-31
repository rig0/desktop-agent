# hass-desktop-agent

Desktop agent for your PC that connects to home assistant and feeds live system data via MQTT.

Has built-in API for fetching system info.

Supports running commands remotely* (Add restrictions)

Cross-Platform with Windows/Linux

Linux Limitations:

- Temeperature sensors

- GPU detection (NVIDIA only)

- Full OS info (Distribution ie. Debian 12)

Copy config_example.ini to config.ini and fill in values

Device will automatically be added to home assistant if discovery is enabled