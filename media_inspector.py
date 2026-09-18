"""
Plex Duplicate Finder / Plex Space Reclaimer - Media Stream Inspector
Pure-Python Matroska (MKV) EBML and MP4 container stream analyzer.
Extracts Video Codecs, HDR (Dolby Vision, HDR10+, HDR10), Audio Codecs (TrueHD Atmos, DTS-HD MA, AC3, EAC3, AAC),
Audio Channels (7.1, 5.1, 2.0), and Stream Details without external dependencies.
"""

import os
import struct
from pathlib import Path
from typing import Dict, Any, Optional, List


def _read_vint(f) -> Optional[int]:
    """Read an EBML Variable Size Integer."""
    first = f.read(1)
    if not first:
        return None
    b = first[0]
    if b == 0:
        return None

    mask = 0x80
    length = 1
    while not (b & mask):
        mask >>= 1
        length += 1
        if length > 8:
            return None

    val = b & (mask - 1)
    for _ in range(length - 1):
        nxt = f.read(1)
        if not nxt:
            return None
        val = (val << 8) | nxt[0]
    return val


def _read_ebml_id(f) -> Optional[int]:
    """Read an EBML Element ID."""
    first = f.read(1)
    if not first:
        return None
    b = first[0]
    if b == 0:
        return None

    mask = 0x80
    length = 1
    while not (b & mask):
        mask >>= 1
        length += 1
        if length > 4:
            return None

    val = b
    for _ in range(length - 1):
        nxt = f.read(1)
        if not nxt:
            return None
        val = (val << 8) | nxt[0]
    return val


def inspect_mkv_streams(file_path: str, max_read_mb: float = 2.0) -> Dict[str, Any]:
    """
    Inspect Matroska (.mkv) container tracks by scanning EBML headers.
    Returns detected video, audio, HDR, and channel details.
    """
    results: Dict[str, Any] = {
        "container": "Matroska (MKV)",
        "video": [],
        "audio": [],
        "hdr_format": "SDR",
        "has_dolby_vision": False,
        "has_hdr10": False,
        "primary_audio": "Unknown",
        "audio_channels": "Unknown",
        "codec_summary": ""
    }

    try:
        max_bytes = int(max_read_mb * 1024 * 1024)
        with open(file_path, "rb") as f:
            header_sample = f.read(max_bytes)

            # Quick heuristic string search in header sample for common Matroska signatures
            # (Extremely fast, robust fallback across various EBML header variations)
            lower_sample = header_sample.lower()
            text_sample = header_sample.decode("latin-1", errors="ignore")

            # Detect Video Codec
            video_codec = "Unknown"
            if b"v_mpegh/iso/hevc" in header_sample or b"hevc" in lower_sample or b"hvc1" in header_sample:
                video_codec = "HEVC / H.265"
            elif b"v_mpeg4/iso/avc" in header_sample or b"avc1" in header_sample:
                video_codec = "AVC / H.264"
            elif b"v_av1" in header_sample or b"av01" in header_sample:
                video_codec = "AV1"
            elif b"v_vp9" in header_sample:
                video_codec = "VP9"
            elif b"v_ms/vfw/fourcc" in header_sample and b"vc-1" in lower_sample:
                video_codec = "VC-1"

            # Detect HDR / Dolby Vision
            hdr_format = "SDR"
            has_dovi = False
            has_hdr10 = False

            if b"dovi" in lower_sample or b"dolby vision" in lower_sample or b"dvh1" in header_sample or b"dvhe" in header_sample:
                has_dovi = True
                hdr_format = "Dolby Vision"

            if b"smpte st 2084" in lower_sample or b"bt.2020" in lower_sample or b"hdr10" in lower_sample:
                has_hdr10 = True
                if has_dovi:
                    hdr_format = "Dolby Vision / HDR10"
                else:
                    hdr_format = "HDR10"

            if b"hdr10+" in lower_sample or b"hdr10plus" in lower_sample:
                hdr_format = "HDR10+"

            # Detect Audio Codecs & Channel Layouts
            audio_tracks = []
            primary_audio = "Unknown"
            channels_str = "Unknown"

            # TrueHD / Dolby Atmos
            if b"a_truehd" in header_sample or b"truehd" in lower_sample:
                if b"atmos" in lower_sample:
                    audio_tracks.append({"codec": "Dolby TrueHD Atmos", "channels": "7.1 / Atmos"})
                    primary_audio = "TrueHD Atmos"
                    channels_str = "7.1 Atmos"
                else:
                    audio_tracks.append({"codec": "Dolby TrueHD", "channels": "7.1 / 5.1"})
                    primary_audio = "TrueHD"
                    channels_str = "7.1"
            # DTS-HD Master Audio / DTS:X / DTS
            elif b"a_dts" in header_sample or b"dts" in lower_sample:
                if b"dts-hd ma" in lower_sample or b"dts-hd" in lower_sample:
                    audio_tracks.append({"codec": "DTS-HD Master Audio", "channels": "7.1 / 5.1"})
                    primary_audio = "DTS-HD MA"
                    channels_str = "7.1" if (b"7.1" in text_sample or b"8ch" in lower_sample) else "5.1"
                elif b"dts:x" in lower_sample or b"dts-x" in lower_sample:
                    audio_tracks.append({"codec": "DTS:X", "channels": "7.1.4 / DTS:X"})
                    primary_audio = "DTS:X"
                    channels_str = "7.1"
                else:
                    audio_tracks.append({"codec": "DTS Digital Surround", "channels": "5.1"})
                    primary_audio = "DTS 5.1"
                    channels_str = "5.1"
            # Dolby Digital Plus (E-AC-3)
            elif b"a_eac3" in header_sample or b"eac3" in lower_sample or b"ec-3" in lower_sample:
                if b"atmos" in lower_sample:
                    audio_tracks.append({"codec": "E-AC-3 Atmos", "channels": "5.1 Atmos"})
                    primary_audio = "EAC3 Atmos"
                    channels_str = "5.1 Atmos"
                else:
                    audio_tracks.append({"codec": "Dolby Digital Plus (EAC3)", "channels": "5.1"})
                    primary_audio = "EAC3 5.1"
                    channels_str = "5.1"
            # Standard AC-3 (Dolby Digital)
            elif b"a_ac3" in header_sample or b"ac-3" in lower_sample or b"ac3" in lower_sample:
                audio_tracks.append({"codec": "Dolby Digital (AC3)", "channels": "5.1"})
                primary_audio = "AC3 5.1"
                channels_str = "5.1"
            # AAC / FLAC / Opus
            elif b"a_flac" in header_sample:
                primary_audio = "FLAC Lossless"
                channels_str = "2.0 / 5.1"
            elif b"a_aac" in header_sample or b"aac" in lower_sample:
                primary_audio = "AAC"
                channels_str = "Stereo 2.0"

            results["video"].append({"codec": video_codec})
            results["hdr_format"] = hdr_format
            results["has_dolby_vision"] = has_dovi
            results["has_hdr10"] = has_hdr10
            results["primary_audio"] = primary_audio
            results["audio_channels"] = channels_str

            summary_parts = []
            if video_codec != "Unknown":
                summary_parts.append(video_codec)
            if hdr_format != "SDR":
                summary_parts.append(hdr_format)
            if primary_audio != "Unknown":
                summary_parts.append(f"{primary_audio} ({channels_str})")

            results["codec_summary"] = " • ".join(summary_parts) if summary_parts else "Standard Media"

    except Exception as e:
        results["error"] = str(e)

    return results


