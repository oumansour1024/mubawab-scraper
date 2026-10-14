"""Orchestrate the raw HTTP scraper across registered cities and actions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from mubawab_scraper.config import settings
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

RAW_ACTION_ALIASES = {
    **ACTION_ALIASES,
    "vente": "a-vendre",
    "location": "a-louer",
    "vacances": "vacational",
}


@dataclass
class RawScrapeSummary:
    city: str
    action: str
    pages_scraped: int
    listings_scraped: int
    error: str | None = None


def _normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    normalized = RAW_ACTION_ALIASES.get(normalized, normalized)
    return normalize_city_action(normalized)


def _resolve_cities(
    city: str,
    registered_cities: list[dict[str, str | None]],
) -> list[tuple[str, str]]:
    if city.strip().lower() == "all":
        city_targets = [
            (
                item.get("name") or item.get("attrNameurl") or "",
                item.get("attrNameurl") or item.get("name") or "",
            )
            for item in registered_cities
        ]
        city_targets = [(name, slug) for name, slug in city_targets if slug]
        if not city_targets:
            raise ValueError(
                "Aucune ville enregistrée. Exécutez d'abord le scraper des villes."
            )
        return city_targets

    matching_city = next(
        (
            item
            for item in registered_cities
            if (item.get("attrNameurl") or "").casefold() == city.casefold()
            or (item.get("name") or "").casefold() == city.casefold()
        ),
        None,
    )
    if matching_city:
        return [
            (
                matching_city.get("name") or city,
                matching_city.get("attrNameurl") or city,
            )
        ]
    return [(city, city)]


def run_pipeline(
    city: str,
    transaction: str,
    max_pages: int | None = None,
    workers: int = 1,
) -> list[RawScrapeSummary]:
    """Scrape one/all cities and one/all actions into the raw listings table."""
    if not 1 <= workers <= MAX_RAW_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_RAW_WORKERS}")

    city_store = SQLiteStore(settings.db_path)
    try:
        city_targets = _resolve_cities(city, city_store.get_all_villes())
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
