from dataclasses import dataclass

from mubawab_scraper.browser.driver import chrome_driver
from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.scrapers.detail import enrich_listings
from mubawab_scraper.scrapers.search import scrape_search_pages
from mubawab_scraper.storage.csv_store import export
from mubawab_scraper.storage.sqlite_store import SQLiteStore
from mubawab_scraper.utils.urls import build_city_url

log = get_logger(__name__)


@dataclass
class CityScrapeSummary:
    city: str
    total_pages: int
    pages_scraped: int
    total_results: int
    listings_scraped: int


def run_pipeline(
    city: str,
    property_type: str,
    transaction: str,
    max_pages: int,
    headless: bool,
) -> list[CityScrapeSummary]:
    """Scrape and store the selected city, or every registered city when city='all'."""
    store = SQLiteStore(settings.db_path)
    registered_cities = store.get_all_villes()
    if city.lower() == "all":
        city_targets = [
            (
                item.get("name") or item.get("attrNameurl") or "",
                item.get("attrNameurl") or item.get("name") or "",
            )
            for item in registered_cities
        ]
        if not city_targets:
            store.close()
            raise ValueError("Aucune ville enregistrée. Exécutez d'abord le scraper des villes.")
    else:
        matching_city = next(
            (
                item
                for item in registered_cities
                if (item.get("attrNameurl") or "").casefold() == city.casefold()
                or (item.get("name") or "").casefold() == city.casefold()
            ),
            None,
        )
        city_targets = [
            (
                matching_city.get("name") or city if matching_city else city,
                matching_city.get("attrNameurl") or city if matching_city else city,
            )
        ]

    summaries: list[CityScrapeSummary] = []
    log.info(
        "pipeline_start",
        cities=len(city_targets),
        transaction=transaction,
        max_pages=max_pages,
    )

    try:
        with chrome_driver(headless=headless) as driver:
            for city_name, city_slug in city_targets:
                url = build_city_url(city_slug, transaction)

                result = scrape_search_pages(driver, url, max_pages=max_pages)
                enriched = enrich_listings(driver, result.listings)

                for listing in enriched:
                    listing.setdefault("city", city_name)
                    listing.setdefault("property_type", property_type)
                    listing.setdefault("transaction_type", transaction)
                    if listing.get("price") and listing.get("area_sqm"):
                        listing["price_per_sqm"] = round(
                            listing["price"] / listing["area_sqm"], 2
                        )

                store.save_many(enriched)
                store.save_scraping_metadata(
                    city_name,
                    transaction,
                    total_pages=result.total_pages,
                    total_results=result.total_results,
                    page_size=result.page_size,
                    pages_scraped=result.pages_scraped,
                )
                summary = CityScrapeSummary(
                    city=city_name,
                    total_pages=result.total_pages,
                    pages_scraped=result.pages_scraped,
                    total_results=result.total_results,
                    listings_scraped=len(enriched),
                )
                summaries.append(summary)
                log.info(
                    "city_scrape_complete",
                    city=summary.city,
                    total_pages=summary.total_pages,
                    pages_scraped=summary.pages_scraped,
                    total_results=summary.total_results,
                    listings_scraped=summary.listings_scraped,
                    url=url,
                )
    finally:
        store.close()

    export_path = export(fmt="csv")
    log.info("pipeline_end", export=export_path, cities=len(summaries))
    return summaries
