"""Page content hashing and text extraction for change detection."""

import difflib
import hashlib
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

STRIP_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"]
MAX_CONTENT_SNIPPET = 1000  # chars to store for diffing


def hash_page(url: str, http_client) -> dict | None:
    """Fetch a page and return its content hash, metadata, and text snippet."""
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

    # Check for noindex
    noindex = False
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    if robots_meta and "noindex" in robots_meta.get("content", "").lower():
        noindex = True

    main_text = _extract_main_content(soup)
    content_hash = _compute_hash(main_text)

    # Store a snippet for diffing (first N chars)
    content_snippet = main_text[:MAX_CONTENT_SNIPPET]

    return {
        "url": url,
        "content_hash": content_hash,
        "title": title,
        "meta_description": meta_desc,
        "content_snippet": content_snippet,
        "noindex": noindex,
    }


def generate_diff_summary(old_text: str, new_text: str) -> dict:
    """Generate a human-readable diff summary between old and new content."""
    if not old_text or not new_text:
        return {"added": [], "removed": [], "summary": "No previous content to compare"}

    old_sentences = _split_sentences(old_text)
    new_sentences = _split_sentences(new_text)

    differ = difflib.unified_diff(old_sentences, new_sentences, lineterm="", n=0)

    added = []
    removed = []

    for line in differ:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            text = line[1:].strip()
            if text and len(text) > 10:
                added.append(text[:150])
        elif line.startswith("-"):
            text = line[1:].strip()
            if text and len(text) > 10:
                removed.append(text[:150])

    # Limit to top 5 each
    added = added[:5]
    removed = removed[:5]

    summary = ""
    if added and removed:
        summary = f"{len(added)} section(s) added, {len(removed)} section(s) removed"
    elif added:
        summary = f"{len(added)} section(s) added"
    elif removed:
        summary = f"{len(removed)} section(s) removed"
    else:
        summary = "Minor text changes detected"

    return {"added": added, "removed": removed, "summary": summary}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-like chunks for diffing."""
    # Split on sentence boundaries or long phrases
    parts = re.split(r'(?<=[.!?])\s+', text)
    # Further split very long parts
    result = []
    for p in parts:
        if len(p) > 200:
            words = p.split()
            for i in range(0, len(words), 15):
                chunk = " ".join(words[i:i+15])
                if chunk.strip():
                    result.append(chunk.strip())
        elif p.strip():
            result.append(p.strip())
    return result


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
