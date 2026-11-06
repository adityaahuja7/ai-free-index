import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from aiindex import store  # noqa: E402


def sample_item(**overrides):
    base = {
        "id": "gh:o/r",
        "source": "github",
        "sources": ["github"],
        "kind": "repo",
        "name": "o/r",
        "url": "https://github.com/o/r",
        "description": "An open-source thing",
        "license": "MIT",
        "license_open": True,
        "stars": 100,
        "topics": ["llm"],
        "tags": ["llm", "mit"],
        "category": "LLM",
        "self_hostable": True,
        "score": 42.5,
        "score_parts": {"popularity": 30.0},
    }
    base.update(overrides)
    return base


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite3"
        self.conn = store.connect(self.db)
        store.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_insert_then_update(self):
        inserted, updated = store.upsert_items(self.conn, [sample_item()])
        self.assertEqual((inserted, updated), (1, 0))
        inserted, updated = store.upsert_items(self.conn, [sample_item(stars=250)])
        self.assertEqual((inserted, updated), (0, 1))
        row = store.get_item(self.conn, "gh:o/r")
        self.assertEqual(row["stars"], 250)
        self.assertTrue(row["self_hostable"])
        self.assertEqual(row["topics"], ["llm"])
        self.assertEqual(row["score_parts"]["popularity"], 30.0)

    def test_first_seen_is_preserved(self):
        store.upsert_items(self.conn, [sample_item()])
        first = store.get_item(self.conn, "gh:o/r")["first_seen"]
        self.conn.execute("UPDATE items SET last_seen = '2000-01-01T00:00:00Z' WHERE id = 'gh:o/r'")
        store.upsert_items(self.conn, [sample_item(stars=999)])
        row = store.get_item(self.conn, "gh:o/r")
        self.assertEqual(row["first_seen"], first)

    def test_enrichment_applies_and_marks_model(self):
        store.upsert_items(self.conn, [sample_item()])
        store.apply_enrichment(self.conn, "gh:o/r", {
            "summary": "Serves models locally.",
            "category": "Serving & Infra",
            "tags": ["serving", "gguf"],
            "self_hostable": True,
            "maturity": "production",
            "target_user": "ops",
            "difficulty": 2,
            "free_tier_notes": "Runs on a laptop.",
            "_model": "gemini-2.5-flash",
            "_prompt_version": "v1",
        })
        row = store.get_item(self.conn, "gh:o/r")
        self.assertEqual(row["summary"], "Serves models locally.")
        self.assertEqual(row["tags"], ["serving", "gguf"])
        self.assertEqual(row["difficulty"], 2)
        self.assertEqual(row["enrichment_model"], "gemini-2.5-flash")
        self.assertTrue(row["enriched_at"])

    def test_items_needing_enrichment_respects_model_and_prompt_version(self):
        store.upsert_items(self.conn, [sample_item(), sample_item(id="gh:a/b", stars=5)])
        pending = store.items_needing_enrichment(self.conn, "gemini-2.5-flash", "v1", limit=10)
        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["id"], "gh:o/r")  # ordered by stars
        store.mark_enrichment_attempt(self.conn, "gh:o/r", "gemini-2.5-flash", "v1")
        pending = store.items_needing_enrichment(self.conn, "gemini-2.5-flash", "v1", limit=10)
        self.assertEqual([entry["id"] for entry in pending], ["gh:a/b"])
        # a new prompt version re-opens every item
        pending = store.items_needing_enrichment(self.conn, "gemini-2.5-flash", "v2", limit=10)
        self.assertEqual(len(pending), 2)

    def test_cache_round_trip_and_json_export(self):
        digest = store.content_hash(sample_item())
        self.assertEqual(len(digest), 40)
        store.cache_put(self.conn, digest, "gemini-2.5-flash", "v1", {"summary": "cached"})
        self.assertEqual(store.cache_get(self.conn, digest, "gemini-2.5-flash", "v1")["summary"], "cached")
        self.assertIsNone(store.cache_get(self.conn, digest, "other-model", "v1"))

        path = Path(self.tmp.name) / "cache.json"
        store.export_cache_json(self.conn, path)
        payload = json.loads(path.read_text())
        self.assertEqual(len(payload["entries"]), 1)

        fresh = store.connect(Path(self.tmp.name) / "fresh.sqlite3")
        store.init_db(fresh)
        imported = store.import_cache_json(fresh, path)
        fresh.close()
        self.assertEqual(imported, 1)

    def test_content_hash_changes_with_metadata(self):
        first = store.content_hash(sample_item())
        second = store.content_hash(sample_item(description="different"))
        self.assertNotEqual(first, second)

    def test_runs_are_recorded(self):
        store.record_run(self.conn, store.utcnow(), {"collected": 10, "inserted": 9, "updated": 1, "enriched": 3})
        run = store.last_run(self.conn)
        self.assertEqual(run["inserted"], 9)
        self.assertEqual(run["enriched"], 3)


if __name__ == "__main__":
    unittest.main()
