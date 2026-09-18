"""
Comprehensive Unit Test Suite for Plex Space Reclaimer 7-Feature Expansion
"""

import os
import json
import time
import shutil
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import media_inspector
import balancer
import cleaner
import plex_api


class TestMediaInspector(unittest.TestCase):
    def test_synthetic_mkv_header_detection(self):
        # Create temporary file with Matroska HEVC + TrueHD Atmos + Dolby Vision bytes
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            temp_path = f.name
            f.write(b"\x1a\x45\xdf\xa3") # EBML header
            f.write(b"random padding... V_MPEGH/ISO/HEVC ... dovi ... dvhe ...")
            f.write(b"audio track: A_TRUEHD ... dolby atmos 7.1 ... smpte st 2084 ...")
            f.write(b"\x00" * 2048)

        try:
            info = media_inspector.inspect_media_file(temp_path)
            self.assertEqual(info["status"], "ok")
            self.assertIn("HEVC", info["codec_summary"])
            self.assertTrue(info["has_dolby_vision"])
            self.assertTrue(info["has_hdr10"])
            self.assertIn("TrueHD Atmos", info["primary_audio"])
            self.assertIn("7.1", info["audio_channels"])
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_synthetic_mp4_header_detection(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            temp_path = f.name
            f.write(b"....ftypisom....moov....trak....mdia....minf....stbl....stsd....")
            f.write(b"hvc1....ec-3....dvh1....")
            f.write(b"\x00" * 1024)

        try:
            info = media_inspector.inspect_media_file(temp_path)
            self.assertEqual(info["status"], "ok")
            self.assertIn("HEVC", info["codec_summary"])
            self.assertTrue(info["has_dolby_vision"])
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestLibraryCleaner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_cleanup_scanning(self):
        # 1. Create empty folder
        empty_dir = Path(self.test_dir) / "Season 02"
        empty_dir.mkdir()

        # 2. Create sample video
        sample_file = Path(self.test_dir) / "movie-sample.mkv"
        sample_file.write_bytes(b"\x00" * 1024 * 10)

        # 3. Create junk files
        nfo_file = Path(self.test_dir) / "info.nfo"
        nfo_file.write_text("release notes")

        # 4. Create orphan subtitle
        orphan_sub = Path(self.test_dir) / "old_movie.en.srt"
        orphan_sub.write_text("1\n00:00:01 --> 00:00:02\nHello")

        # 5. Create legitimate video + matching subtitle (should NOT be marked orphan)
        real_video = Path(self.test_dir) / "LegitMovie (2020).mkv"
        real_video.write_bytes(b"\x00" * 1024 * 50)
        real_sub = Path(self.test_dir) / "LegitMovie (2020).en.srt"
        real_sub.write_text("1\n00:00:01 --> 00:00:02\nHello")

        res = cleaner.library_cleaner.scan_path_for_cleanup(self.test_dir)
        self.assertEqual(res["status"], "ok")

        empty_paths = [x["path"] for x in res["empty_folders"]]
        self.assertIn(str(empty_dir), empty_paths)

        sample_names = [x["name"] for x in res["sample_files"]]
        self.assertIn("movie-sample.mkv", sample_names)

        junk_names = [x["name"] for x in res["junk_files"]]
        self.assertIn("info.nfo", junk_names)

        orphan_names = [x["name"] for x in res["orphan_subtitles"]]
        self.assertIn("old_movie.en.srt", orphan_names)
        self.assertNotIn("LegitMovie (2020).en.srt", orphan_names)


class TestPlexClient(unittest.TestCase):
    def test_config_save_load(self):
        client = plex_api.PlexClient()
        res = client.save_config("http://192.168.1.100:32400", "test_tok_123", False)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(client.server_url, "http://192.168.1.100:32400")
        self.assertEqual(client.token, "test_tok_123")
        self.assertFalse(client.auto_refresh_on_delete)

        # Restore default
        client.save_config("http://127.0.0.1:32400", "", True)


class TestStorageBalancer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.src_file = Path(self.test_dir) / "source_movie.mkv"
        self.src_file.write_bytes(b"Simulated movie content 1234567890" * 100)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_status_reporting(self):
        status = balancer.storage_balancer.get_status()
        self.assertIn("is_moving", status)
        self.assertIn("speed_mbps", status)
        self.assertFalse(status["is_moving"])


class TestApiEndpoints(unittest.TestCase):
    def test_export_csv_endpoint(self):
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8282/api/export/csv")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/csv", resp.headers.get("Content-Type", ""))
            content = resp.read().decode("utf-8-sig")
            self.assertIn("Group Title", content)
            self.assertIn("Full Path", content)

    def test_audit_history_endpoint(self):
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8282/api/audit/history")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertIsInstance(data["records"], list)

    def test_plex_status_endpoint(self):
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8282/api/plex/status")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertIn("connection", data)


if __name__ == "__main__":
    unittest.main()
