"""Core infrastructure modules for Desktop Agent.

This package provides foundational abstractions for the Desktop Agent application,
decoupling business logic from infrastructure concerns.

Modules:
    config: Central configuration management for the application
    messaging: MQTT messaging abstraction layer
    discovery: Home Assistant MQTT discovery management
"""

from .config import (  # Export key config values commonly used across modules
    MQTT_BROKER,
    MQTT_PORT,
    base_topic,
    device_id,
    device_info,
    discovery_prefix,
)
from .discovery import DiscoveryManager
from .messaging import MessageBroker

__all__ = [
    "MessageBroker",
    "DiscoveryManager",
    "MQTT_BROKER",
    "MQTT_PORT",
    "base_topic",
    "device_id",
    "device_info",
    "discovery_prefix",
]
