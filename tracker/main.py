"""Main orchestrator for competitor website change tracking."""

import argparse
import logging
import random
import sys

import yaml

from tracker.http_client import TrackerHTTPClient
from tracker.robots_checker import RobotsChecker
from tracker import sitemap_parser, rss_parser, content_hasher, change_detector
from tracker.state_manager import load_state, save_state, append_changes
from tracker.dashboard_builder import build_dashboard

logger = logging.getLogger("tracker")


def load_config(path: str = "config/competitors.yml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def process_competitor(
    comp: dict,
    settings: dict,
    http_client: TrackerHTTPClient,
    robots: RobotsChecker,
    previous_pages: dict,
    is_first_run: bool,
) -> tuple[list[dict], dict[str, dict]]:
    """Process a single competitor: discover pages, hash content, detect changes."""
    domain = comp["domain"]
    name = comp["name"]
    logger.info("Processing competitor: %s (%s)", name, domain)

    # Respect crawl delay from robots.txt
    base_url = f"https://www.{domain}"
    crawl_delay = robots.get_crawl_delay(base_url)
    if crawl_delay and crawl_delay > http_client.delay_seconds:
        http_client.delay_seconds = crawl_delay
        logger.info("Using crawl delay of %ss from robots.txt for %s", crawl_delay, domain)

    # Discover URLs from sitemaps
    sitemap_pages = sitemap_parser.discover_and_parse(
        domain=domain,
        robots_checker=robots,
        http_client=http_client,
        configured_urls=comp.get("sitemaps"),
        max_urls=settings.get("max_pages_per_domain", 10000),
        include_patterns=comp.get("include_patterns"),
        exclude_patterns=comp.get("exclude_patterns"),
    )

    # Build URL lookup from sitemap data
    current_urls = {}
    for page in sitemap_pages:
        current_urls[page["url"]] = page

    # Discover and parse RSS feeds
    feed_entries = rss_parser.discover_and_parse(
        domain=domain,
        http_client=http_client,
        configured_urls=comp.get("feeds"),
    )

    # Add feed URLs not already in sitemap
    for entry in feed_entries:
        if entry["url"] not in current_urls:
            current_urls[entry["url"]] = {
                "url": entry["url"],
                "lastmod": entry.get("published"),
                "title": entry.get("title", ""),
            }

    logger.info("Found %d total URLs for %s", len(current_urls), domain)

    # Determine which pages to hash (priority-based)
    max_hash = settings.get("max_hash_per_domain", 50)
    urls_to_hash = _prioritize_urls(current_urls, previous_pages, feed_entries, max_hash)

    # Hash content of priority pages
    current_hashes = {}
    for url in urls_to_hash:
        result = content_hasher.hash_page(url, http_client)
        if result:
            current_hashes[url] = result

    logger.info("Hashed %d pages for %s", len(current_hashes), domain)

    # Detect changes
    changes, updated_pages = change_detector.detect_changes(
        domain=domain,
        competitor_name=name,
        current_urls=current_urls,
        current_hashes=current_hashes,
        feed_entries=feed_entries,
        previous_pages=previous_pages,
        is_first_run=is_first_run,
        removal_threshold=settings.get("removal_threshold_runs", 2),
        http_client=http_client,
    )

    return changes, updated_pages


def _prioritize_urls(
    current_urls: dict,
    previous_pages: dict,
    feed_entries: list[dict],
    max_hash: int,
) -> list[str]:
    """Select which URLs to content-hash this run."""
    priority = []

    # 1. New URLs (not in previous state)
    new_urls = [u for u in current_urls if u not in previous_pages]
    priority.extend(new_urls)

    # 2. URLs from RSS feeds
    feed_urls = [e["url"] for e in feed_entries if e["url"] not in new_urls]
    priority.extend(feed_urls)

    # 3. URLs with recent lastmod
    for url, data in current_urls.items():
        if url not in priority and data.get("lastmod"):
            priority.append(url)

    # 4. Random sample of remaining
    remaining = [u for u in current_urls if u not in priority]
    random.shuffle(remaining)
    priority.extend(remaining)

    return priority[:max_hash]


def main():
    parser = argparse.ArgumentParser(description="Competitor Website Change Tracker")
    parser.add_argument("--config", default="config/competitors.yml", help="Config file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config(args.config)
    settings = config.get("settings", {})

    http_client = TrackerHTTPClient(
        delay_seconds=settings.get("request_delay_seconds", 2),
        timeout_seconds=settings.get("request_timeout_seconds", 30),
    )
    robots = RobotsChecker(http_client)

    state = load_state()
    is_first_run = state["run_count"] == 0
    state["run_count"] += 1

    if is_first_run:
        logger.info("First run detected — establishing baseline (no change alerts)")

    all_changes = []

    for comp in config.get("competitors", []):
        domain = comp["domain"]
        previous_pages = state.get("competitors", {}).get(domain, {}).get("pages", {})

        try:
            changes, updated_pages = process_competitor(
                comp=comp,
                settings=settings,
                http_client=http_client,
                robots=robots,
                previous_pages=previous_pages,
                is_first_run=is_first_run,
            )

            # Update state
            if domain not in state.get("competitors", {}):
                state.setdefault("competitors", {})[domain] = {
                    "name": comp["name"],
                    "pages": {},
                }
            state["competitors"][domain]["name"] = comp["name"]
            state["competitors"][domain]["pages"] = updated_pages
            state["competitors"][domain]["total_urls_discovered"] = len(updated_pages)

            all_changes.extend(changes)
            logger.info(
                "%s: %d changes detected", comp["name"], len(changes)
            )

        except Exception as e:
            logger.error("Error processing %s: %s", comp["name"], e, exc_info=True)
            continue

        # Reset delay for next competitor
        http_client.delay_seconds = settings.get("request_delay_seconds", 2)

    # Save state and changes
    save_state(state)
    if all_changes:
        append_changes(
            all_changes,
            max_entries=settings.get("max_changes_history", 5000),
        )

    # Build dashboard
    build_dashboard()

    logger.info(
        "Done — %d changes across %d competitors",
        len(all_changes),
        len(config.get("competitors", [])),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
