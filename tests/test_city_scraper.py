import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from mubawab_scraper.parsers.card_parser import parse_listing_card
from mubawab_scraper.parsers.detail_parser import parse_detail
from mubawab_scraper.parsers.pagination_parser import parse_pagination
from mubawab_scraper.pipeline import orchestrator
from mubawab_scraper.scrapers import detail as detail_scraper
from mubawab_scraper.scrapers import search
from mubawab_scraper.storage.sqlite_store import SQLiteStore
from mubawab_scraper.utils.urls import build_city_url, normalize_city_action


def _page(page: int, listing_id: int) -> str:
    return f"""
    <div id="ads">
        <input id="currentPage" value="{page}" />
        <input id="totalElements" value="3" />
        <input id="pageSize" value="1" />
        <span id="lastPageSpan">3</span>
    </div>
    <div id="adList">
        <div class="listingBox sPremium" linkRef="https://www.mubawab.ma/fr/pa/{listing_id}/test">
            <input class="adId" value="{listing_id}" />
            <h2 class="listingTit"><a href="https://www.mubawab.ma/fr/pa/{listing_id}/test">
                Appartement de test
            </a></h2>
            <span class="priceTag">1 250 000 DH</span>
            <span class="listingH3">Maarif, Casablanca</span>
            <div class="adDetailFeature">
                <i class="icon-triangle"></i><span>88m²</span>
            </div>
            <div class="adDetailFeature">
                <i class="icon-house-boxes"></i><span>4 Pièces</span>
            </div>
            <div class="adDetailFeature">
                <i class="icon-bed"></i><span>2 Chambres</span>
            </div>
            <div class="adDetailFeature">
                <i class="icon-bath"></i><span>1 Salle de bains</span>
            </div>
            <img class="firstPicture" data-lazy="https://images.example/test.avif" />
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
    assert normalize_city_action("a-louer-all") == "a-louer"


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
        "rooms": 4,
        "bedrooms": 2,
        "bathrooms": 1,
        "neighbourhood": "Maarif",
        "image_url": "https://images.example/test.avif",
        "is_promoted": True,
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


def test_enrichment_accepts_premium_ad_url(monkeypatch) -> None:
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

    monkeypatch.setattr(detail_scraper, "_load_detail_page", lambda _driver, _url: html)
    monkeypatch.setattr(detail_scraper, "jittered_sleep", lambda *_args: None)
    listing = {"url": "https://www.mubawab.ma/fr/pa/123/test"}

    result = detail_scraper.enrich_listings(DetailDriver(), [listing])

    assert result[0]["description"] == "Description de l'annonce"
    assert result[0]["_enrich_status"] == "ok"


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


def test_save_many_updates_existing_listing_without_erasing_details(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mubawab.db"
    store = SQLiteStore(str(db_path))
    url = "https://www.mubawab.ma/fr/pa/101/test"
    try:
        store.save_many(
            [
                {
                    "listing_id": "101",
                    "title": "Appartement",
                    "price": 1_250_000,
                    "url": url,
                    "city": "Agadir",
                }
            ]
        )
        store.save_many(
            [
                {
                    "listing_id": "101",
                    "title": "Appartement rénové",
                    "url": url,
                    "description": "Détails enrichis",
                    "amenities": ["Piscine"],
                }
            ]
        )
        store.save_many(
            [{"listing_id": "101", "url": url, "amenities": []}]
        )
    finally:
        store.close()

    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT COUNT(*), title, price, city, description, amenities
            FROM listings
            WHERE url = ?
            """,
            (url,),
        ).fetchone()

    assert rows == (
        1,
        "Appartement rénové",
        1_250_000,
        "Agadir",
        "Détails enrichis",
        '["Piscine"]',
    )


def test_save_many_upserts_by_listing_id_when_url_changes(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "mubawab.db"))
    try:
        store.save_many(
            [
                {
                    "listing_id": "101",
                    "title": "Appartement",
                    "url": "https://www.mubawab.ma/fr/pa/101/ancien-titre",
                }
            ]
        )
        store.save_many(
            [
                {
                    "listing_id": "101",
                    "title": "Nouveau titre",
                    "url": "https://www.mubawab.ma/fr/pa/101/nouveau-titre",
                },
                {
                    "listing_id": "102",
                    "title": "Autre annonce",
                    "url": "https://www.mubawab.ma/fr/pa/102/autre-annonce",
                },
                {
                    "listing_id": "102",
                    "title": "Titre actualisé",
                    "url": "https://www.mubawab.ma/fr/pa/102/autre-titre",
                },
            ]
        )
    finally:
        store.close()

    with closing(sqlite3.connect(tmp_path / "mubawab.db")) as conn:
        rows = conn.execute(
            "SELECT listing_id, title, url FROM listings ORDER BY listing_id"
        ).fetchall()

    assert rows == [
        (
            "101",
            "Nouveau titre",
            "https://www.mubawab.ma/fr/pa/101/nouveau-titre",
        ),
        (
            "102",
            "Titre actualisé",
            "https://www.mubawab.ma/fr/pa/102/autre-titre",
        ),
    ]


