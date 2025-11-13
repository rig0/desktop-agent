# Desktop Agent

> ***Actively being developed. Expect breaking changes until release.***

## About
Desktop Agent is a lightweight desktop monitoring tool. It collects system information from desktop computers and exposes it via MQTT and REST API for integration with [Home Assistant](https://www.home-assistant.io/) and other automation platforms.


## Features
- **Real-time system metrics**: CPU, memory, disk, network, GPU usage and temperatures
- **Media playback monitoring**: Track what's playing with metadata and thumbnails
- **Game monitoring**: Detect running games with IGDB metadata integration including cover art, artwork, playtime, and game details
- **Remote command execution**: Securely execute predefined commands via MQTT or REST API
- **REST API**: HTTP endpoints for external integrations and system queries
- **Automatic Home Assistant discovery**: Devices and sensors automatically appear in Home Assistant
- **Self-updating capabilities**: Optional automatic updates with multiple release channels
- **Modular architecture**: Enable only the features you need


## Preview 
![Preview-1](https://i.imgur.com/I1aVpah.png) 

![Preview-2](https://i.imgur.com/TPpXODN.png)

> These dashboards were created using apexcharts-card, vertical-stack-in-card, mushroom-template-card, mushroom-chips-card, mini-graph-card and home assistant native cards. 

## Requirements
- **Computer** to monitor and send commands to.
- **Home Assistant** instance with **MQTT broker** running to receive info.


## Supported OS
- Windows
- Linux


## Quick Start
- [Getting Started](https://github.com/rig0/desktop-agent/wiki/Getting-Started)
- [Installation](https://github.com/rig0/desktop-agent/wiki/Installation)
- [Configuration Guide](https://github.com/rig0/desktop-agent/wiki/Configuration)
- [Modules Overview](https://github.com/rig0/desktop-agent/wiki/Modules)
