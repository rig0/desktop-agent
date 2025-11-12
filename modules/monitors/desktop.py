"""Desktop system monitoring implementation.

This module provides the DesktopMonitor class which coordinates system
data collection and publishing to MQTT for Home Assistant integration.
It runs in a monitoring loop, periodically collecting metrics and publishing
them along with Home Assistant discovery configurations.
"""

import json
import logging
import math
import threading
from typing import Any, Dict, Optional

from modules.collectors.system import SystemInfoCollector
from modules.core.discovery import DiscoveryManager
from modules.core.messaging import MessageBroker


logger = logging.getLogger(__name__)


class DesktopMonitor:
    """Monitors desktop system metrics and publishes to MQTT.

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
        >>> monitor = DesktopMonitor(collector, broker, discovery, "my_pc", "desktop/my_pc", interval=10)
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
        interval: int = 10
    ):
        """Initialize desktop monitor.

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
        logger.debug(f"DesktopMonitor initialized with interval={interval}s")

    def start(self, stop_event: threading.Event) -> None:
        """Start the monitoring loop.

        Publishes Home Assistant discovery configuration once on startup,
        then enters a loop collecting and publishing metrics until stop_event
        is set. The monitor publishes availability status and handles errors
        gracefully without crashing the monitoring thread.

        Args:
            stop_event: Event to signal monitoring should stop.

        Example:
            >>> monitor = DesktopMonitor(collector, broker, discovery, "my_pc", "desktop/my_pc")
            >>> stop_event = threading.Event()
            >>> # Start monitoring in background
            >>> threading.Thread(target=monitor.start, args=(stop_event,), daemon=True).start()
            >>> # Later, stop monitoring
            >>> stop_event.set()
        """
        logger.info("Desktop monitor started")

        try:
            # Publish discovery configuration once at startup
            self._publish_discovery()

            # Publish availability
            self.broker.publish_availability("online")

            # Main monitoring loop
            while not stop_event.is_set():
                try:
                    self._collect_and_publish()
                except Exception as e:
                    logger.error(f"Error collecting/publishing metrics: {e}", exc_info=True)

                # Wait for interval or stop signal
                stop_event.wait(self.interval)

        except Exception as e:
            logger.critical(f"Fatal error in desktop monitor: {e}", exc_info=True)
        finally:
            # Publish offline status on shutdown
            try:
                self.broker.publish_availability("offline")
            except Exception as e:
                logger.error(f"Error publishing offline status: {e}")

            logger.info("Desktop monitor stopped")

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
            self.discovery.publish_sensor(
                "hostname",
                "Hostname",
                icon="mdi:information",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "uptime_seconds",
                "Uptime",
                unit="s",
                icon="mdi:clock-outline",
                entity_category="diagnostic",
                state_class="total_increasing"
            )

            self.discovery.publish_sensor(
                "os",
                "Operating System",
                icon="mdi:desktop-classic",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "os_version",
                "OS Version",
                icon="mdi:information",
                entity_category="diagnostic"
            )

            # CPU sensors
            self.discovery.publish_sensor(
                "cpu_model",
                "CPU Model",
                icon="mdi:cpu-64-bit",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "cpu_usage",
                "CPU Usage",
                unit="%",
                icon="mdi:chip",
                entity_category="diagnostic",
                state_class="measurement"
            )

            self.discovery.publish_sensor(
                "cpu_cores",
                "CPU Cores",
                icon="mdi:chip",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "cpu_frequency_mhz",
                "CPU Frequency",
                unit="MHz",
                icon="mdi:chip",
                entity_category="diagnostic",
                state_class="measurement"
            )

            # Memory sensors
            self.discovery.publish_sensor(
                "memory_usage",
                "Memory Usage",
                unit="%",
                icon="mdi:memory",
                entity_category="diagnostic",
                state_class="measurement"
            )

            self.discovery.publish_sensor(
                "memory_total_gb",
                "Memory Total",
                unit="GB",
                icon="mdi:memory",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "memory_used_gb",
                "Memory Used",
                unit="GB",
                icon="mdi:memory",
                entity_category="diagnostic",
                state_class="measurement"
            )

            # Disk sensors
            self.discovery.publish_sensor(
                "disk_usage",
                "Disk Usage",
                unit="%",
                icon="mdi:harddisk",
                entity_category="diagnostic",
                state_class="measurement"
            )

            self.discovery.publish_sensor(
                "disk_total_gb",
                "Disk Total",
                unit="GB",
                icon="mdi:harddisk",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "disk_used_gb",
                "Disk Used",
                unit="GB",
                icon="mdi:harddisk",
                entity_category="diagnostic",
                state_class="measurement"
            )

            # Network sensors
            self.discovery.publish_sensor(
                "network_sent_bytes",
                "Network Sent",
                icon="mdi:upload-network",
                entity_category="diagnostic"
            )

            self.discovery.publish_sensor(
                "network_recv_bytes",
                "Network Received",
                icon="mdi:download-network",
                entity_category="diagnostic"
            )

            # GPU sensors (dynamically discovered during collection)
            # Temperature sensors (dynamically discovered during collection)
            # These will be published during first collection if available

            logger.info("Published discovery configurations for desktop sensors")

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
        and publishes them to MQTT. The data is published both as individual
        state topics and as a combined JSON status message for compatibility
        with the existing implementation.

        The method handles dynamic discovery of GPU and temperature sensors,
        publishing their discovery configurations on first detection.
        """
        try:
            # Collect all system data
            raw_data = self.collector.collect_all()

            # Clean all values (remove NaN, Inf)
            cleaned_data = {
                key: self._clean_value(value)
                for key, value in raw_data.items()
            }

            # Publish combined status message (for compatibility with existing setup)
            status_payload = json.dumps(cleaned_data)
            self.broker.client.publish(
                f"{self.base_topic}/status",
                payload=status_payload,
                qos=1,
                retain=True
            )

            # Also publish individual state topics for each metric
            for key, value in cleaned_data.items():
                if value is not None:
                    # Check if this is a new dynamic sensor (GPU or temperature)
                    # that needs discovery configuration
                    if key.startswith("gpu") or (
                        key not in ["hostname", "uptime_seconds", "os", "os_version",
                                   "cpu_model", "cpu_usage", "cpu_cores", "cpu_frequency_mhz",
                                   "memory_usage", "memory_total_gb", "memory_used_gb",
                                   "disk_usage", "disk_total_gb", "disk_used_gb",
                                   "network_sent_bytes", "network_recv_bytes"]
                    ):
                        # This is a dynamic sensor, publish discovery if not already done
                        self._publish_dynamic_sensor_discovery(key, value)

                    # Publish state
                    self.broker.publish_state(key, str(value))

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
            # Determine sensor properties based on key
            if key.startswith("gpu"):
                # GPU sensor
                if "name" in key:
                    self.discovery.publish_sensor(
                        key,
                        key.replace("_", " ").title(),
                        icon="mdi:expansion-card",
                        entity_category="diagnostic"
                    )
                elif "load_percent" in key or "usage" in key:
                    self.discovery.publish_sensor(
                        key,
                        key.replace("_", " ").title(),
                        unit="%",
                        icon="mdi:expansion-card",
                        entity_category="diagnostic",
                        state_class="measurement"
                    )
                elif "temperature" in key:
                    self.discovery.publish_sensor(
                        key,
                        key.replace("_", " ").title(),
                        unit="°C",
                        device_class="temperature",
                        icon="mdi:thermometer",
                        entity_category="diagnostic",
                        state_class="measurement"
                    )
                elif "memory" in key:
                    self.discovery.publish_sensor(
                        key,
                        key.replace("_", " ").title(),
                        unit="GB",
                        icon="mdi:expansion-card",
                        entity_category="diagnostic",
                        state_class="measurement"
                    )
            elif "temperature" in key or key.endswith("_c"):
                # Temperature sensor
                self.discovery.publish_sensor(
                    key,
                    key.replace("_", " ").title(),
                    unit="°C",
                    device_class="temperature",
                    icon="mdi:thermometer",
                    entity_category="diagnostic",
                    state_class="measurement"
                )
            else:
                # Generic sensor
                logger.debug("Skipping generic temperature sensors")
                # self.discovery.publish_sensor(
                #     key,
                #     key.replace("_", " ").title(),
                #     unit="°C",
                #     device_class="temperature",
                #     icon="mdi:thermometer",
                #     entity_category="diagnostic"
                # )

            logger.debug(f"Published dynamic sensor discovery: {key}")

        except Exception as e:
            logger.debug(f"Error publishing dynamic sensor discovery for {key}: {e}")