def test_city_urls_are_never_saved_as_listings(tmp_path: Path) -> None:
    db_path = tmp_path / "mubawab.db"
    store = SQLiteStore(str(db_path))
    try:
        store.save_many(
            [
                {
                    "city": "Casablanca",
                    "url": "https://www.mubawab.ma/fr/t/casablanca",
                },
                {
                    "listing_id": "101",
                    "title": "Appartement de test",
                    "url": "https://www.mubawab.ma/fr/pa/101/test",
                },
            ]
        )
    finally:
        store.close()

    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute("SELECT listing_id, url FROM listings").fetchall()

    assert rows == [("101", "https://www.mubawab.ma/fr/pa/101/test")]


def test_remove_existing_polluted_city_url_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "mubawab.db"
    store = SQLiteStore(str(db_path))
    try:
        store.conn.execute(
            """
            INSERT INTO listings (city, url)
            VALUES (?, ?)
            """,
            ("Casablanca", "https://www.mubawab.ma/fr/t/casablanca"),
        )
        store.conn.execute(
            """
            INSERT INTO listings (listing_id, title, url)
            VALUES (?, ?, ?)
            """,
            ("101", "Annonce", "https://www.mubawab.ma/fr/pa/101/test"),
        )
        store.conn.commit()

        removed_count = store.remove_city_urls_from_listings()
    finally:
        store.close()

    with closing(sqlite3.connect(db_path)) as conn:
        remaining = conn.execute("SELECT listing_id, url FROM listings").fetchall()

    assert removed_count == 1
    assert remaining == [("101", "https://www.mubawab.ma/fr/pa/101/test")]


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


def test_pipeline_runs_each_action_and_saves_each_action_metadata(monkeypatch) -> None:
    store = MagicMock()
    store.get_all_villes.return_value = [
        {"name": "Kénitra", "attrNameurl": "kénitra"}
    ]
    driver = object()
    scrape_result = SimpleNamespace(
        listings=[],
        total_pages=17,
        total_results=532,
        page_size=32,
        pages_scraped=1,
    )
    monkeypatch.setattr(orchestrator, "SQLiteStore", lambda _path: store)

    class DriverContext:
        def __enter__(self):
            return driver

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(orchestrator, "chrome_driver", lambda **_kwargs: DriverContext())
    monkeypatch.setattr(
        orchestrator, "scrape_search_pages", lambda *_args, **_kwargs: scrape_result
    )
    monkeypatch.setattr(
        orchestrator, "enrich_listings", lambda _driver, listings: listings
    )
    monkeypatch.setattr(orchestrator, "export", lambda **_kwargs: "export.csv")

    summaries = orchestrator.run_pipeline(
        "all", "all", "all", max_pages=1, headless=True
    )

    assert [summary.action for summary in summaries] == [
        "a-vendre",
        "a-louer",
        "vacational",
    ]
    assert [summary.total_pages for summary in summaries] == [17, 17, 17]
    assert store.save_scraping_metadata.call_args_list == [
        call(
            "Kénitra",
            action,
            total_pages=17,
            total_results=532,
            page_size=32,
            pages_scraped=1,
        )
        for action in ("a-vendre", "a-louer", "vacational")
    ]


def test_pipeline_continues_after_search_navigation_error(monkeypatch) -> None:
    store = MagicMock()
    store.get_all_villes.return_value = [
        {"name": "Kénitra", "attrNameurl": "kénitra"}
    ]
    scrape_result = SimpleNamespace(
        listings=[],
        total_pages=1,
        total_results=0,
        page_size=0,
        pages_scraped=0,
    )
    monkeypatch.setattr(orchestrator, "SQLiteStore", lambda _path: store)

    class DriverContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(orchestrator, "chrome_driver", lambda **_kwargs: DriverContext())

    def scrape(_driver, url, **_kwargs):
        if "immobilier-a-vendre-all" in url:
            raise WebDriverException("net::ERR_NAME_NOT_RESOLVED")
        return scrape_result

    monkeypatch.setattr(orchestrator, "scrape_search_pages", scrape)
    monkeypatch.setattr(
        orchestrator, "enrich_listings", lambda _driver, listings: listings
    )
    monkeypatch.setattr(orchestrator, "export", lambda **_kwargs: "export.csv")

    summaries = orchestrator.run_pipeline(
        "all", "all", "all", max_pages=1, headless=True
    )

    assert [summary.action for summary in summaries] == [
        "a-vendre",
        "a-louer",
        "vacational",
    ]
    assert "ERR_NAME_NOT_RESOLVED" in summaries[0].error
    assert summaries[1].error is None
    assert summaries[2].error is None
    assert store.save_scraping_metadata.call_count == 2


def test_pipeline_rejects_property_filter_not_supported_by_city_url() -> None:
    try:
        orchestrator.run_pipeline(
            "casablanca", "appartements", "a-vendre", max_pages=1, headless=True
        )
    except ValueError as exc:
        assert "tous les types de biens" in str(exc)
    else:
        raise AssertionError("Expected unsupported property filter to be rejected")
