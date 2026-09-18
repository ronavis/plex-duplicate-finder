"""
Plex Duplicate Finder / Plex Space Reclaimer - Storage Balancer
Safe cross-drive media migration pipeline with progress tracking,
integrity verification, and automatic cache synchronization.
"""

import os
import time
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, Optional

import scanner


class StorageBalancer:
    def __init__(self):
        self.is_moving = False
        self.cancel_requested = False
        self.source_path = ""
        self.dest_path = ""
        self.total_bytes = 0
        self.transferred_bytes = 0
        self.speed_mbps = 0.0
        self.progress_pct = 0.0
        self.eta_seconds = 0
        self.status_message = "Idle"
        self.last_error = ""
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_moving": self.is_moving,
                "source_path": self.source_path,
                "dest_path": self.dest_path,
                "total_bytes": self.total_bytes,
                "transferred_bytes": self.transferred_bytes,
                "progress_pct": round(self.progress_pct, 1),
                "speed_mbps": round(self.speed_mbps, 1),
                "eta_seconds": self.eta_seconds,
                "status_message": self.status_message,
                "last_error": self.last_error,
            }

    def cancel_move(self):
        with self._lock:
            if self.is_moving:
                self.cancel_requested = True
                self.status_message = "Cancelling transfer..."

    def start_move(self, source_path: str, target_drive_letter: str, on_complete_callback=None) -> Dict[str, Any]:
        with self._lock:
            if self.is_moving:
                return {"status": "error", "message": "Another file migration is currently in progress."}

            src = Path(source_path)
            if not src.exists() or not src.is_file():
                return {"status": "error", "message": f"Source file does not exist: {source_path}"}

            target_letter = target_drive_letter.upper().rstrip(":\\")
            target_root = f"{target_letter}:\\"
            if not Path(target_root).exists():
                return {"status": "error", "message": f"Target drive {target_root} is not accessible."}

            # Check target drive free space
            free_bytes = shutil.disk_usage(target_root).free
            file_size = src.stat().st_size
            buffer_bytes = 10 * 1024 * 1024 * 1024  # 10 GB safe headroom
            if free_bytes < (file_size + buffer_bytes):
                return {
                    "status": "error",
                    "message": f"Target drive {target_letter}: does not have enough free space (Needs {scanner.format_bytes(file_size + buffer_bytes)}, Free: {scanner.format_bytes(free_bytes)})."
                }

            # Preserve directory structure
            # e.g., src is "Y:\Plex Movies\Avatar (2009)\Avatar.mkv" -> relative to drive is "Plex Movies\Avatar (2009)\Avatar.mkv"
            parts = src.parts
            if len(parts) > 1:
                relative_path = Path(*parts[1:])
            else:
                relative_path = Path(src.name)

            dest = Path(target_root) / relative_path

            if dest.exists():
                return {"status": "error", "message": f"Destination file already exists: {dest}"}

            self.is_moving = True
            self.cancel_requested = False
            self.source_path = str(src)
            self.dest_path = str(dest)
            self.total_bytes = file_size
            self.transferred_bytes = 0
            self.progress_pct = 0.0
            self.speed_mbps = 0.0
            self.eta_seconds = 0
            self.status_message = f"Starting migration to {target_letter}:..."
            self.last_error = ""

        def worker():
            chunk_size = 4 * 1024 * 1024  # 4 MB chunks
            start_time = time.time()
            last_calc_time = start_time
            bytes_since_calc = 0
            dest_temp = dest.with_suffix(dest.suffix + ".part")

            try:
                dest_temp.parent.mkdir(parents=True, exist_ok=True)
                with open(src, "rb") as fsrc, open(dest_temp, "wb") as fdest:
                    while True:
                        if self.cancel_requested:
                            raise InterruptedError("Transfer cancelled by user.")

                        chunk = fsrc.read(chunk_size)
                        if not chunk:
                            break

                        fdest.write(chunk)
                        chunk_len = len(chunk)

                        with self._lock:
                            self.transferred_bytes += chunk_len
                            bytes_since_calc += chunk_len
                            now = time.time()
                            dt = now - last_calc_time
                            if dt >= 0.5:
                                self.speed_mbps = (bytes_since_calc / (1024 * 1024)) / dt
                                remaining_bytes = self.total_bytes - self.transferred_bytes
                                if self.speed_mbps > 0:
                                    self.eta_seconds = int((remaining_bytes / (1024 * 1024)) / self.speed_mbps)
                                self.progress_pct = (self.transferred_bytes / self.total_bytes) * 100
                                self.status_message = f"Moving: {self.progress_pct:.1f}% ({self.speed_mbps:.1f} MB/s)"
                                last_calc_time = now
                                bytes_since_calc = 0

                # Verify file sizes match
                if dest_temp.stat().st_size != file_size:
                    raise IOError("Integrity verification failed: destination file size does not match source.")

                # Rename temp to final destination
                dest_temp.rename(dest)

                # Safely move source file to Recycle Bin
                with self._lock:
                    self.status_message = "Verifying and recycling source file..."
                success, msg = scanner.safe_delete_file(str(src), use_recycle_bin=True)
                if not success:
                    # Fallback to direct removal
                    try:
                        src.unlink()
                    except Exception:
                        pass

                with self._lock:
                    self.is_moving = False
                    self.progress_pct = 100.0
                    self.status_message = f"Successfully migrated to {dest}"

                if on_complete_callback:
                    on_complete_callback(str(src), str(dest))

            except InterruptedError:
                if dest_temp.exists():
                    try:
                        dest_temp.unlink()
                    except Exception:
                        pass
                with self._lock:
                    self.is_moving = False
                    self.status_message = "Transfer cancelled."
            except Exception as e:
                if dest_temp.exists():
                    try:
                        dest_temp.unlink()
                    except Exception:
                        pass
                with self._lock:
                    self.is_moving = False
                    self.last_error = str(e)
                    self.status_message = f"Transfer failed: {e}"

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        return {"status": "started", "source": str(src), "dest": str(dest)}


storage_balancer = StorageBalancer()
