"""
Plex Duplicate Finder / Plex Space Reclaimer - Library Cleaner
Scans for empty directories, sample clips, junk files, and orphan subtitle files.
Provides safe recycling of debris to free up space and declutter libraries.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
import scanner

JUNK_EXTENSIONS = {".nfo", ".sfv", ".nzb", ".url", ".diz", ".lnk"}
JUNK_FILENAMES = {"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db"}
SUBTITLE_EXTENSIONS = {".srt", ".sub", ".idx", ".vtt", ".smi", ".ass", ".ssa"}
VIDEO_EXTENSIONS = scanner.MEDIA_EXTENSIONS


class LibraryCleaner:
    def __init__(self):
        self.is_scanning = False
        self.cancel_requested = False

    def scan_path_for_cleanup(self, root_path: str) -> Dict[str, Any]:
        """
        Scan a root directory for cleanup candidates:
        - empty_folders: Directories with 0 files
        - sample_files: Sample video clips (< 150 MB)
        - junk_files: .nfo, .sfv, .nzb, thumbs.db
        - orphan_subtitles: .srt/.vtt files with no matching video file
        """
        empty_folders: List[Dict[str, Any]] = []
        sample_files: List[Dict[str, Any]] = []
        junk_files: List[Dict[str, Any]] = []
        orphan_subtitles: List[Dict[str, Any]] = []

        total_reclaimable_bytes = 0
        root = Path(root_path)

        if not root.exists():
            return {
                "status": "error",
                "message": f"Path does not exist: {root_path}",
                "empty_folders": [],
                "sample_files": [],
                "junk_files": [],
                "orphan_subtitles": [],
                "total_reclaimable_bytes": 0,
                "total_reclaimable_human": "0.00 B"
            }

        for current_dir, dirs, files in os.walk(root_path, topdown=False):
            if self.cancel_requested:
                break

            cur_p = Path(current_dir)

            # 1. Check if folder is completely empty
            if not dirs and not files:
                empty_folders.append({
                    "path": current_dir,
                    "name": cur_p.name,
                    "type": "empty_folder",
                    "size_bytes": 0,
                    "size_human": "0 B"
                })
                continue

            # Gather video base names in this directory
            video_basenames = set()
            for f in files:
                fp = cur_p / f
                ext = fp.suffix.lower()
                if ext in VIDEO_EXTENSIONS:
                    video_basenames.add(fp.stem.lower())

            # 2. Check files in current directory
            for f in files:
                fp = cur_p / f
                name_lower = f.lower()
                ext = fp.suffix.lower()

                try:
                    size = fp.stat().st_size
                except Exception:
                    size = 0

                # Sample video detection
                if ext in VIDEO_EXTENSIONS and "sample" in name_lower and size < 150 * 1024 * 1024:
                    sample_files.append({
                        "path": str(fp),
                        "name": f,
                        "type": "sample_video",
                        "size_bytes": size,
                        "size_human": scanner.format_bytes(size)
                    })
                    total_reclaimable_bytes += size

                # Junk file detection
                elif ext in JUNK_EXTENSIONS or name_lower in JUNK_FILENAMES or (ext == ".txt" and "readme" in name_lower):
                    junk_files.append({
                        "path": str(fp),
                        "name": f,
                        "type": "junk_file",
                        "size_bytes": size,
                        "size_human": scanner.format_bytes(size)
                    })
                    total_reclaimable_bytes += size

                # Orphan subtitle detection
                elif ext in SUBTITLE_EXTENSIONS:
                    # Subtitle stems can be "Movie.en.srt", "Movie.forced.srt", etc.
                    sub_stem = fp.stem.lower()
                    has_match = False
                    for vstem in video_basenames:
                        if vstem in sub_stem:
                            has_match = True
                            break
                    if not has_match:
                        orphan_subtitles.append({
                            "path": str(fp),
                            "name": f,
                            "type": "orphan_subtitle",
                            "size_bytes": size,
                            "size_human": scanner.format_bytes(size)
                        })
                        total_reclaimable_bytes += size

        return {
            "status": "ok",
            "empty_folders": empty_folders[:500],
            "sample_files": sample_files[:500],
            "junk_files": junk_files[:500],
            "orphan_subtitles": orphan_subtitles[:500],
            "total_items": len(empty_folders) + len(sample_files) + len(junk_files) + len(orphan_subtitles),
            "total_reclaimable_bytes": total_reclaimable_bytes,
            "total_reclaimable_human": scanner.format_bytes(total_reclaimable_bytes)
        }

    def clean_items(self, item_paths: List[str], use_recycle_bin: bool = True) -> Dict[str, Any]:
        """Safely delete selected debris items."""
        reclaimed_bytes = 0
        success_count = 0
        failures = []

        for path_str in item_paths:
            p = Path(path_str)
            if not p.exists():
                continue

            sz = 0
            is_dir = p.is_dir()
            if not is_dir:
                try:
                    sz = p.stat().st_size
                except Exception:
                    sz = 0

            success, msg = scanner.safe_delete_file(path_str, use_recycle_bin=use_recycle_bin)
            if success:
                reclaimed_bytes += sz
                success_count += 1
            else:
                failures.append({"path": path_str, "error": msg})

        return {
            "status": "completed",
            "success_count": success_count,
            "failed_count": len(failures),
            "reclaimed_bytes": reclaimed_bytes,
            "reclaimed_human": scanner.format_bytes(reclaimed_bytes),
            "failures": failures
        }


library_cleaner = LibraryCleaner()
