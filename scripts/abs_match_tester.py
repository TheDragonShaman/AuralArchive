"""Quick Audiobookshelf ASIN match tester.

Run against an Audiobookshelf server to validate the workflow:
1) (Optional) trigger library scan
2) search for items by ASIN
3) force match using provider=audible + ASIN
4) fetch expanded item details to confirm

Usage:
  python scripts/abs_match_tester.py --base-url http://abs.local:13378 \
      --token <bearer_token> --library-id <lib_id> --asin B002V0QK4C

You can pass multiple --asin flags to test several titles.
"""

import argparse
import json
import sys
from typing import Any, Dict, Iterable, Optional

import requests


def abs_request(
    session: requests.Session,
    method: str,
    url: str,
    token: str,
    timeout: float,
    **kwargs: Any,
) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("Content-Type", "application/json")
    resp = session.request(method, url, headers=headers, timeout=timeout, **kwargs)
    resp.raise_for_status()
    return resp


def trigger_scan(
    session: requests.Session,
    base_url: str,
    token: str,
    library_id: str,
    timeout: float,
    force: bool,
) -> None:
    url = f"{base_url}/api/libraries/{library_id}/scan"
    params = {"force": 1 if force else 0}
    abs_request(session, "POST", url, token, timeout, params=params)
    print(f"[scan] triggered for library={library_id} force={force}")


def search_library(
    session: requests.Session,
    base_url: str,
    token: str,
    library_id: str,
    query: str,
    asin_match: Optional[str],
    timeout: float,
    limit: int = 5,
) -> Optional[Dict[str, Any]]:
    """Search the library using the ABS search endpoint.

    Prefer items whose metadata.asin matches asin_match when provided.
    """

    url = f"{base_url}/api/libraries/{library_id}/search"
    params = {"q": query, "limit": limit}
    resp = abs_request(session, "GET", url, token, timeout, params=params)
    data = resp.json()
    items = data.get("book") or []  # ABS returns {"book": [...]} for book libraries
    if not items:
        return None

    for item in items:
        li = item.get("libraryItem")
        if not li:
            continue
        metadata = li.get("media", {}).get("metadata", {})
        if asin_match and metadata.get("asin") == asin_match:
            return li
    return items[0].get("libraryItem")


def search_by_asin(
    session: requests.Session,
    base_url: str,
    token: str,
    library_id: str,
    asin: str,
    timeout: float,
    limit: int = 5,
) -> Optional[Dict[str, Any]]:
    """Direct ASIN lookup against the library search endpoint."""

    url = f"{base_url}/api/libraries/{library_id}/search"
    params = {"q": asin, "limit": limit}
    resp = abs_request(session, "GET", url, token, timeout, params=params)
    data = resp.json()
    items = data.get("book") or []
    if not items:
        return None

    for item in items:
        li = item.get("libraryItem")
        if not li:
            continue
        metadata = li.get("media", {}).get("metadata", {})
        if metadata.get("asin") == asin:
            return li
    return items[0].get("libraryItem")


def match_item(
    session: requests.Session,
    base_url: str,
    token: str,
    library_item_id: str,
    asin: str,
    timeout: float,
) -> Dict[str, Any]:
    url = f"{base_url}/api/items/{library_item_id}/match"
    payload = {"provider": "audible", "asin": asin, "overrideDefaults": True}
    resp = abs_request(session, "POST", url, token, timeout, json=payload)
    print(f"[match] libraryItemId={library_item_id} asin={asin}")
    return resp.json()


def fetch_item(
    session: requests.Session,
    base_url: str,
    token: str,
    library_item_id: str,
    timeout: float,
) -> Dict[str, Any]:
    url = f"{base_url}/api/items/{library_item_id}"
    params = {"expanded": 1, "include": "progress,authors"}
    resp = abs_request(session, "GET", url, token, timeout, params=params)
    return resp.json()


def run_flow(
    base_url: str,
    token: str,
    library_id: str,
    asins: Iterable[str],
    title_hint: Optional[str],
    timeout: float,
    skip_scan: bool,
) -> None:
    session = requests.Session()
    if not skip_scan:
        trigger_scan(session, base_url, token, library_id, timeout, force=True)

    for asin in asins:
        asin = asin.strip()
        if not asin:
            continue
        print(f"\n=== ASIN {asin} ===")
        # First try library search (title hint if provided), then ASIN fallback
        query = title_hint or asin
        item = search_library(session, base_url, token, library_id, query, asin, timeout)
        search_source = "library search"
        if not item:
            item = search_by_asin(session, base_url, token, library_id, asin, timeout)
            search_source = "asin fallback"
        if not item:
            print(f"[search] no item found for ASIN={asin} (library search then asin fallback)")
            continue

        library_item_id = item.get("id")
        print(f"[search:{search_source}] found libraryItemId={library_item_id} title={item.get('title')}")

        try:
            match_item(session, base_url, token, library_item_id, asin, timeout)
        except requests.HTTPError as err:
            print(f"[match] failed: {err.response.status_code} {err.response.text}")
            continue

        try:
            details = fetch_item(session, base_url, token, library_item_id, timeout)
            media = details.get("media", {}).get("metadata", {})
            print("[verify] title=%s author=%s asin=%s" % (
                media.get("title"),
                media.get("author") or media.get("authors"),
                media.get("asin"),
            ))
            print(json.dumps({"libraryItemId": library_item_id, "metadata": media}, indent=2))
        except requests.HTTPError as err:
            print(f"[verify] failed: {err.response.status_code} {err.response.text}")


def main() -> int:
    parser = argparse.ArgumentParser(description="ABS ASIN match tester")
    parser.add_argument("--base-url", required=True, help="Audiobookshelf base URL, e.g. http://localhost:13378")
    parser.add_argument("--token", required=True, help="ABS bearer token")
    parser.add_argument("--library-id", required=True, help="Target ABS library ID")
    parser.add_argument("--asin", action="append", required=True, help="ASIN(s) to test; repeatable")
    parser.add_argument("--title-hint", help="Optional title to search if ASIN lookup fails")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    parser.add_argument("--skip-scan", action="store_true", help="Skip triggering a library scan")
    args = parser.parse_args()

    try:
        run_flow(
            base_url=args.base_url.rstrip("/"),
            token=args.token,
            library_id=args.library_id,
            asins=args.asin,
            title_hint=args.title_hint,
            timeout=args.timeout,
            skip_scan=args.skip_scan,
        )
    except KeyboardInterrupt:
        print("Interrupted")
        return 1
    except requests.HTTPError as err:
        print(f"HTTP error: {err.response.status_code} {err.response.text}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
