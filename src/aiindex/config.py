"""Configuration and paths.

Everything is resolved from the repository root so the tool works the same from a
checkout, a CI runner, or a container. Environment variables win over files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_ROOT = PACKAGE_DIR.parents[1]


def repo_root() -> Path:
    """Repository root, overridable with AIINDEX_ROOT (used by tests/CI)."""
    return Path(os.environ.get("AIINDEX_ROOT") or _DEFAULT_ROOT).resolve()


def config_path() -> Path:
    return repo_root() / "config" / "sources.json"


def web_dir() -> Path:
    return repo_root() / "web"


def data_dir() -> Path:
    path = Path(os.environ.get("AIINDEX_DATA_DIR") or (repo_root() / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def site_dir() -> Path:
    return Path(os.environ.get("AIINDEX_SITE_DIR") or (repo_root() / "_site"))


def db_path() -> Path:
    return data_dir() / "index.sqlite3"


def index_json_path() -> Path:
    return data_dir() / "index.json"


def cache_json_path() -> Path:
    """Enrichment cache, committed so CI does not re-spend free Gemini quota."""
    return data_dir() / "enrichment-cache.json"


def load_dotenv(path: Optional[Path] = None) -> None:
    """Minimal .env loader. Real environment variables always win."""
    env_file = Path(path) if path else (repo_root() / ".env")
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_sources() -> Dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def env_list(name: str) -> List[str]:
    raw = os.environ.get(name) or ""
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


def gemini_keys() -> List[str]:
    """Free Gemini API keys. Several keys can be rotated when one hits quota."""
    keys = env_list("GEMINI_API_KEYS")
    single = env("GEMINI_API_KEY")
    if single:
        keys.append(single.strip())
    seen: List[str] = []
    for key in keys:
        if key not in seen:
            seen.append(key)
    return seen


def gemini_model(fallback: str = "gemini-2.5-flash") -> str:
    return env("GEMINI_MODEL", fallback) or fallback


def github_token() -> Optional[str]:
    return env("GITHUB_TOKEN") or env("GH_TOKEN")
