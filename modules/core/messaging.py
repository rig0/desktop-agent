"""MQTT messaging abstraction layer for Desktop Agent.

This module provides a clean abstraction over MQTT operations, decoupling
the application logic from the underlying MQTT client implementation.
"""

import json
import logging
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt


logger = logging.getLogger(__name__)


class MessageBroker:
    """Abstraction layer for MQTT messaging operations.

    This class wraps the paho-mqtt client and provides a clean interface
    for publishing states, attributes, and Home Assistant discovery messages.
    It ensures consistent topic naming and message formatting across the application.

    Attributes:
        client: The underlying paho-mqtt client instance.
        base_topic: Base MQTT topic for all device messages.
        discovery_prefix: Home Assistant MQTT discovery prefix.

    Example:
        >>> broker = MessageBroker(client, "desktop/my_pc", "homeassistant")
        >>> broker.publish_state("cpu", "50")
        >>> broker.publish_attributes("cpu", {"frequency": "3.5 GHz"})
    """

    def __init__(
        self,
        client: mqtt.Client,
        base_topic: str,
        discovery_prefix: str = "homeassistant"
    ):
        """Initialize the message broker.

        Args:
            client: Configured paho-mqtt client instance.
            base_topic: Base topic for device messages (e.g., "desktop/my_pc").
            discovery_prefix: Home Assistant discovery prefix (default: "homeassistant").
        """
        self.client = client
        self.base_topic = base_topic
        self.discovery_prefix = discovery_prefix
        logger.debug(f"MessageBroker initialized with base_topic='{base_topic}'")

    def publish_state(
        self,
        entity: str,
        state: str,
        qos: int = 1,
        retain: bool = True
    ) -> None:
        """Publish entity state to MQTT.

        Args:
            entity: Entity identifier (e.g., "cpu", "memory").
            state: State value to publish.
            qos: Quality of Service level (0, 1, or 2).
            retain: Whether to retain the message on the broker.

        Example:
            >>> broker.publish_state("cpu", "75.5")
            >>> broker.publish_state("memory", "8192")
        """
        topic = f"{self.base_topic}/{entity}/state"
        self.client.publish(topic, payload=state, qos=qos, retain=retain)
        logger.debug(f"Published state to {topic}: {state}")

    def publish_attributes(
        self,
        entity: str,
        attrs: Dict[str, Any],
        qos: int = 1,
        retain: bool = True
    ) -> None:
        """Publish entity attributes as JSON to MQTT.

        Args:
            entity: Entity identifier (e.g., "cpu", "memory").
            attrs: Dictionary of attributes to publish.
            qos: Quality of Service level (0, 1, or 2).
            retain: Whether to retain the message on the broker.

        Example:
            >>> broker.publish_attributes("cpu", {
            ...     "model": "Intel i7-9700K",
            ...     "frequency": "3.6 GHz",
            ...     "cores": 8
            ... })
        """
        topic = f"{self.base_topic}/{entity}/attrs"
        payload = json.dumps(attrs)
        self.client.publish(topic, payload=payload, qos=qos, retain=retain)
        logger.debug(f"Published attributes to {topic}")

    def publish_discovery(
        self,
        domain: str,
        entity_id: str,
        config: Dict[str, Any],
        qos: int = 0,
        retain: bool = True
    ) -> None:
        """Publish Home Assistant MQTT discovery configuration.

        Args:
            domain: Home Assistant domain (e.g., "sensor", "binary_sensor").
            entity_id: Unique entity identifier.
            config: Discovery configuration dictionary.
            qos: Quality of Service level (typically 0 for discovery).
            retain: Whether to retain the message (typically True for discovery).

        Example:
            >>> broker.publish_discovery("sensor", "my_pc_cpu", {
            ...     "name": "My PC CPU",
            ...     "state_topic": "desktop/my_pc/cpu/state",
            ...     "unit_of_measurement": "%",
            ...     "device_class": "power_factor"
            ... })
        """
        topic = f"{self.discovery_prefix}/{domain}/{entity_id}/config"
        payload = json.dumps(config)
        self.client.publish(topic, payload=payload, qos=qos, retain=retain)
        logger.debug(f"Published discovery config to {topic}")

    def publish_availability(
        self,
        status: str = "online",
        qos: int = 1,
        retain: bool = True
    ) -> None:
        """Publish device availability status.

        Args:
            status: Availability status ("online" or "offline").
            qos: Quality of Service level (typically 1 for availability).
            retain: Whether to retain the message (typically True for availability).

        Example:
            >>> broker.publish_availability("online")
            >>> broker.publish_availability("offline")
        """
        topic = f"{self.base_topic}/availability"
        self.client.publish(topic, payload=status, qos=qos, retain=retain)
        logger.debug(f"Published availability: {status}")

    def subscribe(self, topic: str, callback: Optional[Callable] = None) -> None:
        """Subscribe to an MQTT topic.

        Args:
            topic: MQTT topic to subscribe to.
            callback: Optional callback function for this specific topic.

        Example:
            >>> def on_command(client, userdata, msg):
            ...     print(f"Received: {msg.payload}")
            >>> broker.subscribe("desktop/my_pc/command", on_command)
        """
        self.client.subscribe(topic)
        if callback:
            self.client.message_callback_add(topic, callback)
        logger.info(f"Subscribed to topic: {topic}")
