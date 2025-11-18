"""Home Assistant MQTT discovery management for Desktop Agent.

This module handles the creation and publishing of Home Assistant MQTT
discovery configurations for all device entities.
"""

# Standard library imports
import logging
from typing import Any, Dict, Optional

# Local imports
from .messaging import MessageBroker

logger = logging.getLogger(__name__)


class DiscoveryManager:
    """Manages Home Assistant MQTT discovery for device entities.

    This class provides a centralized way to publish discovery configurations
    for various Home Assistant entity types (sensors, binary sensors, cameras, etc.).
    It ensures consistent device information and topic structure across all entities.

    Attributes:
        broker: MessageBroker instance for publishing.
        device_id: Unique device identifier.
        device_info: Device information dictionary for Home Assistant.
        base_topic: Base MQTT topic for device messages.

    Example:
        >>> discovery = DiscoveryManager(broker, "my_pc", device_info, "desktop/my_pc")
        >>> discovery.publish_sensor("cpu", "CPU Usage", unit="%", device_class="power_factor")
    """

    def __init__(
        self,
        broker: MessageBroker,
        device_id: str,
        device_info: Dict[str, Any],
        base_topic: str,
    ):
        """Initialize the discovery manager.

        Args:
            broker: MessageBroker instance for publishing discovery configs.
            device_id: Unique device identifier (e.g., "my_pc").
            device_info: Device information dict (name, manufacturer, model, etc.).
            base_topic: Base MQTT topic for device messages.
        """
        self.broker = broker
        self.device_id = device_id
        self.device_info = device_info
        self.base_topic = base_topic
        logger.debug(f"DiscoveryManager initialized for device '{device_id}'")

    def publish_sensor(
        self,
        entity_id: str,
        name: str,
        unit: Optional[str] = None,
        device_class: Optional[str] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
        state_class: Optional[str] = None,
        json_attributes_topic: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Publish sensor discovery configuration.

        Args:
            entity_id: Unique entity identifier suffix.
            name: Friendly name for the sensor.
            unit: Unit of measurement (e.g., "%", "GB", "°C").
            device_class: Home Assistant device class (e.g., "temperature", "power").
            icon: Material Design Icon (e.g., "mdi:cpu").
            entity_category: Entity category ("diagnostic", "config", or None).
            state_class: State class ("measurement", "total", or "total_increasing").
            json_attributes_topic: Optional attributes topic.
            **kwargs: Additional discovery configuration options.

        Example:
            >>> discovery.publish_sensor(
            ...     "cpu_usage",
            ...     "CPU Usage",
            ...     unit="%",
            ...     device_class="power_factor",
            ...     icon="mdi:cpu-64-bit",
            ...     entity_category="diagnostic"
            ... )
        """
        unique_id = f"{self.device_id}_{entity_id}"

        config = {
            "name": name,
            "state_topic": f"{self.base_topic}/{entity_id}/state",
            "unique_id": unique_id,
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
        }

        if unit:
            config["unit_of_measurement"] = unit
        if device_class:
            config["device_class"] = device_class
        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category
        if state_class:
            config["state_class"] = state_class
        if json_attributes_topic:
            config["json_attributes_topic"] = json_attributes_topic

        # Add any additional kwargs
        config.update(kwargs)

        self.broker.publish_discovery("sensor", unique_id, config)
        logger.debug(f"Published sensor discovery: {name} ({unique_id})")

    def publish_binary_sensor(
        self,
        entity_id: str,
        name: str,
        device_class: Optional[str] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
        payload_on: str = "ON",
        payload_off: str = "OFF",
        json_attributes_topic: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Publish binary sensor discovery configuration.

        Args:
            entity_id: Unique entity identifier suffix.
            name: Friendly name for the binary sensor.
            device_class: Home Assistant device class (e.g., "running", "connectivity").
            icon: Material Design Icon.
            entity_category: Entity category ("diagnostic", "config", or None).
            payload_on: Payload for ON state (default: "ON").
            payload_off: Payload for OFF state (default: "OFF").
            json_attributes_topic: Optional attributes topic.
            **kwargs: Additional discovery configuration options.
        """
        unique_id = f"{self.device_id}_{entity_id}"

        config = {
            "name": name,
            "state_topic": f"{self.base_topic}/{entity_id}/state",
            "unique_id": unique_id,
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
            "payload_on": payload_on,
            "payload_off": payload_off,
        }

        if device_class:
            config["device_class"] = device_class
        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category
        if json_attributes_topic:
            config["json_attributes_topic"] = json_attributes_topic

        config.update(kwargs)

        self.broker.publish_discovery("binary_sensor", unique_id, config)
        logger.debug(f"Published binary_sensor discovery: {name} ({unique_id})")

    def publish_button(
        self,
        entity_id: str,
        name: str,
        command_topic: str,
        payload_press: str = "PRESS",
        icon: Optional[str] = None,
        entity_category: Optional[str] = "config",
        **kwargs,
    ) -> None:
        """Publish button discovery configuration.

        Args:
            entity_id: Unique entity identifier suffix.
            name: Friendly name for the button.
            command_topic: MQTT topic to publish button presses to.
            payload_press: Payload sent when button is pressed.
            icon: Material Design Icon.
            entity_category: Entity category (default: "config").
            **kwargs: Additional discovery configuration options.
        """
        unique_id = f"{self.device_id}_{entity_id}"

        config = {
            "name": name,
            "command_topic": command_topic,
            "payload_press": payload_press,
            "unique_id": unique_id,
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
        }

        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category

        config.update(kwargs)

        self.broker.publish_discovery("button", unique_id, config)
        logger.debug(f"Published button discovery: {name} ({unique_id})")

    def publish_camera(
        self,
        entity_id: str,
        name: str,
        topic: str,
        icon: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Publish camera discovery configuration.

        Args:
            entity_id: Unique entity identifier suffix.
            name: Friendly name for the camera.
            topic: MQTT topic where image data is published.
            icon: Material Design Icon.
            **kwargs: Additional discovery configuration options.
        """
        unique_id = f"{self.device_id}_{entity_id}"

        config = {
            "platform": "mqtt",
            "name": name,
            "unique_id": unique_id,
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
            "topic": topic,
        }

        if icon:
            config["icon"] = icon

        config.update(kwargs)

        self.broker.publish_discovery("camera", unique_id, config)
        logger.debug(f"Published camera discovery: {name} ({unique_id})")

    def publish_update(
        self,
        entity_id: str,
        name: str,
        state_topic: str,
        command_topic: str,
        payload_install: str = "INSTALL",
        device_class: str = "firmware",
        entity_category: Optional[str] = "diagnostic",
        json_attributes_topic: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Publish update entity discovery configuration.

        Args:
            entity_id: Unique entity identifier suffix.
            name: Friendly name for the update entity.
            state_topic: Topic where version/state information is published (JSON).
            command_topic: Topic for triggering updates.
            payload_install: Payload to send for installing update.
            device_class: Device class (default: "firmware").
            entity_category: Entity category (default: "diagnostic").
            json_attributes_topic: Optional attributes topic.
            **kwargs: Additional discovery configuration options.
        """
        unique_id = f"{self.device_id}_{entity_id}"

        config = {
            "name": name,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "payload_install": payload_install,
            "unique_id": unique_id,
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
            "device_class": device_class,
        }

        if entity_category:
            config["entity_category"] = entity_category
        if json_attributes_topic:
            config["json_attributes_topic"] = json_attributes_topic

        config.update(kwargs)

        self.broker.publish_discovery("update", unique_id, config)
        logger.debug(f"Published update entity discovery: {name} ({unique_id})")
