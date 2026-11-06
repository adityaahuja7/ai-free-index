import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from aiindex import export, normalize, scoring, store  # noqa: E402


def make_items():
    raw = [
        {"id": "gh:ggml-org/llama.cpp", "source": "github", "kind": "repo", "name": "ggml-org/llama.cpp",
         "url": "https://github.com/ggml-org/llama.cpp", "description": "LLM inference in C/C++",
         "license": "MIT", "stars": 70000, "language": "C++", "topics": ["llm", "llama"],
         "pushed_at": "2026-11-01T00:00:00Z", "created_at": "2023-03-10T00:00:00Z"},
        {"id": "gh:ollama/ollama", "source": "github", "kind": "repo", "name": "ollama/ollama",
         "url": "https://github.com/ollama/ollama", "description": "Get up and running with LLMs locally",
         "license": "MIT", "stars": 90000, "language": "Go", "topics": ["llm", "self-hosted", "local-llm"],
         "pushed_at": "2026-10-20T00:00:00Z"},
        {"id": "hn:42", "source": "hackernews", "kind": "news", "name": "A new open weights model",
         "url": "https://example.com/news", "points": 300, "comments": 40,
         "discussion_url": "https://news.ycombinator.com/item?id=42"},
    ]
    items = normalize.dedupe(raw)
    return scoring.score_all(items)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self.tmp.name) / "test.sqlite3")
        store.init_db(self.conn)
        store.upsert_items(self.conn, make_items())

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_payload_shape_and_stats(self):
        payload = export.build_payload(self.conn)
        self.assertEqual(payload["schema_version"], export.SCHEMA_VERSION)
        self.assertEqual(payload["stats"]["total"], 3)
        self.assertEqual(payload["stats"]["open_source"], 2)
        self.assertEqual(payload["stats"]["self_hostable"], 1)  # only the "locally" hint fires deterministically
        self.assertEqual(payload["stats"]["news"], 1)
        self.assertIn("generated_at", payload)

    def test_items_are_sorted_by_score_and_carry_breakdowns(self):
        payload = export.build_payload(self.conn)
        scores = [item["score"] for item in payload["items"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for item in payload["items"]:
            self.assertIn("popularity", item["score_parts"])

    def test_facets(self):
        facets = export.build_payload(self.conn)["facets"]
        categories = dict((entry["value"], entry["count"]) for entry in facets["category"])
        self.assertIn("Serving & Infra", categories)
        languages = dict((entry["value"], entry["count"]) for entry in facets["language"])
        self.assertEqual(languages["Go"], 1)

    def test_slim_truncates_long_descriptions(self):
        long_text = "x" * 900
        item = export.slim({"id": "x", "description": long_text})
        self.assertEqual(len(item["description"]), 400)
        self.assertTrue(item["description"].endswith("..."))

    def test_index_json_round_trip(self):
        path = export.write_index_json(self.conn, Path(self.tmp.name) / "index.json")
        payload = json.loads(path.read_text())
        self.assertEqual(len(payload["items"]), 3)

    def test_build_site_assembles_static_files(self):
        site = export.build_site(self.conn, Path(self.tmp.name) / "site")
        self.assertTrue((site / "index.html").exists())
        self.assertTrue((site / "app.js").exists())
        self.assertTrue((site / "styles.css").exists())
        self.assertTrue((site / "data" / "index.json").exists())
        payload = json.loads((site / "data" / "index.json").read_text())
        self.assertEqual(len(payload["items"]), 3)
        # rebuild is idempotent
        export.build_site(self.conn, site)
        self.assertTrue((site / "index.html").exists())


class BuildSiteFallbackTests(unittest.TestCase):
    """A CI runner starts from an empty, rebuildable database.

    The committed data/index.json must still be what gets published, otherwise
    the deployed dashboard would show an empty index.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "web").mkdir()
        (self.root / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
        (self.root / "web" / "app.js").write_text("// app", encoding="utf-8")
        (self.root / "web" / "styles.css").write_text("/* css */", encoding="utf-8")
        (self.root / "data").mkdir()
        self.committed = {
            "schema_version": export.SCHEMA_VERSION,
            "generated_at": "2026-11-06T22:35:04Z",
            "stats": {"total": 2},
            "facets": {},
            "items": [{"id": "a"}, {"id": "b"}],
        }
        (self.root / "data" / "index.json").write_text(json.dumps(self.committed), encoding="utf-8")
        self.conn = store.connect(self.root / "data" / "index.sqlite3")
        store.init_db(self.conn)
        self._previous_root = os.environ.get("AIINDEX_ROOT")
        os.environ["AIINDEX_ROOT"] = str(self.root)

    def tearDown(self):
        if self._previous_root is None:
            os.environ.pop("AIINDEX_ROOT", None)
        else:
            os.environ["AIINDEX_ROOT"] = self._previous_root
        self.conn.close()
        self.tmp.cleanup()

    def test_empty_database_publishes_the_committed_index_json(self):
        site = export.build_site(self.conn, self.root / "site")
        payload = json.loads((site / "data" / "index.json").read_text())
        self.assertEqual(payload["stats"]["total"], 2)
        self.assertEqual(len(payload["items"]), 2)
        self.assertTrue((site / ".nojekyll").exists())

    def test_no_database_also_publishes_the_committed_index_json(self):
        site = export.build_site(None, self.root / "site")
        payload = json.loads((site / "data" / "index.json").read_text())
        self.assertEqual(len(payload["items"]), 2)


if __name__ == "__main__":
    unittest.main()
