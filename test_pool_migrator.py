"""
Unit & Integration Tests for PoolMigrator (Smart Drive Offloader)
"""

import os
import shutil
import tempfile
import unittest
import urllib.request
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import pool_migrator


class TestPoolMigrator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.movies_dir = Path(self.test_dir) / "Movies"
        self.tv_dir = Path(self.test_dir) / "TV"
        self.movies_dir.mkdir()
        self.tv_dir.mkdir()

        # Create dummy movie
        movie_folder = self.movies_dir / "Inception (2010)"
        movie_folder.mkdir()
        (movie_folder / "Inception.2010.1080p.mkv").write_bytes(b"\x00" * 1024 * 1024 * 15)  # 15 MB

        # Create dummy TV show
        show_folder = self.tv_dir / "Breaking Bad"
        season_folder = show_folder / "Season 01"
        season_folder.mkdir(parents=True)
        (season_folder / "S01E01.mkv").write_bytes(b"\x00" * 1024 * 1024 * 12)  # 12 MB
        (season_folder / "S01E02.mkv").write_bytes(b"\x00" * 1024 * 1024 * 12)  # 12 MB

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_dir_size_calculation(self):
        sz, count, mtime = pool_migrator.get_dir_size_and_count(self.tv_dir / "Breaking Bad")
        self.assertEqual(count, 2)
        self.assertEqual(sz, 24 * 1024 * 1024)
        self.assertGreater(mtime, 0)

    def test_recommendation_algorithm(self):
        items = [
            {"name": "Breaking Bad", "size_bytes": 24 * 1024 * 1024}
        ]
        res = pool_migrator.pool_migrator.recommend_destinations("R", items)
        self.assertEqual(res["status"], "ok")
        self.assertIn("candidates", res)
        self.assertIn("recommended_drive", res)
        self.assertGreater(len(res["candidates"]), 0)


class TestMigratorApi(unittest.TestCase):
    def test_migrator_status_endpoint(self):
        req = urllib.request.Request("http://127.0.0.1:8282/api/migrator/status")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("is_migrating", data)
            self.assertFalse(data["is_migrating"])

    def test_migrator_recommend_endpoint(self):
        req = urllib.request.Request(
            "http://127.0.0.1:8282/api/migrator/recommend",
            data=json.dumps({
                "source_drive": "R",
                "selected_items": [{"name": "Test Item", "size_bytes": 100 * 1024 * 1024 * 1024}]
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertIn("candidates", data)
            self.assertIn("recommended_drive", data)


if __name__ == "__main__":
    unittest.main()
