"""
Plex Duplicate Finder - Localhost Web Server
Fast, zero-external-dependency REST API and static web server.
"""

import os
import sys
from pathlib import Path
from typing import Any

# Ensure local directory is in path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import json
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import scanner

PORT = 8282
WEB_DIR = Path(__file__).parent / "frontend"
CACHE_FILE = Path(__file__).parent / "scan_cache.json"

scanner_instance = scanner.MediaScanner()
active_scan_thread = None

# Restore previous scan results if available
if CACHE_FILE.exists():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8-sig") as f:
            cached = json.load(f)
            scanner_instance.duplicates = cached.get("duplicate_groups", [])
            scanner_instance.total_files_scanned = cached.get("total_files_scanned", 0)
            scanner_instance.total_media_files = cached.get("total_media_files", 0)
            scanner_instance.last_scan_duration = cached.get("duration_seconds", 0.0)
    except Exception as e:
        print("Warning loading cache:", e)


class PlexDedupHandler(SimpleHTTPRequestHandler):
    """Custom request handler supporting REST API endpoints and web UI serving."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/drives":
            drives = scanner.get_available_drives()
            self._send_json(200, {"status": "ok", "drives": drives})

        elif path == "/api/scan/status":
            self._send_json(200, {
                "status": "ok",
                "is_scanning": scanner_instance.is_scanning,
                "progress_pct": getattr(scanner_instance, "progress_pct", 0.0),
                "current_phase": getattr(scanner_instance, "current_phase", ""),
                "current_drive_index": getattr(scanner_instance, "current_drive_index", 0),
                "total_drives": getattr(scanner_instance, "total_drives", 0),
                "total_files_scanned": scanner_instance.total_files_scanned,
                "total_media_files": scanner_instance.total_media_files,
                "current_scanning_path": scanner_instance.current_scanning_path,
                "duration_seconds": scanner_instance.last_scan_duration,
                "duplicate_groups": scanner_instance.duplicates,
            })

        else:
            # Fallback to serving static frontend files
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(post_data.decode("utf-8"))
        except Exception:
            body = {}

        if path == "/api/scan/start":
            global active_scan_thread
            if scanner_instance.is_scanning:
                self._send_json(400, {"status": "error", "message": "Scan already in progress."})
                return

            target_paths = body.get("paths", [])
            min_size = int(body.get("min_size_mb", 50))

            if not target_paths:
                self._send_json(400, {"status": "error", "message": "No paths provided for scan."})
                return

            def run_scan():
                scanner_instance.scan(target_paths, min_file_size_mb=min_size)
                try:
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump({
                            "status": "ok",
                            "total_files_scanned": scanner_instance.total_files_scanned,
                            "total_media_files": scanner_instance.total_media_files,
                            "duration_seconds": scanner_instance.last_scan_duration,
                            "duplicate_groups": scanner_instance.duplicates,
                        }, f, indent=2)
                except Exception:
                    pass

            active_scan_thread = threading.Thread(target=run_scan, daemon=True)
            active_scan_thread.start()

            self._send_json(200, {"status": "started", "target_paths": target_paths})

        elif path == "/api/scan/cancel":
            scanner_instance.cancel_requested = True
            self._send_json(200, {"status": "cancelling"})

        elif path == "/api/delete":
            file_paths = body.get("files", [])
            use_recycle_bin = body.get("use_recycle_bin", True)

            results = []
            reclaimed_bytes = 0

            for fp in file_paths:
                sz = 0
                try:
                    if os.path.exists(fp):
                        sz = os.path.getsize(fp)
                except Exception:
                    pass

                success, message = scanner.safe_delete_file(fp, use_recycle_bin=use_recycle_bin)
                if success:
                    reclaimed_bytes += sz
                    # Remove from current duplicate list in memory
                    for group in scanner_instance.duplicates:
                        group["items"] = [item for item in group["items"] if item["path"] != fp]
                        if len(group["items"]) > 1:
                            group["reclaimable_bytes"] = sum(x["size_bytes"] for x in group["items"][1:])
                            group["reclaimable_human"] = scanner.format_bytes(group["reclaimable_bytes"])

                    # Filter out groups that no longer have duplicates (< 2 items)
                    scanner_instance.duplicates = [
                        g for g in scanner_instance.duplicates if len(g["items"]) > 1
                    ]

                results.append({
                    "path": fp,
                    "success": success,
                    "message": message,
                    "size_bytes": sz,
                })

            # Immediately persist remaining duplicates to disk cache
            try:
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "status": "ok",
                        "total_files_scanned": scanner_instance.total_files_scanned,
                        "total_media_files": scanner_instance.total_media_files,
                        "duration_seconds": scanner_instance.last_scan_duration,
                        "duplicate_groups": scanner_instance.duplicates,
                    }, f, indent=2)
            except Exception:
                pass

            self._send_json(200, {
                "status": "completed",
                "results": results,
                "reclaimed_bytes": reclaimed_bytes,
                "reclaimed_human": scanner.format_bytes(reclaimed_bytes),
                "remaining_groups": scanner_instance.duplicates,
            })

        else:
            self._send_json(404, {"status": "not_found"})

    def _send_json(self, code: int, data: Any):
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response_bytes)

    def log_message(self, format, *args):
        """Suppress standard access logs for cleaner console output."""
        return


def run_server():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    server_address = ("127.0.0.1", PORT)
    httpd = ThreadingHTTPServer(server_address, PlexDedupHandler)
    print("=" * 60)
    print("Plex Duplicate Finder is running!")
    print(f"Localhost Web UI: http://localhost:{PORT}")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
