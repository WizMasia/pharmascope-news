import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from google_bing_bridge import score_candidate, find_best_match


class GoogleBingBridgeTests(unittest.TestCase):
    def test_exact_title_and_source_get_high_match_score(self):
        article = {
            "title": "FDA approves a new cancer drug",
            "source": "Reuters",
            "published_time": "Tue, 21 Jul 2026 04:00:00 GMT",
        }
        candidate = {
            "title": "FDA approves a new cancer drug - Reuters",
            "source": "Reuters",
            "url": "https://www.reuters.com/world/health/fda-cancer-drug-123",
            "time": "2 hours ago",
        }

        result = score_candidate(article, candidate)

        self.assertGreaterEqual(result["score"], 80)
        self.assertTrue(result["domain_match"])

    def test_unrelated_candidate_is_rejected(self):
        article = {
            "title": "FDA approves a new cancer drug",
            "source": "Reuters",
        }
        candidate = {
            "title": "Weather forecast for Seoul",
            "source": "Local News",
            "url": "https://example.com/weather",
        }

        result = score_candidate(article, candidate)

        self.assertLess(result["score"], 70)
        self.assertIsNone(find_best_match(article, [candidate], threshold=70))

    def test_best_match_returns_verified_direct_url(self):
        article = {
            "title": "Merck gets FDA approval for cholesterol drug",
            "source": "Reuters",
        }
        candidates = [
            {
                "title": "Merck gets FDA approval for cholesterol drug",
                "source": "Reuters",
                "url": "https://news.google.com/rss/articles/CBM...",
            },
            {
                "title": "Merck gets FDA approval for cholesterol drug",
                "source": "Reuters",
                "url": "https://www.reuters.com/business/healthcare-pharmaceuticals/merck-drug-123",
            },
        ]

        result = find_best_match(article, candidates, threshold=70)

        self.assertIsNotNone(result)
        self.assertTrue(result["url"].startswith("https://www.reuters.com/"))
        self.assertEqual(result["url_source"], "bing_match")


if __name__ == "__main__":
    unittest.main()
