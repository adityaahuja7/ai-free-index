import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from aiindex import normalize  # noqa: E402


class LicenseTests(unittest.TestCase):
    def test_known_licenses_pass_through(self):
        self.assertEqual(normalize.normalize_license("MIT"), "MIT")
        self.assertEqual(normalize.normalize_license("Apache-2.0"), "Apache-2.0")

    def test_aliases_are_mapped(self):
        self.assertEqual(normalize.normalize_license("MIT License"), "MIT")
        self.assertEqual(normalize.normalize_license("apache 2.0"), "Apache-2.0")
        self.assertEqual(normalize.normalize_license("GPLv3"), "GPL-3.0")

    def test_unknown_values(self):
        self.assertEqual(normalize.normalize_license("NOASSERTION"), "Unknown")
        self.assertEqual(normalize.normalize_license(None), "Unknown")
        self.assertFalse(normalize.is_open_license("NOASSERTION"))
        self.assertTrue(normalize.is_open_license("AGPL-3.0"))


class UrlTests(unittest.TestCase):
    def test_canonical_url(self):
        self.assertEqual(
            normalize.canonical_url("https://www.GitHub.com/Owner/Repo/"),
            "github.com/owner/repo",
        )
        self.assertEqual(
            normalize.canonical_url("http://github.com/owner/repo.git"),
            "github.com/owner/repo",
        )

    def test_github_slug_filters_noise(self):
        self.assertEqual(normalize.github_slug("https://github.com/ggml-org/llama.cpp"), "ggml-org/llama.cpp")
        self.assertIsNone(normalize.github_slug("https://github.com/topics/llm"))
        self.assertIsNone(normalize.github_slug("https://github.com/sponsors/someone"))
        self.assertIsNone(normalize.github_slug("https://example.com/owner/repo"))
        self.assertIsNone(normalize.github_slug(""))


class CategoryTests(unittest.TestCase):
    def test_topics_win_over_description_noise(self):
        item = {"name": "ollama/ollama", "topics": ["llm", "local-llm"], "description": "Run LLMs locally"}
        self.assertEqual(normalize.guess_category(item), "Serving & Infra")

    def test_serving_from_topics(self):
        item = {"name": "vllm-project/vllm", "topics": ["llm-serving", "inference"],
                "description": "A fast and easy-to-use library for LLM inference"}
        self.assertEqual(normalize.guess_category(item), "Serving & Infra")

    def test_agents(self):
        item = {"name": "x/y", "description": "A multi-agent framework with tool use"}
        self.assertEqual(normalize.guess_category(item), "Agents")

    def test_fallback(self):
        self.assertEqual(normalize.guess_category({"name": "x/y", "description": "hello"}), "Other")

    def test_self_hostable_detection(self):
        self.assertTrue(normalize.guess_self_hostable({"description": "Run it with docker-compose"}))
        self.assertTrue(normalize.guess_self_hostable({"topics": ["self-hosted"]}))
        self.assertFalse(normalize.guess_self_hostable({"description": "A hosted API for agents"}))


class DedupeTests(unittest.TestCase):
    def test_same_id_merges_sources_and_keeps_richest_fields(self):
        items = [
            {"id": "gh:o/r", "source": "github", "kind": "repo", "name": "o/r", "url": "https://github.com/o/r",
             "description": "from github", "stars": 100, "topics": ["llm"]},
            {"id": "gh:o/r", "source": "awesome", "kind": "repo", "name": "o/r", "url": "https://github.com/o/r",
             "description": "from a curated list", "stars": 0, "topics": ["agents"]},
        ]
        merged = normalize.dedupe(items)
        self.assertEqual(len(merged), 1)
        self.assertEqual(sorted(merged[0]["sources"]), ["awesome", "github"])
        self.assertEqual(merged[0]["description"], "from github")
        self.assertEqual(merged[0]["topics"], ["agents", "llm"])
        self.assertEqual(merged[0]["stars"], 100)

    def test_news_story_about_a_known_repo_is_absorbed(self):
        items = [
            {"id": "gh:o/r", "source": "github", "kind": "repo", "name": "o/r",
             "url": "https://github.com/o/r", "stars": 10},
            {"id": "hn:123", "source": "hackernews", "kind": "news", "name": "o/r released",
             "url": "https://github.com/o/r", "points": 420, "comments": 88,
             "discussion_url": "https://news.ycombinator.com/item?id=123"},
        ]
        merged = normalize.dedupe(items)
        self.assertEqual(len(merged), 1)
        self.assertIn("hackernews", merged[0]["sources"])
        self.assertEqual(merged[0]["points"], 420)
        self.assertTrue(merged[0]["discussion_url"].endswith("id=123"))

    def test_unrelated_news_stays_separate(self):
        items = [
            {"id": "hn:9", "source": "hackernews", "kind": "news", "name": "Some launch",
             "url": "https://example.com/launch", "points": 50},
        ]
        merged = normalize.dedupe(items)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["kind"], "news")


class PrepareTests(unittest.TestCase):
    def test_prepare_fills_deterministic_fields(self):
        item = normalize.prepare({
            "id": "gh:o/r", "source": "github", "kind": "repo", "name": "o/r",
            "url": "https://github.com/o/r", "license": "MIT License", "stars": "1200",
        })
        self.assertEqual(item["license"], "MIT")
        self.assertTrue(item["license_open"])
        self.assertEqual(item["stars"], 1200)
        self.assertEqual(item["category"], "Other")
        self.assertEqual(item["maturity"], "usable")
        self.assertEqual(item["sources"], ["github"])


if __name__ == "__main__":
    unittest.main()
