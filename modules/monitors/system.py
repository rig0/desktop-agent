"""System monitoring implementation.

This module provides the SystemMonitor class which coordinates system
data collection and publishing to MQTT for Home Assistant integration.
It runs in a monitoring loop, periodically collecting metrics and publishing
them along with Home Assistant discovery configurations.
"""

# Standard library imports
import json
import logging
import math
import threading
from typing import Any, Optional

# Local imports
from modules.collectors.system import SystemInfoCollector
from modules.core.discovery import DiscoveryManager
from modules.core.messaging import MessageBroker

logger = logging.getLogger(__name__)


class SystemMonitor:
    """Monitors system metrics and publishes to MQTT.

    This class coordinates the collection of system metrics (CPU, memory,
    disk, network, GPU, temperatures) and their publication to MQTT topics
    for Home Assistant integration. It runs in a monitoring loop and handles
    Home Assistant discovery configuration publishing.

    The monitor uses dependency injection for all its components, making it
    easy to test and allowing different implementations to be swapped in.

    Attributes:
        collector: System information collector instance.
        broker: Message broker for publishing metrics.
        discovery: Discovery manager for Home Assistant configuration.
        interval: Publishing interval in seconds.
        device_id: Device identifier for entity naming.
        base_topic: Base MQTT topic for all messages.

    Example:
        >>> collector = SystemInfoCollector()
        >>> broker = MessageBroker(client, "desktop/my_pc", "homeassistant")
        >>> device_info = {
        ...     "identifiers": ["my_pc"],
        ...     "name": "My PC",
        ...     "manufacturer": "Custom",
        ...     "model": "Desktop"
        ... }
        >>> discovery = DiscoveryManager(broker, "my_pc", device_info, "desktop/my_pc")
        >>> monitor = SystemMonitor(collector, broker, discovery, "my_pc", "desktop/my_pc", interval=10)
        >>> stop_event = threading.Event()
        >>> monitor.start(stop_event)
    """

    def __init__(
        self,
        collector: SystemInfoCollector,
        broker: MessageBroker,
        discovery: DiscoveryManager,
        device_id: str,
        base_topic: str,
        interval: int = 10,
    ):
        """Initialize system monitor.

        Args:
            collector: System information collector instance.
            broker: Message broker for publishing metrics.
            discovery: Discovery manager for HA configuration.
            device_id: Unique device identifier (e.g., "my_pc").
            base_topic: Base MQTT topic (e.g., "desktop/my_pc").
            interval: Publishing interval in seconds (default: 10).
        """
        self.collector = collector
        self.broker = broker
        self.discovery = discovery
        self.device_id = device_id
        self.base_topic = base_topic
        self.interval = interval
        logger.debug(f"SystemMonitor initialized with interval={interval}s")

    def _publish_sensor_with_json(
        self,
        entity_id: str,
        name: str,
        json_key: str,
        unit: Optional[str] = None,
        icon: Optional[str] = None,
        device_class: Optional[str] = None,
        entity_category: Optional[str] = None,
        state_class: Optional[str] = None,
    ) -> None:
        """Publish sensor discovery that extracts value from JSON status topic.

        This publishes a Home Assistant MQTT sensor discovery config that uses
        a value_template to extract a specific field from the JSON status message.

        Args:
            entity_id: Entity ID suffix (e.g., "cpu_usage")
            name: Friendly name for the sensor
            json_key: Key to extract from JSON (e.g., "cpu_usage")
            unit: Unit of measurement (e.g., "%", "GB")
            icon: MDI icon (e.g., "mdi:chip")
            device_class: HA device class
            entity_category: Entity category (typically "diagnostic")
            state_class: State class ("measurement", "total_increasing", etc.)
        """
        unique_id = f"{self.device_id}_{entity_id}"

        config = {
            "name": name,
            "state_topic": f"{self.base_topic}/status",
            "value_template": f"{{{{ value_json.{json_key} }}}}",
            "unique_id": unique_id,
            "object_id": f"{self.device_id}_{entity_id}",
            "device": self.discovery.device_info,
            "availability_topic": f"{self.base_topic}/availability",
        }

        if unit:
            config["unit_of_measurement"] = unit
        if icon:
            config["icon"] = icon
        if device_class:
            config["device_class"] = device_class
        if entity_category:
            config["entity_category"] = entity_category
        if state_class:
            config["state_class"] = state_class

        # Publish discovery with nested topic structure
        topic = f"{self.discovery.broker.discovery_prefix}/sensor/{self.device_id}/{entity_id}/config"
        payload = json.dumps(config)
        self.discovery.broker.client.publish(topic, payload=payload, qos=0, retain=True)
        logger.debug(f"Published JSON-based sensor discovery: {name} ({unique_id})")

    def _cleanup_old_discovery(self) -> None:
        """Remove old discovery configurations that used individual state topics.

        This publishes empty retained messages to old discovery topics to clean up
        entities that were created with the previous individual-topic approach.
        Call this once during startup before publishing new discovery configs.
        """
        old_sensors = [
            "hostname",
            "uptime_seconds",
            "os",
            "os_version",
            "cpu_model",
            "cpu_usage",
            "cpu_cores",
            "cpu_frequency_mhz",
            "memory_usage",
            "memory_total_gb",
            "memory_used_gb",
            "disk_usage",
            "disk_total_gb",
            "disk_used_gb",
            "network_sent_bytes",
            "network_recv_bytes",
        ]

        for sensor in old_sensors:
            # Old discovery topic patterns (try multiple possible old formats)
            old_topic_1 = f"{self.discovery.broker.discovery_prefix}/sensor/{self.device_id}_{sensor}/config"
            old_topic_2 = f"{self.discovery.broker.discovery_prefix}/sensor/{self.device_id}_{sensor}/state/config"

            # Publish empty payload to delete
            self.discovery.broker.client.publish(old_topic_1, payload="", retain=True)
            self.discovery.broker.client.publish(old_topic_2, payload="", retain=True)
            logger.debug(f"Cleaned up old discovery: {sensor}")

        logger.info("Cleaned up old discovery configurations")

    def start(self, stop_event: threading.Event) -> None:
        """Start the monitoring loop.

        Publishes Home Assistant discovery configuration once on startup,
        then enters a loop collecting and publishing metrics until stop_event
        is set. The monitor publishes availability status and handles errors
        gracefully without crashing the monitoring thread.

        Args:
            stop_event: Event to signal monitoring should stop.

        Example:
            >>> monitor = SystemMonitor(collector, broker, discovery, "my_pc", "desktop/my_pc")
            >>> stop_event = threading.Event()
            >>> # Start monitoring in background
            >>> threading.Thread(target=monitor.start, args=(stop_event,), daemon=True).start()
            >>> # Later, stop monitoring
            >>> stop_event.set()
        """
        logger.info("System monitor started")

        try:
            # Clean up old discovery configurations
            self._cleanup_old_discovery()

            # Publish discovery configuration once at startup
            self._publish_discovery()

            # Publish availability
            self.broker.publish_availability("online")

            # Main monitoring loop
            while not stop_event.is_set():
                try:
                    self._collect_and_publish()
                except Exception as e:
                    logger.error(
                        f"Error collecting/publishing metrics: {e}", exc_info=True
                    )

                # Wait for interval or stop signal
                stop_event.wait(self.interval)

        except Exception as e:
            logger.critical(f"Fatal error in system monitor: {e}", exc_info=True)
        finally:
            # Publish offline status on shutdown
            try:
                self.broker.publish_availability("offline")
            except Exception as e:
                logger.error(f"Error publishing offline status: {e}")

            logger.info("System monitor stopped")

    def _publish_discovery(self) -> None:
        """Publish Home Assistant discovery configurations for all sensors.

        This method publishes discovery configurations for all system metrics
        that will be monitored. It's called once at startup to register all
        entities with Home Assistant.

        The discovery configurations include:
        - System info sensors (hostname, OS, uptime)
        - CPU sensors (usage, model, frequency, cores)
        - Memory sensors (usage, total, used)
        - Disk sensors (usage, total, used)
        - Network sensors (sent, received)
        - GPU sensors (if available)
        - Temperature sensors (if available)
        """
        try:
            # Host info sensors
            self._publish_sensor_with_json(
                "hostname",
                "Hostname",
                "hostname",
                icon="mdi:information",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "uptime",
                "Uptime",
                "uptime_seconds",
                unit="s",
                icon="mdi:clock-outline",
                entity_category="diagnostic",
                state_class="total_increasing",
            )

            self._publish_sensor_with_json(
                "os",
                "Operating System",
                "os",
                icon="mdi:desktop-classic",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "os_version",
                "OS Version",
                "os_version",
                icon="mdi:information",
                entity_category="diagnostic",
            )

            # CPU sensors
            self._publish_sensor_with_json(
                "cpu_model",
                "CPU Model",
                "cpu_model",
                icon="mdi:cpu-64-bit",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "cpu_usage",
                "CPU Usage",
                "cpu_usage",
                unit="%",
                icon="mdi:chip",
                entity_category="diagnostic",
                state_class="measurement",
            )

            self._publish_sensor_with_json(
                "cpu_cores",
                "CPU Cores",
                "cpu_cores",
                icon="mdi:chip",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "cpu_frequency_mhz",
                "CPU Frequency",
                "cpu_frequency_mhz",
                unit="MHz",
                icon="mdi:chip",
                entity_category="diagnostic",
                state_class="measurement",
            )

            # Memory sensors
            self._publish_sensor_with_json(
                "memory_usage",
                "Memory Usage",
                "memory_usage",
                unit="%",
                icon="mdi:memory",
                entity_category="diagnostic",
                state_class="measurement",
            )

            self._publish_sensor_with_json(
                "memory_total",
                "Memory Total",
                "memory_total_gb",
                unit="GB",
                icon="mdi:memory",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "memory_used",
                "Memory Used",
                "memory_used_gb",
                unit="GB",
                icon="mdi:memory",
                entity_category="diagnostic",
                state_class="measurement",
            )

            # Disk sensors
            self._publish_sensor_with_json(
                "disk_usage",
                "Disk Usage",
                "disk_usage",
                unit="%",
                icon="mdi:harddisk",
                entity_category="diagnostic",
                state_class="measurement",
            )

            self._publish_sensor_with_json(
                "disk_total",
                "Disk Total",
                "disk_total_gb",
                unit="GB",
                icon="mdi:harddisk",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "disk_used",
                "Disk Used",
                "disk_used_gb",
                unit="GB",
                icon="mdi:harddisk",
                entity_category="diagnostic",
                state_class="measurement",
            )

            # Network sensors
            self._publish_sensor_with_json(
                "network_sent",
                "Network Sent",
                "network_sent_bytes",
                icon="mdi:upload-network",
                entity_category="diagnostic",
            )

            self._publish_sensor_with_json(
                "network_received",
                "Network Received",
                "network_recv_bytes",
                icon="mdi:download-network",
                entity_category="diagnostic",
            )

            # GPU sensors (dynamically discovered during collection)
            # Temperature sensors (dynamically discovered during collection)
            # These will be published during first collection if available

            logger.info("Published discovery configurations for system sensors")

        except Exception as e:
            logger.error(f"Error publishing discovery: {e}", exc_info=True)

    def _clean_value(self, value: Any) -> Optional[Any]:
        """Clean a value for JSON serialization.

        Handles NaN and Infinity values which are not valid in JSON.
        Also handles None values appropriately.

        Args:
            value: Value to clean.

        Returns:
            Cleaned value, or None if value is invalid.

        Example:
            >>> monitor._clean_value(float('nan'))
            None
            >>> monitor._clean_value(42.5)
            42.5
        """
        if value is None:
            return None

        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None

        return value

    def _collect_and_publish(self) -> None:
        """Collect current system metrics and publish to MQTT.

        This method collects all available system metrics using the collector
        and publishes them as a combined JSON status message. All sensors
        extract their values from this JSON using value_template in their
        discovery configurations.

        The method handles dynamic discovery of GPU and temperature sensors,
        publishing their discovery configurations on first detection.
        """
        try:
            # Collect all system data
            raw_data = self.collector.collect_all()

            # Clean all values (remove NaN, Inf)
            cleaned_data = {
                key: self._clean_value(value) for key, value in raw_data.items()
            }

            # Publish combined JSON status message
            status_payload = json.dumps(cleaned_data)
            self.broker.client.publish(
                f"{self.base_topic}/status", payload=status_payload, qos=1, retain=True
            )

            # Handle dynamic sensor discovery (GPU and temperature sensors)
            # Note: We don't publish individual states - sensors use value_json templates
            for key, value in cleaned_data.items():
                if value is not None:
                    # Check if this is a new dynamic sensor (GPU or temperature)
                    # that needs discovery configuration
                    if key.startswith("gpu") or (
                        key
                        not in [
                            "hostname",
                            "uptime_seconds",
                            "os",
                            "os_version",
                            "cpu_model",
                            "cpu_usage",
                            "cpu_cores",
                            "cpu_frequency_mhz",
                            "memory_usage",
                            "memory_total_gb",
                            "memory_used_gb",
                            "disk_usage",
                            "disk_total_gb",
                            "disk_used_gb",
                            "network_sent_bytes",
                            "network_recv_bytes",
                        ]
                    ):
                        # This is a dynamic sensor, publish discovery if not already done
                        self._publish_dynamic_sensor_discovery(key, value)

            # Update availability
            self.broker.publish_availability("online")

            logger.debug("Published system metrics")

        except Exception as e:
            logger.error(f"Error in collect and publish: {e}", exc_info=True)

    def _publish_dynamic_sensor_discovery(self, key: str, value: Any) -> None:
        """Publish discovery for dynamically detected sensors.

        Some sensors (GPU, temperatures) are only detected at runtime.
        This method publishes discovery configurations for these sensors
        when they are first detected.

        Args:
            key: Sensor key/identifier.
            value: Sensor value (used to determine sensor type).
        """
        try:
            unique_id = f"{self.device_id}_{key}"

            config = {
                "name": key.replace("_", " ").title(),
                "state_topic": f"{self.base_topic}/status",
                "value_template": f"{{{{ value_json.{key} }}}}",
                "unique_id": unique_id,
                "object_id": f"{self.device_id}_{key}",
                "device": self.discovery.device_info,
                "availability_topic": f"{self.base_topic}/availability",
            }

            # Add type-specific configuration based on sensor key
            if key.startswith("gpu"):
                if "name" in key:
                    config["icon"] = "mdi:expansion-card"
                    config["entity_category"] = "diagnostic"
                elif "load_percent" in key or "usage" in key:
                    config["unit_of_measurement"] = "%"
                    config["icon"] = "mdi:expansion-card"
                    config["entity_category"] = "diagnostic"
                    config["state_class"] = "measurement"
                elif "temperature" in key:
                    config["unit_of_measurement"] = "°C"
                    config["icon"] = "mdi:thermometer"
                    config["entity_category"] = "diagnostic"
                    config["state_class"] = "measurement"
                elif "memory" in key:
                    config["unit_of_measurement"] = "GB"
                    config["icon"] = "mdi:expansion-card"
                    config["entity_category"] = "diagnostic"
                    config["state_class"] = "measurement"
            elif "temperature" in key or key.endswith("_c"):
                config["unit_of_measurement"] = "°C"
                config["icon"] = "mdi:thermometer"
                config["entity_category"] = "diagnostic"
                config["state_class"] = "measurement"

            # Publish discovery with nested topic structure
            topic = f"{self.discovery.broker.discovery_prefix}/sensor/{self.device_id}/{key}/config"
            payload = json.dumps(config)
            self.discovery.broker.client.publish(
                topic, payload=payload, qos=0, retain=True
            )

            logger.debug(f"Published dynamic sensor discovery: {key}")

        except Exception as e:
            logger.debug(f"Error publishing dynamic sensor discovery for {key}: {e}")
