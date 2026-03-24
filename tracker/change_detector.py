"""Change detection: compares current crawl against previous state."""

import hashlib
import logging
from datetime import datetime, timezone

from tracker.content_hasher import generate_diff_summary

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
    http_client=None,
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

    # --- Detect URL case changes ---
    if not is_first_run:
        case_changes = _detect_url_case_changes(current_url_set, previous_url_set)
        for old_url, new_url in case_changes:
            changes.append({
                "id": _generate_id(now, domain, new_url),
                "timestamp": now,
                "competitor": competitor_name,
                "domain": domain,
                "url": new_url,
                "change_type": "url_case_change",
                "title": previous_pages.get(old_url, {}).get("title", ""),
                "details": {
                    "old_url": old_url,
                    "new_url": new_url,
                },
            })

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
            "content_snippet": current_hashes.get(url, {}).get("content_snippet", ""),
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
            "content_snippet": prev.get("content_snippet", ""),
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
            page_data["content_snippet"] = h.get("content_snippet", "")

            if old_hash and new_hash and old_hash != new_hash and not is_first_run:
                # Generate content diff
                old_snippet = prev.get("content_snippet", "")
                new_snippet = h.get("content_snippet", "")
                diff = generate_diff_summary(old_snippet, new_snippet)

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
                        "diff_summary": diff.get("summary", ""),
                        "added": diff.get("added", []),
                        "removed": diff.get("removed", []),
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
    checked_count = 0
    max_missing_checks = 20  # limit HTTP checks for missing URLs per competitor

    for url in missing_urls:
        prev = previous_pages[url]
        consecutive = prev.get("consecutive_missing", 0) + 1
        page_data = dict(prev)
        page_data["consecutive_missing"] = consecutive
        page_data["last_seen"] = prev.get("last_seen", now)

        if consecutive >= removal_threshold and not is_first_run:
            # Check redirect and noindex status for removed pages
            redirect_info = None
            noindex = False
            if http_client and checked_count < max_missing_checks:
                checked_count += 1
                status = http_client.check_status(url)
                if status.get("redirect_to"):
                    redirect_info = {
                        "status_code": status["status_code"],
                        "redirect_to": status["redirect_to"],
                    }
                noindex = status.get("noindex", False)

            change_details = {
                "last_seen": prev.get("last_seen", ""),
                "first_seen": prev.get("first_seen", ""),
                "missing_runs": consecutive,
                "noindex": noindex,
            }
            if redirect_info:
                change_details["redirect"] = redirect_info

            changes.append({
                "id": _generate_id(now, domain, url),
                "timestamp": now,
                "competitor": competitor_name,
                "domain": domain,
                "url": url,
                "change_type": "redirect" if redirect_info else "page_removed",
                "title": prev.get("title", ""),
                "details": change_details,
            })
        else:
            # Keep tracking but don't remove yet
            updated_pages[url] = page_data

    return changes, updated_pages


def _detect_url_case_changes(
    current_urls: set[str], previous_urls: set[str]
) -> list[tuple[str, str]]:
    """Detect URLs that changed only in case (uppercase → lowercase)."""
    # Build lowercase lookup for current URLs
    current_lower = {}
    for url in current_urls:
        current_lower.setdefault(url.lower(), []).append(url)

    changes = []
    missing = previous_urls - current_urls
    for old_url in missing:
        matches = current_lower.get(old_url.lower(), [])
        for new_url in matches:
            if new_url != old_url and new_url not in previous_urls:
                changes.append((old_url, new_url))
    return changes


def _generate_id(timestamp: str, domain: str, url: str) -> str:
    raw = f"{timestamp}:{domain}:{url}"
    return "chg_" + hashlib.md5(raw.encode()).hexdigest()[:12]
