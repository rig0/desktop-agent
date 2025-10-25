# Desktop Agent for Home Assistant

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

### Wiki is a work in progress.