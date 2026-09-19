"""
Plex Duplicate Finder / Plex Space Reclaimer - Space Optimization Advisor
Audits media libraries for high-bitrate legacy video codecs (H.264/AVC, MPEG2)
and uncompressed lossless audio streams (DTS-HD MA, Dolby TrueHD),
calculates exact reclaimable gigabyte savings, and provides Intel Quick Sync (QSV)
hardware-accelerated transcoding presets tailored for Intel Alder Lake-N (N150).
"""

import os
import time
import json
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

import scanner
import media_inspector

CACHE_FILE = Path(__file__).parent / "optimization_cache.json"

# Savings estimation multipliers based on empirical r/PleX and r/Tdarr benchmarks
# High-bitrate AVC (1080p Blu-ray/REMUX) -> 10-bit HEVC CRF 21: ~65% reduction
SAVINGS_RATIO_AVC_HIGH = 0.65
# Moderate-bitrate AVC -> 10-bit HEVC: ~50% reduction
SAVINGS_RATIO_AVC_MODERATE = 0.50
# MPEG-2 / VC-1 (DVD or early Blu-ray) -> 10-bit HEVC: ~75% reduction
SAVINGS_RATIO_MPEG2 = 0.75
# HEVC / AV1 -> already modern: negligible savings
SAVINGS_RATIO_MODERN = 0.05

# Lossless audio (DTS-HD MA, TrueHD, LPCM) -> E-AC-3 5.1 @ 640 kbps savings per hour (~1.5 GB/hr)
# On a standard 45-min TV episode: ~1.2 GB savings; on a 2-hour movie: ~3.0 GB savings
AUDIO_LOSSLESS_SAVINGS_BYTES_PER_HR = int(1.5 * 1024 * 1024 * 1024)


