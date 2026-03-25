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
    changes = []
    now = datetime.now(timezone.utc).isoformat()
    updated_pages = {}
    feed_lookup = {e["url"]: e for e in feed_entries}

    current_url_set = set(current_urls.keys())
    previous_url_set = set(previous_pages.keys())

    # --- URL case changes ---
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
                "details": {"old_url": old_url, "new_url": new_url},
            })

    # --- New pages ---
    new_urls = current_url_set - previous_url_set
    for url in new_urls:
        h = current_hashes.get(url, {})
        page_data = {
            "first_seen": now,
            "last_seen": now,
            "content_hash": h.get("content_hash", ""),
            "title": h.get("title", "") or current_urls[url].get("title", ""),
            "meta_description": h.get("meta_description", ""),
            "content_snippet": h.get("content_snippet", ""),
            "h1_tags": h.get("h1_tags", []),
            "word_count": h.get("word_count", 0),
            "canonical": h.get("canonical", ""),
            "schemas": h.get("schemas", []),
            "lastmod_from_sitemap": current_urls[url].get("lastmod"),
            "consecutive_missing": 0,
        }
        updated_pages[url] = page_data

        if not is_first_run:
            feed_info = feed_lookup.get(url, {})
            details = {
                "source": "sitemap+rss" if url in feed_lookup else "sitemap",
                "published_date": feed_info.get("published"),
                "summary": feed_info.get("summary", ""),
            }
            if page_data["word_count"]:
                details["word_count"] = page_data["word_count"]
            if page_data["h1_tags"]:
                details["h1"] = page_data["h1_tags"][0]
            if page_data["schemas"]:
                details["schemas"] = page_data["schemas"]
            changes.append({
                "id": _generate_id(now, domain, url),
                "timestamp": now,
                "competitor": competitor_name,
                "domain": domain,
                "url": url,
                "change_type": "new_page",
                "title": page_data["title"],
                "details": details,
            })

    # --- Existing pages ---
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
            "h1_tags": prev.get("h1_tags", []),
            "word_count": prev.get("word_count", 0),
            "canonical": prev.get("canonical", ""),
            "schemas": prev.get("schemas", []),
            "lastmod_from_sitemap": current_urls[url].get("lastmod") or prev.get("lastmod_from_sitemap"),
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
            page_data["h1_tags"] = h.get("h1_tags", [])
            page_data["word_count"] = h.get("word_count", 0)
            page_data["canonical"] = h.get("canonical", "")
            page_data["schemas"] = h.get("schemas", [])

            if not is_first_run:
                # Content update
                if old_hash and new_hash and old_hash != new_hash:
                    old_snippet = prev.get("content_snippet", "")
                    new_snippet = h.get("content_snippet", "")
                    diff = generate_diff_summary(old_snippet, new_snippet)

                    old_wc = prev.get("word_count", 0)
                    new_wc = h.get("word_count", 0)
                    wc_change = new_wc - old_wc if old_wc and new_wc else 0

                    details = {
                        "source": "content_hash",
                        "old_hash": old_hash[:12],
                        "new_hash": new_hash[:12],
                        "diff_summary": diff.get("summary", ""),
                        "added": diff.get("added", []),
                        "removed": diff.get("removed", []),
                    }
                    if wc_change:
                        details["word_count_change"] = wc_change
                        details["old_word_count"] = old_wc
                        details["new_word_count"] = new_wc

                    changes.append({
                        "id": _generate_id(now, domain, url),
                        "timestamp": now,
                        "competitor": competitor_name,
                        "domain": domain,
                        "url": url,
                        "change_type": "content_update",
                        "title": page_data["title"],
                        "details": details,
                    })

                # H1 change
                old_h1 = prev.get("h1_tags", [])
                new_h1 = h.get("h1_tags", [])
                if old_h1 and new_h1 and old_h1 != new_h1:
                    changes.append({
                        "id": _generate_id(now, domain, url + ":h1"),
                        "timestamp": now,
                        "competitor": competitor_name,
                        "domain": domain,
                        "url": url,
                        "change_type": "h1_change",
                        "title": page_data["title"],
                        "details": {"old_h1": old_h1[0], "new_h1": new_h1[0]},
                    })

                # Schema changes
                old_schemas = set(prev.get("schemas", []))
                new_schemas = set(h.get("schemas", []))
                if old_schemas != new_schemas:
                    added_s = list(new_schemas - old_schemas)
                    removed_s = list(old_schemas - new_schemas)
                    if added_s or removed_s:
                        changes.append({
                            "id": _generate_id(now, domain, url + ":schema"),
                            "timestamp": now,
                            "competitor": competitor_name,
                            "domain": domain,
                            "url": url,
                            "change_type": "schema_change",
                            "title": page_data["title"],
                            "details": {"added_schemas": added_s, "removed_schemas": removed_s},
                        })

                # Title change (only if content hash is same)
                if old_hash == new_hash:
                    if h.get("title") and prev.get("title") and h["title"] != prev["title"]:
                        changes.append({
                            "id": _generate_id(now, domain, url + ":title"),
                            "timestamp": now,
                            "competitor": competitor_name,
                            "domain": domain,
                            "url": url,
                            "change_type": "title_change",
                            "title": h["title"],
                            "details": {"old_title": prev["title"], "new_title": h["title"]},
                        })
                    if (h.get("meta_description") and prev.get("meta_description")
                            and h["meta_description"] != prev["meta_description"]):
                        changes.append({
                            "id": _generate_id(now, domain, url + ":meta"),
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

    # --- Missing pages ---
    missing_urls = previous_url_set - current_url_set

    # Safety check: if >50% of previously known pages are "missing", it's likely
    # a crawl failure (site blocking, sitemap down) — not real removals.
    # Keep all pages in state and skip removal detection.
    if previous_url_set and len(missing_urls) > len(previous_url_set) * 0.5:
        logger.warning(
            "%s: %d of %d pages missing (>50%%) — likely crawl failure, skipping removals",
            domain, len(missing_urls), len(previous_url_set),
        )
        for url in missing_urls:
            updated_pages[url] = dict(previous_pages[url])
        return changes, updated_pages

    checked_count = 0
    max_missing_checks = 50  # Check up to 50 missing URLs for redirects

    for url in missing_urls:
        prev = previous_pages[url]
        consecutive = prev.get("consecutive_missing", 0) + 1
        page_data = dict(prev)
        page_data["consecutive_missing"] = consecutive
        page_data["last_seen"] = prev.get("last_seen", now)

        if consecutive >= removal_threshold and not is_first_run:
            # Always check redirect status for removed pages
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
            updated_pages[url] = page_data

    return changes, updated_pages


def _detect_url_case_changes(current_urls, previous_urls):
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


def _generate_id(timestamp, domain, url):
    raw = f"{timestamp}:{domain}:{url}"
    return "chg_" + hashlib.md5(raw.encode()).hexdigest()[:12]
