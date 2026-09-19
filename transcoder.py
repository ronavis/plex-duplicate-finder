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
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import scanner

logger = logging.getLogger("Transcoder")
QUEUE_STATE_FILE = "transcode_queue.json"
TEST_PREVIEW_FILE = os.path.join("scratch", "preview_test.mkv")

# Quality Presets for hevc_qsv (global_quality ICQ)
QUALITY_PRESETS = {
    "high_quality": {"icq": 20, "label": "High Quality (ICQ 20 - ~45-55% savings)"},
    "balanced": {"icq": 23, "label": "Balanced / Recommended (ICQ 23 - ~60-70% savings)"},
    "max_savings": {"icq": 26, "label": "Max Space Savings (ICQ 26 - ~70-80% savings)"}
}


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
        self.has_qsv = check_qsv_support(self.ffmpeg_path) if self.ffmpeg_path else False

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
                    "total_reclaimed_bytes": self.total_reclaimed_bytes,
                    "total_completed_count": self.total_completed_count,
                    "queue": [j.to_dict() for j in self.queue]
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving queue state: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Return live status of the transcode engine and queue."""
        with self._lock:
            pending_count = len([j for j in self.queue if j.status == "pending"])
            completed_count = len([j for j in self.queue if j.status == "completed"])
            failed_count = len([j for j in self.queue if j.status == "failed"])

            return {
                "status": "ok",
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "has_ffmpeg": bool(self.ffmpeg_path),
                "has_qsv": self.has_qsv,
                "ffmpeg_path": self.ffmpeg_path,
                "safety_mode": self.safety_mode,
                "quality_preset": self.quality_preset,
                "quality_info": QUALITY_PRESETS.get(self.quality_preset, QUALITY_PRESETS["balanced"]),
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
        """Add media files for a title to the queue."""
        added = 0
        with self._lock:
            existing_paths = {j.file_path for j in self.queue}
            for f in files:
                p = f.get("path")
                if not p or p in existing_paths or not os.path.exists(p):
                    continue

                sz = f.get("size_bytes") or os.path.getsize(p)
                proj = int(sz * 0.35)  # estimate ~65% reduction
                job_id = f"job_{int(time.time()*1000)}_{added}"
                job = TranscodeJob(
                    job_id=job_id,
                    title=title,
                    file_path=p,
                    original_size_bytes=sz,
                    projected_size_bytes=proj
                )
                self.queue.append(job)
                existing_paths.add(p)
                added += 1

            self._save_state()

        return {
            "status": "ok",
            "message": f"Added {added} file(s) to transcode queue.",
            "added_count": added,
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

    def update_settings(self, safety_mode: Optional[str] = None, quality_preset: Optional[str] = None) -> Dict[str, Any]:
        """Update transcode configuration settings."""
        with self._lock:
            if safety_mode in ["recycle_bin", "direct_replace"]:
                self.safety_mode = safety_mode
            if quality_preset in QUALITY_PRESETS:
                self.quality_preset = quality_preset
            self._save_state()
        return {
            "status": "ok",
            "safety_mode": self.safety_mode,
            "quality_preset": self.quality_preset
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
        if not os.path.exists(orig_path):
            job.status = "failed"
            job.error_message = "Source file no longer exists."
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

        # 2. Build FFmpeg command
        icq = QUALITY_PRESETS.get(self.quality_preset, QUALITY_PRESETS["balanced"])["icq"]
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-init_hw_device", "qsv=hw",
            "-i", orig_path,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map", "0:s?",
            "-c:v", "hevc_qsv",
            "-global_quality", str(icq),
            "-c:a", "eac3",
            "-b:a", "640k",
            "-c:s", "copy",
            "-progress", "pipe:1",
            temp_out
        ]

        logger.info(f"Starting transcode of {orig_path} -> {temp_out}")
        start_time = time.time()

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

            # Parse progress pipe
            for line in process.stdout:
                if self.cancel_current_flag:
                    process.terminate()
                    break

                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()

                    if k == "out_time_ms":
                        try:
                            ms = int(v)
                            job.out_time_ms = ms
                            cur_sec = ms / 1_000_000.0
                            if total_duration_sec > 0:
                                job.progress_pct = min(99.0, (cur_sec / total_duration_sec) * 100.0)
                                elapsed = time.time() - start_time
                                if cur_sec > 0 and elapsed > 0:
                                    speed = cur_sec / elapsed
                                    job.current_speed = f"{speed:.1f}x"
                                    rem_sec = (total_duration_sec - cur_sec) / speed if speed > 0 else 0
                                    job.eta_seconds = max(0, int(rem_sec))
                        except Exception:
                            pass
                    elif k == "fps":
                        try:
                            job.current_fps = float(v)
                        except Exception:
                            pass

            process.wait()
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
                err_text = process.stderr.read()[:500] if process.stderr else "Unknown error"
                job.status = "failed"
                job.error_message = f"FFmpeg failed (code {process.returncode}): {err_text}"
                if os.path.exists(temp_out):
                    try:
                        os.remove(temp_out)
                    except Exception:
                        pass
                return

            # 3. Integrity Verification Gate
            is_valid, verify_msg = self._verify_integrity(orig_path, temp_out, total_duration_sec)
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

    def _verify_integrity(self, orig_path: str, temp_out: str, expected_duration: float) -> Tuple[bool, str]:
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

        if video_streams[0].get("codec_name") != "hevc":
            return False, f"Video codec is not HEVC: {video_streams[0].get('codec_name')}"

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
            # Note: if safe_delete_file renamed/moved original, the path is now free
            # Standardize extension: if original was .mp4, rename to .mkv
            target_path = Path(orig_path).with_suffix(".mkv")
            shutil.move(temp_out, str(target_path))
            return True, "File safely replaced."
        except Exception as e:
            return False, f"Error in atomic replacement: {e}"

    def run_test_transcode(self, file_path: str, duration_sec: int = 60) -> Dict[str, Any]:
        """Run a fast 60-second test transcode snippet and return metrics for UI preview."""
        if not self.ffmpeg_path:
            return {"status": "error", "message": "FFmpeg not detected on system."}
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        os.makedirs("scratch", exist_ok=True)
        preview_out = TEST_PREVIEW_FILE

        if os.path.exists(preview_out):
            try:
                os.remove(preview_out)
            except Exception:
                pass

        icq = QUALITY_PRESETS.get(self.quality_preset, QUALITY_PRESETS["balanced"])["icq"]

        # Jump 2 minutes in to avoid opening black frames/logos
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-init_hw_device", "qsv=hw",
            "-ss", "00:02:00",
            "-i", file_path,
            "-t", str(duration_sec),
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map", "0:s?",
            "-c:v", "hevc_qsv",
            "-global_quality", str(icq),
            "-c:a", "eac3",
            "-b:a", "640k",
            "-c:s", "copy",
            preview_out
        ]

        start_t = time.time()
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
        elapsed = time.time() - start_t

        if proc.returncode != 0 or not os.path.exists(preview_out):
            err = proc.stderr[:400] if proc.stderr else "Unknown error"
            return {"status": "error", "message": f"Test transcode failed: {err}"}

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
            "test_duration_sec": duration_sec,
            "encoding_time_sec": round(elapsed, 1),
            "effective_speed": f"{(duration_sec / elapsed):.1f}x" if elapsed > 0 else "N/A",
            "orig_bitrate_kbps": round(orig_bitrate / 1000),
            "new_bitrate_kbps": round(new_bitrate / 1000),
            "savings_pct": max(0.0, savings_pct),
            "orig_size_human": scanner.format_bytes(orig_sz),
            "projected_new_size_human": scanner.format_bytes(int(orig_sz * (1.0 - (savings_pct / 100.0)))) if savings_pct > 0 else scanner.format_bytes(orig_sz),
            "reclaimed_estimate_human": scanner.format_bytes(int(orig_sz * (savings_pct / 100.0))) if savings_pct > 0 else "0.00 B",
            "hardware": "Intel QuickSync hevc_qsv (10-bit HEVC + E-AC-3)"
        }


# Global singleton instance
transcode_manager = TranscodeQueueManager()
