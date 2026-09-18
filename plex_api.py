"""
Plex Duplicate Finder / Plex Space Reclaimer - Plex Server API Client
Direct communication with local/LAN Plex Media Server for library refresh,
edition verification, and server connection diagnostics.
"""

import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional

CONFIG_FILE = Path(__file__).parent / "plex_config.json"


class PlexClient:
    def __init__(self):
        self.server_url = "http://127.0.0.1:32400"
        self.token = ""
        self.auto_refresh_on_delete = True
        self.load_config()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.server_url = cfg.get("server_url", "http://127.0.0.1:32400").rstrip("/")
                    self.token = cfg.get("token", "")
                    self.auto_refresh_on_delete = cfg.get("auto_refresh_on_delete", True)
            except Exception:
                pass

    def save_config(self, server_url: str, token: str, auto_refresh: bool) -> Dict[str, Any]:
        self.server_url = server_url.strip().rstrip("/")
        self.token = token.strip()
        self.auto_refresh_on_delete = bool(auto_refresh)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "server_url": self.server_url,
                    "token": self.token,
                    "auto_refresh_on_delete": self.auto_refresh_on_delete
                }, f, indent=2)
            return {"status": "ok", "message": "Plex configuration saved."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _build_request(self, endpoint: str) -> urllib.request.Request:
        url = f"{self.server_url}/{endpoint.lstrip('/')}"
        headers = {
            "Accept": "application/json",
            "X-Plex-Client-Identifier": "plex-space-reclaimer-local"
        }
        if self.token:
            headers["X-Plex-Token"] = self.token

        return urllib.request.Request(url, headers=headers)

    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Plex Media Server."""
        try:
            req = self._build_request("/identity")
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
                        "server_url": self.server_url,
                    }
                except Exception:
                    # Fallback to XML parsing if JSON header wasn't honored
                    root = ET.fromstring(raw)
                    return {
                        "connected": True,
                        "server_name": root.attrib.get("friendlyName", "Plex Server"),
                        "version": root.attrib.get("version", "Unknown"),
                        "machine_id": root.attrib.get("machineIdentifier", ""),
                        "server_url": self.server_url,
                    }
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {
                    "connected": False,
                    "error": "Authentication required (401 Unauthorized). Please provide a valid Plex Token."
                }
            return {"connected": False, "error": f"HTTP Error {e.code}: {e.reason}"}
        except Exception as e:
            return {
                "connected": False,
                "error": f"Unable to reach Plex server at {self.server_url}: {str(e)}"
            }

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
