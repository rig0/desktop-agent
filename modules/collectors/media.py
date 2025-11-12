"""
Media playback information collection module.

This module provides the MediaCollector class for gathering media playback
information from platform-specific APIs (Windows SMTC, Linux MPRIS). It
provides a unified interface regardless of the underlying platform.

Example:
    >>> from modules.collectors.media import MediaCollector
    >>> collector = MediaCollector()
    >>> media_info = collector.get_media_info()
    >>> if media_info:
    ...     print(f"Now playing: {media_info['title']} by {media_info['artist']}")
"""

# Standard library imports
import asyncio
import logging
import os
from typing import Dict, Any, Optional

# Third-party imports
import requests

# Local imports
from modules.utils.platform import PlatformUtils

# Configure logger
logger = logging.getLogger(__name__)


class MediaCollector:
    """
    Collects media playback information from platform-specific APIs.

    Provides a unified interface for gathering media information regardless
    of platform. On Windows, uses System Media Transport Controls (SMTC).
    On Linux, uses MPRIS D-Bus interface.

    Attributes:
        platform: Platform identifier ("windows" or "linux")
        platform_utils: PlatformUtils instance for platform detection
    """

    def __init__(self):
        """Initialize the MediaCollector with platform detection."""
        self.platform_utils = PlatformUtils()
        self.platform = self.platform_utils.get_platform()
        logger.debug(f"MediaCollector initialized for platform: {self.platform}")

    def get_media_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current media playback information.

        Returns media information from the appropriate platform-specific
        implementation. The returned dictionary has a consistent structure
        regardless of platform.

        Returns:
            Dictionary containing:
            - title: Song/video title
            - artist: Artist name
            - album: Album name
            - is_playing: Boolean indicating if media is playing
            - playback_status: Status string or code
            - thumbnail_bytes: Artwork/thumbnail as bytes (or None)

            Returns None if no media is playing or on error.

        Example:
            >>> collector = MediaCollector()
            >>> info = collector.get_media_info()
            >>> if info and info["is_playing"]:
            ...     print(f"Playing: {info['title']}")
        """
        try:
            if self.platform == "windows":
                return self._get_media_info_windows()
            elif self.platform == "linux":
                return self._get_media_info_linux()
            else:
                logger.warning(f"Unsupported platform for media collection: {self.platform}")
                return None
        except Exception as e:
            logger.error(f"Error getting media info: {e}", exc_info=True)
            return None

    def _get_media_info_windows(self) -> Optional[Dict[str, Any]]:
        """
        Get media information from Windows SMTC API.

        Uses the System Media Transport Controls API to gather information
        about currently playing media on Windows.

        Returns:
            Dictionary with media information, or None if unavailable.
        """
        try:
            # Import Windows-specific modules
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            )
            from winsdk.windows.storage.streams import DataReader

            # Run async function to get media info
            return asyncio.run(self._get_media_info_windows_async())

        except ImportError as e:
            logger.error(f"Windows media modules not available: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting Windows media info: {e}", exc_info=True)
            return None

    async def _get_media_info_windows_async(self) -> Optional[Dict[str, Any]]:
        """
        Async helper for Windows media information retrieval.

        Returns:
            Dictionary with media information, or None if unavailable.
        """
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            )
            from winsdk.windows.storage.streams import DataReader

            sessions = await MediaManager.request_async()
            current = sessions.get_current_session()
            if not current:
                return None

            props = await current.try_get_media_properties_async()
            title = getattr(props, "title", "") or ""
            artist = getattr(props, "artist", "") or ""
            album = getattr(props, "album_title", "") or ""

            # Get thumbnail bytes if available
            thumbnail_bytes = None
            if getattr(props, "thumbnail", None) is not None:
                try:
                    stream = await props.thumbnail.open_read_async()
                    size = int(stream.size or 0)
                    if size > 0:
                        input_stream = stream.get_input_stream_at(0)
                        reader = DataReader(input_stream)
                        await reader.load_async(size)
                        buffer = reader.read_buffer(size)
                        byte_array = bytearray(size)
                        DataReader.from_buffer(buffer).read_bytes(byte_array)
                        thumbnail_bytes = bytes(byte_array)
                except Exception as e:
                    logger.error(f"Failed to read thumbnail: {e}", exc_info=True)

            playback = current.get_playback_info()
            status = int(playback.playback_status)
            is_playing = status == 4  # 4 = Playing

            return {
                "title": title,
                "artist": artist,
                "album": album,
                "is_playing": is_playing,
                "playback_status": status,
                "thumbnail_bytes": thumbnail_bytes
            }

        except Exception as e:
            logger.error(f"Error in Windows async media info: {e}", exc_info=True)
            return None

    def _get_media_info_linux(self) -> Optional[Dict[str, Any]]:
        """
        Get media information from Linux MPRIS D-Bus interface.

        Uses the MPRIS (Media Player Remote Interfacing Specification) via
        D-Bus to gather information about currently playing media on Linux.

        Returns:
            Dictionary with media information, or None if unavailable.
        """
        try:
            # Import Linux-specific modules
            from pydbus import SessionBus

            bus = SessionBus()
            dbus = bus.get("org.freedesktop.DBus", "/org/freedesktop/DBus")
            players = [
                name for name in dbus.ListNames()
                if name.startswith("org.mpris.MediaPlayer2.")
            ]

            if not players:
                return None

            selected_player = None

            # Find a player that is currently playing
            for name in players:
                player = bus.get(name, "/org/mpris/MediaPlayer2")
                if getattr(player, "PlaybackStatus", "").lower() == "playing":
                    selected_player = player
                    break

            # If none are playing, fallback to first available
            if not selected_player:
                selected_player = bus.get(players[0], "/org/mpris/MediaPlayer2")

            metadata = selected_player.Metadata
            status = selected_player.PlaybackStatus

            title = metadata.get("xesam:title", "")
            artist_list = metadata.get("xesam:artist", [])
            artist = ", ".join(artist_list) if artist_list else ""
            album = metadata.get("xesam:album", "")
            is_playing = status.lower() == "playing"

            # Get thumbnail from art URL
            thumbnail_bytes = None
            art_url = metadata.get("mpris:artUrl")
            if art_url:
                try:
                    if art_url.startswith("file://"):
                        # Local file
                        path = art_url[7:]
                        if os.path.exists(path):
                            with open(path, "rb") as f:
                                thumbnail_bytes = f.read()
                    else:
                        # Remote URL
                        resp = requests.get(art_url, timeout=5)
                        if resp.ok:
                            thumbnail_bytes = resp.content
                except (IOError, OSError) as e:
                    logger.error(f"Failed to read artwork from file: {e}")
                except requests.RequestException as e:
                    logger.error(f"Failed to fetch artwork from URL: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error fetching artwork: {e}", exc_info=True)

            return {
                "title": title,
                "artist": artist,
                "album": album,
                "is_playing": is_playing,
                "playback_status": status,
                "thumbnail_bytes": thumbnail_bytes
            }

        except ImportError as e:
            logger.error(f"Linux media modules not available (pydbus): {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting Linux media info: {e}", exc_info=True)
            return None
