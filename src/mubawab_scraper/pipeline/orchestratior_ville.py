from mubawab_scraper.browser.driver import chrome_driver
from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.models import Ville
from mubawab_scraper.scrapers.search_ville_url import get_url_ville
from mubawab_scraper.storage.csv_store import export_villes
from mubawab_scraper.storage.sqlite_store import SQLiteStore
from mubawab_scraper.utils.urls import build_search_url

log = get_logger(__name__)


def run_pipeline(
    city: str,
    transaction: str,
    headless: bool,
) -> list[Ville]:
    """Collect city names and URLs from the search page footer."""
    url = build_search_url(city, transaction)
    log.info("pipeline_start", url=url)
    store = SQLiteStore(settings.db_path)

    try:
        with chrome_driver(headless=headless) as driver:
            villes = get_url_ville(driver, url)

        store.save_villes(villes)
        log.info("cities_collected", n=len(villes))
    finally:
        store.close()

    export_path = export_villes()
    log.info("cities_exported", path=export_path)
    log.info("pipeline_end", url=url)
    return villes
