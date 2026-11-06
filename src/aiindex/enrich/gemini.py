"""Gemini enrichment on the free tier.

Design constraints, in order of importance:

1. Never lose work: every answer is cached in SQLite (and exported to JSON) keyed
   by content hash + model + prompt version, so a re-run costs nothing.
2. Never burn quota blindly: items are batched, requests are paced, the number of
   requests per run is capped, and several free keys can be rotated.
3. Never break the build: with no key, or with quota exhausted, the pipeline
   keeps going with the deterministic fields it already has.

The API surface used is the public Generative Language REST API:
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from .. import config, store
from ..http import post_json

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT_VERSION = "v1"

SYSTEM_INSTRUCTION = (
    "You are a precise technical cataloguer of free and open-source AI software. "
    "You only describe what the given metadata supports; you never invent features. "
    "You always answer with JSON that matches the requested schema."
)

RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "category": {
                        "type": "STRING",
                        "enum": [
                            "Agents", "LLM", "Serving & Infra", "RAG & Search",
                            "Fine-tuning & Training", "Image & Video",
                            "Audio & Speech", "Code & DevTools", "Data & Databases",
                            "Evaluation & Observability", "Multimodal & Vision",
                            "Safety & Privacy", "Other",
                        ],
                    },
                    "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "self_hostable": {"type": "BOOLEAN"},
                    "maturity": {
                        "type": "STRING",
                        "enum": ["experimental", "usable", "production", "archived"],
                    },
                    "target_user": {
                        "type": "STRING",
                        "enum": ["developer", "researcher", "end-user", "ops"],
                    },
                    "difficulty": {"type": "INTEGER"},
                    "free_tier_notes": {"type": "STRING"},
                },
                "required": [
                    "id", "summary", "category", "tags", "self_hostable",
                    "maturity", "target_user", "difficulty",
                ],
                "propertyOrdering": [
                    "id", "summary", "category", "tags", "self_hostable",
                    "maturity", "target_user", "difficulty", "free_tier_notes",
                ],
            },
        }
    },
    "required": ["items"],
}


def available() -> bool:
    return bool(config.gemini_keys())


def _compact(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "url": item.get("url"),
        "description": (item.get("description") or "")[:300],
        "topics": (item.get("topics") or [])[:12],
        "license": item.get("license"),
        "language": item.get("language"),
        "stars": item.get("stars"),
        "pushed_at": item.get("pushed_at"),
        "kind": item.get("kind"),
        "hacker_news_points": item.get("points") or 0,
    }


def build_payload(items: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    prompt = (
        "For each entry below, classify this free/open-source AI project.\n"
        "Rules:\n"
        "- summary: one factual sentence, max 160 characters, no marketing words.\n"
        "- tags: 3 to 6 lowercase kebab-case technical tags.\n"
        "- self_hostable: true only if the metadata implies it can run on your own machine or server.\n"
        "- maturity: judge from activity date, stars and description.\n"
        "- difficulty: 1 (clone and run) to 5 (needs GPUs, cluster or training data).\n"
        "- free_tier_notes: short note on how it can be used for free, or empty string.\n"
        "- Copy each id back exactly as given.\n\n"
        "Entries:\n" + json.dumps([_compact(item) for item in items], ensure_ascii=False)
    )
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "temperature": 0.2,
            "maxOutputTokens": 8192,
        },
    }


def _extract(response: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    if not response:
        return [], "empty response"
    candidates = response.get("candidates") or []
    if not candidates:
        feedback = response.get("promptFeedback") or {}
        return [], "no candidates (%s)" % (feedback.get("blockReason") or "unknown")
    candidate = candidates[0]
    parts = ((candidate.get("content") or {}).get("parts")) or []
    text = "".join(part.get("text") or "" for part in parts)
    if not text:
        return [], "no text (finishReason=%s)" % candidate.get("finishReason")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [], "invalid JSON from model"
    entries = parsed.get("items") if isinstance(parsed, dict) else parsed
    if not isinstance(entries, list):
        return [], "unexpected JSON shape"
    clean = [entry for entry in entries if isinstance(entry, dict) and entry.get("id")]
    return clean, ""


def _retry_delay(response: Optional[Dict[str, Any]], text: str, default: float) -> float:
    """Honour Google's RetryInfo when present, otherwise exponential default."""
    try:
        details = ((response or {}).get("error") or {}).get("details") or []
        for detail in details:
            if str(detail.get("@type", "")).endswith("RetryInfo"):
                raw = str(detail.get("retryDelay") or "")
                if raw.endswith("s"):
                    return min(60.0, float(raw[:-1]) + 1.0)
    except Exception:  # pragma: no cover - defensive
        pass
    if "429" in text or "quota" in text.lower():
        return default
    return default


