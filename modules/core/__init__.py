"""Core infrastructure modules for Desktop Agent.

This package provides foundational abstractions for the Desktop Agent application,
decoupling business logic from infrastructure concerns.

Modules:
    messaging: MQTT messaging abstraction layer
    discovery: Home Assistant MQTT discovery management
"""

from .messaging import MessageBroker
from .discovery import DiscoveryManager

__all__ = [
    "MessageBroker",
    "DiscoveryManager",
]
