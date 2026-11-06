import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from aiindex import scoring  # noqa: E402

NOW = datetime.datetime(2026, 11, 7, tzinfo=datetime.timezone.utc)


def item(**overrides):
    base = {
        "id": "gh:o/r",
        "name": "o/r",
        "kind": "repo",
        "license": "MIT",
        "license_open": True,
        "stars": 5000,
        "pushed_at": "2026-11-01T00:00:00Z",
        "sources": ["github"],
    }
    base.update(overrides)
    return base


class ScoringTests(unittest.TestCase):
    def test_score_is_bounded_and_has_parts(self):
        score, parts = scoring.score_item(item(), NOW)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
        for key in scoring.WEIGHTS:
            self.assertIn(key, parts)
            self.assertGreaterEqual(parts[key], 0.0)
            self.assertLessEqual(parts[key], 100.0)

    def test_more_stars_scores_higher(self):
        low, _ = scoring.score_item(item(stars=100), NOW)
        high, _ = scoring.score_item(item(stars=90000), NOW)
        self.assertGreater(high, low)

    def test_stale_projects_lose_activity_points(self):
        fresh, fresh_parts = scoring.score_item(item(pushed_at="2026-11-06T00:00:00Z"), NOW)
        stale, stale_parts = scoring.score_item(item(pushed_at="2021-01-01T00:00:00Z"), NOW)
        self.assertGreater(fresh_parts["activity"], stale_parts["activity"])
        self.assertGreater(fresh, stale)

    def test_archived_projects_get_no_activity(self):
        _, parts = scoring.score_item(item(archived=True), NOW)
        self.assertEqual(parts["activity"], 0.0)

    def test_curation_and_discussion_contribute(self):
        plain, _ = scoring.score_item(item(sources=["github"]), NOW)
        curated, _ = scoring.score_item(item(sources=["github", "awesome"]), NOW)
        discussed, _ = scoring.score_item(item(points=900, sources=["github"]), NOW)
        self.assertGreater(curated, plain)
        self.assertGreater(discussed, plain)

    def test_proprietary_license_loses_openness(self):
        _, parts = scoring.score_item(item(license="Unknown", license_open=False), NOW)
        self.assertEqual(parts["openness"], 0.0)

    def test_missing_dates_do_not_crash(self):
        score, parts = scoring.score_item({"id": "x", "name": "x"}, NOW)
        self.assertGreaterEqual(score, 0.0)
        self.assertEqual(parts["activity"], 0.0)

    def test_score_all_mutates_items(self):
        items = scoring.score_all([item(), item(id="gh:a/b", stars=0)])
        self.assertTrue(all("score" in entry and "score_parts" in entry for entry in items))
        self.assertGreater(items[0]["score"], items[1]["score"])


if __name__ == "__main__":
    unittest.main()