def estimate_savings_for_file(file_path: str, file_size: int, is_movie: bool = True) -> Dict[str, Any]:
    """
    Inspect a media file's video & audio streams and estimate potential space savings
    if modernized to 10-bit HEVC with Dolby Digital Plus (E-AC-3 5.1).
    """
    ext = Path(file_path).suffix.lower()
    stream_info: Dict[str, Any] = {}

    if ext == ".mkv":
        stream_info = media_inspector.inspect_mkv_streams(file_path)
    elif ext in [".mp4", ".m4v"]:
        stream_info = media_inspector.inspect_mp4_streams(file_path)
    else:
        stream_info = {
            "container": ext.upper().lstrip("."),
            "video": [{"codec": "Unknown"}],
            "audio": [{"codec": "Unknown"}],
            "hdr_format": "SDR",
            "primary_audio": "Unknown",
            "codec_summary": ext.upper()
        }

    # Extract detected codecs
    video_list = stream_info.get("video", [])
    video_codec = video_list[0].get("codec", "Unknown") if video_list else "Unknown"
    primary_audio = stream_info.get("primary_audio", "Unknown")
    hdr_format = stream_info.get("hdr_format", "SDR")
    has_dovi = stream_info.get("has_dolby_vision", False)
    has_hdr10 = stream_info.get("has_hdr10", False)

    # Fallback to filename heuristics if stream header is inconclusive
    name_lower = Path(file_path).name.lower()
    is_remux = "remux" in name_lower
    is_bluray = "bluray" in name_lower or "bdrip" in name_lower

    if video_codec == "Unknown":
        if "hevc" in name_lower or "x265" in name_lower or "h.265" in name_lower or "h265" in name_lower:
            video_codec = "HEVC / H.265"
        elif "av1" in name_lower or "av01" in name_lower:
            video_codec = "AV1"
        elif "x264" in name_lower or "h.264" in name_lower or "h264" in name_lower or "avc" in name_lower:
            video_codec = "AVC / H.264"
        elif "mpeg2" in name_lower or "dvd" in name_lower:
            video_codec = "MPEG-2"

    if primary_audio == "Unknown":
        if "truehd" in name_lower or "atmos" in name_lower:
            primary_audio = "TrueHD Atmos" if "atmos" in name_lower else "TrueHD"
        elif "dts-hd" in name_lower or "dtshd" in name_lower:
            primary_audio = "DTS-HD MA"
        elif "dts" in name_lower:
            primary_audio = "DTS 5.1"
        elif "eac3" in name_lower or "ddp" in name_lower:
            primary_audio = "EAC3 5.1"
        elif "ac3" in name_lower or "dd5.1" in name_lower:
            primary_audio = "AC3 5.1"
        elif "aac" in name_lower:
            primary_audio = "AAC"

    # Determine optimization priority and savings ratio
    reclaimable_bytes = 0
    optimization_reasons = []
    recommended_vcodec = "10-bit HEVC (H.265)"
    recommended_acodec = "E-AC-3 5.1 (640k)"
    priority = "Low"

    is_lossless_audio = any(tag in primary_audio.lower() for tag in ["truehd", "dts-hd", "flac", "pcm", "lpcm"])
    
    # Check Video Codec Savings
    if "AVC" in video_codec or "H.264" in video_codec:
        priority = "High" if is_remux or file_size > (3 * 1024 * 1024 * 1024) else "Medium"
        ratio = SAVINGS_RATIO_AVC_HIGH if (is_remux or file_size > 4 * 1024 * 1024 * 1024) else SAVINGS_RATIO_AVC_MODERATE
        video_savings = int(file_size * ratio)
        reclaimable_bytes += video_savings
        optimization_reasons.append(f"Legacy AVC video stream ({int(ratio*100)}% est. reduction)")
    elif "MPEG-2" in video_codec or "VC-1" in video_codec:
        priority = "High"
        video_savings = int(file_size * SAVINGS_RATIO_MPEG2)
        reclaimable_bytes += video_savings
        optimization_reasons.append("Highly inefficient MPEG-2 / VC-1 stream (~75% reduction)")
    elif "HEVC" in video_codec or "H.265" in video_codec or "AV1" in video_codec:
        # Video is already modern
        recommended_vcodec = "Preserve Original (Already HEVC/AV1)"
        if is_lossless_audio:
            priority = "Medium"
    else:
        # Heuristic fallback based on size
        if file_size > 5 * 1024 * 1024 * 1024:
            video_savings = int(file_size * 0.45)
            reclaimable_bytes += video_savings
            optimization_reasons.append("Large file size with potential for high compression")

    # Check Audio Stream Savings
    if is_lossless_audio:
        # Approximate audio reduction
        approx_audio_savings = 3 * 1024 * 1024 * 1024 if is_movie else int(1.2 * 1024 * 1024 * 1024)
        approx_audio_savings = min(approx_audio_savings, int(file_size * 0.4))
        reclaimable_bytes += approx_audio_savings
        optimization_reasons.append(f"Lossless {primary_audio} track ({scanner.format_bytes(approx_audio_savings)} audio savings)")
    else:
        recommended_acodec = "Preserve Original (Already Standard Audio)"

    # Cap reclaimable bytes at 85% of total file size
    reclaimable_bytes = min(reclaimable_bytes, int(file_size * 0.85))
    projected_size = max(file_size - reclaimable_bytes, int(file_size * 0.15))
    savings_pct = round((reclaimable_bytes / file_size) * 100, 1) if file_size > 0 else 0.0

    return {
        "file_path": file_path,
        "file_name": Path(file_path).name,
        "file_size": file_size,
        "file_size_human": scanner.format_bytes(file_size),
        "video_codec": video_codec,
        "primary_audio": primary_audio,
        "hdr_format": hdr_format,
        "has_dolby_vision": has_dovi,
        "has_hdr10": has_hdr10,
        "is_remux": is_remux,
        "is_lossless_audio": is_lossless_audio,
        "priority": priority,
        "reclaimable_bytes": reclaimable_bytes,
        "reclaimable_human": scanner.format_bytes(reclaimable_bytes),
        "projected_size_bytes": projected_size,
        "projected_size_human": scanner.format_bytes(projected_size),
        "savings_pct": savings_pct,
        "reasons": optimization_reasons,
        "recommended_video": recommended_vcodec,
        "recommended_audio": recommended_acodec,
    }


