"""
Game monitoring module.

This module provides the GameMonitor class which monitors game activity
and publishes state, attributes, and artwork to MQTT for Home Assistant
integration.

Example:
    >>> from modules.collectors.game import GameCollector
    >>> from modules.monitors.game import GameMonitor
    >>> from modules.core.messaging import MessageBroker
    >>> from modules.core.discovery import DiscoveryManager
    >>>
    >>> collector = GameCollector("/path/to/game.txt")
    >>> monitor = GameMonitor(collector, broker, discovery, "/path/to/game.txt")
    >>> stop_event = threading.Event()
    >>> monitor.start(stop_event)
"""

# Standard library imports
import json
import logging
import threading

# Local imports
from modules.collectors.game import GameCollector
from modules.core.config import base_topic, device_id, device_info, discovery_prefix
from modules.core.discovery import DiscoveryManager
from modules.core.messaging import MessageBroker

# Configure logger
logger = logging.getLogger(__name__)


class GameMonitor:
    """
    Monitors game activity and publishes to MQTT.

    This class polls a game file for changes, fetches game metadata,
    and publishes state updates, attributes, and artwork to MQTT topics
    for Home Assistant integration.

    Attributes:
        collector: GameCollector instance for data collection
        broker: MessageBroker instance for MQTT publishing
        discovery: DiscoveryManager for publishing HA discovery configs
        game_file_path: Path to the file being monitored
        poll_interval: Seconds between checks (default: 3)
    """

    def __init__(
        self,
        collector: GameCollector,
        broker: MessageBroker,
        discovery: DiscoveryManager,
        game_file_path: str,
        poll_interval: int = 3,
    ):
        """
        Initialize the GameMonitor.

        Args:
            collector: GameCollector instance for data collection
            broker: MessageBroker instance for MQTT publishing
            discovery: DiscoveryManager for HA discovery publishing
            game_file_path: Path to file containing current game name
            poll_interval: Seconds between polling (default: 3)
        """
        self.collector = collector
        self.broker = broker
        self.discovery = discovery
        self.game_file_path = game_file_path
        self.poll_interval = poll_interval

        # Track last known state to avoid redundant publishing
        self.last_attrs = None
        self.last_known_game_name = None
        self.last_cover = None
        self.last_artwork = None
        self.last_state = "idle"  # Track last published state

    def start(self, stop_event: threading.Event) -> None:
        """
        Start the game monitoring loop.

        Publishes Home Assistant discovery configs on startup, then enters
        a polling loop that monitors the game file for changes and publishes
        updates to MQTT.

        Args:
            stop_event: Threading event to signal shutdown

        Example:
            >>> monitor = GameMonitor(collector, broker, discovery, "/path/to/game.txt")
            >>> stop_event = threading.Event()
            >>> threading.Thread(target=monitor.start, args=(stop_event,)).start()
        """
        logger.info("Game monitor started")

        try:
            # Publish discovery configs on startup
            self._publish_discovery()

            # Ensure idle state on startup
            self.broker.publish_state("game", "idle")
            logger.debug("Published initial idle state")

            # Main polling loop
            while not stop_event.is_set():
                try:
                    self._poll_and_publish()
                except Exception as e:
                    logger.error(f"Error in game monitor poll: {e}", exc_info=True)

                # Sleep but allow interruption
                stop_event.wait(self.poll_interval)

        except Exception as e:
            logger.critical(f"Fatal error in game monitor: {e}", exc_info=True)
        finally:
            logger.info("Game monitor stopped")

    def _poll_and_publish(self) -> None:
        """
        Poll for game changes and publish updates if needed.

        Checks the game file for the current game, fetches metadata if the
        game changed, and publishes state, attributes, and artwork to MQTT.
        """
        # Get current game name from file
        game_name = self.collector.get_current_game()

        # Check if game changed
        if game_name and game_name != self.last_known_game_name:
            logger.info(f"Game changed: {game_name}")

            # Fetch metadata and attributes
            game_info = self.collector.get_game_metadata(game_name)

            if not game_info:
                logger.warning(f"Could not fetch metadata for game: {game_name}")
                return

            attrs, images = self.collector.get_game_attributes(game_info)

            # Publish state
            state = "playing"
            self.broker.publish_state("game", state)
            self.last_state = state
            logger.debug(f"Published game state: {state}")

            # Publish attributes if changed
            if attrs != self.last_attrs:
                self.broker.publish_attributes("game", attrs)
                self.last_attrs = attrs
                logger.debug(f"Published game attributes for: {attrs['name']}")

            # Publish cover image if changed
            cover_bytes = images.get("cover")
            if cover_bytes and cover_bytes != self.last_cover:
                topic = f"{base_topic}/game/cover"
                self.broker.client.publish(topic, cover_bytes, retain=True)
                self.last_cover = cover_bytes
                logger.debug("Published game cover image")

            # Publish artwork image if changed
            artwork_bytes = images.get("artwork")
            if artwork_bytes and artwork_bytes != self.last_artwork:
                topic = f"{base_topic}/game/artwork"
                self.broker.client.publish(topic, artwork_bytes, retain=True)
                self.last_artwork = artwork_bytes
                logger.debug("Published game artwork image")

            self.last_known_game_name = game_name

        elif not game_name:
            # Game stopped - publish idle state if not already idle
            if self.last_state != "idle":
                logger.info("Game stopped, transitioning to idle state")
                self.broker.publish_state("game", "idle")
                self.last_state = "idle"
                logger.debug("Published idle state")

                # Clear attributes by publishing empty/idle attributes
                idle_attrs = {
                    "name": "",
                    "summary": "",
                    "release_date": "",
                    "genres": "",
                    "status": "idle",
                }
                self.broker.publish_attributes("game", idle_attrs)

                # Reset tracking variables
                self.last_attrs = idle_attrs
                self.last_cover = None
                self.last_artwork = None
                self.last_known_game_name = None
                logger.debug("Cleared game attributes")
            else:
                logger.debug("Already in idle state, no game detected")

    def _cleanup_old_camera_discovery(self) -> None:
        """
        Remove old camera discovery configurations with invalid nested topics.

        This publishes empty retained messages to old camera discovery topics
        that used slashes in the object_id segment (which is invalid).
        """
        # Old broken discovery topics with slashes in object_id
        old_cover_topic = f"{discovery_prefix}/camera/{device_id}/game/cover/config"
        old_artwork_topic = f"{discovery_prefix}/camera/{device_id}/game/artwork/config"

        self.broker.client.publish(old_cover_topic, payload="", retain=True)
        self.broker.client.publish(old_artwork_topic, payload="", retain=True)
        logger.debug("Cleaned up old game camera discovery topics")

    def _publish_discovery(self) -> None:
        """
        Publish Home Assistant MQTT discovery configs.

        Publishes discovery for:
        - Game status sensor (with attributes)
        - Game cover camera entity
        - Game artwork camera entity

        Note: The availability_topic ensures the sensor shows as unavailable
        when the device goes offline. On reconnection, the monitor will
        publish the current state (likely "idle" if no game is running).
        """
        try:
            # Clean up old broken camera discovery
            self._cleanup_old_camera_discovery()
            # Game status sensor
            sensor_config = {
                "name": "Game Status",
                "state_topic": f"{base_topic}/game/state",
                "json_attributes_topic": f"{base_topic}/game/attrs",
                "icon": "mdi:gamepad-variant",
                "unique_id": f"{device_id}_game_status",
                "object_id": f"{device_id}_game_status",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
            }

            topic = f"{discovery_prefix}/sensor/{device_id}/game_status/config"
            self.broker.client.publish(topic, json.dumps(sensor_config), retain=True)
            logger.debug("Published discovery for game status sensor")

            # Game cover camera
            cover_config = {
                "name": "Game Cover",
                "unique_id": f"{device_id}_game_cover",
                "object_id": f"{device_id}_game_cover",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "topic": f"{base_topic}/game/cover",
                "icon": "mdi:gamepad-variant",
            }

            # Discovery topic - object_id cannot contain slashes
            topic = f"{discovery_prefix}/camera/{device_id}/game_cover/config"
            self.broker.client.publish(topic, json.dumps(cover_config), retain=True)
            logger.debug("Published discovery for game cover camera")

            # Game artwork camera
            artwork_config = {
                "name": "Game Artwork",
                "unique_id": f"{device_id}_game_artwork",
                "object_id": f"{device_id}_game_artwork",
                "device": device_info,
                "availability_topic": f"{base_topic}/availability",
                "topic": f"{base_topic}/game/artwork",
                "icon": "mdi:gamepad-variant",
            }

            # Discovery topic - object_id cannot contain slashes
            topic = f"{discovery_prefix}/camera/{device_id}/game_artwork/config"
            self.broker.client.publish(topic, json.dumps(artwork_config), retain=True)
            logger.debug("Published discovery for game artwork camera")

            logger.info("Published discovery for game monitor entities")

        except Exception as e:
            logger.error(f"Error publishing game monitor discovery: {e}", exc_info=True)
