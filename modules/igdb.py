import os
import sqlite3
import time
import requests
import json
from datetime import datetime, timezone

class IGDBClient:
    def __init__(self, client_id, access_token, cache_db="igdb_cache.sqlite"):
        self.client_id = client_id
        self.access_token = access_token
        base_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'game_agent')
        os.makedirs(base_dir, exist_ok=True)
        self.cache_db = os.path.join(base_dir, cache_db)
        self._init_cache()

    def _init_cache(self):
        conn = sqlite3.connect(self.cache_db)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                game_name TEXT UNIQUE,
                data TEXT,
                last_updated INTEGER
            )
        """)
        conn.commit()
        conn.close()

    def _query_cache(self, game_name):
        conn = sqlite3.connect(self.cache_db)
        cur = conn.cursor()
        cur.execute("SELECT data, last_updated FROM games WHERE game_name=?", (game_name,))
        row = cur.fetchone()
        conn.close()
        if row:
            data, last_updated = row
            if time.time() - last_updated < 30 * 86400:  # 30 days
                return json.loads(data)
        return None

    def _save_cache(self, game_name, data):
        conn = sqlite3.connect(self.cache_db)
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO games (id, game_name, data, last_updated)
            VALUES (
                COALESCE((SELECT id FROM games WHERE game_name=?), NULL),
                ?, ?, ?
            )
        """, (game_name, game_name, json.dumps(data), int(time.time())))
        conn.commit()
        conn.close()

    def _download_image(self, url, folder, filename):
        if not url:
            return None
        
        base_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'game_agent')

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
        # Cache lookup
        cached = self._query_cache(game_name)
        if cached:
            return cached

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }

        query = f'''
        search "{game_name}";
        fields name, summary, total_rating, first_release_date,
               cover.url, artworks.url, screenshots.url,
               genres.name, platforms.name, involved_companies.company.name, url;
        limit 1;
        '''

        resp = requests.post("https://api.igdb.com/v4/games", headers=headers, data=query)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None

        game = data[0]

        # Cover and artwork
        cover_url = "https:" + game["cover"]["url"].replace("t_thumb", "t_cover_big") if "cover" in game else None
        artwork_url = None
        if "artworks" in game and game["artworks"]:
            artwork_url = "https:" + game["artworks"][-1]["url"].replace("t_thumb", "t_720p")
        elif "screenshots" in game and game["screenshots"]:
            artwork_url = "https:" + game["screenshots"][0]["url"].replace("t_thumb", "t_720p")

        # Save images locally
        cover_path = self._download_image(cover_url, "covers", f"{game['name']}.png")
        artwork_path = self._download_image(artwork_url, "artworks", f"{game['name']}.png")

        # Humanize release date
        release_date = (
            datetime.fromtimestamp(game["first_release_date"], tz=timezone.utc).strftime("%Y-%m-%d")
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
            "developers": [ic["company"]["name"] for ic in game.get("involved_companies", []) if "company" in ic],
            "url": game.get("url"),
            "_raw": game  # full untouched IGDB response
        }

        self._save_cache(game_name, result)
        return result

