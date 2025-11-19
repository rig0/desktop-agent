"""
Media playback monitoring module.

This module provides the MediaMonitor class which monitors media playback
and publishes state, attributes, and thumbnails to MQTT for Home Assistant
integration.

Example:
    >>> from modules.collectors.media import MediaCollector
    >>> from modules.monitors.media import MediaMonitor
    >>> from modules.core.messaging import MessageBroker
    >>> from modules.core.discovery import DiscoveryManager
    >>>
    >>> collector = MediaCollector()
    >>> monitor = MediaMonitor(collector, broker, discovery)
    >>> stop_event = threading.Event()
    >>> monitor.start(stop_event)
"""

# Standard library imports
import json
import logging
import threading

# import time
from pathlib import Path
from typing import Optional

# Local imports
from modules.collectors.media import MediaCollector
from modules.core.config import (
    DEVICE_NAME,
    base_topic,
    device_id,
    device_info,
    discovery_prefix,
)
from modules.core.discovery import DiscoveryManager
from modules.core.messaging import MessageBroker

# Configure logger
logger = logging.getLogger(__name__)


class MediaMonitor:
    """
    Monitors media playback and publishes to MQTT.

    This class polls for media playback changes, and publishes state updates,
    attributes, and thumbnails to MQTT topics for Home Assistant integration.

    Attributes:
        collector: MediaCollector instance for data collection
        broker: MessageBroker instance for MQTT publishing
        discovery: DiscoveryManager for publishing HA discovery configs
        poll_interval: Seconds between checks (default: 5)
    """

    def __init__(
        self,
        collector: MediaCollector,
        broker: MessageBroker,
        discovery: DiscoveryManager,
        poll_interval: int = 5,
    ):
        """
        Initialize the MediaMonitor.

        Args:
            collector: MediaCollector instance for data collection
            broker: MessageBroker instance for MQTT publishing
            discovery: DiscoveryManager for HA discovery publishing
            poll_interval: Seconds between polling (default: 5)
        """
        self.collector = collector
        self.broker = broker
        self.discovery = discovery
        self.poll_interval = poll_interval

        # Track last known state to avoid redundant publishing
        self.last_attrs = None
        self.last_image = None

        # Placeholder image paths
        base_dir = Path(__file__).parent.parent.parent
        self.placeholder_path = base_dir / "resources" / "media_thumb.png"
        self.placeholder_path_custom = (
            base_dir / "data" / "media_monitor" / "media_thumb.png"
        )

    def start(self, stop_event: threading.Event) -> None:
        """
        Start the media monitoring loop.

        Publishes Home Assistant discovery configs on startup, then enters
        a polling loop that monitors media playback and publishes updates
        to MQTT.

        Args:
            stop_event: Threading event to signal shutdown

        Example:
            >>> monitor = MediaMonitor(collector, broker, discovery)
            >>> stop_event = threading.Event()
            >>> threading.Thread(target=monitor.start, args=(stop_event,)).start()
        """
        logger.info("Media monitor started")

        try:
            # Publish discovery configs on startup
            self._publish_discovery()

            # Main polling loop
            while not stop_event.is_set():
                try:
                    self._poll_and_publish()
                except Exception as e:
                    logger.error(f"Error in media monitor poll: {e}", exc_info=True)

                # Sleep but allow interruption
                stop_event.wait(self.poll_interval)

        except Exception as e:
            logger.critical(f"Fatal error in media monitor: {e}", exc_info=True)
        finally:
            logger.info("Media monitor stopped")

    def _poll_and_publish(self) -> None:
        """
        Poll for media changes and publish updates if needed.

        Checks for current media playback, and publishes state, attributes,
        and thumbnails to MQTT if changes detected.
        """
        # Get current media info
        info = self.collector.get_media_info()

        if info:
            # Determine state based on playback status
            if info["is_playing"]:
                state = "playing"
            elif (
                isinstance(info["playback_status"], str)
                and info["playback_status"].lower() == "paused"
            ):
                state = "paused"
            elif (
                isinstance(info["playback_status"], int) and info["playback_status"] == 5
            ):
                state = "paused"  # Windows status code 5 = Paused
            else:
                state = "idle"

            # Build attributes
            attrs = {
                "title": info["title"],
                "artist": info["artist"],
                "album": info["album"],
                "status": state,
            }

            # Publish state
            self.broker.publish_state("media", state)
            logger.debug(f"Published media state: {state}")

            # Publish attributes if changed
            if attrs != self.last_attrs:
                self.broker.publish_attributes("media", attrs)
                self.last_attrs = attrs
                logger.debug("Published media attributes")

            # Handle thumbnail
            thumbnail_bytes = info.get("thumbnail_bytes")

            # Use placeholder if no thumbnail available
            if not thumbnail_bytes:
                thumbnail_bytes = self._load_placeholder()

            # Only publish if image changed
            if thumbnail_bytes and thumbnail_bytes != self.last_image:
                topic = f"{base_topic}/media/thumbnail"
                self.broker.client.publish(topic, thumbnail_bytes, retain=True)
                self.last_image = thumbnail_bytes
                logger.debug("Published media thumbnail")

    def _load_placeholder(self) -> Optional[bytes]:
        """
        Load placeholder thumbnail image.

        Tries to load custom placeholder first, then falls back to default.

        Returns:
            Placeholder image as bytes, or None if unavailable.
        """
        # Try custom placeholder first
        if self.placeholder_path_custom.exists():
            try:
                with open(self.placeholder_path_custom, "rb") as f:
                    return f.read()
            except (IOError, OSError) as e:
                logger.debug(f"No custom thumbnail detected: {e}")

        # Fallback to default placeholder
        if self.placeholder_path.exists():
            try:
                with open(self.placeholder_path, "rb") as f:
                    return f.read()
            except (IOError, OSError) as e:
                logger.error(f"Failed to load default placeholder thumbnail: {e}")

        return None

    def _cleanup_old_camera_discovery(self) -> None:
        """
        Remove old camera discovery configurations with invalid nested topics.

        This publishes empty retained messages to old camera discovery topics
        that used slashes in the object_id segment (which is invalid).
        """
        # Old broken discovery topic with slashes in object_id
        old_topic = f"{discovery_prefix}/camera/{device_id}/media/thumbnail/config"
        self.broker.client.publish(old_topic, payload="", retain=True)
        logger.debug("Cleaned up old media camera discovery topic")

    def _publish_discovery(self) -> None:
        """
        Publish Home Assistant MQTT discovery configs.

        Publishes discovery for:
        - Media status sensor (with attributes)
        - Media thumbnail camera entity
        """
        try:
            # Clean up old broken camera discovery
            self._cleanup_old_camera_discovery()
            # Media status sensor
            sensor_config = {
                "name": "Media Status",
                "state_topic": f"{base_topic}/media/state",
                "icon": "mdi:multimedia",
                "unique_id": f"{device_id}_media_status",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "json_attributes_topic": f"{base_topic}/media/attrs",
            }

            topic = f"{discovery_prefix}/sensor/{device_id}/media_status/config"
            self.broker.client.publish(topic, json.dumps(sensor_config), retain=True)
            logger.debug("Published discovery for media status sensor")

            # Media thumbnail camera
            camera_config = {
                "name": f"{DEVICE_NAME} Media",
                "unique_id": f"{device_id}_media_thumbnail",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "topic": f"{base_topic}/media/thumbnail",
                "icon": "mdi:music",
            }

            # Discovery topic - object_id cannot contain slashes
            topic = f"{discovery_prefix}/camera/{device_id}/media_thumbnail/config"
            self.broker.client.publish(topic, json.dumps(camera_config), retain=True)
            logger.debug("Published discovery for media camera")

            logger.info("Published discovery for media monitor entities")

        except Exception as e:
            logger.error(f"Error publishing media monitor discovery: {e}", exc_info=True)
