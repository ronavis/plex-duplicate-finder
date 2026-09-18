"""
Plex Duplicate Finder / Plex Space Reclaimer - Pool Migrator
Smart Drive Offloader for migrating non-duplicate TV shows and movies
from full staging/intake drives (e.g. Drive R:) to drives with free space.
"""

import os
import time
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

import scanner
import plex_api

BUFFER_HEADROOM_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB safe headroom on target


def get_dir_size_and_count(dir_path: Path) -> tuple[int, int, float]:
    """Calculate total byte size, file count, and latest modified time for a directory."""
    total_size = 0
    file_count = 0
    latest_mtime = 0.0

    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        stat = entry.stat()
                        total_size += stat.st_size
                        file_count += 1
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
                    elif entry.is_dir(follow_symlinks=False):
                        sub_size, sub_count, sub_mtime = get_dir_size_and_count(Path(entry.path))
                        total_size += sub_size
                        file_count += sub_count
                        if sub_mtime > latest_mtime:
                            latest_mtime = sub_mtime
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass

    return total_size, file_count, latest_mtime


class PoolMigrator:
    def __init__(self):
        self.is_migrating = False
        self.cancel_requested = False
        self.source_drive = ""
        self.target_drive = ""
        self.total_items = 0
        self.current_item_index = 0
        self.current_item_name = ""
        self.current_file_name = ""
        self.total_batch_bytes = 0
        self.transferred_batch_bytes = 0
        self.current_file_transferred = 0
        self.current_file_total = 0
        self.speed_mbps = 0.0
        self.progress_pct = 0.0
        self.eta_seconds = 0
        self.status_message = "Idle"
        self.errors: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def scan_drive_content(self, drive_letter: str, category: str = "all") -> Dict[str, Any]:
        """Scan a drive's Movies and TV directories and return aggregated shows/movies."""
        drive_letter = drive_letter.upper().rstrip(":\\")
        drive_root = Path(f"{drive_letter}:\\")

        if not drive_root.exists():
            return {"status": "error", "message": f"Drive {drive_letter}: is not accessible."}

        items: List[Dict[str, Any]] = []

        # Look for standard media parent folders
        candidate_parents = []
        if category in ["all", "movies"]:
            for name in ["Movies", "Movie", "Plex Movies"]:
                p = drive_root / name
                if p.exists() and p.is_dir():
                    candidate_parents.append((p, "movie", name))

        if category in ["all", "tv"]:
            for name in ["TV", "TV Shows", "Television", "Plex TV"]:
                p = drive_root / name
                if p.exists() and p.is_dir():
                    candidate_parents.append((p, "tv", name))

        # Also inspect top-level directories on drive if standard folders aren't found
        if not candidate_parents:
            try:
                for entry in os.scandir(drive_root):
                    if entry.is_dir() and not entry.name.startswith("$") and not entry.name.startswith("System"):
                        candidate_parents.append((Path(entry.path), "mixed", entry.name))
            except Exception:
                pass

        for parent_dir, media_type, parent_rel in candidate_parents:
            try:
                with os.scandir(parent_dir) as it:
                    for entry in it:
                        if entry.name.startswith(".") or entry.name.startswith("$"):
                            continue

                        entry_path = Path(entry.path)
                        if entry.is_dir():
                            sz, count, mtime = get_dir_size_and_count(entry_path)
                            if count > 0 and sz > 10 * 1024 * 1024:  # At least 10 MB
                                items.append({
                                    "id": f"{media_type}_{entry.name}",
                                    "name": entry.name,
                                    "type": media_type,
                                    "path": str(entry_path),
                                    "relative_parent": parent_rel,
                                    "size_bytes": sz,
                                    "size_human": scanner.format_bytes(sz),
                                    "file_count": count,
                                    "modified_time": mtime or entry_path.stat().st_mtime,
                                    "is_folder": True
                                })
                        elif entry.is_file():
                            stat = entry.stat()
                            sz = stat.st_size
                            ext = entry_path.suffix.lower()
                            if ext in scanner.MEDIA_EXTENSIONS and sz > 50 * 1024 * 1024:
                                items.append({
                                    "id": f"{media_type}_{entry.name}",
                                    "name": entry_path.stem,
                                    "type": media_type,
                                    "path": str(entry_path),
                                    "relative_parent": parent_rel,
                                    "size_bytes": sz,
                                    "size_human": scanner.format_bytes(sz),
                                    "file_count": 1,
                                    "modified_time": stat.st_mtime,
                                    "is_folder": False
                                })
            except (OSError, PermissionError):
                continue

        # Sort largest first by default
        items.sort(key=lambda x: x["size_bytes"], reverse=True)

        return {
            "status": "ok",
            "drive": drive_letter,
            "total_items": len(items),
            "total_bytes": sum(x["size_bytes"] for x in items),
            "total_human": scanner.format_bytes(sum(x["size_bytes"] for x in items)),
            "items": items
        }

    def recommend_destinations(self, source_drive: str, selected_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate all candidate drives and recommend the best target with capacity previews."""
        src_letter = source_drive.upper().rstrip(":\\")
        all_drives = scanner.get_available_drives()

        total_needed = sum(it.get("size_bytes", 0) for it in selected_items)
        needed_with_buffer = total_needed + BUFFER_HEADROOM_BYTES

        src_drive_info = next((d for d in all_drives if d["letter"] == src_letter), None)

        candidates = []
        for d in all_drives:
            letter = d["letter"]
            if letter == src_letter:
                continue
            # Exclude Windows system drive or small thumb drives (< 500 GB)
            if d.get("label", "").lower() in ["windows", "system"] or d["total_bytes"] < 500 * 1024 * 1024 * 1024:
                continue

            free = d["free_bytes"]
            total = d["total_bytes"]
            used = d["used_bytes"]

            can_fit = free >= needed_with_buffer
            projected_used = used + total_needed
            projected_free = total - projected_used
            projected_pct = round((projected_used / total) * 100, 1) if total > 0 else 100.0

            candidates.append({
                "letter": letter,
                "label": d["label"],
                "total_bytes": total,
                "free_bytes": free,
                "free_human": scanner.format_bytes(free),
                "used_percent": d["used_percent"],
                "can_fit": can_fit,
                "projected_used_percent": projected_pct,
                "projected_free_human": scanner.format_bytes(max(0, projected_free)),
                "is_safe": can_fit and projected_pct < 95.0,
            })

        # Rank candidates: prioritize safe drives with lowest projected utilization
        candidates.sort(key=lambda c: (not c["can_fit"], not c["is_safe"], c["projected_used_percent"]))

        recommended = candidates[0]["letter"] if candidates and candidates[0]["can_fit"] else None

        # Calculate source drive projected stats
        src_preview = None
        if src_drive_info:
            src_total = src_drive_info["total_bytes"]
            src_used = max(0, src_drive_info["used_bytes"] - total_needed)
            src_free = src_total - src_used
            src_pct = round((src_used / src_total) * 100, 1) if src_total > 0 else 0.0
            src_preview = {
                "letter": src_letter,
                "current_used_percent": src_drive_info["used_percent"],
                "projected_used_percent": src_pct,
                "freed_bytes": total_needed,
                "freed_human": scanner.format_bytes(total_needed),
                "projected_free_human": scanner.format_bytes(src_free),
            }

        return {
            "status": "ok",
            "source_preview": src_preview,
            "total_selected_bytes": total_needed,
            "total_selected_human": scanner.format_bytes(total_needed),
            "candidates": candidates,
            "recommended_drive": recommended,
        }

    def start_batch_migration(self, source_drive: str, target_drive: str, item_paths: List[str], use_recycle_bin: bool = True) -> Dict[str, Any]:
        """Start background worker to migrate selected movies/shows."""
        with self._lock:
            if self.is_migrating:
                return {"status": "error", "message": "A drive migration task is already running."}

            src_letter = source_drive.upper().rstrip(":\\")
            dst_letter = target_drive.upper().rstrip(":\\")
            target_root = Path(f"{dst_letter}:\\")

            if not target_root.exists():
                return {"status": "error", "message": f"Target drive {dst_letter}: is not accessible."}

            # Pre-calculate files and total size
            migration_queue = []
            total_bytes = 0

            for p_str in item_paths:
                p = Path(p_str)
                if not p.exists():
                    continue

                if p.is_file():
                    sz = p.stat().st_size
                    migration_queue.append((p, sz, p.name))
                    total_bytes += sz
                elif p.is_dir():
                    for root, _, files in os.walk(p):
                        for f in files:
                            file_p = Path(root) / f
                            try:
                                sz = file_p.stat().st_size
                                migration_queue.append((file_p, sz, p.name))
                                total_bytes += sz
                            except Exception:
                                continue

            if not migration_queue:
                return {"status": "error", "message": "No valid files found to migrate."}

            # Check target drive space
            target_free = shutil.disk_usage(target_root).free
            if target_free < (total_bytes + BUFFER_HEADROOM_BYTES):
                return {
                    "status": "error",
                    "message": f"Target drive {dst_letter}: requires {scanner.format_bytes(total_bytes + BUFFER_HEADROOM_BYTES)} free, but only has {scanner.format_bytes(target_free)}."
                }

            self.is_migrating = True
            self.cancel_requested = False
            self.source_drive = src_letter
            self.target_drive = dst_letter
            self.total_items = len(item_paths)
            self.current_item_index = 0
            self.current_item_name = ""
            self.current_file_name = ""
            self.total_batch_bytes = total_bytes
            self.transferred_batch_bytes = 0
            self.speed_mbps = 0.0
            self.progress_pct = 0.0
            self.eta_seconds = 0
            self.status_message = f"Starting migration from {src_letter}: to {dst_letter}:..."
            self.errors = []

        def worker():
            chunk_size = 4 * 1024 * 1024  # 4 MB
            start_time = time.time()
            last_calc_time = start_time
            bytes_since_calc = 0
            affected_items_set = set(item_paths)

            try:
                for file_idx, (src_file, file_size, parent_item_name) in enumerate(migration_queue):
                    if self.cancel_requested:
                        raise InterruptedError("Migration cancelled by user.")

                    with self._lock:
                        self.current_item_name = parent_item_name
                        self.current_file_name = src_file.name
                        self.current_file_total = file_size
                        self.current_file_transferred = 0

                    # Map destination path preserving relative path
                    # e.g. R:\Movies\MovieName\file.mkv -> J:\Movies\MovieName\file.mkv
                    parts = src_file.parts
                    if len(parts) > 1:
                        rel_path = Path(*parts[1:])
                    else:
                        rel_path = Path(src_file.name)

                    dest_file = target_root / rel_path
                    dest_temp = dest_file.with_suffix(dest_file.suffix + ".part")

                    dest_temp.parent.mkdir(parents=True, exist_ok=True)

                    with open(src_file, "rb") as fsrc, open(dest_temp, "wb") as fdest:
                        while True:
                            if self.cancel_requested:
                                raise InterruptedError("Migration cancelled by user.")

                            chunk = fsrc.read(chunk_size)
                            if not chunk:
                                break

                            fdest.write(chunk)
                            chunk_len = len(chunk)

                            with self._lock:
                                self.transferred_batch_bytes += chunk_len
                                self.current_file_transferred += chunk_len
                                bytes_since_calc += chunk_len
                                now = time.time()
                                dt = now - last_calc_time
                                if dt >= 0.5:
                                    self.speed_mbps = (bytes_since_calc / (1024 * 1024)) / dt
                                    remaining = self.total_batch_bytes - self.transferred_batch_bytes
                                    if self.speed_mbps > 0:
                                        self.eta_seconds = int((remaining / (1024 * 1024)) / self.speed_mbps)
                                    self.progress_pct = (self.transferred_batch_bytes / self.total_batch_bytes) * 100
                                    self.status_message = f"Moving {self.current_item_name}: {self.progress_pct:.1f}% ({self.speed_mbps:.1f} MB/s)"
                                    last_calc_time = now
                                    bytes_since_calc = 0

                    # Verify integrity
                    if dest_temp.stat().st_size != file_size:
                        dest_temp.unlink(missing_ok=True)
                        raise IOError(f"Byte mismatch verifying {src_file.name}")

                    # Finalize destination file
                    if dest_file.exists():
                        dest_file.unlink()
                    dest_temp.rename(dest_file)

                    # Remove source file
                    scanner.safe_delete_file(str(src_file), use_recycle_bin=use_recycle_bin)

                # Post-migration directory cleanup for empty folders
                for p_str in affected_items_set:
                    p = Path(p_str)
                    if p.is_dir() and p.exists():
                        try:
                            # Remove if empty or only contains desktop.ini/.DS_Store
                            remaining_files = [f for f in p.rglob("*") if f.is_file()]
                            if not remaining_files:
                                shutil.rmtree(p, ignore_errors=True)
                        except Exception:
                            pass

                with self._lock:
                    self.is_migrating = False
                    self.progress_pct = 100.0
                    self.status_message = "Migration completed successfully!"

                # Trigger Plex library refresh so Plex spots relocated media immediately
                try:
                    plex_api.plex_client.refresh_all_sections()
                except Exception:
                    pass

            except InterruptedError:
                with self._lock:
                    self.is_migrating = False
                    self.status_message = "Migration cancelled by user."
            except Exception as e:
                with self._lock:
                    self.is_migrating = False
                    self.errors.append(str(e))
                    self.status_message = f"Error during migration: {str(e)}"

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

        return {
            "status": "ok",
            "message": f"Started migration of {len(item_paths)} item(s) ({scanner.format_bytes(total_bytes)}) to Drive {dst_letter}:"
        }

    def cancel_migration(self):
        """Cancel ongoing batch migration."""
        with self._lock:
            if self.is_migrating:
                self.cancel_requested = True
                self.status_message = "Cancelling migration..."

    def get_status(self) -> Dict[str, Any]:
        """Poll active status of the pool migrator."""
        with self._lock:
            return {
                "is_migrating": self.is_migrating,
                "source_drive": self.source_drive,
                "target_drive": self.target_drive,
                "total_items": self.total_items,
                "current_item_index": self.current_item_index,
                "current_item_name": self.current_item_name,
                "current_file_name": self.current_file_name,
                "total_batch_bytes": self.total_batch_bytes,
                "transferred_batch_bytes": self.transferred_batch_bytes,
                "progress_pct": round(self.progress_pct, 1),
                "speed_mbps": round(self.speed_mbps, 1),
                "eta_seconds": self.eta_seconds,
                "status_message": self.status_message,
                "errors": self.errors,
            }


pool_migrator = PoolMigrator()
