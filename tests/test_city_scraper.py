import sqlite3
from contextlib import closing
from pathlib import Path

from bs4 import BeautifulSoup

from mubawab_scraper.parsers.card_parser import parse_listing_card
from mubawab_scraper.parsers.detail_parser import parse_detail
from mubawab_scraper.parsers.pagination_parser import parse_pagination
from mubawab_scraper.scrapers import detail as detail_scraper
from mubawab_scraper.scrapers import search
from mubawab_scraper.storage.sqlite_store import SQLiteStore
from mubawab_scraper.utils.urls import build_city_url


def _page(page: int, listing_id: int) -> str:
    return f"""
    <div id="ads">
        <input id="currentPage" value="{page}" />
        <input id="totalElements" value="3" />
        <input id="pageSize" value="1" />
        <span id="lastPageSpan">3</span>
    </div>
    <div id="adList">
        <div class="listingBox" linkRef="https://www.mubawab.ma/fr/pa/{listing_id}/test">
            <input class="adId" value="{listing_id}" />
            <h2 class="listingTit"><a href="https://www.mubawab.ma/fr/pa/{listing_id}/test">
                Appartement de test
            </a></h2>
            <span class="priceTag">1 250 000 DH</span>
            <div class="adDetailFeature"><span>88m²</span></div>
        </div>
    </div>
    """


class FakeDriver:
    def __init__(self) -> None:
        self.page_source = ""
        self.visited_urls: list[str] = []

    def get(self, url: str) -> None:
        self.visited_urls.append(url)
        page = int(url.rsplit(":p:", 1)[1])
        self.page_source = _page(page, 100 + page)


def test_build_city_url_encodes_slug_and_supports_actions() -> None:
    assert build_city_url("béni-mellal", "a-vendre") == (
        "https://www.mubawab.ma/fr/ct/b%C3%A9ni-mellal/immobilier-a-vendre-all"
    )
    assert build_city_url("agadir", "a-louer-all") == (
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-louer-all"
    )
    assert build_city_url("b%C3%A9ni-mellal") == (
        "https://www.mubawab.ma/fr/ct/b%C3%A9ni-mellal/immobilier-a-vendre-all"
    )


def test_pagination_reads_total_results_and_calculates_pages() -> None:
    soup = BeautifulSoup(_page(1, 101), "lxml")

    pagination = parse_pagination(soup, "agadir")

    assert pagination is not None
    assert pagination.current_page == 1
    assert pagination.total_pages == 3
    assert pagination.total_elements == 3
    assert pagination.page_size == 1


def test_pagination_reads_site_metadata_values() -> None:
    html = """
    <div id="ads">
        <input id="currentPage" value="1" />
        <input id="totalElements" value="532" />
        <input id="pageSize" value="32" />
        <span id="lastPageSpan">17</span>
    </div>
    """

    pagination = parse_pagination(BeautifulSoup(html, "lxml"), "kénitra")

    assert pagination is not None
    assert pagination.total_pages == 17
    assert pagination.total_elements == 532
    assert pagination.page_size == 32


def test_card_parser_matches_live_card_markup() -> None:
    soup = BeautifulSoup(_page(1, 101), "lxml")

    listing = parse_listing_card(soup.select_one(".listingBox"))

    assert listing == {
        "listing_id": "101",
        "title": "Appartement de test",
        "price": 1_250_000,
        "area_sqm": 88.0,
        "url": "https://www.mubawab.ma/fr/pa/101/test",
    }


def test_detail_parser_reads_current_mubawab_detail_markup() -> None:
    html = """
    <html>
        <head>
            <meta name="description" content="Description de l'annonce">
        </head>
        <body>
            <div class="disFlex adDetails">
                <div class="adDetailFeature"><span>240m²</span></div>
            </div>
            <div class="agency-info">
                <span class="link businessName">
                    <a href="/fr/b/12770/agadir-living">AGADIR LIVING</a>
                </span>
            </div>
        </body>
    </html>
    """

    detail = parse_detail(BeautifulSoup(html, "lxml"))

    assert detail["description"] == "Description de l'annonce"
    assert detail["agency_name"] == "AGADIR LIVING"


def test_enrichment_waits_for_current_detail_page_marker(monkeypatch) -> None:
    html = """
    <html>
        <head><meta name="description" content="Description de l'annonce"></head>
        <body><div class="adDetails"></div></body>
    </html>
    """

    class DetailDriver:
        page_source = html

        def get(self, url: str) -> None:
            self.url = url

    requested_selectors: list[str] = []

    def fake_wait(_driver, selector: str, timeout: int) -> None:
        requested_selectors.append(selector)
        assert timeout == 10

    monkeypatch.setattr(detail_scraper, "wait_for_selector", fake_wait)
    monkeypatch.setattr(detail_scraper, "jittered_sleep", lambda *_args: None)
    listing = {"url": "https://www.mubawab.ma/fr/a/123/test"}

    result = detail_scraper.enrich_listings(DetailDriver(), [listing])

    assert requested_selectors == ["div.adDetails, meta[name='description']"]
    assert result[0]["description"] == "Description de l'annonce"


def test_parsed_city_listing_is_saved_to_sqlite(tmp_path: Path) -> None:
    soup = BeautifulSoup(_page(1, 101), "lxml")
    listing = parse_listing_card(soup.select_one(".listingBox"))
    assert listing is not None
    listing.update(
        city="Agadir",
        property_type="all",
        transaction_type="a-vendre",
    )
    db_path = tmp_path / "mubawab.db"
    store = SQLiteStore(str(db_path))
    try:
        store.save_many([listing])
    finally:
        store.close()

    with closing(sqlite3.connect(db_path)) as conn:
        saved = conn.execute(
            """
            SELECT listing_id, title, price, area_sqm, url, city,
                   property_type, transaction_type
            FROM listings
            """
        ).fetchone()

    assert saved == (
        "101",
        "Appartement de test",
        1_250_000,
        88.0,
        "https://www.mubawab.ma/fr/pa/101/test",
        "Agadir",
        "all",
        "a-vendre",
    )


def test_scraping_metadata_saves_pagination_values(tmp_path: Path) -> None:
    db_path = tmp_path / "mubawab.db"
    store = SQLiteStore(str(db_path))
    try:
        store.save_scraping_metadata(
            "Kénitra",
            "a-vendre",
            total_pages=17,
            total_results=532,
            page_size=32,
            pages_scraped=17,
        )
        store.save_scraping_metadata(
            "Kénitra",
            "a-vendre",
            total_pages=18,
            total_results=550,
            page_size=32,
            pages_scraped=10,
        )
    finally:
        store.close()

    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT city, transaction_type, total_pages, total_results,
                   page_size, pages_scraped
            FROM scraping_metadata
            """
        ).fetchall()

    assert rows == [("Kénitra", "a-vendre", 18, 550, 32, 10)]


def test_scraper_reports_total_and_scrapes_up_to_page_limit(monkeypatch) -> None:
    monkeypatch.setattr(search, "wait_for_id", lambda *_args: None)
    monkeypatch.setattr(search, "jittered_sleep", lambda *_args: None)
    driver = FakeDriver()

    result = search.scrape_search_pages(
        driver, "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all", max_pages=2
    )

    assert result.total_pages == 3
    assert result.total_results == 3
    assert result.page_size == 1
    assert result.pages_scraped == 2
    assert len(result.listings) == 2
    assert driver.visited_urls == [
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:1",
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:2",
    ]
