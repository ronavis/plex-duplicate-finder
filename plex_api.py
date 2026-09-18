"""
Plex Duplicate Finder / Plex Space Reclaimer - Plex Server API Client
Direct communication with local/LAN Plex Media Server for library refresh,
edition verification, server connection diagnostics, 1-click OAuth sign-in,
and poster artwork discovery.
"""

import json
import uuid
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

CONFIG_FILE = Path(__file__).parent / "plex_config.json"
CLIENT_PRODUCT = "Plex Space Reclaimer"
CLIENT_VERSION = "2.0.0"


class PlexClient:
    def __init__(self):
        self.server_url = "http://127.0.0.1:32400"
        self.token = ""
        self.client_id = "plex-space-reclaimer-local"
        self.auto_refresh_on_delete = True
        self._poster_cache: Dict[str, str] = {}
        self._image_cache: Dict[str, Tuple[bytes, str]] = {}
        self.load_config()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.server_url = cfg.get("server_url", "http://127.0.0.1:32400").rstrip("/")
                    self.token = cfg.get("token", "")
                    self.client_id = cfg.get("client_id", "plex-space-reclaimer-local")
                    self.auto_refresh_on_delete = cfg.get("auto_refresh_on_delete", True)
            except Exception:
                pass

    def save_config(self, server_url: str, token: str, auto_refresh: bool = True) -> Dict[str, Any]:
        self.server_url = server_url.strip().rstrip("/")
        self.token = token.strip()
        self.auto_refresh_on_delete = bool(auto_refresh)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "server_url": self.server_url,
                    "token": self.token,
                    "client_id": self.client_id,
                    "auto_refresh_on_delete": self.auto_refresh_on_delete
                }, f, indent=2)
            # Clear cached poster mappings when switching servers/tokens
            self._poster_cache.clear()
            self._image_cache.clear()
            return {"status": "ok", "message": "Plex configuration saved."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _build_request(self, endpoint: str, override_url: Optional[str] = None, override_token: Optional[str] = None) -> urllib.request.Request:
        base = (override_url or self.server_url).rstrip("/")
        url = f"{base}/{endpoint.lstrip('/')}"
        headers = {
            "Accept": "application/json",
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Product": CLIENT_PRODUCT,
            "X-Plex-Version": CLIENT_VERSION
        }
        tok = override_token if override_token is not None else self.token
        if tok:
            headers["X-Plex-Token"] = tok

        return urllib.request.Request(url, headers=headers)

    def test_connection(self, url: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """Test connection to Plex Media Server."""
        test_url = (url or self.server_url).rstrip("/")
        test_tok = token if token is not None else self.token
        try:
            req = self._build_request("/identity", override_url=test_url, override_token=test_tok)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw.decode("utf-8"))
                    media_container = data.get("MediaContainer", {})
                    return {
                        "connected": True,
                        "server_name": media_container.get("friendlyName", "Plex Server"),
                        "version": media_container.get("version", "Unknown"),
                        "machine_id": media_container.get("machineIdentifier", ""),
                        "server_url": test_url,
                    }
                except Exception:
                    root = ET.fromstring(raw)
                    return {
                        "connected": True,
                        "server_name": root.attrib.get("friendlyName", "Plex Server"),
                        "version": root.attrib.get("version", "Unknown"),
                        "machine_id": root.attrib.get("machineIdentifier", ""),
                        "server_url": test_url,
                    }
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {
                    "connected": False,
                    "error": "Authentication required (401 Unauthorized). Please provide a valid Plex Token or Sign in with Plex."
                }
            return {"connected": False, "error": f"HTTP Error {e.code}: {e.reason}"}
        except Exception as e:
            return {
                "connected": False,
                "error": f"Unable to reach Plex server at {test_url}: {str(e)}"
            }

    # ==========================================
    # Feature: Plex 1-Click OAuth Flow
    # ==========================================

    def create_oauth_pin(self) -> Dict[str, Any]:
        """Create a Plex OAuth PIN to allow 1-click browser sign-in."""
        headers = {
            "X-Plex-Product": CLIENT_PRODUCT,
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Version": CLIENT_VERSION,
            "Accept": "application/json"
        }
        req = urllib.request.Request("https://plex.tv/api/v2/pins?strong=true", data=b"", headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                code = data.get("code", "")
                pin_id = data.get("id")
                encoded_product = urllib.parse.quote(CLIENT_PRODUCT)
                auth_url = f"https://app.plex.tv/auth/#!?clientID={self.client_id}&code={code}&context%5Bdevice%5D%5Bproduct%5D={encoded_product}"
                return {
                    "status": "ok",
                    "pin_id": pin_id,
                    "code": code,
                    "auth_url": auth_url
                }
        except Exception as e:
            return {"status": "error", "message": f"Failed to initialize Plex OAuth: {str(e)}"}

    def check_oauth_pin(self, pin_id: int) -> Dict[str, Any]:
        """Poll a Plex OAuth PIN to check if the user has signed in."""
        headers = {
            "X-Plex-Client-Identifier": self.client_id,
            "Accept": "application/json"
        }
        url = f"https://plex.tv/api/v2/pins/{pin_id}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                auth_token = data.get("authToken")
                if auth_token:
                    return {
                        "status": "ok",
                        "claimed": True,
                        "auth_token": auth_token
                    }
                return {
                    "status": "ok",
                    "claimed": False
                }
        except Exception as e:
            return {"status": "error", "message": f"Error checking PIN: {str(e)}"}

    def discover_servers(self, auth_token: str) -> List[Dict[str, Any]]:
        """Query Plex Resources API to discover all Plex Media Servers for the account."""
        headers = {
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Token": auth_token,
            "Accept": "application/json"
        }
        req = urllib.request.Request("https://plex.tv/api/v2/resources?includeHttps=1", headers=headers, method="GET")
        servers = []
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for res in data:
                    provides = res.get("provides", "")
                    if "server" in provides:
                        server_name = res.get("name", "Unknown Server")
                        client_ident = res.get("clientIdentifier", "")
                        access_token = res.get("accessToken") or auth_token
                        conns = res.get("connections", [])
                        parsed_conns = []
                        for c in conns:
                            uri = c.get("uri")
                            if uri:
                                parsed_conns.append({
                                    "uri": uri,
                                    "address": c.get("address"),
                                    "port": c.get("port"),
                                    "local": bool(c.get("local")),
                                    "protocol": c.get("protocol")
                                })
                        # Sort connections: local LAN http first, then local https, then remote
                        parsed_conns.sort(key=lambda x: (not x["local"], x["protocol"] != "http"))
                        servers.append({
                            "name": server_name,
                            "client_identifier": client_ident,
                            "access_token": access_token,
                            "owned": res.get("owned", True),
                            "connections": parsed_conns
                        })
        except Exception as e:
            print(f"[PlexClient] Error discovering servers: {e}")
        return servers

    def auto_connect_oauth(self, auth_token: str) -> Dict[str, Any]:
        """Automatically find best reachable connection for user's server and configure client."""
        servers = self.discover_servers(auth_token)
        if not servers:
            return {
                "status": "error",
                "message": "No Plex Media Servers found under this Plex account.",
                "auth_token": auth_token
            }

        # Try connecting to discovered servers
        best_server = None
        working_url = None
        working_token = None

        for s in servers:
            s_token = s.get("access_token") or auth_token
            for conn in s.get("connections", []):
                uri = conn["uri"]
                test = self.test_connection(uri, s_token)
                if test.get("connected"):
                    best_server = s
                    working_url = uri
                    working_token = s_token
                    break
            if best_server:
                break

        if best_server and working_url and working_token:
            self.save_config(working_url, working_token, self.auto_refresh_on_delete)
            return {
                "status": "ok",
                "connected": True,
                "server_name": best_server["name"],
                "server_url": working_url,
                "token": working_token,
                "all_servers": servers,
                "message": f"Successfully connected to Plex server '{best_server['name']}' at {working_url}!"
            }

        # If direct probe failed (e.g. firewall/NAT loopback issue), choose the top candidate connection
        top_server = servers[0]
        top_token = top_server.get("access_token") or auth_token
        fallback_url = top_server["connections"][0]["uri"] if top_server.get("connections") else "http://127.0.0.1:32400"
        self.save_config(fallback_url, top_token, self.auto_refresh_on_delete)

        return {
            "status": "ok",
            "connected": False,
            "server_name": top_server["name"],
            "server_url": fallback_url,
            "token": top_token,
            "all_servers": servers,
            "message": f"Found server '{top_server['name']}'. Saved connection settings, but local connection check timed out. You may test or select a different URI."
        }

    # ==========================================
    # Feature: Poster Artwork Search & Streaming
    # ==========================================

    def search_poster(self, title: str, year: Optional[int] = None) -> Optional[str]:
        """Search Plex library for movie/show title and return thumbnail path."""
        if not self.server_url:
            return None

        cache_key = f"{title.lower().strip()}_{year or ''}"
        if cache_key in self._poster_cache:
            return self._poster_cache[cache_key]

        # Clean search query: remove release artifacts and non-alphanumerics
        clean_q = re.sub(r"[\._\-\+]", " ", title)
        clean_q = re.sub(r"\b(1080p|720p|2160p|4k|bluray|web-dl|x264|x265|hevc|remux)\b", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"\s+", " ", clean_q).strip()

        if not clean_q:
            clean_q = title.strip()

        encoded_q = urllib.parse.quote(clean_q)
        try:
            req = self._build_request(f"/search?query={encoded_q}")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw.decode("utf-8"))
                    mc = data.get("MediaContainer", {})
                    items = mc.get("Metadata", [])
                    if not items and "SearchResult" in mc:
                        items = mc.get("SearchResult", [])
                except Exception:
                    root = ET.fromstring(raw)
                    items = []
                    for el in root.findall(".//Video"):
                        items.append(el.attrib)
                    for el in root.findall(".//Directory"):
                        items.append(el.attrib)

                # Prioritize year match if year provided
                matched_thumb = None
                for it in items:
                    thumb = it.get("thumb") or it.get("parentThumb") or it.get("grandparentThumb")
                    if not thumb:
                        continue
                    it_year = it.get("year")
                    if year and it_year:
                        try:
                            if abs(int(it_year) - int(year)) <= 1:
                                matched_thumb = thumb
                                break
                        except Exception:
                            pass

                if not matched_thumb:
                    for it in items:
                        thumb = it.get("thumb") or it.get("parentThumb") or it.get("grandparentThumb")
                        if thumb:
                            matched_thumb = thumb
                            break

                if matched_thumb:
                    self._poster_cache[cache_key] = matched_thumb
                    return matched_thumb

        except Exception as e:
            pass

        return None

    def search_hero_art(self, title: str, year: Optional[int] = None) -> Optional[str]:
        """Search Plex library for movie/show title and return backdrop/fanart (art or grandparentArt) path."""
        if not self.server_url:
            return None

        cache_key = f"hero_{title.lower().strip()}_{year or ''}"
        if cache_key in self._poster_cache:
            return self._poster_cache[cache_key]

        clean_q = re.sub(r"[\._\-\+]", " ", title)
        clean_q = re.sub(r"\b(1080p|720p|2160p|4k|bluray|web-dl|x264|x265|hevc|remux)\b", "", clean_q, flags=re.IGNORECASE)
        clean_q = re.sub(r"\s+", " ", clean_q).strip()
        if not clean_q:
            clean_q = title.strip()

        encoded_q = urllib.parse.quote(clean_q)
        try:
            req = self._build_request(f"/search?query={encoded_q}")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw.decode("utf-8"))
                    mc = data.get("MediaContainer", {})
                    items = mc.get("Metadata", [])
                    if not items and "SearchResult" in mc:
                        items = mc.get("SearchResult", [])
                except Exception:
                    root = ET.fromstring(raw)
                    items = []
                    for el in root.findall(".//Video"):
                        items.append(el.attrib)
                    for el in root.findall(".//Directory"):
                        items.append(el.attrib)

                matched_art = None
                for it in items:
                    art = it.get("art") or it.get("grandparentArt")
                    if not art:
                        continue
                    it_year = it.get("year")
                    if year and it_year:
                        try:
                            if abs(int(it_year) - int(year)) <= 1:
                                matched_art = art
                                break
                        except Exception:
                            pass

                if not matched_art:
                    for it in items:
                        art = it.get("art") or it.get("grandparentArt")
                        if art:
                            matched_art = art
                            break

                if matched_art:
                    self._poster_cache[cache_key] = matched_art
                    return matched_art
        except Exception:
            pass

        return None

    def get_thumbnail_data(self, thumb_path: str) -> Optional[Tuple[bytes, str]]:
        """Fetch raw thumbnail image bytes and content-type from Plex server."""
        if not self.server_url or not thumb_path:
            return None

        clean_path = thumb_path.strip()
        if clean_path in self._image_cache:
            return self._image_cache[clean_path]

        try:
            req = self._build_request(clean_path)
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                data = resp.read()
                if len(self._image_cache) > 200:
                    self._image_cache.clear()
                self._image_cache[clean_path] = (data, content_type)
                return data, content_type
        except Exception:
            return None

    # ==========================================
    # Library Sections & Refresh
    # ==========================================

    def get_library_sections(self) -> List[Dict[str, Any]]:
        """Fetch list of library sections with their IDs and names."""
        sections = []
        try:
            req = self._build_request("/library/sections")
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw.decode("utf-8"))
                    dir_list = data.get("MediaContainer", {}).get("Directory", [])
                    for d in dir_list:
                        sections.append({
                            "id": d.get("key"),
                            "title": d.get("title"),
                            "type": d.get("type"),
                        })
                except Exception:
                    root = ET.fromstring(raw)
                    for d in root.findall("Directory"):
                        sections.append({
                            "id": d.attrib.get("key"),
                            "title": d.attrib.get("title"),
                            "type": d.attrib.get("type"),
                        })
        except Exception:
            pass
        return sections

    def refresh_section(self, section_id: str) -> bool:
        """Trigger library refresh for a specific section."""
        try:
            req = self._build_request(f"/library/sections/{section_id}/refresh")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status in [200, 204]
        except Exception:
            return False

    def refresh_all_sections(self) -> int:
        """Trigger refresh across all movie and TV library sections."""
        sections = self.get_library_sections()
        count = 0
        for s in sections:
            sid = s.get("id")
            if sid and self.refresh_section(sid):
                count += 1
        return count


plex_client = PlexClient()
