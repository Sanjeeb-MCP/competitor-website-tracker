"""Page content hashing, text extraction, and SEO metadata for change detection."""

import difflib
import hashlib
import json
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

STRIP_TAGS = ["script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"]
STRIP_CLASSES = [
    "sidebar", "side-bar", "related", "recommended", "popular",
    "newsletter", "subscribe", "signup", "sign-up", "cta",
    "social", "share", "sharing", "comments", "comment",
    "breadcrumb", "pagination", "widget", "ad", "ads",
    "banner", "cookie", "popup", "modal", "menu",
    "table-of-contents", "toc",
]
STRIP_IDS = [
    "sidebar", "related", "recommended", "comments", "newsletter",
    "subscribe", "social", "share", "breadcrumb", "toc",
]
MAX_CONTENT_SNIPPET = 2000  # Increased for better diffing


def hash_page(url: str, http_client) -> dict | None:
    """Fetch a page and return content hash, metadata, and SEO signals."""
    resp = http_client.get(url)
    if resp is None:
        return None

    html = resp.text
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.warning("Failed to parse HTML for %s: %s", url, e)
        return None

    # Title
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    # Meta description
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()

    # H1 tags
    h1_tags = []
    for h1 in soup.find_all("h1"):
        text = h1.get_text(strip=True)
        if text:
            h1_tags.append(text)

    # Noindex check
    noindex = False
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    if robots_meta and "noindex" in robots_meta.get("content", "").lower():
        noindex = True

    # Canonical
    canonical = ""
    canon_tag = soup.find("link", attrs={"rel": "canonical"})
    if canon_tag:
        canonical = canon_tag.get("href", "").strip()

    # Schema markup (JSON-LD)
    schemas = _extract_schemas(soup)

    # Main content
    main_text = _extract_main_content(soup)
    content_hash = _compute_hash(main_text)
    word_count = len(main_text.split())
    content_snippet = main_text[:MAX_CONTENT_SNIPPET]

    return {
        "url": url,
        "content_hash": content_hash,
        "title": title,
        "meta_description": meta_desc,
        "h1_tags": h1_tags,
        "word_count": word_count,
        "canonical": canonical,
        "schemas": schemas,
        "content_snippet": content_snippet,
        "noindex": noindex,
    }


def _extract_schemas(soup: BeautifulSoup) -> list[str]:
    """Extract Schema.org types from JSON-LD blocks."""
    schemas = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                t = data.get("@type", "")
                if isinstance(t, list):
                    schemas.extend(t)
                elif t:
                    schemas.append(t)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        t = item.get("@type", "")
                        if isinstance(t, list):
                            schemas.extend(t)
                        elif t:
                            schemas.append(t)
        except (json.JSONDecodeError, TypeError):
            continue
    return schemas


def generate_diff_summary(old_text: str, new_text: str) -> dict:
    """Generate a human-readable diff summary between old and new content."""
    if not old_text and not new_text:
        return {"added": [], "removed": [], "summary": "No content available"}
    if not old_text:
        # First time we have a snippet — show new content as "added"
        sentences = _split_sentences(new_text)[:5]
        return {"added": [s[:150] for s in sentences], "removed": [], "summary": f"Content captured ({len(new_text.split())} words)"}
    if not new_text:
        sentences = _split_sentences(old_text)[:5]
        return {"added": [], "removed": [s[:150] for s in sentences], "summary": "Content removed"}

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
    parts = re.split(r'(?<=[.!?])\s+', text)
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
    # Strip known non-content tags
    for tag in STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Strip elements by class name (sidebars, related posts, widgets, etc.)
    for el in soup.find_all(True):
        classes = " ".join(el.get("class", [])).lower()
        el_id = (el.get("id") or "").lower()
        if any(c in classes for c in STRIP_CLASSES):
            el.decompose()
            continue
        if any(i in el_id for i in STRIP_IDS):
            el.decompose()
            continue

    # Strip aside elements (typically sidebars/related content)
    for el in soup.find_all("aside"):
        el.decompose()

    # Strip forms (newsletter signups, search, etc.)
    for el in soup.find_all("form"):
        el.decompose()

    main = soup.find("main") or soup.find("article")
    if main:
        text = main.get_text(separator=" ", strip=True)
    else:
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)
    return _normalize_text(text)


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
