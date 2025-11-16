"""Data collection classes for Desktop Agent.

This package provides pure data collection functionality, separated from
publishing logic for better testability and reusability.

The collectors follow the Single Responsibility Principle - they only
collect data and don't handle MQTT publishing, formatting for display,
or other concerns. This makes them easy to test and reusable across
different contexts (monitors, API endpoints, CLI tools).

Modules:
    system: System metrics collection (CPU, memory, disk, network, GPU)
    game: Game information collection (IGDB metadata, playtime, artwork)
    media: Media playback collection (Windows SMTC, Linux MPRIS)
"""

from .game import GameCollector
from .media import MediaCollector
from .system import (
    CPUCollector,
    DiskCollector,
    GPUCollector,
    MemoryCollector,
    NetworkCollector,
    SystemInfoCollector,
)

__all__ = [
    "CPUCollector",
    "MemoryCollector",
    "DiskCollector",
    "NetworkCollector",
    "GPUCollector",
    "SystemInfoCollector",
    "GameCollector",
    "MediaCollector",
]
