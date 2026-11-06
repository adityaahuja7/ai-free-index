"""Transparent scoring so the dashboard can explain why something ranks high."""

from __future__ import annotations

import datetime
import math
from typing import Any, Dict, Tuple

from . import normalize

WEIGHTS = {
    "popularity": 0.42,
    "activity": 0.24,
    "openness": 0.14,
    "curation": 0.12,
    "discussion": 0.08,
}

MAX_STARS_FOR_SCALE = 100_000
ACTIVITY_HORIZON_DAYS = 730.0
MAX_HN_POINTS = 1_000
CURATED_SOURCES = {"awesome", "curated"}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_item(item: Dict[str, Any], now: datetime.datetime = None) -> Tuple[float, Dict[str, float]]:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stars = int(item.get("stars") or 0)
    popularity = _clamp(math.log10(stars + 1) / math.log10(MAX_STARS_FOR_SCALE + 1))

    days = normalize.recency_days(item.get("pushed_at") or item.get("created_at"), now)
    activity = 0.0 if days is None else _clamp(1.0 - (days / ACTIVITY_HORIZON_DAYS))
    if item.get("archived"):
        activity = 0.0

    openness = 0.0
    if item.get("license_open") or normalize.is_open_license(item.get("license")):
        openness = 1.0
    if item.get("kind") == "curated":
        openness = max(openness, 0.5)

    sources = set(item.get("sources") or [item.get("source") or ""])
    curation = 1.0 if (sources & CURATED_SOURCES) or item.get("kind") == "curated" else 0.0

    points = int(item.get("points") or 0)
    discussion = _clamp(points / float(MAX_HN_POINTS))

    parts = {
        "popularity": round(popularity * 100, 1),
        "activity": round(activity * 100, 1),
        "openness": round(openness * 100, 1),
        "curation": round(curation * 100, 1),
        "discussion": round(discussion * 100, 1),
    }
    total = (
        WEIGHTS["popularity"] * popularity
        + WEIGHTS["activity"] * activity
        + WEIGHTS["openness"] * openness
        + WEIGHTS["curation"] * curation
        + WEIGHTS["discussion"] * discussion
    )
    return round(total * 100, 2), parts


def score_all(items, now: datetime.datetime = None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    for item in items:
        total, parts = score_item(item, now)
        item["score"] = total
        item["score_parts"] = parts
    return items
