"""Shared HTTP client with User-Agent rotation, rate limiting, and retries."""

import logging
import random
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


class TrackerHTTPClient:
    """HTTP client with retry logic, UA rotation, and per-domain rate limiting."""

    def __init__(self, delay_seconds: float = 2.0, timeout_seconds: float = 30.0):
        self.delay_seconds = delay_seconds
        self.timeout = timeout_seconds
        self._last_request_time: dict[str, float] = {}

        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _rate_limit(self, domain: str) -> None:
        now = time.monotonic()
        last = self._last_request_time.get(domain, 0)
        wait = self.delay_seconds - (now - last)
        if wait > 0:
            time.sleep(wait)
        self._last_request_time[domain] = time.monotonic()

    def get(self, url: str) -> requests.Response | None:
        """Fetch a URL with rate limiting and UA rotation. Returns None on failure."""
        domain = self._get_domain(url)
        self._rate_limit(domain)

        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

    def get_text(self, url: str) -> str | None:
        """Fetch a URL and return its text content, or None on failure."""
        resp = self.get(url)
        if resp is None:
            return None
        return resp.text

    def check_redirect(self, url: str) -> dict | None:
        """Check if a URL redirects (301/302). Returns redirect info or None."""
        domain = self._get_domain(url)
        self._rate_limit(domain)

        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            resp = self.session.get(
                url, headers=headers, timeout=self.timeout, allow_redirects=False
            )
            if resp.status_code in (301, 302, 307, 308):
                location = resp.headers.get("Location", "")
                return {
                    "status_code": resp.status_code,
                    "redirect_to": location,
                }
            return None
        except requests.RequestException:
            return None

    def check_status(self, url: str) -> dict:
        """Check URL status, meta robots, and redirects without following redirects."""
        domain = self._get_domain(url)
        self._rate_limit(domain)

        headers = {"User-Agent": random.choice(USER_AGENTS)}
        result = {"status_code": None, "redirect_to": None, "noindex": False, "x_robots": None}
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            result["status_code"] = resp.status_code

            # Check if it was redirected
            if resp.history:
                result["redirect_to"] = resp.url
                result["status_code"] = resp.history[0].status_code

            # Check X-Robots-Tag header
            x_robots = resp.headers.get("X-Robots-Tag", "")
            if x_robots:
                result["x_robots"] = x_robots
                if "noindex" in x_robots.lower():
                    result["noindex"] = True

            # Check meta robots tag in HTML
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                text = resp.text[:5000].lower()
                if 'name="robots"' in text and "noindex" in text:
                    result["noindex"] = True

            return result
        except requests.RequestException:
            return result
