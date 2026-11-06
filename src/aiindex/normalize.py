"""Normalisation: licences, categories, tags, free-ness flags, and de-duplication.

This module does the cheap, deterministic work so that Gemini is only used where
judgement is actually needed (short summaries and category refinement).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

# OSI-approved / free-ish licences we treat as "open source".
OPEN_LICENSES = {
    "MIT", "Apache-2.0", "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0",
    "GPL-2.0-only", "GPL-2.0-or-later", "AGPL-3.0", "AGPL-3.0-only",
    "AGPL-3.0-or-later", "LGPL-3.0", "LGPL-3.0-only", "LGPL-2.1", "BSD-2-Clause",
    "BSD-3-Clause", "BSD-3-Clause-Clear", "0BSD", "MPL-2.0", "ISC", "Unlicense",
    "CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "EPL-2.0", "Zlib", "BSL-1.0",
    "PostgreSQL", "Artistic-2.0", "OFL-1.1", "CDDL-1.0", "EUPL-1.2", "NCSA",
}

LICENSE_ALIASES = {
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "mit license": "MIT",
    "bsd": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "gplv3": "GPL-3.0",
    "gpl-3": "GPL-3.0",
    "gplv2": "GPL-2.0",
    "agplv3": "AGPL-3.0",
    "lgplv3": "LGPL-3.0",
    "mpl 2.0": "MPL-2.0",
    "cc-by-4": "CC-BY-4.0",
    "cc0": "CC0-1.0",
    "noassertion": "Unknown",
    "other": "Unknown",
    "none": "Unknown",
    "": "Unknown",
}

CATEGORY_RULES: List[Dict[str, Any]] = [
    {"category": "Agents", "keywords": [
        "agent", "agentic", "autogpt", "multi-agent", "tool-use", "tool use",
        "function calling", "computer use", "workflow automation", "swarm",
        "crew", "autonomous",
    ]},
    {"category": "Serving & Infra", "keywords": [
        "serving", "inference", "inference engine", "vllm", "llama.cpp", "ollama",
        "ggml", "gguf", "sglang", "text-generation-inference", "llm-serving",
        "local-llm", "local llm", "quantization", "quantiz", "gpu", "cuda",
        "runtime", "kubernetes", "deployment", "inference server",
        "edge inference", "model runner",
    ]},
    {"category": "RAG & Search", "keywords": [
        "rag", "retrieval", "vector", "embedding", "semantic search",
        "knowledge base", "vector database", "hybrid search", "rerank",
    ]},
    {"category": "Fine-tuning & Training", "keywords": [
        "fine-tun", "finetun", "lora", "qlora", "peft", "training", "rlhf",
        "dpo", "distill", "pretrain", "pretraining",
    ]},
    {"category": "Image & Video", "keywords": [
        "diffusion", "stable diffusion", "text-to-image", "text to image",
        "image generation", "comfyui", "flux", "video generation", "image editing",
    ]},
    {"category": "Audio & Speech", "keywords": [
        "speech", "tts", "text-to-speech", "asr", "whisper", "voice", "audio",
        "music generation", "transcription",
    ]},
    {"category": "Code & DevTools", "keywords": [
        "coding assistant", "copilot", "code completion", "codegen",
        "program synthesis", "ide", "linter", "developer tool",
    ]},
    {"category": "Data & Databases", "keywords": [
        "dataset", "etl", "data pipeline", "sql", "database", "data quality",
        "labeling", "annotation",
    ]},
    {"category": "Evaluation & Observability", "keywords": [
        "eval", "benchmark", "observability", "monitoring", "tracing",
        "guardrail", "testing", "red team", "llmops",
    ]},
    {"category": "Multimodal & Vision", "keywords": [
        "multimodal", "vision", "vlm", "ocr", "object detection", "segmentation",
        "image understanding",
    ]},
    {"category": "Safety & Privacy", "keywords": [
        "safety", "privacy", "jailbreak", "moderation", "alignment",
        "differential privacy", "watermark",
    ]},
    {"category": "LLM", "keywords": [
        "llm", "large language model", "language model", "gpt", "llama",
        "mistral", "qwen", "chatbot", "transformer", "foundation model",
        "text generation",
    ]},
]

SELF_HOST_HINTS = (
    "self-host", "selfhost", "docker", "docker-compose", "kubernetes", "helm",
    "local-first", "offline", "on-prem", "run locally", "locally", "own server",
    "own machine", "your machine", "own hardware", "air-gapped", "no cloud",
    "single binary", "runs on your", "private deployment",
)

NOISE_HOSTS = {
    "github.com/sponsors", "github.com/orgs", "github.com/features",
    "github.com/marketplace", "github.com/apps", "github.com/settings",
    "github.com/login", "github.com/topics", "github.com/collections",
    "github.com/explore", "github.com/pricing", "github.com/enterprise",
}

GITHUB_RESERVED = {
    "about", "apps", "blog", "collections", "contact", "customer-stories",
    "enterprise", "events", "explore", "features", "issues", "login", "marketplace",
    "new", "notifications", "orgs", "pricing", "pulls", "search", "security",
    "settings", "site", "sponsors", "stars", "topics", "trending", "watching",
}

LINK_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\[([^\]]+)\]\((https?://[^)\s]+)\)\s*(?:[-–—:]\s*(.*))?$")


def normalize_license(value: Optional[str]) -> str:
    if not value:
        return "Unknown"
    raw = str(value).strip()
    if raw in OPEN_LICENSES:
        return raw
    alias = LICENSE_ALIASES.get(raw.lower())
    if alias:
        return alias
    lowered = raw.lower().replace("_", "-")
    for known in OPEN_LICENSES:
        if known.lower() == lowered:
            return known
    return raw if raw.upper() not in ("NOASSERTION", "OTHER") else "Unknown"


def is_open_license(value: Optional[str]) -> bool:
    return normalize_license(value) in OPEN_LICENSES


def canonical_url(url: Optional[str]) -> str:
    if not url:
        return ""
    parts = urlsplit(str(url).strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return (host + path).lower()


def github_slug(url: Optional[str]) -> Optional[str]:
    """Return 'owner/repo' for a GitHub repository URL, else None."""
    key = canonical_url(url)
    if not key.startswith("github.com/"):
        return None
    parts = [part for part in key.split("/") if part]
    if len(parts) < 3:
        return None
    owner, repo = parts[1], parts[2]
    if owner in GITHUB_RESERVED or repo in GITHUB_RESERVED:
        return None
    return "%s/%s" % (owner, repo)


def _haystack(item: Dict[str, Any]) -> str:
    pieces = [
        str(item.get("name") or ""),
        str(item.get("description") or ""),
        " ".join(item.get("topics") or []),
        str(item.get("language") or ""),
        str(item.get("summary") or ""),
    ]
    return " ".join(pieces).lower()


def guess_category(item: Dict[str, Any]) -> str:
    text = _haystack(item)
    topics = set(str(topic).lower() for topic in (item.get("topics") or []))
    best = ("Other", 0)
    for rule in CATEGORY_RULES:
        score = 0
        for keyword in rule["keywords"]:
            if keyword in topics:
                score += 3
            elif keyword in text:
                score += 1
        if score > best[1]:
            best = (rule["category"], score)
    return best[0] if best[1] > 0 else "Other"


def guess_tags(item: Dict[str, Any], limit: int = 8) -> List[str]:
    tags: List[str] = []
    for topic in item.get("topics") or []:
        topic = str(topic).strip().lower()
        if topic and topic not in tags:
            tags.append(topic)
    language = str(item.get("language") or "").strip()
    if language:
        tags.append(language.lower())
    license_name = normalize_license(item.get("license"))
    if license_name != "Unknown":
        tags.append(license_name.lower())
    if item.get("kind") == "news":
        tags.append("news")
    return tags[:limit]


def guess_self_hostable(item: Dict[str, Any]) -> bool:
    text = _haystack(item)
    topics = set(str(topic).lower() for topic in (item.get("topics") or []))
    if topics & {"self-hosted", "selfhosted", "docker", "local-first", "offline"}:
        return True
    return any(hint in text for hint in SELF_HOST_HINTS)


def guess_maturity(item: Dict[str, Any]) -> str:
    stars = int(item.get("stars") or 0)
    archived = bool(item.get("archived"))
    if archived:
        return "archived"
    if stars >= 5000:
        return "production"
    if stars >= 500:
        return "usable"
    return "experimental"


def recency_days(iso_timestamp: Optional[str], now: Optional[datetime.datetime] = None) -> Optional[float]:
    if not iso_timestamp:
        return None
    moment = parse_timestamp(iso_timestamp)
    if moment is None:
        return None
    reference = now or datetime.datetime.now(datetime.timezone.utc)
    return max(0.0, (reference - moment).total_seconds() / 86400.0)


def parse_timestamp(value: str) -> Optional[datetime.datetime]:
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def prepare(item: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in deterministic fields on a collected item."""
    prepared = dict(item)
    prepared["license"] = normalize_license(prepared.get("license"))
    prepared["license_open"] = is_open_license(prepared.get("license"))
    prepared["topics"] = sorted({str(topic).strip().lower() for topic in (prepared.get("topics") or []) if str(topic).strip()})
    prepared.setdefault("sources", [prepared.get("source") or "unknown"])
    if not prepared.get("category"):
        prepared["category"] = guess_category(prepared)
    if prepared.get("self_hostable") is None:
        prepared["self_hostable"] = guess_self_hostable(prepared)
    if not prepared.get("tags"):
        prepared["tags"] = guess_tags(prepared)
    if not prepared.get("maturity"):
        prepared["maturity"] = guess_maturity(prepared)
    prepared["stars"] = int(prepared.get("stars") or 0)
    prepared["forks"] = int(prepared.get("forks") or 0)
    prepared["open_issues"] = int(prepared.get("open_issues") or 0)
    prepared["points"] = int(prepared.get("points") or 0)
    prepared["comments"] = int(prepared.get("comments") or 0)
    prepared["archived"] = bool(prepared.get("archived"))
    return prepared


