"""Utility functions and helpers for Desktop Agent.

This package provides reusable utility functions for platform detection,
data formatting, game integration, media integration, updates, and deployment.

Modules:
    platform: Platform detection and platform-specific operations
    formatting: Data formatting and transformation utilities
    color: Image color analysis utilities
    playtime: Lutris/Steam playtime tracking
    igdb: IGDB API client for game metadata
    deployment: Jenkins pipeline notification utilities
"""

from .color import get_dominant_color, load_image
from .deployment import notify_pipeline
from .formatting import (
    format_bytes,
    format_frequency,
    format_percentage,
    format_temperature,
    sanitize_topic,
)
from .igdb import IGDBClient
from .platform import PlatformUtils
from .playtime import find_lutris_db, get_lutris_playtime

__all__ = [
    "PlatformUtils",
    "format_bytes",
    "format_percentage",
    "format_temperature",
    "format_frequency",
    "sanitize_topic",
    "get_dominant_color",
    "load_image",
    "get_lutris_playtime",
    "find_lutris_db",
    "IGDBClient",
    "notify_pipeline",
]
