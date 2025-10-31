# Desktop Agent

## About
A lightweight desktop agent that integrates your PC with [Home Assistant](https://www.home-assistant.io/) using **MQTT**.  
It publishes live system metrics, exposes a simple API, and lets you run custom commands remotely.


## Features
- **System monitoring**: CPU, memory, storage, and other stats sent to Home Assistant via MQTT.
- **Built-in API**: Fetch system info or run commands via HTTP.
- **Remote commands**: Define and trigger your own scripts/commands remotely.
- **Media agent**: Now playing info. Title, artist, album and thumbnail via MQTT.
- **Game agent**: Current game info. Cover, artwork, playtime and game details via MQTT.
- **Auto updater**: Optional auto updates
- **Home Assistant auto-discovery**: Device and sensors show up automatically if MQTT discovery is enabled.


## Preview 
<img src="https://files.rigslab.com/-pDCgGegpYb/Desktop_Agent_Dash_Example-1.png" alt="Preview-1" width="700">

<img src="https://files.rigslab.com/-twQu8mtTei/Desktop_Agent_Dash_Example-2.png" alt="Preview-2" width="700">


## Requirements
- **Computer** to monitor and send commands to.
- **Home Assistant** instance with **MQTT broker** running to receive info.


## Supported OS
- Windows
- Linux

## Quick Start
- [Documentation](/wiki/Home)
- [Getting Started](/wiki/Getting-Started)
- [Configuration Guide](/wiki/Configuration)
- [Modules Overview](/wiki/Modules)
