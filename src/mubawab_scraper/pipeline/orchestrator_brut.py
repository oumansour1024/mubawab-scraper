"""Orchestrate the raw HTTP scraper across registered cities and actions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from mubawab_scraper.config import settings
from mubawab_scraper.application.services.city_resolution import (
    resolve_cities,
    resolve_city_range,
)
from mubawab_scraper.application.services.transaction_normalization import (
    RAW_ACTION_ALIASES,
    normalize_scrape_action,
)
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.scrapers.search_brut import RawSearchResult, scrape_search_pages
from mubawab_scraper.storage.csv_store import export_raw_bundle
from mubawab_scraper.storage.raw_store import RawListingStore
from mubawab_scraper.storage.sqlite_store import SQLiteStore
from mubawab_scraper.utils.rate_limit import RequestRateLimiter
from mubawab_scraper.utils.urls import (
    ACTION_ALIASES,
    CT_ACTIONS,
    normalize_city_action,
)

log = get_logger(__name__)

MAX_RAW_WORKERS = 2

@dataclass
class RawScrapeSummary:
    city: str
    action: str
    pages_scraped: int
    listings_scraped: int
    error: str | None = None


def _normalize_action(action: str) -> str:
    return normalize_scrape_action(action)


def _resolve_cities(
    city: str,
    registered_cities: list[dict[str, str | None]],
) -> list[tuple[str, str]]:
    return resolve_cities(city, registered_cities)


def _resolve_city_range(
    city_range: str,
    registered_cities: list[dict[str, str | None]],
) -> list[tuple[str, str]]:
    return resolve_city_range(city_range, registered_cities)


def run_pipeline(
    city: str,
    transaction: str,
    max_pages: int | None = None,
    workers: int = 1,
    city_range: str | None = None,
    page_range: tuple[int, int] | None = None,
) -> list[RawScrapeSummary]:
    """Scrape one/all cities and one/all actions into the raw listings table."""
    if not 1 <= workers <= MAX_RAW_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_RAW_WORKERS}")

    city_store = SQLiteStore(settings.db_path)
    try:
        registered_cities = city_store.get_all_villes()
        city_targets = (
            _resolve_city_range(city_range, registered_cities)
            if city_range is not None
            else _resolve_cities(city, registered_cities)
        )
    finally:
        city_store.close()

    if transaction.strip().lower() == "all":
        actions = list(CT_ACTIONS)
    else:
        actions = [_normalize_action(transaction)]

    raw_store = RawListingStore(settings.db_path)
    summaries: list[RawScrapeSummary] = []
    try:
        targets = [
            (city_name, city_slug, action)
            for city_name, city_slug in city_targets
            for action in actions
        ]
        rate_limiter = RequestRateLimiter() if workers > 1 else None

        def scrape_target(
            target: tuple[str, str, str],
        ) -> tuple[str, str, RawSearchResult]:
            city_name, city_slug, action = target
            if page_range is not None:
                result = scrape_search_pages(
                    city_slug=city_slug,
                    transaction_type=action,
                    max_pages=max_pages,
                    rate_limiter=rate_limiter,
                    page_range=page_range,
                )
            else:
                result = scrape_search_pages(
                    city_slug=city_slug,
                    transaction_type=action,
                    max_pages=max_pages,
                    rate_limiter=rate_limiter,
                )
            return city_name, action, result

        log.info(
            "raw_pipeline_started",
            cities=len(city_targets),
            actions=actions,
            max_pages=settings.max_pages if max_pages is None else max_pages,
            city_range=city_range,
            page_range=page_range,
            workers=workers,
        )
        if workers == 1:
            results = map(scrape_target, targets)
            for city_name, action, result in results:
                _save_result(raw_store, summaries, city_name, action, result)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for city_name, action, result in executor.map(scrape_target, targets):
                    _save_result(raw_store, summaries, city_name, action, result)
    finally:
        raw_store.close()

    export_paths = export_raw_bundle()
    log.info("raw_pipeline_finished", exports=export_paths, runs=len(summaries))
    return summaries


def _save_result(
    raw_store: RawListingStore,
    summaries: list[RawScrapeSummary],
    city_name: str,
    action: str,
    result: RawSearchResult,
) -> None:
    raw_store.save_many(
        [dict(listing, city=city_name) for listing in result.listings]
    )
    summary = RawScrapeSummary(
        city=city_name,
        action=action,
        pages_scraped=result.pages_scraped,
        listings_scraped=len(result.listings),
        error=result.error,
    )
    summaries.append(summary)
    log.info(
        "raw_city_scrape_complete",
        city=summary.city,
        action=summary.action,
        pages_scraped=summary.pages_scraped,
        listings_scraped=summary.listings_scraped,
        error=summary.error,
    )