def enrich_batch(
    items: List[Dict[str, Any]],
    model: str,
    key: str,
    timeout: int = 120,
) -> Tuple[List[Dict[str, Any]], str]:
    url = ENDPOINT.format(model=model)
    payload = build_payload(items, model)
    response, status, raw = post_json(
        url, payload, headers={"x-goog-api-key": key}, timeout=timeout, retries=0
    )
    if status and 200 <= status < 300:
        entries, error = _extract(response)
        return entries, error
    message = raw[:300]
    if response and isinstance(response, dict):
        error = response.get("error") or {}
        message = "%s: %s" % (error.get("status") or status, error.get("message") or raw[:200])
    return [], message


def enrich(
    conn,
    items: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    log=print,
) -> Dict[str, Any]:
    """Enrich items with Gemini, using the cache first."""
    model = config.gemini_model(cfg.get("model") or "gemini-2.5-flash")
    prompt_version = cfg.get("prompt_version") or PROMPT_VERSION
    keys = config.gemini_keys()
    batch_size = int(cfg.get("batch_size", 12))
    delay = float(cfg.get("request_delay_seconds", 5.0))
    max_requests = int(cfg.get("max_requests_per_run", 40))
    stats = {"enriched": 0, "cached": 0, "requests": 0, "skipped": 0, "errors": []}

    if cfg.get("enabled") is False:
        log("  gemini: disabled in config")
        return stats
    if not keys:
        log("  gemini: no API key found (set GEMINI_API_KEY) - skipping enrichment")
        return stats

    pending: List[Dict[str, Any]] = []
    for item in items:
        digest = store.content_hash(item)
        cached = store.cache_get(conn, digest, model, prompt_version)
        if cached:
            cached["_model"] = model
            cached["_prompt_version"] = prompt_version
            store.apply_enrichment(conn, item["id"], cached)
            stats["cached"] += 1
            continue
        item["_content_hash"] = digest
        pending.append(item)
    store.commit(conn)
    log("  gemini: %d cached, %d to enrich" % (stats["cached"], len(pending)))

    key_index = 0
    for start in range(0, len(pending), batch_size):
        if stats["requests"] >= max_requests:
            stats["skipped"] = len(pending) - start
            log("  gemini: request cap reached (%d), %d items left for next run" % (max_requests, stats["skipped"]))
            break
        batch = pending[start:start + batch_size]
        entries, error = enrich_batch(batch, model, keys[key_index])
        stats["requests"] += 1

        if not entries and error:
            lowered = error.lower()
            quota_hit = "429" in error or "quota" in lowered or "rate" in lowered or "resource_exhausted" in lowered
            if quota_hit and len(keys) > 1 and key_index + 1 < len(keys):
                key_index += 1
                log("  gemini: rotating to key #%d" % (key_index + 1))
                entries, error = enrich_batch(batch, model, keys[key_index])
                stats["requests"] += 1
            elif quota_hit:
                wait = _retry_delay(None, error, 20.0)
                log("  gemini: quota/rate limit, sleeping %.0fs then retrying once" % wait)
                time.sleep(wait)
                entries, error = enrich_batch(batch, model, keys[key_index])
                stats["requests"] += 1

        if not entries:
            stats["errors"].append(error or "unknown error")
            log("  gemini: batch failed (%s)" % (error or "unknown"))
            for item in batch:
                store.mark_enrichment_attempt(conn, item["id"], model, prompt_version)
            store.commit(conn)
            time.sleep(delay)
            continue

        by_id = {str(entry.get("id")): entry for entry in entries}
        for item in batch:
            entry = by_id.get(str(item["id"]))
            if not entry:
                store.mark_enrichment_attempt(conn, item["id"], model, prompt_version)
                continue
            entry["_model"] = model
            entry["_prompt_version"] = prompt_version
            store.apply_enrichment(conn, item["id"], entry)
            store.cache_put(conn, item["_content_hash"], model, prompt_version, entry)
            stats["enriched"] += 1
        store.commit(conn)
        log("  gemini: batch %d-%d enriched (%d)" % (start + 1, start + len(batch), stats["enriched"]))
        time.sleep(delay)

    store.export_cache_json(conn)
    return stats
