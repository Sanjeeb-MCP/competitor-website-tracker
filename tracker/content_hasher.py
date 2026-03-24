"""Page content hashing for change detection."""

import hashlib
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

STRIP_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"]


def hash_page(url: str, http_client) -> dict | None:
    """Fetch a page and return its content hash and metadata."""
    resp = http_client.get(url)
    if resp is None:
        return None

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        logger.warning("Failed to parse HTML for %s: %s", url, e)
        return None

    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()

    main_text = _extract_main_content(soup)
    content_hash = _compute_hash(main_text)

    return {
        "url": url,
        "content_hash": content_hash,
        "title": title,
        "meta_description": meta_desc,
    }


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Extract main content text, stripping boilerplate."""
    for tag in STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Try to find main content container
    main = soup.find("main") or soup.find("article")
    if main:
        text = main.get_text(separator=" ", strip=True)
    else:
        # Fall back to body
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

    return _normalize_text(text)


def _normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compute_hash(text: str) -> str:
    """SHA-256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
