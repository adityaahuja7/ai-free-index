"""Enrichment backends. Gemini is the default (free tier); the package works
without any backend at all, just with fewer editorial fields.
"""

from __future__ import annotations

from . import gemini

BACKENDS = {"gemini": gemini}

__all__ = ["BACKENDS", "gemini"]