def _merge_into(target: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    sources = list(target.get("sources") or [])
    for source in incoming.get("sources") or [incoming.get("source")]:
        if source and source not in sources:
            sources.append(source)
    target["sources"] = sources

    for field in ("description", "homepage", "license", "language", "pushed_at", "created_at", "url", "name"):
        if not target.get(field) and incoming.get(field):
            target[field] = incoming[field]

    topics = set(target.get("topics") or [])
    topics.update(incoming.get("topics") or [])
    target["topics"] = sorted(topics)

    for field in ("stars", "forks", "open_issues", "points", "comments"):
        target[field] = max(int(target.get(field) or 0), int(incoming.get(field) or 0))

    if incoming.get("discussion_url") and not target.get("discussion_url"):
        target["discussion_url"] = incoming["discussion_url"]
    if incoming.get("kind") == "repo":
        target["kind"] = "repo"
    if incoming.get("license_open"):
        target["license_open"] = True
    return target


def dedupe(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge duplicates: same id, same URL, and news stories about a known repo."""
    ordered: List[str] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for raw in items:
        item = prepare(raw)
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id in by_id:
            by_id[item_id] = _merge_into(by_id[item_id], item)
        else:
            by_id[item_id] = item
            ordered.append(item_id)

    # Only non-news entries index URLs: a story linking to a repository must find
    # the repository, not itself (its URL is the same).
    url_index: Dict[str, str] = {}
    for candidate in ordered:
        if by_id[candidate].get("kind") == "news":
            continue
        key = canonical_url(by_id[candidate].get("url"))
        if key:
            url_index.setdefault(key, candidate)

    for item_id in list(ordered):
        item = by_id[item_id]
        if item.get("kind") != "news":
            continue
        key = canonical_url(item.get("url"))
        target_id = url_index.get(key)
        if not target_id or target_id == item_id:
            continue
        target = by_id[target_id]
        target["points"] = max(int(target.get("points") or 0), int(item.get("points") or 0))
        target["comments"] = max(int(target.get("comments") or 0), int(item.get("comments") or 0))
        target["discussion_url"] = item.get("discussion_url") or target.get("discussion_url")
        sources = list(target.get("sources") or [])
        if "hackernews" not in sources:
            sources.append("hackernews")
        target["sources"] = sources
        ordered.remove(item_id)
        by_id.pop(item_id, None)

    return [by_id[item_id] for item_id in ordered]
