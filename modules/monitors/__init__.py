"""Monitoring loop implementations for Desktop Agent.

This package provides monitoring classes that coordinate data collection
and publishing to MQTT for Home Assistant integration. Monitors use
collectors to gather data and message brokers to publish it.

The monitors follow the Single Responsibility Principle - they coordinate
the monitoring loop but delegate actual data collection and publishing
to specialized classes.

Modules:
    desktop: Desktop system monitoring implementation
    game: Game activity monitoring implementation
    media: Media playback monitoring implementation
"""

from .desktop import DesktopMonitor
from .game import GameMonitor
from .media import MediaMonitor

__all__ = ["DesktopMonitor", "GameMonitor", "MediaMonitor"]
