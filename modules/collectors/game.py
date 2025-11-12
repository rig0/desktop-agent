"""
Game information collection module.

This module provides the GameCollector class for gathering game information
including metadata from IGDB, playtime statistics, and artwork. It separates
data collection logic from publishing concerns.

Example:
    >>> from modules.collectors.game import GameCollector
    >>> collector = GameCollector("/path/to/game_file.txt")
    >>> game_info = collector.get_current_game()
    >>> if game_info:
    ...     print(game_info["name"])
    ...     metadata = collector.get_game_metadata(game_info["name"])
"""

# Standard library imports
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Third-party imports
import requests

# Local imports
from modules.core.config import IGDB_CLIENT, IGDB_TOKEN
from modules.utils.igdb import IGDBClient
from modules.utils.playtime import get_lutris_playtime

# Configure logger
logger = logging.getLogger(__name__)


class GameCollector:
    """
    Collects game information from file monitoring and external APIs.

    This class provides methods to read the current game from a file,
    fetch metadata from IGDB, retrieve playtime information, and download
    game artwork.

    Attributes:
        game_file_path: Path to the file containing the current game name
        igdb_client: IGDB API client for fetching game metadata
    """

    def __init__(self, game_file_path: str):
        """
        Initialize the GameCollector.

        Args:
            game_file_path: Path to file containing the current game name
        """
        self.game_file_path = game_file_path
        self.igdb_client = IGDBClient(IGDB_CLIENT, IGDB_TOKEN)

    def get_current_game(self) -> Optional[str]:
        """
        Read the current game name from the monitored file.

        Returns:
            Game name as string if file exists and contains valid data,
            None if file doesn't exist or is empty.

        Example:
            >>> collector = GameCollector("/path/to/game.txt")
            >>> game = collector.get_current_game()
            >>> if game:
            ...     print(f"Currently playing: {game}")
        """
        try:
            # Check if the file exists, and if not, create an empty file
            if not os.path.exists(self.game_file_path):
                os.makedirs(os.path.dirname(self.game_file_path), exist_ok=True)
                with open(self.game_file_path, 'w') as f:
                    pass  # Create an empty file
                logger.info(f"Created game file at {self.game_file_path}")
                return None

            # Read game name from file
            with open(self.game_file_path, 'r') as f:
                game_name = f.readline().strip()

            if not game_name or game_name.lower() == "unknown":
                return None

            return game_name

        except FileNotFoundError:
            logger.debug("Game name file not found")
            return None
        except (IOError, OSError) as e:
            logger.error(f"Error reading game file: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading game file: {e}", exc_info=True)
            return None

    def get_game_metadata(self, game_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch game metadata from IGDB API.

        Args:
            game_name: Name of the game to search for

        Returns:
            Dictionary containing game metadata including name, summary,
            release date, genres, developers, platforms, rating, cover,
            artwork, and URL. Returns None if game not found or on error.

        Example:
            >>> collector = GameCollector("/path/to/game.txt")
            >>> metadata = collector.get_game_metadata("Portal 2")
            >>> if metadata:
            ...     print(metadata["summary"])
            ...     print(metadata["genres"])
        """
        try:
            game_info = self.igdb_client.search_game(game_name)
            return game_info
        except requests.RequestException as e:
            logger.error(f"Network error fetching game metadata: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error fetching game metadata: {e}", exc_info=True)
            return None

    def get_game_artwork(
        self,
        img_dir: Optional[str],
        img_url: Optional[str]
    ) -> Optional[bytes]:
        """
        Retrieve game artwork as bytes.

        Tries to load from local cache first, then downloads from URL if needed.

        Args:
            img_dir: Path to cached image file
            img_url: URL to download image from if not cached

        Returns:
            Image data as bytes, or None if unavailable or on error.

        Example:
            >>> collector = GameCollector("/path/to/game.txt")
            >>> artwork = collector.get_game_artwork(
            ...     "/path/to/cache/cover.png",
            ...     "https://images.igdb.com/cover.png"
            ... )
            >>> if artwork:
            ...     print(f"Downloaded {len(artwork)} bytes")
        """
        img_bytes = None

        try:
            # Try to load from local cache first
            if img_dir and os.path.exists(img_dir):
                with open(img_dir, "rb") as f:
                    img_bytes = f.read()
                logger.debug(f"Loaded image from cache: {img_dir}")

            # Download from URL if not cached
            elif img_url:
                resp = requests.get(img_url, timeout=5)
                if resp.ok:
                    img_bytes = resp.content
                    logger.debug(f"Downloaded image from URL: {img_url}")
                else:
                    logger.warning(f"Failed to download image, status: {resp.status_code}")

        except (IOError, OSError) as e:
            logger.error(f"Failed to read cover image from file: {e}")
        except requests.RequestException as e:
            logger.error(f"Failed to fetch cover image from URL: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching cover: {e}", exc_info=True)

        return img_bytes

    def get_playtime(self, game_name: str) -> Optional[float]:
        """
        Get playtime for a game from Lutris database.

        Args:
            game_name: Name of the game

        Returns:
            Playtime in hours as float, or None if not available.

        Example:
            >>> collector = GameCollector("/path/to/game.txt")
            >>> playtime = collector.get_playtime("Portal 2")
            >>> if playtime:
            ...     print(f"Played for {playtime} hours")
        """
        try:
            playtime = get_lutris_playtime(game_name)
            return playtime
        except Exception as e:
            logger.error(f"Error getting playtime: {e}", exc_info=True)
            return None

    def get_game_attributes(
        self,
        game_info: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Optional[bytes]]]:
        """
        Process game metadata into attributes and images.

        Takes raw game metadata and extracts attributes for publishing,
        along with downloading/caching cover and artwork images.

        Args:
            game_info: Game metadata dictionary from get_game_metadata()

        Returns:
            Tuple of (attributes_dict, images_dict) where:
            - attributes_dict contains name, summary, release_date, genres,
              developers, platforms, rating, URLs, and playtime
            - images_dict contains 'cover' and 'artwork' as bytes or None

        Example:
            >>> collector = GameCollector("/path/to/game.txt")
            >>> metadata = collector.get_game_metadata("Portal 2")
            >>> attrs, images = collector.get_game_attributes(metadata)
            >>> print(attrs["name"])
            >>> if images["cover"]:
            ...     print(f"Cover: {len(images['cover'])} bytes")
        """
        try:
            # Extract cover URL
            cover_url = game_info["_raw"].get("cover", {}).get("url", "")
            cover_full_url = (
                "https:" + cover_url.replace("t_thumb", "t_cover_big")
                if cover_url.startswith("//")
                else cover_url
            )

            # Extract artwork or screenshot URL
            artworks = game_info["_raw"].get("artworks", [])
            screenshots = game_info["_raw"].get("screenshots", [])

            if artworks:
                artwork_url = artworks[-1].get("url", "")
                artwork_full_url = (
                    "https:" + artwork_url.replace("t_thumb", "t_original")
                    if artwork_url.startswith("//")
                    else artwork_url
                )
            elif screenshots:
                screenshot_url = screenshots[0].get("url", "")
                artwork_full_url = (
                    "https:" + screenshot_url.replace("t_thumb", "t_original")
                    if screenshot_url.startswith("//")
                    else screenshot_url
                )
            else:
                artwork_full_url = None

            # Get cached image paths
            cover_local = game_info.get('cover')
            artwork_local = game_info.get('artwork')

            # Download or load images
            cover_bytes = self.get_game_artwork(cover_local, cover_full_url)
            artwork_bytes = self.get_game_artwork(artwork_local, artwork_full_url)

            # Get playtime
            game_name = game_info.get("name", "Unknown")
            playtime = self.get_playtime(game_name)
            playtime_str = f"{playtime} hrs" if playtime is not None else "Unknown"

            # Build attributes dictionary
            attrs = {
                "name": game_info.get("name", "Unknown"),
                "title": game_info.get("name", "Unknown"),
                "summary": game_info.get("summary", "No summary available."),
                "release_date": game_info.get("release_date", "Not available"),
                "genres": ', '.join(game_info.get("genres", [])),
                "developers": ', '.join(game_info.get("developers", [])),
                "platforms": ', '.join(game_info.get("platforms", [])),
                "total_rating": round(game_info.get("total_rating", 0), 2),
                "cover_url": cover_full_url or "Cover image not available",
                "artwork_url": artwork_full_url or "Artwork not available",
                "url": game_info.get("url", ""),
                "playtime": playtime_str
            }

            # Build images dictionary
            images = {
                "cover": cover_bytes,
                "artwork": artwork_bytes
            }

            return attrs, images

        except KeyError as e:
            logger.error(f"Missing expected key in game info: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error processing game attributes: {e}", exc_info=True)
            raise
