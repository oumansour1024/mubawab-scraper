"""Convenience entry point for the generalized raw HTTP scraping pipeline."""

from mubawab_scraper.parsers.card_parser_brut import (
    extract_raw_fields,
    parse_page as _parse_page,
)
from mubawab_scraper.pipeline.orchestrator_brut import run_pipeline
from mubawab_scraper.scrapers.search_brut import (
    build_page_url,
    fetch,
    scrape_search_pages,
)
from mubawab_scraper.utils.urls import ACTION_ALIASES, normalize_city_action

TRANSACTION_ALIASES = {
    **ACTION_ALIASES,
    "vente": "a-vendre",
    "location": "a-louer",
    "vacances": "vacational",
}


def parse_page(
    html: str,
    transaction_type: str,
    source_url: str,
    city: str = "agadir",
) -> list[dict[str, str | bool]]:
    """Keep the original three-argument parser call compatible."""
    return _parse_page(html, transaction_type, city, source_url)


def scrape_transaction(
    transaction_type: str,
    city: str = "agadir",
    max_pages: int | None = None,
) -> list[dict[str, str | bool]]:
    """Fetch raw listings for one transaction and city."""
    action = TRANSACTION_ALIASES.get(
        transaction_type.strip().lower(), transaction_type.strip().lower()
    )
    action = normalize_city_action(action)
    return scrape_search_pages(
        city_slug=city,
        transaction_type=action,
        max_pages=max_pages,
    ).listings


def main(
    city: str = "all",
    transaction: str = "all",
    max_pages: int | None = None,
) -> None:
    """Run the raw scraper for a city/action selection."""
    summaries = run_pipeline(city, transaction, max_pages)
    print("\n" + "=" * 50)
    print("RÉSUMÉ FINAL (stockage brut)")
    print("=" * 50)
    for summary in summaries:
        print(
            f"  {summary.city:16s} {summary.action:12s} : "
            f"{summary.listings_scraped} lignes / "
            f"{summary.pages_scraped} pages"
        )
    print("=" * 50)


if __name__ == "__main__":
    main()