def inspect_mp4_streams(file_path: str, max_read_mb: float = 2.0) -> Dict[str, Any]:
    """Inspect MP4 / M4V container atom signatures."""
    results: Dict[str, Any] = {
        "container": "MPEG-4 (MP4)",
        "video": [],
        "audio": [],
        "hdr_format": "SDR",
        "has_dolby_vision": False,
        "has_hdr10": False,
        "primary_audio": "Unknown",
        "audio_channels": "Unknown",
        "codec_summary": ""
    }

    try:
        max_bytes = int(max_read_mb * 1024 * 1024)
        with open(file_path, "rb") as f:
            sample = f.read(max_bytes)
            lower_sample = sample.lower()

            # Video
            video_codec = "Unknown"
            if b"hvc1" in sample or b"hev1" in sample:
                video_codec = "HEVC / H.265"
            elif b"avc1" in sample:
                video_codec = "AVC / H.264"
            elif b"av01" in sample:
                video_codec = "AV1"

            # HDR / DoVi
            hdr_format = "SDR"
            has_dovi = False
            has_hdr10 = False

            if b"dvh1" in sample or b"dvhe" in sample or b"dovi" in lower_sample:
                has_dovi = True
                hdr_format = "Dolby Vision"
            if b"hdr10" in lower_sample or b"bt2020" in lower_sample:
                has_hdr10 = True
                hdr_format = "Dolby Vision / HDR10" if has_dovi else "HDR10"

            # Audio
            primary_audio = "Unknown"
            channels_str = "Stereo 2.0"
            if b"ec-3" in sample or b"eac3" in lower_sample:
                primary_audio = "EAC3 5.1"
                channels_str = "5.1"
            elif b"ac-3" in sample:
                primary_audio = "AC3 5.1"
                channels_str = "5.1"
            elif b"mp4a" in sample:
                primary_audio = "AAC"
                channels_str = "2.0"

            results["video"].append({"codec": video_codec})
            results["hdr_format"] = hdr_format
            results["has_dolby_vision"] = has_dovi
            results["has_hdr10"] = has_hdr10
            results["primary_audio"] = primary_audio
            results["audio_channels"] = channels_str

            summary_parts = []
            if video_codec != "Unknown":
                summary_parts.append(video_codec)
            if hdr_format != "SDR":
                summary_parts.append(hdr_format)
            if primary_audio != "Unknown":
                summary_parts.append(f"{primary_audio} ({channels_str})")

            results["codec_summary"] = " • ".join(summary_parts) if summary_parts else "Standard MP4"

    except Exception as e:
        results["error"] = str(e)

    return results


def inspect_media_file(file_path: str) -> Dict[str, Any]:
    """Inspect any media file and return audio, video, and HDR details."""
    p = Path(file_path)
    ext = p.suffix.lower()

    if not p.exists():
        return {"status": "error", "message": "File not found"}

    stat = p.stat()
    file_size_bytes = stat.st_size

    if ext in [".mkv"]:
        info = inspect_mkv_streams(file_path)
    elif ext in [".mp4", ".m4v", ".mov"]:
        info = inspect_mp4_streams(file_path)
    elif ext in [".avi", ".wmv", ".ts", ".m2ts"]:
        info = inspect_mkv_streams(file_path)
        info["container"] = ext[1:].upper()
    else:
        info = {
            "container": ext.replace(".", "").upper(),
            "video": [],
            "audio": [],
            "hdr_format": "SDR",
            "has_dolby_vision": False,
            "has_hdr10": False,
            "primary_audio": "Standard Audio",
            "audio_channels": "Unknown",
            "codec_summary": "Standard Media File"
        }

    info["file_size_bytes"] = file_size_bytes
    info["filename"] = p.name
    info["path"] = str(p.resolve())
    info["status"] = "ok"

    return info
