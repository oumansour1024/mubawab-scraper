"""HTTP search scraper that preserves the original listing-card text."""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from itertools import count

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.parsers.card_parser_brut import parse_page
from mubawab_scraper.parsers.pagination_parser import parse_pagination
from mubawab_scraper.utils.rate_limit import RequestRateLimiter, jittered_sleep
from mubawab_scraper.utils.urls import build_city_url

log = get_logger(__name__)

REQUEST_TIMEOUT = 20
MAX_RATE_LIMIT_RETRIES = 3
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


@dataclass
class RawSearchResult:
    listings: list[dict[str, str | bool]]
    pages_scraped: int
    error: str | None = None


def _rate_limit_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(
                    0.0,
                    (retry_at - datetime.now(UTC)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                pass
    return float(min(5 * (2**attempt), 60))


def fetch(
    url: str,
    session: requests.Session | None = None,
    rate_limiter: RequestRateLimiter | None = None,
) -> str:
    owns_session = session is None
    client = session or requests.Session()
    try:
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                if rate_limiter is not None:
                    rate_limiter.wait()
                response = client.get(
                    url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.RequestException as exc:
                log.warning("raw_fetch_failed", url=url, error=str(exc))
                raise

            if response.status_code != 429:
                response.raise_for_status()
                return response.text
            if attempt == MAX_RATE_LIMIT_RETRIES:
                log.error(
                    "raw_rate_limit_retries_exhausted",
                    url=url,
                    attempts=attempt + 1,
                    retry_after=response.headers.get("Retry-After"),
                )
                response.raise_for_status()

            delay = _rate_limit_delay(
                response.headers.get("Retry-After"),
                attempt,
            )
            log.warning(
                "raw_rate_limited",
                url=url,
                retry=attempt + 1,
                retry_after=response.headers.get("Retry-After"),
                wait_seconds=delay,
            )
            time.sleep(delay)
        raise RuntimeError("Rate-limit retry loop exited unexpectedly")
    finally:
        if owns_session:
            client.close()


def build_page_url(base_url: str, page: int) -> str:
    return f"{base_url}:p:{page}"


def _pages(max_pages: int) -> Iterator[int]:
    return iter(range(1, max_pages + 1)) if max_pages > 0 else count(1)


def scrape_search_pages(
    city_slug: str,
    transaction_type: str,
    max_pages: int | None = None,
    rate_limiter: RequestRateLimiter | None = None,
) -> RawSearchResult:
    """Scrape raw listings for a city/action; zero pages means no page limit."""
    page_limit = settings.max_pages if max_pages is None else max_pages
    if page_limit < 0:
        raise ValueError("max_pages must be zero (unlimited) or a positive integer")

    base_url = build_city_url(city_slug, transaction_type)
    listings: list[dict[str, str | bool]] = []
    pages_scraped = 0
    page_numbers = _pages(page_limit)
    progress = tqdm(
        page_numbers,
        total=page_limit if page_limit > 0 else None,
        desc=f"[{city_slug}:{transaction_type}]",
        disable=rate_limiter is not None,
    )

    error = None
    discovered_total_pages = 0
    with requests.Session() as session, progress:
        for page in progress:
            url = build_page_url(base_url, page)
            try:
                html = fetch(url, session=session, rate_limiter=rate_limiter)
            except requests.RequestException as exc:
                error = f"{type(exc).__name__}: {exc}"
                log.error(
                    "raw_page_fetch_failed",
                    city=city_slug,
                    action=transaction_type,
                    page=page,
                    error=error,
                )
                break
            if not html:
                log.warning(
                    "raw_empty_page_stopping",
                    city=city_slug,
                    action=transaction_type,
                    url=url,
                )
                break

            if page == 1 and page_limit == 0:
                pagination = parse_pagination(
                    BeautifulSoup(html, "html.parser"),
                    base_url,
                )
                discovered_total_pages = pagination.total_pages if pagination else 0
                if discovered_total_pages:
                    progress.total = discovered_total_pages
                    progress.refresh()

            rows = parse_page(html, transaction_type, city_slug, url)
            if not rows:
                log.info(
                    "raw_no_listings_stopping",
                    city=city_slug,
                    action=transaction_type,
                    page=page,
                )
                break

            listings.extend(rows)
            pages_scraped += 1
            log.info(
                "raw_page_scraped",
                city=city_slug,
                action=transaction_type,
                page=page,
                listings=len(rows),
                total=len(listings),
            )
            if rate_limiter is None and (
                (page_limit == 0 or page < page_limit)
                and (not discovered_total_pages or page < discovered_total_pages)
            ):
                jittered_sleep()
            if discovered_total_pages and page >= discovered_total_pages:
                break

    return RawSearchResult(
        listings=listings,
        pages_scraped=pages_scraped,
        error=error,
    )