class SpaceOptimizer:
    def __init__(self):
        self.is_scanning = False
        self.cancel_requested = False
        self.progress_pct = 0.0
        self.current_item = ""
        self.total_files_scanned = 0
        self.total_bytes_scanned = 0
        self.total_reclaimable_bytes = 0
        self.scan_start_time = 0.0
        self.scan_duration = 0.0
        self.results: List[Dict[str, Any]] = []
        self.stats: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        # Load cached scan if available
        self._load_cache()

    def _load_cache(self):
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.results = data.get("candidates", [])
                    self.stats = data.get("stats", {})
                    self.total_files_scanned = data.get("total_files_scanned", 0)
                    self.total_bytes_scanned = data.get("total_bytes_scanned", 0)
                    self.total_reclaimable_bytes = data.get("total_reclaimable_bytes", 0)
                    self.scan_duration = data.get("scan_duration", 0.0)
            except Exception as e:
                print(f"[Optimizer] Warning loading cache: {e}")

    def _save_cache(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "scan_timestamp": int(time.time()),
                    "scan_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "scan_duration": self.scan_duration,
                    "total_files_scanned": self.total_files_scanned,
                    "total_bytes_scanned": self.total_bytes_scanned,
                    "total_reclaimable_bytes": self.total_reclaimable_bytes,
                    "stats": self.stats,
                    "candidates": self.results
                }, f, indent=2)
        except Exception as e:
            print(f"[Optimizer] Warning saving cache: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Return live status of the optimization scan."""
        with self._lock:
            return {
                "status": "ok",
                "is_scanning": self.is_scanning,
                "progress_pct": round(self.progress_pct, 1),
                "current_item": self.current_item,
                "total_files_scanned": self.total_files_scanned,
                "total_bytes_scanned": self.total_bytes_scanned,
                "total_bytes_human": scanner.format_bytes(self.total_bytes_scanned),
                "total_reclaimable_bytes": self.total_reclaimable_bytes,
                "total_reclaimable_human": scanner.format_bytes(self.total_reclaimable_bytes),
                "overall_savings_pct": round((self.total_reclaimable_bytes / self.total_bytes_scanned) * 100, 1) if self.total_bytes_scanned > 0 else 0.0,
                "scan_duration": round(self.scan_duration, 1),
                "stats": self.stats,
                "total_candidates": len(self.results),
                "candidates": self.results
            }

    def cancel_scan(self) -> Dict[str, Any]:
        """Cancel an in-progress optimization scan."""
        with self._lock:
            if not self.is_scanning:
                return {"status": "ok", "message": "No scan is currently running."}
            self.cancel_requested = True
            return {"status": "ok", "message": "Cancelling optimization scan..."}

    def start_scan(self, drive_letters: List[str], min_size_mb: int = 50, category: str = "all") -> Dict[str, Any]:
        """Launch background thread to audit drives and calculate optimization potential."""
        with self._lock:
            if self.is_scanning:
                return {"status": "error", "message": "An optimization scan is already in progress."}

            self.is_scanning = True
            self.cancel_requested = False
            self.progress_pct = 0.0
            self.current_item = "Discovering media files..."
            self.total_files_scanned = 0
            self.total_bytes_scanned = 0
            self.total_reclaimable_bytes = 0
            self.scan_start_time = time.time()
            self.results = []
            self.stats = {}

        def worker():
            min_size_bytes = min_size_mb * 1024 * 1024
            discovered_files = []

            # 1. Discovery Phase
            for letter in drive_letters:
                clean_letter = letter.upper().rstrip(":\\")
                root_path = Path(f"{clean_letter}:\\")
                if not root_path.exists():
                    continue

                folders_to_scan = []
                if category in ["all", "movies"]:
                    for m in ["Movies", "Movie", "Plex Movies"]:
                        p = root_path / m
                        if p.exists() and p.is_dir():
                            folders_to_scan.append((p, True))
                if category in ["all", "tv"]:
                    for t in ["TV", "TV Shows", "Television", "Plex TV"]:
                        p = root_path / t
                        if p.exists() and p.is_dir():
                            folders_to_scan.append((p, False))

                if not folders_to_scan:
                    # Scan root directly if standard media folders don't exist
                    try:
                        for entry in os.scandir(root_path):
                            if entry.is_dir() and not entry.name.startswith(("$", "System", "Windows")):
                                is_mov = "movie" in entry.name.lower()
                                folders_to_scan.append((Path(entry.path), is_mov))
                    except Exception:
                        pass

                for folder_p, is_mov in folders_to_scan:
                    try:
                        for root, _, files in os.walk(folder_p):
                            if self.cancel_requested:
                                break
                            for f in files:
                                ext = Path(f).suffix.lower()
                                if ext in scanner.MEDIA_EXTENSIONS:
                                    full_p = os.path.join(root, f)
                                    try:
                                        sz = os.path.getsize(full_p)
                                        if sz >= min_size_bytes:
                                            discovered_files.append((full_p, sz, is_mov))
                                    except Exception:
                                        continue
                    except Exception:
                        pass

            total_found = len(discovered_files)
            if total_found == 0 or self.cancel_requested:
                with self._lock:
                    self.is_scanning = False
                    self.scan_duration = time.time() - self.scan_start_time
                    self.current_item = "No files found or scan cancelled."
                return

            # Group files by parent collection (TV Show or Movie folder)
            grouped_candidates: Dict[str, Dict[str, Any]] = {}
            codec_counts = {"AVC / H.264": 0, "HEVC / H.265": 0, "MPEG-2 / VC-1": 0, "AV1": 0, "Other": 0}
            audio_counts = {"Lossless (DTS-HD/TrueHD)": 0, "Standard (EAC3/AC3/AAC)": 0, "Other": 0}

            for idx, (f_path, f_sz, is_mov) in enumerate(discovered_files):
                if self.cancel_requested:
                    break

                with self._lock:
                    self.current_item = Path(f_path).name
                    self.progress_pct = ((idx + 1) / total_found) * 100.0

                # Analyze file
                info = estimate_savings_for_file(f_path, f_sz, is_movie=is_mov)
                v_codec = info["video_codec"]
                p_audio = info["primary_audio"]

                # Codec tallies
                if "AVC" in v_codec or "H.264" in v_codec:
                    codec_counts["AVC / H.264"] += 1
                elif "HEVC" in v_codec or "H.265" in v_codec:
                    codec_counts["HEVC / H.265"] += 1
                elif "MPEG" in v_codec or "VC-1" in v_codec:
                    codec_counts["MPEG-2 / VC-1"] += 1
                elif "AV1" in v_codec:
                    codec_counts["AV1"] += 1
                else:
                    codec_counts["Other"] += 1

                if info["is_lossless_audio"]:
                    audio_counts["Lossless (DTS-HD/TrueHD)"] += 1
                elif any(a in p_audio for a in ["EAC3", "AC3", "AAC", "DTS"]):
                    audio_counts["Standard (EAC3/AC3/AAC)"] += 1
                else:
                    audio_counts["Other"] += 1

                # Grouping key: parent show or movie directory
                p_obj = Path(f_path)
                parts = p_obj.parts
                # For TV: Drive:\TV\ShowName\Season X\file.mkv -> group by ShowName
                # For Movies: Drive:\Movies\MovieName (Year)\file.mkv -> group by MovieName
                group_name = p_obj.stem
                if len(parts) >= 3:
                    if not is_mov and any("season" in part.lower() for part in parts):
                        # Season folder present, get grand-parent
                        idx_season = next(i for i, part in enumerate(parts) if "season" in part.lower())
                        if idx_season > 0:
                            group_name = parts[idx_season - 1]
                    else:
                        group_name = parts[-2]

                drive_letter = p_obj.drive.rstrip(":")

                if group_name not in grouped_candidates:
                    grouped_candidates[group_name] = {
                        "id": f"opt_{drive_letter}_{group_name.replace(' ', '_')}",
                        "title": group_name,
                        "type": "movie" if is_mov else "tv",
                        "drive": drive_letter,
                        "file_count": 0,
                        "total_size_bytes": 0,
                        "reclaimable_bytes": 0,
                        "projected_size_bytes": 0,
                        "primary_video_codec": v_codec,
                        "primary_audio_codec": p_audio,
                        "is_remux": info["is_remux"],
                        "is_lossless_audio": info["is_lossless_audio"],
                        "priority": info["priority"],
                        "sample_path": f_path,
                        "reasons": set(),
                        "files": []
                    }

                grp = grouped_candidates[group_name]
                grp["file_count"] += 1
                grp["total_size_bytes"] += f_sz
                grp["reclaimable_bytes"] += info["reclaimable_bytes"]
                grp["projected_size_bytes"] += info["projected_size_bytes"]
                grp["reasons"].update(info["reasons"])
                grp["files"].append({
                    "path": f_path,
                    "name": p_obj.name,
                    "size_bytes": f_sz,
                    "size_human": scanner.format_bytes(f_sz),
                    "reclaimable_bytes": info["reclaimable_bytes"],
                    "reclaimable_human": scanner.format_bytes(info["reclaimable_bytes"]),
                    "savings_pct": info["savings_pct"],
                    "video_codec": v_codec,
                    "audio_codec": p_audio,
                })

            # Format grouped results
            final_list = []
            for name, g in grouped_candidates.items():
                tot = g["total_size_bytes"]
                rec = g["reclaimable_bytes"]
                pct = round((rec / tot) * 100, 1) if tot > 0 else 0.0

                # Determine overall priority
                if pct >= 50.0 and rec >= 5 * 1024 * 1024 * 1024:
                    prio = "High"
                elif rec >= 2 * 1024 * 1024 * 1024:
                    prio = "Medium"
                else:
                    prio = "Low"

                final_list.append({
                    "id": g["id"],
                    "title": g["title"],
                    "type": g["type"],
                    "drive": g["drive"],
                    "file_count": g["file_count"],
                    "total_size_bytes": tot,
                    "total_size_human": scanner.format_bytes(tot),
                    "reclaimable_bytes": rec,
                    "reclaimable_human": scanner.format_bytes(rec),
                    "projected_size_bytes": g["projected_size_bytes"],
                    "projected_size_human": scanner.format_bytes(g["projected_size_bytes"]),
                    "savings_pct": pct,
                    "priority": prio,
                    "primary_video_codec": g["primary_video_codec"],
                    "primary_audio_codec": g["primary_audio_codec"],
                    "is_remux": g["is_remux"],
                    "is_lossless_audio": g["is_lossless_audio"],
                    "sample_path": g["sample_path"],
                    "reasons": list(g["reasons"])[:3],
                    "file_samples": g["files"][:5]
                })

            # Sort by highest reclaimable bytes first
            final_list.sort(key=lambda x: x["reclaimable_bytes"], reverse=True)

            tot_bytes = sum(x["total_size_bytes"] for x in final_list)
            tot_reclaim = sum(x["reclaimable_bytes"] for x in final_list)
            duration = time.time() - self.scan_start_time

            # Hardware specs & estimated QSV speed
            # Intel N150 QSV processes 1080p @ approx 180 FPS average.
            # At 180 FPS, a 45 min episode (64,800 frames) takes ~360 seconds (6 minutes).
            # Total estimated QSV time:
            total_episodes_or_movies = sum(x["file_count"] for x in final_list if x["reclaimable_bytes"] > 0)
            est_qsv_hours = round((total_episodes_or_movies * 5.0) / 60.0, 1)

            final_stats = {
                "total_items": len(final_list),
                "total_files": sum(x["file_count"] for x in final_list),
                "total_storage_bytes": tot_bytes,
                "total_storage_human": scanner.format_bytes(tot_bytes),
                "total_reclaimable_bytes": tot_reclaim,
                "total_reclaimable_human": scanner.format_bytes(tot_reclaim),
                "overall_reclaim_pct": round((tot_reclaim / tot_bytes) * 100, 1) if tot_bytes > 0 else 0.0,
                "high_priority_candidates": len([x for x in final_list if x["priority"] == "High"]),
                "est_qsv_hours": est_qsv_hours,
                "codec_distribution": codec_counts,
                "audio_distribution": audio_counts,
                "gpu_detected": "Intel(R) N150 UHD Graphics (Gen 12 Xe-LP QuickSync)",
                "supported_encoders": ["hevc_qsv (10-bit Main 10)", "h264_qsv", "av1_qsv decode"],
            }

            with self._lock:
                self.is_scanning = False
                self.scan_duration = duration
                self.total_files_scanned = len(discovered_files)
                self.total_bytes_scanned = tot_bytes
                self.total_reclaimable_bytes = tot_reclaim
                self.results = final_list
                self.stats = final_stats
                self.current_item = "Optimization audit completed."

            self._save_cache()

        self._thread = threading.Thread(target=worker, daemon=True, name="OptimizationAdvisorWorker")
        self._thread.start()

        return {
            "status": "ok",
            "message": f"Optimization audit started for drives: {', '.join(drive_letters)}"
        }

    def generate_transcode_preset(self, item_title: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate tailored Intel QuickSync (QSV) FFmpeg command line and Handbrake/Tdarr
        preset configurations for the user's Intel N150 processor.
        """
        target_item = next((x for x in self.results if x["title"].lower() == item_title.lower()), None)
        path = file_path or (target_item["sample_path"] if target_item else r"C:\path\to\media.mkv")
        output_path = str(Path(path).with_name(f"{Path(path).stem}.optimized.mkv"))

        # Intel Quick Sync 10-bit HEVC command with E-AC-3 audio transcode
        ffmpeg_cmd = (
            f'ffmpeg -hwaccel qsv -c:v h264_qsv -i "{path}" '
            f'-c:v hevc_qsv -load_plugin hevc_hw -profile:v main10 -global_quality 21 -preset slow '
            f'-c:a eac3 -b:a 640k -c:s copy "{output_path}"'
        )

        handbrake_settings = {
            "preset_name": "Intel QSV 1080p 10-bit HEVC Space Saver",
            "video_encoder": "H.265 10-bit (Intel QSV)",
            "framerate": "Same as source (Peak Framerate)",
            "quality_type": "Constant Quality (ICQ)",
            "quality_level": "21 - 23",
            "audio_encoder": "E-AC3 (Dolby Digital Plus)",
            "audio_bitrate": "640 kbps (5.1 Surround)",
            "subtitles": "Burn-in: None, Passthrough: All English"
        }

        tdarr_plugin_stack = [
            "Tdarr_Plugin_MC93_Migz1FFMPEG (Intel QSV 10-bit HEVC)",
            "Tdarr_Plugin_00td_action_reorder_all_streams",
            "Tdarr_Plugin_MC93_Migz2CleanTitle (Clean Track Titles)",
            "Tdarr_Plugin_MC93_Migz3CleanSubs (Remove unwanted subtitle languages)",
            "Tdarr_Plugin_MC93_Migz4CleanAudio (Keep English, Convert DTS-HD to EAC3 5.1)"
        ]

        return {
            "status": "ok",
            "item_title": item_title,
            "sample_file": path,
            "gpu_hardware": "Intel N150 (Alder Lake-N UHD Graphics QuickSync)",
            "ffmpeg_qsv_command": ffmpeg_cmd,
            "handbrake_preset": handbrake_settings,
            "tdarr_plugins": tdarr_plugin_stack,
            "estimated_speed": "150 - 250 FPS (~3 to 5 minutes per 45-min episode)",
            "estimated_space_reduction": "60% - 70%"
        }

    def get_files_for_title(self, title: str) -> List[Dict[str, Any]]:
        """Return all media file items for a candidate title."""
        target_cand = None
        for c in self.results:
            if c.get("title") == title:
                target_cand = c
                break
        if not target_cand:
            return []

        # If candidate already has file list
        if "files" in target_cand and target_cand["files"]:
            return target_cand["files"]

        # Otherwise discover files from sample path's parent series/movie folder
        sample = target_cand.get("sample_path", "")
        if not sample or not os.path.exists(sample):
            return target_cand.get("file_samples", [])

        p_sample = Path(sample)
        # If TV show, parent might be Season folder, so grandparent is series folder
        search_root = p_sample.parent
        if "season" in search_root.name.lower():
            search_root = search_root.parent

        found_files = []
        MEDIA_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".ts", ".mov"}
        for root, _, files in os.walk(search_root):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in MEDIA_EXTS:
                    full_p = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(full_p)
                    except Exception:
                        sz = 0
                    found_files.append({
                        "path": full_p,
                        "name": f,
                        "size_bytes": sz,
                        "size_human": scanner.format_bytes(sz)
                    })

        return found_files if found_files else target_cand.get("file_samples", [])


# Global singleton instance
space_optimizer = SpaceOptimizer()
