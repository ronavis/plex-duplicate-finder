"""
Unit tests for transcoder.py - In-App Transcode Queue & Runner
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transcoder

class TestTranscoder(unittest.TestCase):

    def setUp(self):
        self.test_state = os.path.join("scratch", "test_transcode_queue.json")
        os.makedirs("scratch", exist_ok=True)
        self.mgr = transcoder.TranscodeQueueManager(state_file=self.test_state)
        self.mgr.clear_queue()

    def tearDown(self):
        if hasattr(self, 'test_state') and os.path.exists(self.test_state):
            try:
                os.remove(self.test_state)
            except Exception:
                pass

    def test_start_queue_empty_error(self):
        res = self.mgr.start_queue()
        self.assertEqual(res["status"], "error")
        self.assertIn("empty", res["message"].lower())

    def test_verify_file_readable_nonexistent(self):
        ok, err = transcoder.verify_file_readable("C:\\nonexistent_file_xyz.mkv")
        self.assertFalse(ok)
        self.assertIn("does not exist", err)

    def test_staging_path_generation(self):
        path, is_staged = transcoder.get_transcode_staging_path("R:\\Movies\\Test.mkv", 1000000)
        self.assertTrue(path.endswith(".mkv"))
        self.assertNotEqual(path, "R:\\Movies\\Test.mkv")

    def test_find_binaries(self):
        ff, pr = transcoder.find_binaries()
        self.assertIsNotNone(ff, "ffmpeg binary should be detected")
        self.assertIsNotNone(pr, "ffprobe binary should be detected")
        self.assertTrue(os.path.exists(ff), f"ffmpeg exists at {ff}")
        self.assertTrue(os.path.exists(pr), f"ffprobe exists at {pr}")

    def test_qsv_support(self):
        ff, _ = transcoder.find_binaries()
        has_qsv = transcoder.check_qsv_support(ff)
        self.assertTrue(has_qsv, "Intel QuickSync (hevc_qsv) should be supported in FFmpeg")

    def test_queue_add_remove_clear(self):
        fake_files = [
            {"path": "C:\\fake\\episode1.mkv", "size_bytes": 1000000000},
            {"path": "C:\\fake\\episode2.mkv", "size_bytes": 2000000000},
        ]
        job1 = transcoder.TranscodeJob("j1", "Show A", "C:\\fake\\ep1.mkv", 1000000000)
        job2 = transcoder.TranscodeJob("j2", "Show A", "C:\\fake\\ep2.mkv", 2000000000)
        self.mgr.queue.append(job1)
        self.mgr.queue.append(job2)

        st = self.mgr.get_status()
        self.assertEqual(st["queue_counts"]["total"], 2)
        self.assertEqual(st["queue_counts"]["pending"], 2)

        # Remove job 1
        res = self.mgr.remove_job("j1")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(self.mgr.queue), 1)
        self.assertEqual(self.mgr.queue[0].id, "j2")

        # Clear queue
        res = self.mgr.clear_queue()
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(self.mgr.queue), 0)

    def test_settings_update(self):
        res = self.mgr.update_settings(safety_mode="direct_replace", quality_preset="high_quality")
        self.assertEqual(res["safety_mode"], "direct_replace")
        self.assertEqual(res["quality_preset"], "high_quality")

        res = self.mgr.update_settings(safety_mode="recycle_bin", quality_preset="balanced")
        self.assertEqual(res["safety_mode"], "recycle_bin")
        self.assertEqual(res["quality_preset"], "balanced")

    def test_verify_integrity_rejects_missing(self):
        ok, msg = self.mgr._verify_integrity("C:\\nonexistent.mkv", "C:\\nonexistent_out.mkv", 100.0)
        self.assertFalse(ok)
        self.assertIn("not created", msg)

    def test_encoder_detection_and_selection(self):
        encoders = self.mgr.available_encoders
        self.assertGreater(len(encoders), 0, "At least one encoder should be detected")
        enc_ids = [e["id"] for e in encoders]
        self.assertIn("hevc_qsv", enc_ids, "Intel hevc_qsv should be detected")
        self.assertIn("libx264", enc_ids, "CPU libx264 should be detected")

        # Test selecting different encoder
        res = self.mgr.update_settings(encoder="libx264")
        self.assertEqual(res["selected_encoder"], "libx264")
        self.assertEqual(self.mgr.selected_encoder, "libx264")

        # Status should reflect active encoder
        st = self.mgr.get_status()
        self.assertEqual(st["selected_encoder"], "libx264")
        self.assertEqual(st["encoder_info"]["id"], "libx264")

        # Switch back to hevc_qsv
        res2 = self.mgr.update_settings(encoder="hevc_qsv")
        self.assertEqual(res2["selected_encoder"], "hevc_qsv")

    def test_encoder_video_args_generation(self):
        flags, codec = transcoder.get_encoder_video_args("hevc_qsv", "balanced")
        self.assertEqual(codec, "hevc")
        self.assertIn("hevc_qsv", flags)

        flags_h264, codec_h264 = transcoder.get_encoder_video_args("h264_qsv", "balanced")
        self.assertEqual(codec_h264, "h264")
        self.assertIn("h264_qsv", flags_h264)

        flags_x265, codec_x265 = transcoder.get_encoder_video_args("libx265", "max_savings")
        self.assertEqual(codec_x265, "hevc")
        self.assertIn("libx265", flags_x265)

if __name__ == "__main__":
    unittest.main()
