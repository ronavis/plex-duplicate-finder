"""
Plex Duplicate Finder / Plex Space Reclaimer - Localhost Web Server
Fast, zero-external-dependency REST API and static web server.
"""

import os
import sys
import time
import io
import csv
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Ensure local directory is in path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import json
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import scanner
import media_inspector
import balancer
import cleaner
import plex_api
import pool_migrator

PORT = 8282
WEB_DIR = Path(__file__).parent / "frontend"
CACHE_FILE = Path(__file__).parent / "scan_cache.json"
AUDIT_FILE = Path(__file__).parent / "deletion_audit.json"

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


def _sync_balancer_completion(src_path: str, dest_path: str):
    """Callback when balancer moves a file: update duplicate items in memory and cache."""
    changed = False
    for group in scanner_instance.duplicates:
        for item in group.get("items", []):
            if item.get("path") == src_path:
                item["path"] = dest_path
                dest_p = Path(dest_path)
                item["drive"] = dest_p.drive.rstrip(":")
                item["filename"] = dest_p.name
                item["parent_folder"] = dest_p.parent.name
                changed = True

    if changed:
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


class PlexDedupHandler(SimpleHTTPRequestHandler):
    """Custom request handler supporting REST API endpoints and web UI serving."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

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

        # Feature 7: Export CSV
        elif path == "/api/export/csv":
            self._handle_export_csv()

        # Feature 7: Audit History
        elif path == "/api/audit/history":
            records = []
            if AUDIT_FILE.exists():
                try:
                    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                        records = json.load(f)
                except Exception:
                    records = []
            self._send_json(200, {"status": "ok", "records": records})

        # Feature 2: Plex Status
        elif path == "/api/plex/status":
            status = plex_api.plex_client.test_connection()
            sections = plex_api.plex_client.get_library_sections() if status.get("connected") else []
            self._send_json(200, {
                "status": "ok",
                "connection": status,
                "sections": sections,
                "config": {
                    "server_url": plex_api.plex_client.server_url,
                    "has_token": bool(plex_api.plex_client.token),
                    "auto_refresh_on_delete": plex_api.plex_client.auto_refresh_on_delete
                }
            })

        # Feature 4: Balancer Status
        elif path == "/api/balance/status":
            self._send_json(200, {"status": "ok", "balancer": balancer.storage_balancer.get_status()})

        # Smart Drive Offloader / Pool Migrator Status
        elif path == "/api/migrator/status":
            self._send_json(200, pool_migrator.pool_migrator.get_status())

        # Feature 5: Media Stream Range Requests
        elif path == "/api/media/stream":
            file_path = query.get("path", [""])[0]
            self._handle_media_stream(file_path)

        # Feature: Plex OAuth PIN Creation
        elif path == "/api/plex/oauth/pin":
            pin_data = plex_api.plex_client.create_oauth_pin()
            self._send_json(200 if pin_data.get("status") == "ok" else 500, pin_data)

        # Feature: Plex OAuth PIN Polling
        elif path == "/api/plex/oauth/check":
            pin_id = query.get("pin_id", [""])[0]
            if not pin_id:
                self._send_json(400, {"status": "error", "message": "Missing pin_id parameter"})
            else:
                try:
                    res = plex_api.plex_client.check_oauth_pin(int(pin_id))
                    self._send_json(200, res)
                except Exception as e:
                    self._send_json(500, {"status": "error", "message": str(e)})

        # Feature: Plex Poster Proxy / Artwork Search
        elif path == "/api/plex/poster":
            title = query.get("title", [""])[0]
            year_str = query.get("year", [""])[0]
            year = int(year_str) if year_str.isdigit() else None
            thumb = plex_api.plex_client.search_poster(title, year)
            if thumb:
                img_data = plex_api.plex_client.get_thumbnail_data(thumb)
                if img_data:
                    data, ctype = img_data
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self._send_json(404, {"status": "not_found", "message": "Poster not found"})

        # Feature: Direct Plex Thumb Proxy
        elif path == "/api/plex/thumb":
            thumb = query.get("thumb", [""])[0]
            if thumb:
                img_data = plex_api.plex_client.get_thumbnail_data(thumb)
                if img_data:
                    data, ctype = img_data
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self._send_json(404, {"status": "not_found", "message": "Thumbnail not found"})

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
                    "filename": Path(fp).name,
                    "success": success,
                    "message": message,
                    "size_bytes": sz,
                    "size_human": scanner.format_bytes(sz),
                })

            # Feature 7: Write to deletion audit log
            if results:
                audit_entry = {
                    "timestamp": int(time.time()),
                    "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "files_count": len(file_paths),
                    "reclaimed_bytes": reclaimed_bytes,
                    "reclaimed_human": scanner.format_bytes(reclaimed_bytes),
                    "use_recycle_bin": use_recycle_bin,
                    "items": results
                }
                try:
                    records = []
                    if AUDIT_FILE.exists():
                        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                            records = json.load(f)
                    records.insert(0, audit_entry)
                    records = records[:500]
                    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2)
                except Exception as e:
                    print("Audit log write error:", e)

            # Feature 2: Trigger Plex auto-refresh if enabled
            if plex_api.plex_client.auto_refresh_on_delete:
                threading.Thread(target=plex_api.plex_client.refresh_all_sections, daemon=True).start()

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

        # Feature 5: Open Explorer
        elif path == "/api/open_explorer":
            target_path = body.get("path", "").strip()
            if not target_path or not Path(target_path).exists():
                self._send_json(400, {"status": "error", "message": "File does not exist."})
                return
            try:
                subprocess.Popen(["explorer.exe", f"/select,{target_path}"])
                self._send_json(200, {"status": "ok"})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})

        # Feature 7: Clear Audit History
        elif path == "/api/audit/clear":
            try:
                if AUDIT_FILE.exists():
                    AUDIT_FILE.unlink()
                self._send_json(200, {"status": "ok"})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})

        # Feature 3: Inspect Media Streams
        elif path == "/api/media/inspect":
            file_path = body.get("path", "").strip()
            if not file_path or not Path(file_path).exists():
                self._send_json(400, {"status": "error", "message": "File does not exist."})
                return
            info = media_inspector.inspect_media_file(file_path)
            self._send_json(200, info)

        # Feature 4: Balancer Move
        elif path == "/api/balance/move":
            src = body.get("source_path", "").strip()
            dest_drive = body.get("target_drive", "").strip()
            res = balancer.storage_balancer.start_move(src, dest_drive, on_complete_callback=_sync_balancer_completion)
            code = 200 if res.get("status") == "started" else 400
            self._send_json(code, res)

        elif path == "/api/balance/cancel":
            balancer.storage_balancer.cancel_move()
            self._send_json(200, {"status": "cancelling"})

        # Feature 6: Cleaner Scan & Clean
        elif path == "/api/cleaner/scan":
            scan_path = body.get("path", "").strip()
            if not scan_path or not Path(scan_path).exists():
                self._send_json(400, {"status": "error", "message": "Directory does not exist."})
                return
            res = cleaner.library_cleaner.scan_path_for_cleanup(scan_path)
            self._send_json(200, res)

        elif path == "/api/cleaner/clean":
            items = body.get("items", [])
            use_bin = body.get("use_recycle_bin", True)
            res = cleaner.library_cleaner.clean_items(items, use_recycle_bin=use_bin)
            self._send_json(200, res)

        # Feature 2: Plex Config & Refresh
        elif path == "/api/plex/config":
            url = body.get("server_url", "http://127.0.0.1:32400")
            tok = body.get("token", "")
            auto_ref = body.get("auto_refresh_on_delete", True)
            res = plex_api.plex_client.save_config(url, tok, auto_ref)
            self._send_json(200, res)

        elif path == "/api/plex/refresh":
            sec_id = body.get("section_id")
            if sec_id:
                success = plex_api.plex_client.refresh_section(str(sec_id))
            else:
                count = plex_api.plex_client.refresh_all_sections()
                success = count > 0
            self._send_json(200, {"status": "ok" if success else "error"})

        # Feature: Plex OAuth Auto-Claim & Connect
        elif path == "/api/plex/oauth/claim":
            auth_token = body.get("auth_token", "").strip()
            if not auth_token:
                self._send_json(400, {"status": "error", "message": "Missing auth_token parameter"})
            else:
                res = plex_api.plex_client.auto_connect_oauth(auth_token)
                self._send_json(200, res)

        # Feature: Plex OAuth Server Selection
        elif path == "/api/plex/oauth/select":
            server_url = body.get("server_url", "").strip()
            token = body.get("token", "").strip()
            if not server_url:
                self._send_json(400, {"status": "error", "message": "Missing server_url"})
            else:
                plex_api.plex_client.save_config(server_url, token, plex_api.plex_client.auto_refresh_on_delete)
                conn = plex_api.plex_client.test_connection(server_url, token)
                self._send_json(200, {
                    "status": "ok",
                    "connected": conn.get("connected", False),
                    "connection": conn,
                    "server_url": server_url
                })

        # Smart Drive Offloader / Pool Migrator Endpoints
        elif path == "/api/migrator/scan":
            drive = body.get("drive", "R")
            cat = body.get("category", "all")
            res = pool_migrator.pool_migrator.scan_drive_content(drive, cat)
            self._send_json(200, res)

        elif path == "/api/migrator/recommend":
            src_drive = body.get("source_drive", "R")
            selected = body.get("selected_items", [])
            res = pool_migrator.pool_migrator.recommend_destinations(src_drive, selected)
            self._send_json(200, res)

        elif path == "/api/migrator/start":
            src_drive = body.get("source_drive", "R")
            target_drive = body.get("target_drive", "")
            item_paths = body.get("item_paths", [])
            use_bin = body.get("use_recycle_bin", True)
            res = pool_migrator.pool_migrator.start_batch_migration(src_drive, target_drive, item_paths, use_bin)
            self._send_json(200, res)

        elif path == "/api/migrator/cancel":
            pool_migrator.pool_migrator.cancel_migration()
            self._send_json(200, {"status": "ok", "message": "Migration cancel requested"})

        else:
            self._send_json(404, {"status": "not_found"})

    def _handle_export_csv(self):
        """Feature 7: Export all duplicates into CSV spreadsheet."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Group Title", "Match Type", "Match Reason", "Drive", "Filename", "Resolution", "Codec", "Size (Bytes)", "Size Human", "Full Path"])
        for group in scanner_instance.duplicates:
            for item in group.get("items", []):
                writer.writerow([
                    group.get("title", ""),
                    group.get("type", ""),
                    group.get("match_reason", ""),
                    item.get("drive", ""),
                    item.get("filename", ""),
                    item.get("resolution", ""),
                    item.get("codec", ""),
                    item.get("size_bytes", 0),
                    item.get("size_human", ""),
                    item.get("path", "")
                ])
        data = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8-sig")
        self.send_header("Content-Disposition", 'attachment; filename="plex_duplicates_report.csv"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_media_stream(self, file_path: str):
        """Feature 5: HTTP Range Request video streaming for in-browser preview."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            self.send_error(404, "File not found")
            return

        file_size = p.stat().st_size
        range_header = self.headers.get("Range")

        ext = p.suffix.lower()
        content_type = "video/mp4" if ext in [".mp4", ".m4v"] else "video/webm" if ext == ".webm" else "video/x-matroska" if ext == ".mkv" else "video/octet-stream"

        if range_header:
            try:
                range_str = range_header.split("=")[1].strip()
                parts = range_str.split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
            except Exception:
                start, end = 0, file_size - 1

            start = max(0, min(start, file_size - 1))
            end = max(start, min(end, file_size - 1))
            content_length = end - start + 1

            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Length", str(content_length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(p, "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_sz = 64 * 1024
                while remaining > 0:
                    read_len = min(remaining, chunk_sz)
                    data = f.read(read_len)
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        else:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(p, "rb") as f:
                shutil.copyfileobj(f, self.wfile, length=64 * 1024)

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
    print("Plex Space Reclaimer Server is running!")
    print(f"Localhost Web UI: http://localhost:{PORT}")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
