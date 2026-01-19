#!/usr/bin/env python3
"""Manual MyAnonamouse search runner to debug direct adapter requests."""

from __future__ import annotations

import argparse
import json
import sys
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict

import requests

# Ensure `services` package is importable when executing from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.indexers.direct_indexer import DirectIndexer  # noqa: E402
from utils.search_normalization import normalize_search_terms  # noqa: E402


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def load_indexer_config(path: Path, section: str) -> Dict[str, Any]:
    parser = ConfigParser()
    parser.read(path)
    if section not in parser:
        raise SystemExit(f"Section '{section}' not found in {path}")

    raw = parser[section]
    cfg: Dict[str, Any] = {k: v for k, v in raw.items()}

    cfg.setdefault("name", section.replace("indexer:", ""))
    cfg.setdefault("type", "direct")
    cfg["protocol"] = "direct"
    cfg["base_url"] = cfg.get("base_url", "").rstrip("/")
    cfg["session_id"] = cfg.get("session_id", "").strip()
    cfg["verify_ssl"] = _as_bool(cfg.get("verify_ssl"), True)
    cfg["timeout"] = _as_int(cfg.get("timeout"), 30)
    cfg["search_type"] = (cfg.get("search_type") or "all").strip().lower() or "all"

    categories = cfg.get("categories")
    cfg["categories"] = _split_csv(categories)

    languages = cfg.get("languages")
    if languages:
        cfg["languages"] = _split_csv(languages)

    if not cfg["base_url"]:
        raise SystemExit("Base URL missing in config")
    if not cfg["session_id"]:
        raise SystemExit("Session ID missing in config")

    return cfg


def debug_search(indexer: DirectIndexer, query: str, title: str, author: str, limit: int, offset: int) -> None:
    adapter = indexer.adapter
    spec = adapter.build_search_request(query, author, title, limit, offset)

    url = indexer._build_url(spec.path or indexer.search_path)
    headers = indexer._build_headers()
    if spec.headers:
        headers.update(spec.headers)
    cookies = indexer._build_cookies()

    print("=== Request ===")
    print(f"Method: {spec.method}")
    print(f"URL: {url}")
    if spec.params:
        print(f"Params: {spec.params}")
    if spec.json:
        print("JSON payload:")
        print(json.dumps(spec.json, indent=2))
    if spec.data and not spec.json:
        print(f"Data: {spec.data}")
    print(f"Headers: {headers}")
    print(f"Cookies: session_id set: {bool(cookies.get('session_id'))}")
    print()

    response = requests.request(
        spec.method,
        url,
        params=spec.params,
        data=spec.data,
        json=spec.json,
        headers=headers,
        cookies=cookies,
        timeout=indexer.timeout,
        verify=indexer.verify_ssl,
    )

    print("=== Response ===")
    print(f"Status: {response.status_code}")
    content_type = response.headers.get("Content-Type", "")
    print(f"Content-Type: {content_type}")

    snippet = response.text[:500]
    print(f"Raw body (first 500 chars):\n{snippet}")

    try:
        payload = response.json()
    except ValueError:
        payload = None

    normalized = []
    if isinstance(payload, dict):
        print(f"Keys: {list(payload.keys())}")
        data = payload.get("data")
        print(f"Result count: {len(data) if isinstance(data, list) else 'n/a'}")
        if isinstance(data, list) and data:
            print("Sample item:")
            print(json.dumps(data[0], indent=2)[:1000])
        try:
            normalized = list(adapter.parse_search_results(payload))
        except Exception as parse_exc:  # pragma: no cover - debug helper only
            print(f"Failed to normalize results: {parse_exc}")
    else:
        print("Response was not valid JSON.")

    if normalized:
        print("\n=== Normalized Results ===")
        for idx, item in enumerate(normalized[: min(10, len(normalized))], start=1):
            author_label = item.get("author") or "Unknown Author"
            narrator_label = item.get("narrator") or "Unknown Narrator"
            size_label = item.get("size_bytes") or item.get("size") or 0
            print(f"{idx:02d}. {item.get('title', 'Unknown Title')} | {author_label} | {narrator_label} | {size_label} bytes")
    else:
        print("No normalized results parsed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug direct MyAnonamouse adapter searches")
    parser.add_argument(
        "query",
        nargs="?",
        default="Path of the Berserker 4: A Daopocalypse Progression Fantasy by Rick Scott",
        help="Search text (default targets 'Path of the Berserker 4' test case)",
    )
    parser.add_argument("--title", default="", help="Optional title override")
    parser.add_argument("--author", default="", help="Optional author")
    parser.add_argument("--config", default="config/config.txt", help="Path to config file")
    parser.add_argument("--section", default="indexer:myanonamouse", help="Config section name")
    parser.add_argument("--limit", type=int, default=25, help="Results per page")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    parser.add_argument("--categories", default="", help="Override category list (comma separated)")
    parser.add_argument("--languages", default="", help="Override language list (comma separated)")
    args = parser.parse_args()

    cfg = load_indexer_config(Path(args.config), args.section)
    if args.categories:
        cfg["categories"] = _split_csv(args.categories)
    if args.languages:
        cfg["languages"] = _split_csv(args.languages)
    indexer = DirectIndexer(cfg)

    normalized_query, normalized_title, normalized_author = normalize_search_terms(
        args.query, args.title, args.author
    )

    debug_search(indexer, normalized_query, normalized_title, normalized_author, args.limit, args.offset)


if __name__ == "__main__":
    main()
