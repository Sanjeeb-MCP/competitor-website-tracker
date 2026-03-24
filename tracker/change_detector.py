"""Change detection: compares current crawl against previous state."""

import hashlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def detect_changes(
    domain: str,
    competitor_name: str,
    current_urls: dict[str, dict],
    current_hashes: dict[str, dict],
    feed_entries: list[dict],
    previous_pages: dict[str, dict],
    is_first_run: bool,
    removal_threshold: int = 2,
) -> tuple[list[dict], dict[str, dict]]:
    """
    Detect changes between current crawl and previous state.

    Returns (changes, updated_pages) where:
    - changes: list of change events
    - updated_pages: merged page state for saving
    """
    changes = []
    now = datetime.now(timezone.utc).isoformat()
    updated_pages = {}

    # Build feed lookup for enrichment
    feed_lookup = {e["url"]: e for e in feed_entries}

    current_url_set = set(current_urls.keys())
    previous_url_set = set(previous_pages.keys())

    # --- New pages ---
    new_urls = current_url_set - previous_url_set
    for url in new_urls:
        page_data = {
            "first_seen": now,
            "last_seen": now,
            "content_hash": current_hashes.get(url, {}).get("content_hash", ""),
            "title": current_hashes.get(url, {}).get("title", "")
                or current_urls[url].get("title", ""),
            "meta_description": current_hashes.get(url, {}).get("meta_description", ""),
            "lastmod_from_sitemap": current_urls[url].get("lastmod"),
            "consecutive_missing": 0,
        }
        updated_pages[url] = page_data

        if not is_first_run:
            feed_info = feed_lookup.get(url, {})
            changes.append({
                "id": _generate_id(now, domain, url),
                "timestamp": now,
                "competitor": competitor_name,
                "domain": domain,
                "url": url,
                "change_type": "new_page",
                "title": page_data["title"],
                "details": {
                    "source": "sitemap+rss" if url in feed_lookup else "sitemap",
                    "published_date": feed_info.get("published"),
                    "summary": feed_info.get("summary", ""),
                },
            })

    # --- Existing pages: check for content changes ---
    existing_urls = current_url_set & previous_url_set
    for url in existing_urls:
        prev = previous_pages[url]
        page_data = {
            "first_seen": prev.get("first_seen", now),
            "last_seen": now,
            "content_hash": prev.get("content_hash", ""),
            "title": prev.get("title", ""),
            "meta_description": prev.get("meta_description", ""),
            "lastmod_from_sitemap": current_urls[url].get("lastmod")
                or prev.get("lastmod_from_sitemap"),
            "consecutive_missing": 0,
        }

        if url in current_hashes:
            h = current_hashes[url]
            new_hash = h.get("content_hash", "")
            old_hash = prev.get("content_hash", "")

            page_data["content_hash"] = new_hash
            page_data["title"] = h.get("title", "") or page_data["title"]
            page_data["meta_description"] = h.get("meta_description", "") or page_data["meta_description"]

            if old_hash and new_hash and old_hash != new_hash and not is_first_run:
                changes.append({
                    "id": _generate_id(now, domain, url),
                    "timestamp": now,
                    "competitor": competitor_name,
                    "domain": domain,
                    "url": url,
                    "change_type": "content_update",
                    "title": page_data["title"],
                    "details": {
                        "source": "content_hash",
                        "old_hash": old_hash[:12],
                        "new_hash": new_hash[:12],
                    },
                })
            elif not is_first_run:
                # Check title/meta changes
                if h.get("title") and prev.get("title") and h["title"] != prev["title"]:
                    changes.append({
                        "id": _generate_id(now, domain, url),
                        "timestamp": now,
                        "competitor": competitor_name,
                        "domain": domain,
                        "url": url,
                        "change_type": "title_change",
                        "title": h["title"],
                        "details": {
                            "old_title": prev["title"],
                            "new_title": h["title"],
                        },
                    })
                if (
                    h.get("meta_description")
                    and prev.get("meta_description")
                    and h["meta_description"] != prev["meta_description"]
                ):
                    changes.append({
                        "id": _generate_id(now, domain, url),
                        "timestamp": now,
                        "competitor": competitor_name,
                        "domain": domain,
                        "url": url,
                        "change_type": "meta_change",
                        "title": page_data["title"],
                        "details": {
                            "old_meta": prev["meta_description"][:100],
                            "new_meta": h["meta_description"][:100],
                        },
                    })

        updated_pages[url] = page_data

    # --- Missing pages (potential removals) ---
    missing_urls = previous_url_set - current_url_set
    for url in missing_urls:
        prev = previous_pages[url]
        consecutive = prev.get("consecutive_missing", 0) + 1
        page_data = dict(prev)
        page_data["consecutive_missing"] = consecutive
        page_data["last_seen"] = prev.get("last_seen", now)

        if consecutive >= removal_threshold and not is_first_run:
            changes.append({
                "id": _generate_id(now, domain, url),
                "timestamp": now,
                "competitor": competitor_name,
                "domain": domain,
                "url": url,
                "change_type": "page_removed",
                "title": prev.get("title", ""),
                "details": {
                    "last_seen": prev.get("last_seen", ""),
                    "first_seen": prev.get("first_seen", ""),
                    "missing_runs": consecutive,
                },
            })
        else:
            # Keep tracking but don't remove yet
            updated_pages[url] = page_data

    return changes, updated_pages


def _generate_id(timestamp: str, domain: str, url: str) -> str:
    raw = f"{timestamp}:{domain}:{url}"
    return "chg_" + hashlib.md5(raw.encode()).hexdigest()[:12]
