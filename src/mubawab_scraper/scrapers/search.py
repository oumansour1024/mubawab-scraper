from dataclasses import dataclass

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException

from mubawab_scraper.browser.waits import wait_for_id
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.parsers.card_parser import parse_listing_card
from mubawab_scraper.parsers.pagination_parser import parse_pagination
from mubawab_scraper.utils.rate_limit import jittered_sleep
from mubawab_scraper.utils.retry import selenium_retry

log = get_logger(__name__)


@selenium_retry
def _navigate_to_search_page(driver, url: str) -> None:
    driver.get(url)


@dataclass
class SearchScrapeResult:
    listings: list[dict]
    total_pages: int
    total_results: int
    page_size: int
    pages_scraped: int


def scrape_search_pages(
    driver, base_url: str, max_pages: int = 10
) -> SearchScrapeResult:
    all_listings: list[dict] = []
    seen_listings: set[str] = set()
    total_pages = 0
    total_results = 0
    pages_scraped = 0

    _navigate_to_search_page(driver, f"{base_url}:p:1")
    try:
        wait_for_id(driver, "adList")
    except TimeoutException:
        log.info("no_listings_found", page=1)
        return SearchScrapeResult([], 0, 0, 0, 0)

    soup = BeautifulSoup(driver.page_source, "lxml")
    pagination = parse_pagination(soup, base_url)
    cards = soup.select("#adList .listingBox")
    if not cards:
        return SearchScrapeResult([], 0, 0, 0, 0)

    total_pages = pagination.total_pages if pagination else 1
    total_results = pagination.total_elements if pagination else len(cards)
    page_size = pagination.page_size if pagination else len(cards)
    pages_to_scrape = min(total_pages, max_pages) if max_pages > 0 else total_pages

    for page in range(1, pages_to_scrape + 1):
        if page == 1:
            page_soup = soup
        else:
            try:
                _navigate_to_search_page(driver, f"{base_url}:p:{page}")
                wait_for_id(driver, "adList")
            except TimeoutException:
                log.info("page_unavailable", page=page)
                break
            except WebDriverException as exc:
                log.warning(
                    "page_navigation_failed",
                    page=page,
                    err_type=type(exc).__name__,
                    err=str(exc)[:200],
                )
                break
            page_soup = BeautifulSoup(driver.page_source, "lxml")

        cards = page_soup.select("#adList .listingBox")
        if not cards:
            break

        for card in cards:
            if listing := parse_listing_card(card):
                key = listing.get("listing_id") or listing["url"]
                if key not in seen_listings:
                    seen_listings.add(key)
                    all_listings.append(listing)

        pages_scraped += 1
        log.info("page_scraped", page=page, n=len(cards))
        if page < pages_to_scrape:
            jittered_sleep()

    return SearchScrapeResult(
        listings=all_listings,
        total_pages=total_pages,
        total_results=total_results,
        page_size=page_size,
        pages_scraped=pages_scraped,
    )