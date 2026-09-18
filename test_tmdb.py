"""
Unit Tests for TMDb API Client & Search Logic
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import tmdb_api


class TestTmdbApi(unittest.TestCase):
    def test_query_generation_standard(self):
        client = tmdb_api.TmdbClient()
        queries = client._generate_search_queries("Inception.2010.1080p.BluRay.x264")
        self.assertTrue(any("inception" in q.lower() for q in queries))

    def test_query_generation_rifftrax(self):
        client = tmdb_api.TmdbClient()
        queries = client._generate_search_queries("RiffTrax: Day of the Animals (1977)")
        # Should include both full and stripped base title
        self.assertIn("RiffTrax Day of the Animals", queries)
        self.assertIn("Day of the Animals", queries)

    def test_query_generation_mst3k(self):
        client = tmdb_api.TmdbClient()
        queries = client._generate_search_queries("MST3K: The Final Sacrifice 720p")
        self.assertIn("The Final Sacrifice", queries)

    def test_test_connection_invalid_key(self):
        client = tmdb_api.TmdbClient()
        res = client.test_connection("invalid_key_1234567890abcdef")
        self.assertFalse(res["connected"])
        self.assertIn("error", res)

    def test_config_cycle(self):
        client = tmdb_api.TmdbClient()
        orig_key = client.api_key
        orig_enabled = client.enabled

        client.save_config("test_mock_key_abc123", enabled=True, priority="tmdb_first")
        self.assertEqual(client.api_key, "test_mock_key_abc123")
        self.assertTrue(client.is_configured())
        self.assertEqual(client.priority, "tmdb_first")

        # Restore original
        client.save_config(orig_key, enabled=orig_enabled, priority="plex_first")

    def test_backdrop_methods(self):
        client = tmdb_api.TmdbClient()
        self.assertIsNone(client.search_backdrop(""))
        self.assertIsNone(client.get_backdrop_data(""))
        self.assertIsNone(client.get_backdrop_by_title(""))


if __name__ == "__main__":
    unittest.main()
