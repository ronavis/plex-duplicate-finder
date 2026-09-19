"""
Plex Space Reclaimer - In-App Transcode Queue & Runner
Hardware accelerated video transcoding using Intel QuickSync (hevc_qsv)
for automated library space reclamation with strict integrity checks.
"""

import os
import sys
import time
import json
import shutil
import logging
import threading
import subprocess
import collections
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import scanner

logger = logging.getLogger("Transcoder")
QUEUE_STATE_FILE = "transcode_queue.json"
TEST_PREVIEW_FILE = os.path.join("scratch", "preview_test.mkv")

# Video Encoder Definitions & Profiles
ENCODER_DEFINITIONS = [
    {
        "id": "hevc_qsv",
        "name": "Intel QuickSync HEVC (Hardware - Recommended)",
        "badge": "⚡ Intel QSV HEVC (Hardware)",
        "codec": "hevc",
        "is_hardware": True,
        "vendor": "Intel",
        "description": "Ultra-fast hardware HEVC compression. ~60-75% space reduction at 150-300+ FPS.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "hevc_qsv", "-global_quality", "20"], "label": "High Quality (ICQ 20 - ~50% savings)"},
            "balanced": {"flags": ["-c:v", "hevc_qsv", "-global_quality", "23"], "label": "Balanced / Recommended (ICQ 23 - ~65% savings)"},
            "max_savings": {"flags": ["-c:v", "hevc_qsv", "-global_quality", "26"], "label": "Max Space Savings (ICQ 26 - ~75% savings)"}
        }
    },
    {
        "id": "h264_qsv",
        "name": "Intel QuickSync H.264 (Hardware - Max Compatibility)",
        "badge": "⚡ Intel QSV H.264 (Hardware)",
        "codec": "h264",
        "is_hardware": True,
        "vendor": "Intel",
        "description": "Hardware accelerated H.264. Fast encoding with 100% universal playback compatibility.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "h264_qsv", "-global_quality", "21"], "label": "High Quality (ICQ 21 - ~35% savings)"},
            "balanced": {"flags": ["-c:v", "h264_qsv", "-global_quality", "24"], "label": "Balanced (ICQ 24 - ~45% savings)"},
            "max_savings": {"flags": ["-c:v", "h264_qsv", "-global_quality", "27"], "label": "Max Space Savings (ICQ 27 - ~55% savings)"}
        }
    },
    {
        "id": "hevc_nvenc",
        "name": "NVIDIA NVENC HEVC (Hardware)",
        "badge": "⚡ NVIDIA NVENC HEVC (Hardware)",
        "codec": "hevc",
        "is_hardware": True,
        "vendor": "NVIDIA",
        "description": "NVIDIA GeForce/RTX GPU hardware encoding. High speed HEVC compression.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "hevc_nvenc", "-rc", "vbr", "-cq", "20", "-preset", "p5"], "label": "High Quality (CQ 20 - ~50% savings)"},
            "balanced": {"flags": ["-c:v", "hevc_nvenc", "-rc", "vbr", "-cq", "24", "-preset", "p5"], "label": "Balanced (CQ 24 - ~65% savings)"},
            "max_savings": {"flags": ["-c:v", "hevc_nvenc", "-rc", "vbr", "-cq", "28", "-preset", "p5"], "label": "Max Space Savings (CQ 28 - ~75% savings)"}
        }
    },
    {
        "id": "h264_nvenc",
        "name": "NVIDIA NVENC H.264 (Hardware)",
        "badge": "⚡ NVIDIA NVENC H.264 (Hardware)",
        "codec": "h264",
        "is_hardware": True,
        "vendor": "NVIDIA",
        "description": "NVIDIA GeForce/RTX GPU hardware H.264 encoding.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "20", "-preset", "p5"], "label": "High Quality (CQ 20 - ~35% savings)"},
            "balanced": {"flags": ["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "24", "-preset", "p5"], "label": "Balanced (CQ 24 - ~45% savings)"},
            "max_savings": {"flags": ["-c:v", "h264_nvenc", "-rc", "vbr", "-cq", "28", "-preset", "p5"], "label": "Max Space Savings (CQ 28 - ~55% savings)"}
        }
    },
    {
        "id": "hevc_amf",
        "name": "AMD AMF HEVC (Hardware)",
        "badge": "⚡ AMD AMF HEVC (Hardware)",
        "codec": "hevc",
        "is_hardware": True,
        "vendor": "AMD",
        "description": "AMD Radeon AMF hardware HEVC encoder.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "hevc_amf", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20", "-quality", "quality"], "label": "High Quality (QP 20 - ~50% savings)"},
            "balanced": {"flags": ["-c:v", "hevc_amf", "-rc", "cqp", "-qp_i", "24", "-qp_p", "24", "-quality", "balanced"], "label": "Balanced (QP 24 - ~65% savings)"},
            "max_savings": {"flags": ["-c:v", "hevc_amf", "-rc", "cqp", "-qp_i", "28", "-qp_p", "28", "-quality", "speed"], "label": "Max Space Savings (QP 28 - ~75% savings)"}
        }
    },
    {
        "id": "h264_amf",
        "name": "AMD AMF H.264 (Hardware)",
        "badge": "⚡ AMD AMF H.264 (Hardware)",
        "codec": "h264",
        "is_hardware": True,
        "vendor": "AMD",
        "description": "AMD Radeon AMF hardware H.264 encoder.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20", "-quality", "quality"], "label": "High Quality (QP 20 - ~35% savings)"},
            "balanced": {"flags": ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", "24", "-qp_p", "24", "-quality", "balanced"], "label": "Balanced (QP 24 - ~45% savings)"},
            "max_savings": {"flags": ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", "28", "-qp_p", "28", "-quality", "speed"], "label": "Max Space Savings (QP 28 - ~55% savings)"}
        }
    },
    {
        "id": "libx265",
        "name": "CPU Software x265 (High Efficiency)",
        "badge": "💻 CPU Software x265",
        "codec": "hevc",
        "is_hardware": False,
        "vendor": "Software",
        "description": "Pure CPU software HEVC encoder. Pristine visual quality, higher CPU utilization (~10-25 FPS).",
        "presets": {
            "high_quality": {"flags": ["-c:v", "libx265", "-crf", "20", "-preset", "medium"], "label": "High Quality (CRF 20 - ~50% savings)"},
            "balanced": {"flags": ["-c:v", "libx265", "-crf", "24", "-preset", "medium"], "label": "Balanced (CRF 24 - ~65% savings)"},
            "max_savings": {"flags": ["-c:v", "libx265", "-crf", "28", "-preset", "medium"], "label": "Max Space Savings (CRF 28 - ~75% savings)"}
        }
    },
    {
        "id": "libx264",
        "name": "CPU Software x264 (Universal Compatibility)",
        "badge": "💻 CPU Software x264",
        "codec": "h264",
        "is_hardware": False,
        "vendor": "Software",
        "description": "Standard CPU software H.264 encoder. Universal compatibility across all platforms.",
        "presets": {
            "high_quality": {"flags": ["-c:v", "libx264", "-crf", "19", "-preset", "medium"], "label": "High Quality (CRF 19 - ~35% savings)"},
            "balanced": {"flags": ["-c:v", "libx264", "-crf", "22", "-preset", "medium"], "label": "Balanced (CRF 22 - ~45% savings)"},
            "max_savings": {"flags": ["-c:v", "libx264", "-crf", "26", "-preset", "medium"], "label": "Max Space Savings (CRF 26 - ~55% savings)"}
        }
    }
]

