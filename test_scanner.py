"""
Tests for Plex Duplicate Finder Scanner
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import scanner


class TestPlexScanner(unittest.TestCase):

    def test_clean_title(self):
        self.assertEqual(scanner.clean_title("The Americas (2025)"), "the americas")
        self.assertEqual(scanner.clean_title("57 Seconds (2023)"), "57 seconds")
        self.assertEqual(
            scanner.clean_title("The.Last.of.Us.S01.1080p.BluRay.x265.DDP5.1-B3YG1R"),
            "the last of us"
        )
        self.assertEqual(
            scanner.clean_title("3000.Miles.to.Graceland.2001.1080p.BluRay.x264"),
            "3000 miles to graceland"
        )

    def test_parse_media_metadata(self):
        meta = scanner.parse_media_metadata(
            r"C:\Movies\57.Seconds.2023.2160p.WEB-DL.DDP5.1.Atmos.H.265-FLUX.mkv",
            14000000000
        )
        self.assertEqual(meta["year"], 2023)
        self.assertEqual(meta["resolution"], "4K / 2160p")
        self.assertEqual(meta["codec"], "HEVC / x265")
        self.assertFalse(meta["is_tv"])

        meta_tv = scanner.parse_media_metadata(
            r"C:\TV\The Last of Us\Season 01\The.Last.of.Us.S01E03.1080p.mkv",
            4000000000
        )
        self.assertTrue(meta_tv["is_tv"])
        self.assertEqual(meta_tv["season"], 1)
        self.assertEqual(meta_tv["episode"], 3)
        self.assertEqual(meta_tv["resolution"], "1080p")

    def test_sparse_hashing_and_grouping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two dummy video files with exact same contents
            f1 = os.path.join(tmpdir, "Movie.A.1080p.mkv")
            f2 = os.path.join(tmpdir, "Movie.A.Copy.mkv")
            data = b"HEAD" + (b"\x00" * 100000) + b"MID" + (b"\x00" * 100000) + b"TAIL"

            with open(f1, "wb") as fh:
                fh.write(data)
            with open(f2, "wb") as fh:
                fh.write(data)

            hash1 = scanner.compute_sparse_hash(f1)
            hash2 = scanner.compute_sparse_hash(f2)
            self.assertEqual(hash1, hash2)
            self.assertNotEqual(hash1, "empty")

            # Test grouping
            scan_obj = scanner.MediaScanner()
            res = scan_obj.scan([tmpdir], min_file_size_mb=0)
            self.assertEqual(res["total_media_files"], 2)
            self.assertEqual(len(res["duplicates"]), 1)
            self.assertEqual(res["duplicates"][0]["type"], "exact_match")


if __name__ == "__main__":
    unittest.main()
