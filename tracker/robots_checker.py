"""Robots.txt compliance checker with caching."""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

BOT_USER_AGENT = "*"


class RobotsChecker:
    """Checks robots.txt rules for URLs. Caches per domain."""

    def __init__(self, http_client):
        self.http_client = http_client
        self._cache: dict[str, RobotFileParser | None] = {}
        self._crawl_delays: dict[str, float | None] = {}

    def _get_robots_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _load(self, domain: str, url: str) -> None:
        if domain in self._cache:
            return

        robots_url = self._get_robots_url(url)
        rp = RobotFileParser()
        try:
            text = self.http_client.get_text(robots_url)
            if text:
                rp.parse(text.splitlines())
                self._cache[domain] = rp
                delay = rp.crawl_delay(BOT_USER_AGENT)
                self._crawl_delays[domain] = delay
                logger.info("Loaded robots.txt for %s", domain)
            else:
                self._cache[domain] = None
                self._crawl_delays[domain] = None
        except Exception as e:
            logger.warning("Error parsing robots.txt for %s: %s", domain, e)
            self._cache[domain] = None
            self._crawl_delays[domain] = None

    def can_fetch(self, url: str) -> bool:
        """Check if the URL is allowed by robots.txt. Permissive on failure."""
        domain = self._get_domain(url)
        self._load(domain, url)
        rp = self._cache.get(domain)
        if rp is None:
            return True
        return rp.can_fetch(BOT_USER_AGENT, url)

    def get_crawl_delay(self, url: str) -> float | None:
        """Get the Crawl-delay for a domain, or None if not specified."""
        domain = self._get_domain(url)
        self._load(domain, url)
        return self._crawl_delays.get(domain)

    def get_sitemap_urls(self, url: str) -> list[str]:
        """Extract Sitemap directives from robots.txt."""
        domain = self._get_domain(url)
        self._load(domain, url)
        rp = self._cache.get(domain)
        if rp is None:
            return []
        sitemaps = rp.site_maps()
        return sitemaps if sitemaps else []
