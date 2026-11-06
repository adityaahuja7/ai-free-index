"""Collectors turn remote sources into normalised item dicts.

Every collector takes its own config block and returns a list of dicts with at
least: id, source, kind, name, url. Adding a source means adding a module and a
config block, never touching the pipeline.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import awesome, github, hackernews

COLLECTORS: Dict[str, Callable[..., List[Dict[str, Any]]]] = {
    "github": github.collect,
    "hackernews": hackernews.collect,
    "awesome": awesome.collect,
}

__all__ = ["COLLECTORS", "awesome", "github", "hackernews"]
