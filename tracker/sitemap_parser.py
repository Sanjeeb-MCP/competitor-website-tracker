"""Sitemap XML parser with index support and gzip handling."""

import gzip
import io
import logging
from urllib.parse import urlparse

from lxml import etree

logger = logging.getLogger(__name__)

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
MAX_DEPTH = 3


def discover_sitemaps(
    domain: str,
    robots_checker,
    http_client,
    configured_urls: list[str] | None = None,
) -> list[str]:
    """Find sitemap URLs for a domain via config, robots.txt, and common paths."""
    sitemaps = []

    if configured_urls:
        sitemaps.extend(configured_urls)

    base_url = f"https://www.{domain}"
    robot_sitemaps = robots_checker.get_sitemap_urls(base_url)
    for s in robot_sitemaps:
        if s not in sitemaps:
            sitemaps.append(s)

    default_paths = [
        f"https://www.{domain}/sitemap.xml",
        f"https://www.{domain}/sitemap_index.xml",
        f"https://{domain}/sitemap.xml",
    ]
    for path in default_paths:
        if path not in sitemaps:
            sitemaps.append(path)

    return sitemaps


def parse_sitemap(
    url: str,
    http_client,
    max_urls: int = 10000,
    depth: int = 0,
) -> list[dict]:
    """Parse a sitemap URL. Handles sitemap index files and gzip."""
    if depth > MAX_DEPTH:
        logger.warning("Max sitemap depth reached for %s", url)
        return []

    resp = http_client.get(url)
    if resp is None:
        return []

    content = resp.content
    if url.endswith(".gz") or resp.headers.get("Content-Type", "").startswith(
        "application/gzip"
    ):
        try:
            content = gzip.decompress(content)
        except Exception as e:
            logger.warning("Failed to decompress gzip sitemap %s: %s", url, e)
            return []

    try:
        root = etree.fromstring(content)
    except etree.XMLSyntaxError:
        try:
            parser = etree.XMLParser(recover=True)
            root = etree.fromstring(content, parser=parser)
        except Exception as e:
            logger.warning("Failed to parse sitemap XML %s: %s", url, e)
            return []

    tag = etree.QName(root.tag).localname if root.tag else ""

    if tag == "sitemapindex":
        return _parse_sitemap_index(root, http_client, max_urls, depth)
    elif tag == "urlset":
        return _parse_urlset(root, max_urls)
    else:
        logger.warning("Unknown sitemap root element <%s> in %s", tag, url)
        return []


def _parse_sitemap_index(
    root, http_client, max_urls: int, depth: int
) -> list[dict]:
    """Parse a sitemap index and recursively fetch child sitemaps."""
    urls = []
    for sitemap_el in root.findall("sm:sitemap", SITEMAP_NS):
        loc_el = sitemap_el.find("sm:loc", SITEMAP_NS)
        if loc_el is not None and loc_el.text:
            child_urls = parse_sitemap(
                loc_el.text.strip(), http_client, max_urls - len(urls), depth + 1
            )
            urls.extend(child_urls)
            if len(urls) >= max_urls:
                break
    return urls[:max_urls]


def _parse_urlset(root, max_urls: int) -> list[dict]:
    """Parse a urlset sitemap and extract URLs with metadata."""
    urls = []
    for url_el in root.findall("sm:url", SITEMAP_NS):
        if len(urls) >= max_urls:
            break
        loc_el = url_el.find("sm:loc", SITEMAP_NS)
        if loc_el is None or not loc_el.text:
            continue

        lastmod_el = url_el.find("sm:lastmod", SITEMAP_NS)
        lastmod = lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None

        urls.append({
            "url": loc_el.text.strip(),
            "lastmod": lastmod,
        })
    return urls


def discover_and_parse(
    domain: str,
    robots_checker,
    http_client,
    configured_urls: list[str] | None = None,
    max_urls: int = 10000,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[dict]:
    """Discover sitemaps for a domain and parse all URLs."""
    sitemap_urls = discover_sitemaps(domain, robots_checker, http_client, configured_urls)

    all_urls = []
    seen = set()
    parsed_sitemaps = set()

    for sm_url in sitemap_urls:
        if len(all_urls) >= max_urls:
            break
        if sm_url in parsed_sitemaps:
            continue
        parsed_sitemaps.add(sm_url)
        logger.info("Parsing sitemap: %s", sm_url)
        pages = parse_sitemap(sm_url, http_client, max_urls - len(all_urls))
        # If we already have enough URLs from the first sitemap, skip the rest
        if all_urls and not pages:
            continue
        for page in pages:
            url = page["url"]
            if url in seen:
                continue
            if not robots_checker.can_fetch(url):
                continue
            if include_patterns and not any(p in url for p in include_patterns):
                continue
            if exclude_patterns and any(p in url for p in exclude_patterns):
                continue
            seen.add(url)
            all_urls.append(page)

    logger.info("Discovered %d URLs for %s", len(all_urls), domain)
    return all_urls[:max_urls]
