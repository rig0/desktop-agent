"""IGDB (Internet Game Database) API integration with caching.

This module provides a client for querying the IGDB API to retrieve
comprehensive game information including metadata, artwork, ratings,
genres, and platform information. It implements SQLite-based caching
to reduce API calls and improve performance.

The IGDBClient downloads and stores game cover art and artwork locally,
making them available for display in Home Assistant or other UIs.

API Requirements:
    - IGDB Client ID (from Twitch Developer Console)
    - IGDB Access Token (OAuth token from Twitch)
    - See: https://api-docs.igdb.com/#authentication

Cache Strategy:
    - Results cached for 30 days
    - Images stored in modules/data/game_agent/covers/ and .../artworks/
    - Database: modules/data/game_agent/igdb_cache.sqlite

Example:
    >>> from modules.utils.igdb import IGDBClient
    >>>
    >>> # Initialize client with credentials
    >>> client = IGDBClient(
    ...     client_id="your_client_id",
    ...     access_token="your_access_token"
    ... )
    >>>
    >>> # Search for a game
    >>> game = client.search_game("Elden Ring")
    >>> if game:
    ...     print(f"Name: {game['name']}")
    ...     print(f"Rating: {game['total_rating']}")
    ...     print(f"Genres: {', '.join(game['genres'])}")
    ...     print(f"Cover art: {game['cover']}")
"""

# Standard library imports
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

# Third-party imports
import requests


