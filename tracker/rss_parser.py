"""RSS/Atom feed discovery and parsing."""

import logging

import feedparser

logger = logging.getLogger(__name__)

COMMON_FEED_PATHS = [
    "/feed",
    "/feed/",
    "/rss",
    "/rss.xml",
    "/blog/feed",
    "/blog/feed/",
    "/blog/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/blog/atom.xml",
    "/resources/feed",
]


def discover_feeds(
    domain: str,
    http_client,
    configured_urls: list[str] | None = None,
) -> list[str]:
    """Find RSS/Atom feed URLs for a domain."""
    feeds = []

    if configured_urls:
        feeds.extend(configured_urls)
        return feeds

    # Only try www. variant to avoid redundant requests on redirects
    base_urls = [f"https://www.{domain}"]
    for base in base_urls:
        for path in COMMON_FEED_PATHS:
            url = base + path
            resp = http_client.get(url)
            if resp is not None:
                content_type = resp.headers.get("Content-Type", "")
                text = resp.text[:500].lower()
                if any(
                    t in content_type
                    for t in ["xml", "rss", "atom", "feed"]
                ) or "<rss" in text or "<feed" in text or "<atom" in text:
                    feeds.append(url)
                    logger.info("Found feed: %s", url)
                    return feeds  # One good feed is enough

    return feeds


def parse_feed(url: str, http_client) -> list[dict]:
    """Parse an RSS/Atom feed and return entries."""
    resp = http_client.get(url)
    if resp is None:
        return []

    try:
        feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.warning("Failed to parse feed %s: %s", url, e)
        return []

    entries = []
    for entry in feed.entries[:50]:
        published = None
        if hasattr(entry, "published"):
            published = entry.published
        elif hasattr(entry, "updated"):
            published = entry.updated

        link = entry.get("link", "")
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        if len(summary) > 200:
            summary = summary[:200] + "..."

        if link:
            entries.append({
                "url": link,
                "title": title,
                "published": published,
                "summary": summary,
            })

    logger.info("Parsed %d entries from feed %s", len(entries), url)
    return entries


def discover_and_parse(
    domain: str,
    http_client,
    configured_urls: list[str] | None = None,
) -> list[dict]:
    """Discover feeds for a domain and parse all entries."""
    feed_urls = discover_feeds(domain, http_client, configured_urls)
    all_entries = []
    seen_urls = set()

    for feed_url in feed_urls:
        entries = parse_feed(feed_url, http_client)
        for entry in entries:
            if entry["url"] not in seen_urls:
                seen_urls.add(entry["url"])
                all_entries.append(entry)

    return all_entries
