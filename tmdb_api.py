"""
Plex Duplicate Finder / Plex Space Reclaimer - The Movie Database (TMDb) API Client
Direct communication with TMDb API v3/v4 for movie & TV poster artwork discovery,
with intelligent title cleaning, RiffTrax specialty match fallback, and in-memory caching.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

CONFIG_FILE = Path(__file__).parent / "plex_config.json"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_API_BASE = "https://api.themoviedb.org/3"


class TmdbClient:
    def __init__(self):
        self.api_key = ""
        self.enabled = True
        self.priority = "plex_first"  # "plex_first" or "tmdb_first"
        self._poster_cache: Dict[str, str] = {}  # title_year -> poster_path
        self._image_cache: Dict[str, Tuple[bytes, str]] = {}  # poster_path -> (bytes, content_type)
        self.load_config()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.api_key = cfg.get("tmdb_api_key", "").strip()
                    self.enabled = cfg.get("tmdb_enabled", True)
                    self.priority = cfg.get("poster_source_priority", "plex_first")
            except Exception:
                pass

    def save_config(self, api_key: str, enabled: bool = True, priority: str = "plex_first") -> Dict[str, Any]:
        self.api_key = api_key.strip()
        self.enabled = bool(enabled)
        self.priority = priority if priority in ("plex_first", "tmdb_first") else "plex_first"

        # Read existing config to preserve plex settings
        cfg = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                pass

        cfg["tmdb_api_key"] = self.api_key
        cfg["tmdb_enabled"] = self.enabled
        cfg["poster_source_priority"] = self.priority

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._poster_cache.clear()
            self._image_cache.clear()
            return {"status": "ok", "message": "TMDb configuration saved."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def is_configured(self) -> bool:
        return bool(self.enabled and self.api_key)

    def _build_request(self, endpoint: str, query_params: Optional[Dict[str, Any]] = None, override_key: Optional[str] = None) -> urllib.request.Request:
        key = (override_key if override_key is not None else self.api_key).strip()
        params = dict(query_params or {})

        headers = {
            "Accept": "application/json",
            "User-Agent": "PlexSpaceReclaimer/2.0"
        }

        # Support both v4 Bearer token (JWT > 40 chars or starts with ey) and v3 key (32 chars hex)
        if len(key) > 40 or key.startswith("ey"):
            headers["Authorization"] = f"Bearer {key}"
        else:
            params["api_key"] = key

        qs = urllib.parse.urlencode(params)
        url = f"{TMDB_API_BASE}/{endpoint.lstrip('/')}"
        if qs:
            url += f"?{qs}"

        return urllib.request.Request(url, headers=headers)

    def test_connection(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Test authentication with TMDb API."""
        key = (api_key if api_key is not None else self.api_key).strip()
        if not key:
            return {"connected": False, "error": "Please enter a TMDb API Key or API Read Access Token."}

        try:
            req = self._build_request("/authentication", override_key=key)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("success"):
                    return {
                        "connected": True,
                        "message": "Valid TMDb API credentials! Successfully connected to The Movie Database."
                    }
                else:
                    return {
                        "connected": False,
                        "error": data.get("status_message", "Authentication check failed.")
                    }
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {
                    "connected": False,
                    "error": "Invalid TMDb API Key (401 Unauthorized). Please check your key from themoviedb.org/settings/api."
                }
            return {"connected": False, "error": f"TMDb HTTP Error {e.code}: {e.reason}"}
        except Exception as e:
            return {"connected": False, "error": f"Unable to reach TMDb: {str(e)}"}

    def _generate_search_queries(self, title: str) -> List[str]:
        """Generate smart search queries handling RiffTrax, MST3K, and scene naming."""
        clean = re.sub(r"[\._\-\+:]", " ", title)
        clean = re.sub(r"\b(1080p|720p|2160p|4k|bluray|web-dl|x264|x265|hevc|remux|edition|dvdrip)\b", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s+", " ", clean).strip()

        queries = []
        if clean:
            queries.append(clean)

        # Specialty prefix stripping for RiffTrax, MST3K, etc.
        # e.g. "RiffTrax: Day of the Animals" -> "Day of the Animals"
        # e.g. "RiffTrax Live - Birdemic" -> "Birdemic"
        stripped = re.sub(r"^(rifftrax(\s+live)?|mst3k|mystery\s+science\s+theater(\s+3000)?)\s*", "", clean, flags=re.IGNORECASE).strip()
        if stripped and stripped.lower() != clean.lower() and len(stripped) >= 2:
            queries.append(stripped)

        # Also remove any parenthesized year or notes from all generated queries
        additional = []
        for q in queries:
            no_parens = re.sub(r"\(.*?\)|\[.*?\]", "", q).strip()
            no_parens = re.sub(r"\s+", " ", no_parens).strip()
            if no_parens and no_parens not in queries and no_parens not in additional:
                additional.append(no_parens)

        queries.extend(additional)
        return queries

    def search_poster(self, title: str, year: Optional[int] = None) -> Optional[str]:
        """Search TMDb for title and return relative poster_path (e.g. '/abc.jpg')."""
        if not self.is_configured():
            return None

        cache_key = f"{title.lower().strip()}_{year or ''}"
        if cache_key in self._poster_cache:
            return self._poster_cache[cache_key]

        candidate_queries = self._generate_search_queries(title)

        for q in candidate_queries:
            try:
                # Use /search/multi to match movies and TV shows
                params = {"query": q, "include_adult": "true"}
                if year:
                    params["year"] = str(year)

                req = self._build_request("/search/multi", params)
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    results = data.get("results", [])

                    # Find best match with a poster
                    matched_path = None

                    # If year is provided, prioritize results matching year
                    if year:
                        for it in results:
                            p_path = it.get("poster_path")
                            if not p_path:
                                continue
                            date_str = it.get("release_date") or it.get("first_air_date") or ""
                            if date_str and len(date_str) >= 4:
                                try:
                                    it_yr = int(date_str[:4])
                                    if abs(it_yr - int(year)) <= 1:
                                        matched_path = p_path
                                        break
                                except Exception:
                                    pass

                    # Fallback to first result with a poster
                    if not matched_path:
                        for it in results:
                            if it.get("poster_path"):
                                matched_path = it.get("poster_path")
                                break

                    if matched_path:
                        self._poster_cache[cache_key] = matched_path
                        return matched_path

            except Exception:
                continue

        return None

    def get_poster_data(self, poster_path: str, size: str = "w500") -> Optional[Tuple[bytes, str]]:
        """Download and cache poster image bytes from TMDb."""
        if not poster_path:
            return None

        clean_path = poster_path.lstrip("/")
        cache_key = f"{size}_{clean_path}"
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        url = f"https://image.tmdb.org/t/p/{size}/{clean_path}"
        headers = {"User-Agent": "PlexSpaceReclaimer/2.0"}
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                data = resp.read()
                if len(self._image_cache) > 200:
                    self._image_cache.clear()
                self._image_cache[cache_key] = (data, content_type)
                return data, content_type
        except Exception:
            return None

    def get_poster_by_title(self, title: str, year: Optional[int] = None, size: str = "w500") -> Optional[Tuple[bytes, str]]:
        """Search TMDb and fetch raw poster image in one step."""
        poster_path = self.search_poster(title, year)
        if poster_path:
            return self.get_poster_data(poster_path, size)
        return None


tmdb_client = TmdbClient()
