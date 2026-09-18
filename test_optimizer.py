import os
import sys
import unittest
from pathlib import Path

# Ensure root dir is in sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import optimizer


class TestSpaceOptimizer(unittest.TestCase):

    def test_estimate_savings_avc_remux(self):
        """Test savings calculation on high-bitrate AVC REMUX with DTS-HD MA."""
        dummy_path = r"R:\TV\The Blacklist\Season 1\The.Blacklist.S01E01.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1.mkv"
        file_size = 7 * 1024 * 1024 * 1024  # 7 GB

        info = optimizer.estimate_savings_for_file(dummy_path, file_size, is_movie=False)
        self.assertIn("AVC", info["video_codec"])
        self.assertIn("DTS-HD", info["primary_audio"])
        self.assertTrue(info["is_remux"])
        self.assertTrue(info["is_lossless_audio"])
        self.assertEqual(info["priority"], "High")
        self.assertGreater(info["reclaimable_bytes"], 3 * 1024 * 1024 * 1024)
        self.assertGreater(info["savings_pct"], 50.0)

    def test_estimate_savings_already_hevc(self):
        """Test that modern HEVC with standard audio is marked low savings / preserve."""
        dummy_path = r"J:\Movies\Inception (2010)\Inception.2010.1080p.HEVC.x265.EAC3.mkv"
        file_size = 2 * 1024 * 1024 * 1024  # 2 GB

        info = optimizer.estimate_savings_for_file(dummy_path, file_size, is_movie=True)
        self.assertIn("HEVC", info["video_codec"])
        self.assertIn("Preserve", info["recommended_video"])
        self.assertLess(info["savings_pct"], 10.0)

    def test_generate_transcode_preset(self):
        """Test preset generator produces Intel QSV commands tailored to N150."""
        preset = optimizer.space_optimizer.generate_transcode_preset("The Blacklist", r"R:\TV\The Blacklist\episode.mkv")
        self.assertEqual(preset["status"], "ok")
        self.assertIn("hevc_qsv", preset["ffmpeg_qsv_command"])
        self.assertIn("Intel N150", preset["gpu_hardware"])
        self.assertIn("handbrake_preset", preset)
        self.assertIn("tdarr_plugins", preset)
        self.assertGreater(len(preset["tdarr_plugins"]), 0)


if __name__ == "__main__":
    unittest.main()
