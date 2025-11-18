"""Monitoring loop implementations for Desktop Agent.

This package provides monitoring classes that coordinate data collection
and publishing to MQTT for Home Assistant integration. Monitors use
collectors to gather data and message brokers to publish it.

The monitors follow the Single Responsibility Principle - they coordinate
the monitoring loop but delegate actual data collection and publishing
to specialized classes.

Modules:
    system: System monitoring implementation
    game: Game monitoring implementation
    media: Media monitoring implementation
"""

from .game import GameMonitor
from .media import MediaMonitor
from .system import SystemMonitor

__all__ = ["SystemMonitor", "GameMonitor", "MediaMonitor"]
