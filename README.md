# Desktop Agent

## About

Desktop Agent is a lightweight, modular system monitoring tool designed for seamless integration with [Home Assistant](https://www.home-assistant.io/) and other automation platforms. It provides real-time system metrics, media playback monitoring, game tracking, and remote command execution through MQTT and REST API interfaces.

> ***Actively being developed. Expect breaking changes until release.***

## Project Overview

| | |
|----------------------|------------------------------------------------------------------|
| **Platform Support** | Windows, Linux |
| **Integration** | Home Assistant (MQTT Discovery), REST API |
| **Architecture** | Modular, thread-based monitoring with security-first design |
| **Communication** | MQTT (primary), REST API (optional) |
| **Language** | Python 3.10+ |

## Key Features

### System Monitoring
- Real-time CPU, memory, disk, and network metrics
- GPU usage and temperature monitoring
- Hardware temperature sensors (CPU, GPU, drives, system)
- Automatic Home Assistant discovery
- Configurable polling intervals

### Media & Entertainment
- **Media Playback Tracking**: Monitor what's playing across browsers and media players with metadata and thumbnails
- **Game Monitoring**: Track running games with IGDB metadata, cover art, artwork, and playtime tracking

### Remote Control
- **Command Execution**: Securely execute predefined commands via MQTT or REST API
- **REST API**: HTTP endpoints for system queries and external integrations
- **Multi-layered Security**: Command whitelisting, input validation, authentication

### Automation Features
- **Self-Updating**: Automatic updates with multiple release channels (stable/beta/nightly)
- **Modular Design**: Enable only the features you need
- **Thread-Safe**: Independent monitoring modules running concurrently

## Screenshots

![Desktop Agent Dashboard](https://i.imgur.com/I1aVpah.png)

![System Monitoring View](https://i.imgur.com/TPpXODN.png)

> These dashboards use apexcharts-card, vertical-stack-in-card, mushroom-template-card, mushroom-chips-card, mini-graph-card, and Home Assistant native cards.

## Requirements

- **Computer** to monitor (Windows or Linux)
- **Home Assistant** instance with MQTT broker configured
- **MQTT Broker** running (built-in or external)

## Documentation

### Getting Started
- [Getting Started](https://github.com/rig0/desktop-agent/wiki/Getting-Started) - Quick start checklist and overview
- [Installation](https://github.com/rig0/desktop-agent/wiki/Installation) - Installation instructions for Windows and Linux
- [Configuration](https://github.com/rig0/desktop-agent/wiki/Configuration) - Complete configuration reference
- [System Services](https://github.com/rig0/desktop-agent/wiki/System-Services) - Set up autostart on boot

### Reference
- [Architecture](https://github.com/rig0/desktop-agent/wiki/Architecture) - Technical architecture and design documentation
- [Modules](https://github.com/rig0/desktop-agent/wiki/Modules) - Overview of available modules
  - [Desktop Monitor](https://github.com/rig0/desktop-agent/wiki/Modules-Desktop-Agent) - System metrics monitoring
  - [MQTT](https://github.com/rig0/desktop-agent/wiki/Modules-MQTT) - MQTT communication and topics
  - [Media Agent](https://github.com/rig0/desktop-agent/wiki/Modules-Media-Agent) - Media playback tracking
  - [Game Agent](https://github.com/rig0/desktop-agent/wiki/Modules-Game-Agent) - Game monitoring with IGDB
  - [Commands](https://github.com/rig0/desktop-agent/wiki/Modules-Commands) - Remote command execution
  - [API](https://github.com/rig0/desktop-agent/wiki/Modules-API) - REST API endpoints
  - [Updates](https://github.com/rig0/desktop-agent/wiki/Modules-Updates) - Automatic update system

## Quick Links

**New Users**: Start with [Getting Started](https://github.com/rig0/desktop-agent/wiki/Getting-Started) → [Installation](https://github.com/rig0/desktop-agent/wiki/Installation) → [Configuration](https://github.com/rig0/desktop-agent/wiki/Configuration)

**Developers**: See [Architecture](https://github.com/rig0/desktop-agent/wiki/Architecture) for technical details and design decisions
