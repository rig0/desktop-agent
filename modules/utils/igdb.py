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
    - Images stored in modules/data/game_monitor/covers/ and .../artworks/
    - Database: modules/data/game_monitor/igdb_cache.sqlite

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
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Third-party imports
import requests

# Configure logger
logger = logging.getLogger(__name__)


class IGDBClient:
    """Client for querying IGDB API with local caching and image storage.

    This class provides methods to search for games using the IGDB API,
    caching results locally to minimize API calls. It also downloads and
    stores game cover art and promotional artwork.

    Attributes:
        client_id: IGDB API client ID (from Twitch Developer Console).
        access_token: IGDB API access token (OAuth token).
        cache_db: Path to SQLite cache database file.

    IGDB Category Constants:
        CATEGORY_MAIN_GAME = 0: Main game
        CATEGORY_DLC_ADDON = 1: DLC/Add-on content
        CATEGORY_EXPANSION = 2: Expansion
        CATEGORY_BUNDLE = 3: Bundle
        CATEGORY_STANDALONE_EXPANSION = 4: Standalone expansion
        CATEGORY_MOD = 5: Mod
        CATEGORY_EPISODE = 6: Episode
        CATEGORY_SEASON = 7: Season
        CATEGORY_REMAKE = 8: Remake
        CATEGORY_REMASTER = 9: Remaster
        CATEGORY_EXPANDED_GAME = 10: Expanded game
        CATEGORY_PORT = 11: Port
        CATEGORY_FORK = 12: Fork
        CATEGORY_PACK = 13: Pack
        CATEGORY_UPDATE = 14: Update

    Example:
        >>> client = IGDBClient("my_client_id", "my_access_token")
        >>> game = client.search_game("Cyberpunk 2077")
        >>> print(f"{game['name']} - {game['total_rating']}/100")
        'Cyberpunk 2077 - 85.5/100'
    """

    # IGDB Category constants - used to filter search results
    CATEGORY_MAIN_GAME = 0
    CATEGORY_DLC_ADDON = 1
    CATEGORY_EXPANSION = 2
    CATEGORY_BUNDLE = 3
    CATEGORY_STANDALONE_EXPANSION = 4
    CATEGORY_MOD = 5
    CATEGORY_EPISODE = 6
    CATEGORY_SEASON = 7
    CATEGORY_REMAKE = 8
    CATEGORY_REMASTER = 9
    CATEGORY_EXPANDED_GAME = 10
    CATEGORY_PORT = 11
    CATEGORY_FORK = 12
    CATEGORY_PACK = 13
    CATEGORY_UPDATE = 14

    def __init__(self, client_id, access_token, cache_db="igdb_cache.sqlite"):
        """Initialize IGDB client with credentials.

        Args:
            client_id: IGDB API client ID.
            access_token: IGDB API access token (OAuth).
            cache_db: SQLite database filename (default: "igdb_cache.sqlite").
                     Stored in modules/data/game_monitor/ directory.
        """
        self.client_id = client_id
        self.access_token = access_token
        self.data_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "game_monitor")
        )
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_db = os.path.join(self.data_dir, cache_db)
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
            folder: Subfolder within game_monitor data directory ("covers" or "artworks").
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
            '/home/user/.../modules/data/game_monitor/covers/Elden Ring.png'
        """
        if not url:
            return None

        full_folder_path = os.path.join(self.data_dir, folder)

        os.makedirs(full_folder_path, exist_ok=True)

        filepath = os.path.join(full_folder_path, filename)

        try:
            img_data = requests.get(url).content
            with open(filepath, "wb") as f:
                f.write(img_data)

            absolute_filepath = os.path.abspath(filepath)
            return absolute_filepath

        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            return None

    def _normalize_string(self, text: str) -> str:
        """Normalize a string for comparison.

        Converts to lowercase, removes extra whitespace, and strips common
        special characters that might differ between game titles.

        Args:
            text: String to normalize

        Returns:
            Normalized string for comparison

        Example:
            >>> client._normalize_string("The Witcher 3: Wild Hunt")
            'the witcher 3 wild hunt'
        """
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Remove common punctuation that doesn't affect matching
        for char in [":", "-", "'", ".", "!", "?", "&", ","]:
            text = text.replace(char, " ")

        # Normalize whitespace
        text = " ".join(text.split())

        return text

    def _calculate_match_score(self, search_name: str, game: Dict) -> float:
        """Calculate a match score for a game result.

        Scores are based on:
        - Exact name match: 100 points
        - Case-insensitive exact match: 90 points
        - Normalized exact match: 80 points
        - Starts with search term: 50 points
        - Contains search term: 30 points
        - Base game category bonus: +20 points
        - DLC/expansion penalty: -50 points

        Args:
            search_name: The name being searched for
            game: Game data dictionary from IGDB

        Returns:
            Match score as float (higher is better)

        Example:
            >>> score = client._calculate_match_score(
            ...     "Portal 2",
            ...     {"name": "Portal 2", "category": 0}
            ... )
            >>> print(score)
            120.0
        """
        game_name = game.get("name", "")
        category = game.get("category")

        # Start with base score of 0
        score = 0.0

        # Exact match (case-sensitive)
        if game_name == search_name:
            score += 100
            logger.debug(f"Exact match: '{game_name}' == '{search_name}' (+100)")

        # Case-insensitive exact match
        elif game_name.lower() == search_name.lower():
            score += 90
            logger.debug(
                f"Case-insensitive match: '{game_name}' ~= '{search_name}' (+90)"
            )

        # Normalized exact match (ignoring punctuation/whitespace differences)
        elif self._normalize_string(game_name) == self._normalize_string(search_name):
            score += 80
            logger.debug(f"Normalized match: '{game_name}' ~= '{search_name}' (+80)")

        # Starts with search term (normalized)
        elif self._normalize_string(game_name).startswith(
            self._normalize_string(search_name)
        ):
            score += 50
            logger.debug(f"Starts with: '{game_name}' starts with '{search_name}' (+50)")

        # Contains search term (normalized)
        elif self._normalize_string(search_name) in self._normalize_string(game_name):
            score += 30
            logger.debug(f"Contains: '{game_name}' contains '{search_name}' (+30)")

        # Bonus for main games, penalty for DLCs/expansions
        if category == self.CATEGORY_MAIN_GAME:
            score += 20
            logger.debug("Main game category bonus (+20)")
        elif category in (
            self.CATEGORY_DLC_ADDON,
            self.CATEGORY_EXPANSION,
            self.CATEGORY_STANDALONE_EXPANSION,
        ):
            score -= 50
            logger.debug("DLC/Expansion penalty (-50)")

        return score

    def _filter_and_rank_results(
        self, search_name: str, results: List[Dict]
    ) -> Optional[Dict]:
        """Filter and rank search results to find the best match.

        Filters out DLCs and expansions when a base game is available,
        then ranks remaining results by match quality.

        Args:
            search_name: The name being searched for
            results: List of game dictionaries from IGDB API

        Returns:
            Best matching game dictionary, or None if no suitable match found

        Example:
            >>> results = [
            ...     {"name": "Portal 2", "category": 0},
            ...     {"name": "Portal 2: Lab Rat", "category": 1}
            ... ]
            >>> best = client._filter_and_rank_results("Portal 2", results)
            >>> print(best["name"])
            'Portal 2'
        """
        if not results:
            logger.warning(f"No results to filter for search: '{search_name}'")
            return None

        logger.info(f"Filtering and ranking {len(results)} results for: '{search_name}'")

        # Score all results
        scored_results = []
        for game in results:
            score = self._calculate_match_score(search_name, game)
            game_name = game.get("name", "Unknown")
            category = game.get("category", "Unknown")

            logger.debug(f"  [{score:6.1f}] {game_name} (category: {category})")

            scored_results.append((score, game))

        # Sort by score (descending)
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # Log top results
        logger.info(f"Top 3 matches for '{search_name}':")
        for i, (score, game) in enumerate(scored_results[:3], 1):
            logger.info(
                f"  {i}. [{score:6.1f}] {game.get('name')} "
                f"(category: {game.get('category', 'Unknown')})"
            )

        # Return best match
        best_score, best_game = scored_results[0]

        if best_score <= 0:
            logger.warning(f"Best match score too low ({best_score}) for '{search_name}'")
            return None

        logger.info(f"Selected: '{best_game.get('name')}' with score {best_score}")
        return best_game

    def search_game(self, game_name):
        """Search for a game and retrieve comprehensive information.

        Queries IGDB API for the specified game and returns detailed information
        including metadata, artwork URLs, ratings, genres, platforms, and developers.
        Results are cached locally to reduce API calls.

        The method implements intelligent matching to select the most appropriate
        game from search results:
        - Prioritizes exact title matches over partial matches
        - Filters out DLCs, expansions, and add-ons in favor of base games
        - Uses a scoring system to rank results
        - Logs detailed match information for debugging

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
            logger.debug(f"Cache hit for game: '{game_name}'")
            return cached

        logger.info(f"Searching IGDB for game: '{game_name}'")

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }

        # Query with category field included and increased limit to get multiple results
        # We request more results so we can apply intelligent filtering and ranking
        query = f"""
        search "{game_name}";
        fields name, summary, total_rating, first_release_date, category,
               cover.url, artworks.url, screenshots.url,
               genres.name, platforms.name, involved_companies.company.name, url;
        limit 10;
        """

        try:
            resp = requests.post(
                "https://api.igdb.com/v4/games", headers=headers, data=query
            )
            resp.raise_for_status()
            data = resp.json()

            if not data:
                logger.warning(f"No results found for game: '{game_name}'")
                return None

            logger.info(f"IGDB returned {len(data)} results for '{game_name}'")

            # Filter and rank results to find the best match
            game = self._filter_and_rank_results(game_name, data)

            if not game:
                logger.warning(
                    f"No suitable match found after filtering for: '{game_name}'"
                )
                return None

        except requests.HTTPError as e:
            logger.error(f"IGDB API HTTP error: {e}", exc_info=True)
            raise
        except requests.RequestException as e:
            logger.error(f"IGDB API request failed: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error searching IGDB: {e}", exc_info=True)
            raise

        # Extract cover and artwork URLs
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

        # Format release date
        release_date = (
            datetime.fromtimestamp(game["first_release_date"], tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )
            if "first_release_date" in game
            else None
        )

        # Build result dictionary
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

        # Cache the result
        self._save_cache(game_name, result)
        logger.info(f"Successfully fetched and cached game: '{game['name']}'")

        return result