# Legacy dictionary for backward compatibility
QUALITY_PRESETS = ENCODER_DEFINITIONS[0]["presets"]


_CACHED_AVAILABLE_ENCODERS: Optional[List[Dict[str, Any]]] = None


def detect_available_encoders(ffmpeg_path: Optional[str], force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Actively probe FFmpeg to detect all functional hardware and software video encoders on this host."""
    global _CACHED_AVAILABLE_ENCODERS
    if _CACHED_AVAILABLE_ENCODERS is not None and not force_refresh:
        return _CACHED_AVAILABLE_ENCODERS

    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return []
    
    available = []
    for enc_def in ENCODER_DEFINITIONS:
        enc_id = enc_def["id"]
        cmd = [
            ffmpeg_path, "-y",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.04",
            "-c:v", enc_id,
            "-frames:v", "1",
            "-f", "null", "-"
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if proc.returncode == 0:
                available.append({
                    "id": enc_def["id"],
                    "name": enc_def["name"],
                    "badge": enc_def["badge"],
                    "codec": enc_def["codec"],
                    "is_hardware": enc_def["is_hardware"],
                    "vendor": enc_def["vendor"],
                    "description": enc_def["description"]
                })
        except Exception as e:
            logger.debug(f"Encoder probe failed for {enc_id}: {e}")

    # Fallback to software x264/x265 if probe was empty
    if not available:
        available.append({
            "id": "libx264",
            "name": "CPU Software x264 (Universal Compatibility)",
            "badge": "💻 CPU Software x264",
            "codec": "h264",
            "is_hardware": False,
            "vendor": "Software",
            "description": "Standard CPU software H.264 encoder."
        })
    _CACHED_AVAILABLE_ENCODERS = available
    return available


def get_default_encoder(available: List[Dict[str, Any]]) -> str:
    """Select the best encoder by priority: Hardware HEVC -> Hardware H.264 -> Software HEVC -> Software H.264."""
    for enc in available:
        if enc["is_hardware"] and enc["codec"] == "hevc":
            return enc["id"]
    for enc in available:
        if enc["is_hardware"]:
            return enc["id"]
    for enc in available:
        if enc["id"] == "libx265":
            return enc["id"]
    return available[0]["id"] if available else "hevc_qsv"


def get_encoder_video_args(encoder_id: str, preset_name: str) -> Tuple[List[str], str]:
    """Return the FFmpeg video flags and target codec name for an encoder and quality preset."""
    enc_def = next((e for e in ENCODER_DEFINITIONS if e["id"] == encoder_id), None)
    if not enc_def:
        enc_def = ENCODER_DEFINITIONS[0]
    target_codec = enc_def["codec"]
    preset_dict = enc_def["presets"].get(preset_name, enc_def["presets"].get("balanced"))
    if not preset_dict:
        preset_dict = enc_def["presets"]["balanced"]
    return list(preset_dict["flags"]), target_codec


def get_encoder_global_args(encoder_id: str) -> List[str]:
    """Return device init flags if required by the encoder."""
    if encoder_id.endswith("_qsv"):
        return ["-init_hw_device", "qsv=hw"]
    return []


def find_binaries() -> Tuple[Optional[str], Optional[str]]:
    """Locate ffmpeg and ffprobe on the system."""
    # 1. Check WinGet Gyan.FFmpeg install location
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_path = os.path.join(
            local_app_data,
            "Microsoft", "WinGet", "Packages",
            "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
            "ffmpeg-7.1-full_build", "bin"
        )
        ff_bin = os.path.join(winget_path, "ffmpeg.exe")
        pr_bin = os.path.join(winget_path, "ffprobe.exe")
        if os.path.exists(ff_bin) and os.path.exists(pr_bin):
            return ff_bin, pr_bin

    # 2. Check system PATH
    sys_ffmpeg = shutil.which("ffmpeg")
    sys_ffprobe = shutil.which("ffprobe")
    if sys_ffmpeg and sys_ffprobe:
        return sys_ffmpeg, sys_ffprobe

    # 3. Fallback search common paths
    for root in [r"C:\Program Files\ffmpeg\bin", r"C:\ffmpeg\bin"]:
        ff_bin = os.path.join(root, "ffmpeg.exe")
        pr_bin = os.path.join(root, "ffprobe.exe")
        if os.path.exists(ff_bin) and os.path.exists(pr_bin):
            return ff_bin, pr_bin

    return None, None


def check_qsv_support(ffmpeg_path: str) -> bool:
    """Verify that hevc_qsv encoder is available in FFmpeg."""
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        return False
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return "hevc_qsv" in proc.stdout
    except Exception as e:
        logger.warning(f"Error checking QSV support: {e}")
        return False


def get_media_info(ffprobe_path: str, file_path: str) -> Optional[Dict[str, Any]]:
    """Extract format and stream metadata using ffprobe."""
    if not ffprobe_path or not os.path.exists(file_path):
        return None
    try:
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=index,codec_name,codec_type,channels,bit_rate",
            "-of", "json",
            file_path
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception as e:
        logger.warning(f"ffprobe error on {file_path}: {e}")
    return None


def get_optimal_audio_args(source_meta: Optional[Dict[str, Any]]) -> List[str]:
    """
    Intelligently select audio transcode flags:
    - Surround sound (>= 6 channels / 5.1 / 7.1): encode to modern E-AC-3 5.1 @ 640k
    - Stereo / Mono (<= 2 channels):
      - If already AAC, AC3, or MP3: copy directly (-c:a copy) without bloating or re-compression
      - If lossless FLAC, PCM, DTS, or other: compress to clean standard 160k AAC (-c:a aac -b:a 160k)
    """
    if not source_meta:
        return ["-c:a", "eac3", "-b:a", "640k"]

    audio_streams = [s for s in source_meta.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        return ["-c:a", "copy"]

    main_a = audio_streams[0]
    try:
        channels = int(main_a.get("channels", 2))
    except Exception:
        channels = 2
    codec_name = (main_a.get("codec_name") or "").lower()

    if channels >= 6:
        return ["-c:a", "eac3", "-b:a", "640k"]
    else:
        if codec_name in ["aac", "ac3", "mp3"]:
            return ["-c:a", "copy"]
        else:
            return ["-c:a", "aac", "-b:a", "160k"]


class TranscodeJob:
    """Represents an individual transcode task in the queue."""

    def __init__(
        self,
        job_id: str,
        title: str,
        file_path: str,
        original_size_bytes: int,
        projected_size_bytes: int = 0,
        drive: str = ""
    ):
        self.id = job_id
        self.title = title
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.original_size_bytes = original_size_bytes
        self.original_size_human = scanner.format_bytes(original_size_bytes)
        self.projected_size_bytes = projected_size_bytes
        self.drive = drive or (os.path.splitdrive(file_path)[0].rstrip(":") if os.path.splitdrive(file_path)[0] else "")
        self.status = "pending"  # pending, running, completed, failed, skipped, cancelled
        self.progress_pct = 0.0
        self.current_fps = 0.0
        self.current_speed = "0.0x"
        self.eta_seconds = 0
        self.out_time_ms = 0
        self.new_size_bytes = 0
        self.new_size_human = "0.00 B"
        self.reclaimed_bytes = 0
        self.reclaimed_human = "0.00 B"
        self.error_message: Optional[str] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

    def get_eta_human(self) -> str:
        if not self.eta_seconds or self.eta_seconds <= 0:
            return "Finalizing..."
        sec = int(self.eta_seconds)
        if sec < 60:
            return f"{sec} second{'s' if sec != 1 else ''}"
        hrs = sec // 3600
        mins = (sec % 3600) // 60
        rem_sec = sec % 60
        if hrs > 0:
            return f"{hrs} hr {mins} min" if mins > 0 else f"{hrs} hr"
        if rem_sec > 0:
            return f"{mins} min {rem_sec} second{'s' if rem_sec != 1 else ''}"
        return f"{mins} min"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "file_path": self.file_path,
            "drive": self.drive,
            "original_size_bytes": self.original_size_bytes,
            "original_size_human": self.original_size_human,
            "projected_size_bytes": self.projected_size_bytes,
            "status": self.status,
            "progress_pct": round(self.progress_pct, 1),
            "current_fps": round(self.current_fps, 1),
            "current_speed": self.current_speed,
            "eta_seconds": self.eta_seconds,
            "eta_human": self.get_eta_human(),
            "new_size_bytes": self.new_size_bytes,
            "new_size_human": self.new_size_human,
            "reclaimed_bytes": self.reclaimed_bytes,
            "reclaimed_human": self.reclaimed_human,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }


class TranscodeQueueManager:
    """Manages the background transcode queue, workers, and integrity verification."""

    def __init__(self):
        self.queue: List[TranscodeJob] = []
        self.active_job: Optional[TranscodeJob] = None
        self.is_running = False
        self.is_paused = False
        self.cancel_current_flag = False
        self.safety_mode = "recycle_bin"  # "recycle_bin" | "direct_replace"
        self.quality_preset = "balanced"  # "high_quality" | "balanced" | "max_savings"
        self.total_reclaimed_bytes = 0
        self.total_completed_count = 0
        self.total_failed_count = 0

        self.ffmpeg_path, self.ffprobe_path = find_binaries()
        self.available_encoders = detect_available_encoders(self.ffmpeg_path)
        self.selected_encoder = get_default_encoder(self.available_encoders)
        self.has_qsv = any(e["id"].endswith("_qsv") for e in self.available_encoders)

        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._active_process: Optional[subprocess.Popen] = None

        self._load_state()

    def _load_state(self):
        """Restore queue state from disk if available."""
        if not os.path.exists(QUEUE_STATE_FILE):
            return
        try:
            with open(QUEUE_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.safety_mode = data.get("safety_mode", "recycle_bin")
                self.quality_preset = data.get("quality_preset", "balanced")
                self.total_reclaimed_bytes = data.get("total_reclaimed_bytes", 0)
                self.total_completed_count = data.get("total_completed_count", 0)
                saved_enc = data.get("selected_encoder")
                if saved_enc and any(e["id"] == saved_enc for e in self.available_encoders):
                    self.selected_encoder = saved_enc

                for item in data.get("queue", []):
                    job = TranscodeJob(
                        job_id=item["id"],
                        title=item["title"],
                        file_path=item["file_path"],
                        original_size_bytes=item["original_size_bytes"],
                        projected_size_bytes=item.get("projected_size_bytes", 0),
                        drive=item.get("drive", "")
                    )
                    job.status = item.get("status", "pending")
                    job.progress_pct = item.get("progress_pct", 0.0)
                    job.new_size_bytes = item.get("new_size_bytes", 0)
                    job.new_size_human = item.get("new_size_human", "0.00 B")
                    job.reclaimed_bytes = item.get("reclaimed_bytes", 0)
                    job.reclaimed_human = item.get("reclaimed_human", "0.00 B")
                    # If server restarted during running, reset to pending
                    if job.status == "running":
                        job.status = "pending"
                    self.queue.append(job)
        except Exception as e:
            logger.warning(f"Error loading queue state: {e}")

    def _save_state(self):
        """Save queue state to disk."""
        try:
            with open(QUEUE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "safety_mode": self.safety_mode,
                    "quality_preset": self.quality_preset,
                    "selected_encoder": self.selected_encoder,
                    "total_reclaimed_bytes": self.total_reclaimed_bytes,
                    "total_completed_count": self.total_completed_count,
                    "queue": [j.to_dict() for j in self.queue]
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving queue state: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Return live status of the transcode engine, encoders, and queue."""
        with self._lock:
            pending_count = len([j for j in self.queue if j.status == "pending"])
            completed_count = len([j for j in self.queue if j.status == "completed"])
            failed_count = len([j for j in self.queue if j.status == "failed"])
            active_enc_info = next((e for e in self.available_encoders if e["id"] == self.selected_encoder), None)

            return {
                "status": "ok",
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "has_ffmpeg": bool(self.ffmpeg_path),
                "has_qsv": self.has_qsv,
                "ffmpeg_path": self.ffmpeg_path,
                "available_encoders": self.available_encoders,
                "selected_encoder": self.selected_encoder,
                "encoder_info": active_enc_info,
                "safety_mode": self.safety_mode,
                "quality_preset": self.quality_preset,
                "active_job": self.active_job.to_dict() if self.active_job else None,
                "queue_counts": {
                    "total": len(self.queue),
                    "pending": pending_count,
                    "completed": completed_count,
                    "failed": failed_count
                },
                "total_reclaimed_bytes": self.total_reclaimed_bytes,
                "total_reclaimed_human": scanner.format_bytes(self.total_reclaimed_bytes),
                "queue": [j.to_dict() for j in self.queue]
            }

    def add_files_to_queue(self, title: str, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add media files for a title to the queue, re-queuing failed/cancelled items if re-added."""
        added = 0
        requeued = 0
        already_present = 0
        with self._lock:
            existing_jobs = {os.path.normpath(j.file_path): j for j in self.queue}
            for f in files:
                raw_p = f.get("path") if isinstance(f, dict) else str(f)
                if not raw_p:
                    continue
                p = os.path.normpath(raw_p)

                # If job already exists in queue
                if p in existing_jobs:
                    job = existing_jobs[p]
                    if job.status in ["failed", "cancelled"]:
                        job.status = "pending"
                        job.error_message = None
                        job.progress_pct = 0.0
                        job.current_fps = 0.0
                        job.current_speed = "0.0x"
                        job.eta_seconds = 0
                        requeued += 1
                    else:
                        already_present += 1
                    continue

                sz = f.get("size_bytes", 0) if isinstance(f, dict) else 0
                if not sz:
                    try:
                        sz = os.path.getsize(p)
                    except Exception:
                        sz = 0

                proj = int(sz * 0.35) if sz > 0 else 0
                job_id = f"job_{int(time.time()*1000)}_{added}"
                job = TranscodeJob(
                    job_id=job_id,
                    title=title,
                    file_path=p,
                    original_size_bytes=sz,
                    projected_size_bytes=proj
                )
                self.queue.append(job)
                existing_jobs[p] = job
                added += 1

            self._save_state()

        if added > 0:
            msg = f"Added {added} file(s) to transcode queue."
            if requeued > 0:
                msg += f" (Reset {requeued} previously failed file(s) to pending)."
        elif requeued > 0:
            msg = f"Reset {requeued} previously failed file(s) to pending in the queue."
        elif already_present > 0:
            msg = f"'{title}' is already in the transcode queue."
        else:
            msg = f"No eligible media files found for '{title}'."

        return {
            "status": "ok",
            "message": msg,
            "added_count": added,
            "requeued_count": requeued,
            "already_present_count": already_present,
            "total_queue": len(self.queue)
        }

    def remove_job(self, job_id: str) -> Dict[str, Any]:
        """Remove a job from the queue."""
        with self._lock:
            # If removing active job, flag cancel
            if self.active_job and self.active_job.id == job_id:
                self.skip_active_job()
                return {"status": "ok", "message": "Cancelled active job."}

            self.queue = [j for j in self.queue if j.id != job_id]
            self._save_state()

        return {"status": "ok", "message": "Job removed from queue."}

    def clear_queue(self) -> Dict[str, Any]:
        """Clear all non-running items from the queue."""
        with self._lock:
            self.queue = [j for j in self.queue if j.status == "running"]
            self._save_state()
        return {"status": "ok", "message": "Queue cleared."}

    def retry_job(self, job_id: str) -> Dict[str, Any]:
        """Reset a failed or cancelled job back to pending status."""
        with self._lock:
            for j in self.queue:
                if j.id == job_id:
                    j.status = "pending"
                    j.error_message = None
                    j.progress_pct = 0.0
                    j.current_fps = 0.0
                    j.current_speed = "0.0x"
                    j.eta_seconds = 0
                    self._save_state()
                    return {"status": "ok", "message": f"Job reset to pending: {j.filename}"}
        return {"status": "error", "message": "Job not found in queue."}

    def update_settings(
        self,
        safety_mode: Optional[str] = None,
        quality_preset: Optional[str] = None,
        encoder: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update transcode configuration settings."""
        with self._lock:
            if safety_mode in ["recycle_bin", "direct_replace"]:
                self.safety_mode = safety_mode
            if quality_preset in ["high_quality", "balanced", "max_savings"]:
                self.quality_preset = quality_preset
            if encoder and any(e["id"] == encoder for e in self.available_encoders):
                self.selected_encoder = encoder
            self._save_state()
        return {
            "status": "ok",
            "safety_mode": self.safety_mode,
            "quality_preset": self.quality_preset,
            "selected_encoder": self.selected_encoder
        }

    def start_queue(self) -> Dict[str, Any]:
        """Start or resume queue processing worker."""
        if not self.ffmpeg_path:
            return {"status": "error", "message": "FFmpeg not detected on system."}

        with self._lock:
            self.is_paused = False
            if self.is_running and self._worker_thread and self._worker_thread.is_alive():
                return {"status": "ok", "message": "Transcode queue resumed."}

            self.is_running = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

        return {"status": "ok", "message": "Transcode queue worker started."}

    def pause_queue(self) -> Dict[str, Any]:
        """Pause queue execution after current file finishes."""
        with self._lock:
            self.is_paused = True
        return {"status": "ok", "message": "Transcode queue will pause after current file completes."}

    def skip_active_job(self) -> Dict[str, Any]:
        """Cancel the currently active job and proceed to next."""
        with self._lock:
            self.cancel_current_flag = True
            if self._active_process:
                try:
                    self._active_process.terminate()
                except Exception:
                    pass
        return {"status": "ok", "message": "Skipping current job..."}

    def _worker_loop(self):
        """Sequential worker executing pending jobs."""
        logger.info("Transcode queue worker thread started.")

        while True:
            job_to_run: Optional[TranscodeJob] = None

            with self._lock:
                if self.is_paused:
                    self.is_running = False
                    self.active_job = None
                    break

                # Find next pending job
                for j in self.queue:
                    if j.status == "pending":
                        job_to_run = j
                        break

                if not job_to_run:
                    self.is_running = False
                    self.active_job = None
                    break

                self.active_job = job_to_run
                job_to_run.status = "running"
                self.cancel_current_flag = False

            # Process the job
            self._process_single_job(job_to_run)

            with self._lock:
                self._save_state()

        logger.info("Transcode queue worker thread exited.")

    def _process_single_job(self, job: TranscodeJob):
        """Execute FFmpeg transcoding on an individual file with verification."""
        orig_path = job.file_path
        try:
            if not os.path.exists(orig_path):
                job.status = "failed"
                job.error_message = f"File not found on drive {job.drive}: ({job.filename})"
                return
        except OSError as e:
            job.status = "failed"
            if getattr(e, 'winerror', None) == 1117 or "I/O device error" in str(e):
                job.error_message = f"Drive I/O error on {job.drive}: (WinError 1117). External USB drive may need reconnecting or checking."
            else:
                job.error_message = f"Drive access error on {job.drive}: {str(e)}"
            return

        temp_out = orig_path + ".tmp_opt.mkv"
        if os.path.exists(temp_out):
            try:
                os.remove(temp_out)
            except Exception:
                pass

        # 1. Get source duration for progress tracking
        source_meta = get_media_info(self.ffprobe_path, orig_path)
        total_duration_sec = 0.0
        if source_meta and "format" in source_meta:
            try:
                total_duration_sec = float(source_meta["format"].get("duration", 0))
            except Exception:
                total_duration_sec = 0.0

        # 2. Build FFmpeg command with chosen encoder and smart audio handling
        audio_args = get_optimal_audio_args(source_meta)
        video_args, target_codec = get_encoder_video_args(self.selected_encoder, self.quality_preset)
        global_args = get_encoder_global_args(self.selected_encoder)

        cmd = [
            self.ffmpeg_path,
            "-y",
            *global_args,
            "-i", orig_path,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map", "0:s?",
            *video_args,
            *audio_args,
            "-c:s", "copy",
            "-progress", "pipe:1",
            temp_out
        ]

        logger.info(f"Starting transcode of {orig_path} -> {temp_out} using {self.selected_encoder}")
        start_time = time.time()
        stderr_lines = collections.deque(maxlen=50)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self._active_process = process

            # Drain stderr asynchronously to prevent pipe buffer exhaustion deadlocks on Windows
            def drain_stderr():
                try:
                    for err_line in process.stderr:
                        stderr_lines.append(err_line)
                except Exception:
                    pass

            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()

            # Parse progress pipe
            for line in process.stdout:
                if self.cancel_current_flag:
                    process.terminate()
                    break

                line = line.strip()
                if not line or "=" not in line:
                    continue

                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()

                cur_sec = None
                if k in ("out_time_us", "out_time_ms"):
                    try:
                        ms = int(v)
                        cur_sec = ms / 1_000_000.0
                        job.out_time_ms = ms
                    except Exception:
                        pass
                elif k == "out_time":
                    if v and v != "N/A" and ":" in v:
                        try:
                            parts = v.split(":")
                            if len(parts) == 3:
                                cur_sec = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                        except Exception:
                            pass
                elif k == "fps":
                    try:
                        job.current_fps = float(v)
                    except Exception:
                        pass
                elif k == "speed":
                    if v and v != "N/A":
                        job.current_speed = v

                if cur_sec is not None and cur_sec >= 0 and total_duration_sec > 0:
                    job.progress_pct = min(99.0, max(0.0, (cur_sec / total_duration_sec) * 100.0))
                    elapsed = time.time() - start_time
                    if cur_sec > 0 and elapsed > 0:
                        speed_val = cur_sec / elapsed
                        if not job.current_speed or job.current_speed == "0.0x":
                            job.current_speed = f"{speed_val:.1f}x"
                        rem_sec = (total_duration_sec - cur_sec) / speed_val if speed_val > 0 else 0
                        job.eta_seconds = max(0, int(rem_sec))

            process.wait()
            stderr_thread.join(timeout=2.0)
            self._active_process = None

            if self.cancel_current_flag:
                job.status = "cancelled"
                job.error_message = "Cancelled by user."
                if os.path.exists(temp_out):
                    try:
                        os.remove(temp_out)
                    except Exception:
                        pass
                return

            if process.returncode != 0:
                err_text = "".join(list(stderr_lines)[-15:]) if stderr_lines else "Unknown error"
                job.status = "failed"
                if process.returncode in (4294967274, -22) or "I/O error" in err_text or "Input/output error" in err_text:
                    job.error_message = f"Drive I/O interruption on {job.drive}: (USB read/write latency timeout or disconnect)."
                else:
                    job.error_message = f"FFmpeg failed (code {process.returncode}): {err_text[:300]}"
                if os.path.exists(temp_out):
                    try:
                        os.remove(temp_out)
                    except Exception:
                        pass
                return

            # 3. Integrity Verification Gate
            is_valid, verify_msg = self._verify_integrity(orig_path, temp_out, total_duration_sec, target_codec=target_codec)
            if not is_valid:
                job.status = "failed"
                job.error_message = f"Verification failed: {verify_msg}"
                if os.path.exists(temp_out):
                    try:
                        os.remove(temp_out)
                    except Exception:
                        pass
                return

            # 4. Safe Atomic Replacement
            new_sz = os.path.getsize(temp_out)
            reclaimed = max(0, job.original_size_bytes - new_sz)

            replace_ok, replace_msg = self._safe_replace_file(orig_path, temp_out)
            if not replace_ok:
                job.status = "failed"
                job.error_message = f"Replacement failed: {replace_msg}"
                return

            # Success!
            job.status = "completed"
            job.progress_pct = 100.0
            job.new_size_bytes = new_sz
            job.new_size_human = scanner.format_bytes(new_sz)
            job.reclaimed_bytes = reclaimed
            job.reclaimed_human = scanner.format_bytes(reclaimed)
            job.completed_at = time.time()
            job.current_fps = 0.0
            job.current_speed = "Done"
            job.eta_seconds = 0

            with self._lock:
                self.total_reclaimed_bytes += reclaimed
                self.total_completed_count += 1

            logger.info(f"Successfully optimized {orig_path} (Reclaimed: {job.reclaimed_human})")

        except Exception as e:
            job.status = "failed"
            job.error_message = f"Transcode exception: {str(e)}"
            if os.path.exists(temp_out):
                try:
                    os.remove(temp_out)
                except Exception:
                    pass

    def _verify_integrity(self, orig_path: str, temp_out: str, expected_duration: float, target_codec: str = "hevc") -> Tuple[bool, str]:
        """Verify output file validity before modifying the original."""
        if not os.path.exists(temp_out):
            return False, "Output file was not created."

        out_sz = os.path.getsize(temp_out)
        if out_sz < 100 * 1024:  # smaller than 100KB is definitely bad
            return False, "Output file is suspiciously small (<100KB)."

        info = get_media_info(self.ffprobe_path, temp_out)
        if not info or "streams" not in info:
            return False, "Unable to probe output media streams."

        streams = info.get("streams", [])
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

        if not video_streams:
            return False, "No video stream found in output file."

        vcodec = video_streams[0].get("codec_name", "").lower()
        if target_codec == "hevc" and vcodec != "hevc":
            return False, f"Video codec is not HEVC: {vcodec}"
        elif target_codec == "h264" and vcodec not in ["h264", "avc"]:
            return False, f"Video codec is not H.264: {vcodec}"

        # Check duration if expected
        if expected_duration > 5.0:
            out_dur = float(info.get("format", {}).get("duration", 0))
            if abs(out_dur - expected_duration) > 2.5:
                return False, f"Duration mismatch: orig={expected_duration:.1f}s, new={out_dur:.1f}s"

        return True, "Integrity verified successfully."

    def _safe_replace_file(self, orig_path: str, temp_out: str) -> Tuple[bool, str]:
        """Safely stage the original to Recycle Bin or backup, then rename temp file."""
        try:
            # Stage original to Recycle Bin
            use_bin = (self.safety_mode == "recycle_bin")
            ok, msg = scanner.safe_delete_file(orig_path, use_recycle_bin=use_bin)
            if not ok:
                return False, f"Could not stage original file: {msg}"

            # Rename temp file to target filename
            target_path = Path(orig_path).with_suffix(".mkv")
            shutil.move(temp_out, str(target_path))
            return True, "File safely replaced."
        except Exception as e:
            return False, f"Error in atomic replacement: {e}"

    def run_test_transcode(
        self,
        file_path: str,
        duration_sec: int = 15,
        encoder: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run a fast test transcode snippet and return metrics for UI preview."""
        if not self.ffmpeg_path:
            return {"status": "error", "message": "FFmpeg not detected on system."}
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        active_encoder = encoder if (encoder and any(e["id"] == encoder for e in self.available_encoders)) else self.selected_encoder
        video_args, target_codec = get_encoder_video_args(active_encoder, self.quality_preset)
        global_args = get_encoder_global_args(active_encoder)
        enc_info = next((e for e in self.available_encoders if e["id"] == active_encoder), None)
        enc_label = enc_info["name"] if enc_info else active_encoder

        os.makedirs("scratch", exist_ok=True)
        preview_out = TEST_PREVIEW_FILE

        if os.path.exists(preview_out):
            try:
                os.remove(preview_out)
            except Exception:
                pass

        audio_args = get_optimal_audio_args(get_media_info(self.ffprobe_path, file_path))

        test_dur = min(max(duration_sec, 5), 30) if duration_sec > 0 else 15
        cmd = [
            self.ffmpeg_path,
            "-y",
            *global_args,
            "-ss", "00:02:00",
            "-i", file_path,
            "-t", str(test_dur),
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map", "0:s?",
            *video_args,
            *audio_args,
            "-c:s", "copy",
            preview_out
        ]

        start_t = time.time()
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
            elapsed = time.time() - start_t
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": f"Test transcode timed out after 45 seconds. The drive ({os.path.splitdrive(file_path)[0]}) may be spinning up, disconnected, or experiencing high I/O latency."
            }
        except Exception as e:
            return {"status": "error", "message": f"Test transcode execution error: {str(e)}"}

        if proc.returncode != 0 or not os.path.exists(preview_out):
            err = proc.stderr[-400:] if proc.stderr else "Unknown error"
            return {"status": "error", "message": f"Test transcode failed (code {proc.returncode}): {err}"}

        # Calculate snippet stats
        orig_info = get_media_info(self.ffprobe_path, file_path)
        new_info = get_media_info(self.ffprobe_path, preview_out)

        orig_sz = os.path.getsize(file_path)
        new_snippet_sz = os.path.getsize(preview_out)

        orig_bitrate = 0
        new_bitrate = 0
        if orig_info and "format" in orig_info:
            orig_bitrate = int(orig_info["format"].get("bit_rate", 0))
        if new_info and "format" in new_info:
            new_bitrate = int(new_info["format"].get("bit_rate", 0))

        # Projected savings pct based on bitrates
        savings_pct = round(((orig_bitrate - new_bitrate) / orig_bitrate) * 100, 1) if orig_bitrate > 0 else 0.0

        return {
            "status": "ok",
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "preview_url": "/api/transcode/preview_clip",
            "test_duration_sec": test_dur,
            "encoding_time_sec": round(elapsed, 1),
            "effective_speed": f"{(test_dur / elapsed):.1f}x" if elapsed > 0 else "N/A",
            "orig_bitrate_kbps": round(orig_bitrate / 1000),
            "new_bitrate_kbps": round(new_bitrate / 1000),
            "savings_pct": max(0.0, savings_pct),
            "orig_size_human": scanner.format_bytes(orig_sz),
            "projected_new_size_human": scanner.format_bytes(int(orig_sz * (1.0 - (savings_pct / 100.0)))) if savings_pct > 0 else scanner.format_bytes(orig_sz),
            "reclaimed_estimate_human": scanner.format_bytes(int(orig_sz * (savings_pct / 100.0))) if savings_pct > 0 else "0.00 B",
            "encoder_id": active_encoder,
            "hardware": enc_label
        }


# Global singleton instance
transcode_manager = TranscodeQueueManager()

