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
        self.mgr = transcoder.TranscodeQueueManager()
        self.mgr.clear_queue()

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
        # Since files don't exist, we test manual TranscodeJob creation
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

if __name__ == "__main__":
    unittest.main()
