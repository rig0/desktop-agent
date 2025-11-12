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

from .platform import PlatformUtils
from .formatting import (
    format_bytes,
    format_percentage,
    format_temperature,
    format_frequency,
    sanitize_topic
)
from .color import get_dominant_color, load_image
from .playtime import get_lutris_playtime, find_lutris_db
from .igdb import IGDBClient
from .deployment import notify_pipeline

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
    "notify_pipeline"
]