class IGDBClient:
    """Client for querying IGDB API with local caching and image storage.

    This class provides methods to search for games using the IGDB API,
    caching results locally to minimize API calls. It also downloads and
    stores game cover art and promotional artwork.

    Attributes:
        client_id: IGDB API client ID (from Twitch Developer Console).
        access_token: IGDB API access token (OAuth token).
        cache_db: Path to SQLite cache database file.

    Example:
        >>> client = IGDBClient("my_client_id", "my_access_token")
        >>> game = client.search_game("Cyberpunk 2077")
        >>> print(f"{game['name']} - {game['total_rating']}/100")
        'Cyberpunk 2077 - 85.5/100'
    """

    def __init__(self, client_id, access_token, cache_db="igdb_cache.sqlite"):
        """Initialize IGDB client with credentials.

        Args:
            client_id: IGDB API client ID.
            access_token: IGDB API access token (OAuth).
            cache_db: SQLite database filename (default: "igdb_cache.sqlite").
                     Stored in modules/data/game_agent/ directory.
        """
        self.client_id = client_id
        self.access_token = access_token
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "game_agent")
        )
        os.makedirs(base_dir, exist_ok=True)
        self.cache_db = os.path.join(base_dir, cache_db)
        self._init_cache()

    def _init_cache(self):
        """Initialize SQLite cache database.

        Creates the games table if it doesn't exist, with columns for
        storing game data as JSON and tracking when it was cached.
        """
        conn = sqlite3.connect(self.cache_db)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                game_name TEXT UNIQUE,
                data TEXT,
                last_updated INTEGER
            )
        """
        )
        conn.commit()
        conn.close()

    def _query_cache(self, game_name):
        """Query cache for game data.

        Args:
            game_name: Name of the game to look up.

        Returns:
            Cached game data dictionary if found and not expired (< 30 days old),
            None otherwise.
        """
        conn = sqlite3.connect(self.cache_db)
        cur = conn.cursor()
        cur.execute(
            "SELECT data, last_updated FROM games WHERE game_name=?", (game_name,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            data, last_updated = row
            if time.time() - last_updated < 30 * 86400:  # 30 days
                return json.loads(data)
        return None

    def _save_cache(self, game_name, data):
        """Save game data to cache.

        Args:
            game_name: Name of the game (used as cache key).
            data: Game data dictionary to cache.
        """
        conn = sqlite3.connect(self.cache_db)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO games (id, game_name, data, last_updated)
            VALUES (
                COALESCE((SELECT id FROM games WHERE game_name=?), NULL),
                ?, ?, ?
            )
        """,
            (game_name, game_name, json.dumps(data), int(time.time())),
        )
        conn.commit()
        conn.close()

    def _download_image(self, url, folder, filename):
        """Download and save an image from a URL.

        Args:
            url: Image URL to download.
            folder: Subfolder within game_agent data directory ("covers" or "artworks").
            filename: Filename to save as (e.g., "game_name.png").

        Returns:
            Absolute path to saved image file, or None if download fails or URL is None.

        Example:
            >>> path = client._download_image(
            ...     "https://images.igdb.com/igdb/image/upload/t_cover_big/co1234.jpg",
            ...     "covers",
            ...     "Elden Ring.png"
            ... )
            >>> print(path)
            '/home/user/.../modules/data/game_agent/covers/Elden Ring.png'
        """
        if not url:
            return None

        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "game_agent")
        )

        full_folder_path = os.path.join(base_dir, folder)

        os.makedirs(full_folder_path, exist_ok=True)

        filepath = os.path.join(full_folder_path, filename)

        try:
            img_data = requests.get(url).content
            with open(filepath, "wb") as f:
                f.write(img_data)

            absolute_filepath = os.path.abspath(filepath)
            return absolute_filepath

        except Exception as e:
            print(f"Failed to download image {url}: {e}")
            return None

    def search_game(self, game_name):
        """Search for a game and retrieve comprehensive information.

        Queries IGDB API for the specified game and returns detailed information
        including metadata, artwork URLs, ratings, genres, platforms, and developers.
        Results are cached locally to reduce API calls.

        The method downloads cover art and promotional artwork, storing them locally
        and returning absolute file paths for use in UIs.

        Args:
            game_name: Name of the game to search for.

        Returns:
            Dictionary containing game information with keys:
                - name: Game title
                - summary: Game description
                - total_rating: Aggregate rating (0-100)
                - release_date: Release date (YYYY-MM-DD format)
                - cover: Absolute path to downloaded cover image
                - artwork: Absolute path to downloaded artwork/screenshot
                - genres: List of genre names
                - platforms: List of platform names
                - developers: List of developer/publisher names
                - url: IGDB URL for the game
                - _raw: Full unprocessed IGDB API response

            Returns None if game not found.

        Raises:
            requests.HTTPError: If IGDB API request fails (e.g., invalid credentials).
            requests.RequestException: If network request fails.

        Example:
            >>> client = IGDBClient("client_id", "access_token")
            >>> game = client.search_game("The Witcher 3")
            >>> if game:
            ...     print(f"{game['name']} ({game['release_date']})")
            ...     print(f"Rating: {game['total_rating']:.1f}/100")
            ...     print(f"Genres: {', '.join(game['genres'])}")
            ...     print(f"Cover: {game['cover']}")
            'The Witcher 3: Wild Hunt (2015-05-19)'
            'Rating: 92.3/100'
            'Genres: RPG, Adventure'
            'Cover: /home/user/.../covers/The Witcher 3.png'
        """
        # Cache lookup
        cached = self._query_cache(game_name)
        if cached:
            return cached

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }

        query = f"""
        search "{game_name}";
        fields name, summary, total_rating, first_release_date,
               cover.url, artworks.url, screenshots.url,
               genres.name, platforms.name, involved_companies.company.name, url;
        limit 1;
        """

        resp = requests.post("https://api.igdb.com/v4/games", headers=headers, data=query)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None

        game = data[0]

        # Cover and artwork
        cover_url = (
            "https:" + game["cover"]["url"].replace("t_thumb", "t_cover_big")
            if "cover" in game
            else None
        )
        artwork_url = None
        if "artworks" in game and game["artworks"]:
            artwork_url = "https:" + game["artworks"][-1]["url"].replace(
                "t_thumb", "t_720p"
            )
        elif "screenshots" in game and game["screenshots"]:
            artwork_url = "https:" + game["screenshots"][0]["url"].replace(
                "t_thumb", "t_720p"
            )

        # Save images locally
        cover_path = self._download_image(cover_url, "covers", f"{game['name']}.png")
        artwork_path = self._download_image(
            artwork_url, "artworks", f"{game['name']}.png"
        )

        # Humanize release date
        release_date = (
            datetime.fromtimestamp(game["first_release_date"], tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )
            if "first_release_date" in game
            else None
        )

        result = {
            "name": game.get("name"),
            "summary": game.get("summary"),
            "total_rating": game.get("total_rating"),
            "release_date": release_date,
            "cover": cover_path,
            "artwork": artwork_path,
            "genres": [g["name"] for g in game.get("genres", [])],
            "platforms": [p["name"] for p in game.get("platforms", [])],
            "developers": [
                ic["company"]["name"]
                for ic in game.get("involved_companies", [])
                if "company" in ic
            ],
            "url": game.get("url"),
            "_raw": game,  # full untouched IGDB response
        }

        self._save_cache(game_name, result)
        return result
