import json
import sqlite3
from pathlib import Path
from threading import Barrier, BrokenBarrierError

from mubawab_scraper.models import PropertyDetail
from mubawab_scraper.parsers.card_parser_brut import parse_page
from mubawab_scraper.parsers.detail_parser import parse_detail_page
from mubawab_scraper.pipeline import orchestrator_brut
from mubawab_scraper.pipeline.orchestrator_brut import (
    _normalize_action,
    _resolve_cities,
)
from mubawab_scraper.scrapers import search_brut
from mubawab_scraper.scrapers.detail import (
    _read_rate_limit_response,
    build_raw_detail_url,
)
from mubawab_scraper.scrapers.search_brut import (
    RawSearchResult,
    build_page_url,
    scrape_search_pages,
)
from mubawab_scraper.storage.csv_store import export_raw, export_raw_details
from mubawab_scraper.storage.raw_store import RawListingStore
from mubawab_scraper.utils.rate_limit import RequestRateLimiter

LISTING_HTML = """
<div class="listingBox premium" linkref="/ad/123">
    <input class="adId" value="123">
    <h2 class="listingTit"><a>Appartement</a></h2>
    <span class="priceTag"><bdi>1 200 000</bdi></span>
    <span class="priceCurrency">DH</span>
    <span class="listingH3">Agadir</span>
    <div class="adDetailFeature"><span>80 m²</span></div>
    <div class="adFeatures"><div class="adFeature"><span>Garage</span></div></div>
    <p class="listingP">Texte brut de l'annonce</p>
    <img class="sliderImage firstPicture" src="image.jpg">
</div>
"""

DETAIL_HTML = """
<h1 class="searchTitle">Appartement à vendre</h1>
<div class="blockProp"><p>Première ligne<br>Deuxième ligne</p></div>
<div class="adMainFeature">
    <p class="adMainFeatureContentLabel">Type de bien</p>
    <p class="adMainFeatureContentValue">Appartement</p>
</div>
<div class="adMainFeature">
    <p class="adMainFeatureContentLabel">Surface de la parcelle</p>
    <p class="adMainFeatureContentValue">120 m²</p>
</div>
<input id="latField" value="30.42">
<input id="lngField" value="-9.6">
<input id="locationId" value="loc-1">
<div class="adDetails"><div class="adDetailFeature">
    <span>90 m²</span><span>3 Pièces</span><span>2 Chambres</span>
    <span>1 Salle de bain</span>
</div></div>
<h3 class="orangeTit"><bdi>900 000</bdi><span class="priceCurrency">DH</span></h3>
<div class="caractBlockProp"><div class="adFeature"><p>Garage</p></div></div>
<div class="picturesGallery">
    <img src="one.jpg"><img src="one.jpg"><img src="two.jpg">
</div>
<div class="flipsnap" numpics="5"></div>
<span class="businessName"><a href="/fr/agence/1">Agence test</a></span>
<div class="businessInfo"><img class="image" src="logo.jpg"></div>
<div class="refBox"><span>REF-42</span></div>
"""


def test_parse_page_keeps_raw_fields_and_city_context() -> None:
    rows = parse_page(
        LISTING_HTML,
        transaction_type="a-vendre",
        city="agadir",
        source_url="https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all",
    )

    assert rows == [
        {
            "ad_id": "123",
            "url": "/ad/123",
            "is_premium": True,
            "title": "Appartement",
            "price_raw": "1 200 000 DH",
            "location": "Agadir",
            "details": "80 m²",
            "features": "Garage",
            "description": "Texte brut de l'annonce",
            "image_url": "image.jpg",
            "card_text": "Appartement 1 200 000 DH Agadir 80 m² Garage Texte brut de l'annonce",
            "transaction_type": "a-vendre",
            "city": "agadir",
            "source_url": "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all",
        }
    ]


def test_parse_page_handles_xml_declaration_as_html() -> None:
    rows = parse_page(
        '<?xml version="1.0" encoding="UTF-8"?>' + LISTING_HTML,
        transaction_type="a-vendre",
        city="agadir",
        source_url="https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all",
    )

    assert len(rows) == 1
    assert rows[0]["ad_id"] == "123"


def test_build_page_url_uses_mubawab_page_route() -> None:
    assert build_page_url(
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all", 2
    ) == "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:2"


def test_raw_pipeline_scrapes_city_jobs_concurrently(monkeypatch) -> None:
    barrier = Barrier(2)
    scraped_cities = []
    persisted = []

    class FakeCityStore:
        def __init__(self, _path: str) -> None:
            pass

        def get_all_villes(self) -> list[dict[str, str]]:
            return [
                {"name": "Agadir", "attrNameurl": "agadir"},
                {"name": "Rabat", "attrNameurl": "rabat"},
            ]

        def close(self) -> None:
            pass

    class FakeRawStore:
        def __init__(self, _path: str) -> None:
            pass

        def save_many(self, rows) -> None:
            persisted.extend(rows)

        def close(self) -> None:
            pass

    def fake_scrape_search_pages(
        city_slug: str,
        transaction_type: str,
        max_pages: int | None,
        rate_limiter,
    ) -> RawSearchResult:
        assert transaction_type == "a-vendre"
        assert max_pages == 1
        assert rate_limiter is not None
        try:
            barrier.wait(timeout=2)
        except BrokenBarrierError as exc:
            raise AssertionError("city jobs were not started concurrently") from exc
        scraped_cities.append(city_slug)
        return RawSearchResult(
            listings=[{"ad_id": city_slug}],
            pages_scraped=1,
        )

    monkeypatch.setattr(orchestrator_brut, "SQLiteStore", FakeCityStore)
    monkeypatch.setattr(orchestrator_brut, "RawListingStore", FakeRawStore)
    monkeypatch.setattr(orchestrator_brut, "scrape_search_pages", fake_scrape_search_pages)
    monkeypatch.setattr(orchestrator_brut, "export_raw_bundle", lambda: [])

    summaries = orchestrator_brut.run_pipeline(
        "all",
        "a-vendre",
        max_pages=1,
        workers=2,
    )

    assert set(scraped_cities) == {"agadir", "rabat"}
    assert {summary.city for summary in summaries} == {"Agadir", "Rabat"}
    assert {row["city"] for row in persisted} == {"Agadir", "Rabat"}


def test_scrape_cli_accepts_workers_for_raw_orchestrator(monkeypatch) -> None:
    from typer.testing import CliRunner

    from mubawab_scraper import cli

    calls = []
    monkeypatch.setattr(
        cli,
        "run_pipeline_brut",
        lambda city, action, max_pages, workers: calls.append(workers) or [],
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "scrape",
            "--orchestrator",
            "brut",
            "--city",
            "agadir",
            "--action",
            "a-vendre",
            "--max-pages",
            "1",
            "--workers",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [2]


def test_fetch_respects_retry_after_on_http_429(monkeypatch) -> None:
    class FakeResponse:
        def __init__(
            self,
            status_code: int,
            text: str,
            headers: dict[str, str],
        ) -> None:
            self.status_code = status_code
            self.text = text
            self.headers = headers

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                import requests

                raise requests.HTTPError(f"HTTP {self.status_code}")

    class FakeSession:
        def __init__(self) -> None:
            self.responses = [
                FakeResponse(429, "", {"Retry-After": "7"}),
                FakeResponse(200, "ok", {}),
            ]

        def get(self, *args: object, **kwargs: object) -> FakeResponse:
            return self.responses.pop(0)

    waits = []
    monkeypatch.setattr(search_brut.time, "sleep", waits.append)

    assert search_brut.fetch("https://example.test", session=FakeSession()) == "ok"
    assert waits == [7.0]


def test_unlimited_search_visits_each_page_until_no_listings(monkeypatch) -> None:
    visited_urls = []

    def fake_fetch(url: str, session=None) -> str:
        visited_urls.append(url)
        return LISTING_HTML if not url.endswith(":p:3") else "<html></html>"

    monkeypatch.setattr(search_brut, "fetch", fake_fetch)
    monkeypatch.setattr(search_brut, "jittered_sleep", lambda: None)

    result = scrape_search_pages("agadir", "a-vendre", max_pages=0)

    assert result.pages_scraped == 2
    assert len(result.listings) == 2
    assert visited_urls == [
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:1",
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:2",
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:3",
    ]


def test_parallel_search_disables_conflicting_progress_bar(monkeypatch) -> None:
    progress_settings = []
    original_tqdm = search_brut.tqdm

    def capture_tqdm(*args, **kwargs):
        progress_settings.append(kwargs)
        return original_tqdm(*args, **kwargs)

    monkeypatch.setattr(search_brut, "tqdm", capture_tqdm)
    monkeypatch.setattr(search_brut, "fetch", lambda *_args, **_kwargs: LISTING_HTML)

    scrape_search_pages(
        "agadir",
        "a-vendre",
        max_pages=1,
        rate_limiter=RequestRateLimiter(min_s=0, max_s=0),
    )

    assert progress_settings[0]["disable"] is True


def test_raw_store_upserts_by_city_action_and_ad_id(tmp_path: Path) -> None:
    db_path = tmp_path / "raw.db"
    store = RawListingStore(str(db_path))
    try:
        record = parse_page(LISTING_HTML, "a-vendre", "agadir", "https://example.test")
        store.save_many(record)
        updated = {**record[0], "title": "Titre mis à jour"}
        store.save_many([updated])
    finally:
        store.close()

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT ad_id, title, city, transaction_type FROM raw_listings"
        ).fetchall()

    assert rows == [("123", "Titre mis à jour", "agadir", "a-vendre")]


def test_parse_detail_page_extracts_raw_values() -> None:
    detail = parse_detail_page(
        DETAIL_HTML,
        "123",
        "https://www.mubawab.ma/fr/a/123/example",
    )

    assert isinstance(detail, PropertyDetail)
    assert detail.title_full == "Appartement à vendre"
    assert detail.property_type == "Appartement"
    assert detail.land_surface_raw == "120 m²"
    assert detail.latitude == 30.42
    assert detail.longitude == -9.6
    assert detail.waze_url.endswith("30.42%2C-9.6&zoom=17")
    assert detail.surface_raw == "90 m²"
    assert detail.rooms_raw == "3 Pièces"
    assert detail.bedrooms_raw == "2 Chambres"
    assert detail.bathrooms_raw == "1 Salle de bain"
    assert detail.price_detail_raw == "900 000 DH"
    assert detail.images == ["one.jpg", "two.jpg"]
    assert detail.image_count == 5
    assert detail.agency_name == "Agence test"
    assert json.loads(detail.raw_json)["ad_id"] == "123"


def test_build_raw_detail_url_resolves_listing_routes() -> None:
    assert build_raw_detail_url("/fr/a/123/apartment", "123") == (
        "https://www.mubawab.ma/fr/a/123/apartment"
    )
    assert build_raw_detail_url("/a/123/apartment", "123") == (
        "https://www.mubawab.ma/fr/a/123/apartment"
    )


def test_detail_rate_limit_detection_does_not_require_retry_after() -> None:
    class FakeDriver:
        def get_log(self, log_type: str) -> list[dict[str, str]]:
            assert log_type == "performance"
            return [
                {
                    "message": json.dumps(
                        {
                            "message": {
                                "method": "Network.responseReceived",
                                "params": {
                                    "response": {
                                        "status": 429,
                                        "url": "https://www.mubawab.ma/fr/a/123",
                                        "headers": {},
                                    }
                                },
                            }
                        }
                    )
                }
            ]

    assert _read_rate_limit_response(
        FakeDriver(),
        "https://www.mubawab.ma/fr/a/123",
    ) == (True, None)


def test_detail_store_completes_only_scraped_listing(tmp_path: Path) -> None:
    store = RawListingStore(str(tmp_path / "details.db"))
    record = parse_page(
        LISTING_HTML,
        "a-vendre",
        "agadir",
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all",
    )
    try:
        store.save_many(record)
        assert len(store.get_pending_details()) == 1

        detail = parse_detail_page(
            DETAIL_HTML, "123", "https://www.mubawab.ma/fr/a/123/example"
        )
        store.save_detail(detail)
        assert store.get_pending_details() == []
        saved = store.conn.execute(
            "SELECT images_json, agency_name FROM raw_listing_details WHERE ad_id = ?",
            ("123",),
        ).fetchone()
        marked = store.conn.execute(
            "SELECT detail_scraped FROM raw_listings WHERE ad_id = ?",
            ("123",),
        ).fetchone()
    finally:
        store.close()

    assert json.loads(saved["images_json"]) == ["one.jpg", "two.jpg"]
    assert saved["agency_name"] == "Agence test"
    assert marked["detail_scraped"] == 1


def test_raw_store_migrates_existing_raw_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE raw_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_id TEXT NOT NULL,
                url TEXT NOT NULL,
                is_premium INTEGER NOT NULL,
                title TEXT NOT NULL,
                price_raw TEXT NOT NULL,
                location TEXT NOT NULL,
                details TEXT NOT NULL,
                features TEXT NOT NULL,
                description TEXT NOT NULL,
                image_url TEXT NOT NULL,
                card_text TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                city TEXT NOT NULL,
                source_url TEXT NOT NULL,
                UNIQUE (city, transaction_type, ad_id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO raw_listings (
                ad_id, url, is_premium, title, price_raw, location, details,
                features, description, image_url, card_text, transaction_type,
                city, source_url
            ) VALUES ('123', '/fr/a/123/item', 0, '', '', '', '', '', '', '', '',
                      'a-vendre', 'Agadir', 'https://example.test')
            """
        )

    store = RawListingStore(str(db_path))
    try:
        columns = {
            row["name"] for row in store.conn.execute("PRAGMA table_info(raw_listings)")
        }
        row = store.conn.execute(
            "SELECT detail_scraped, scraped_at FROM raw_listings WHERE ad_id = '123'"
        ).fetchone()
    finally:
        store.close()

    assert {"detail_scraped", "scraped_at"} <= columns
    assert row["detail_scraped"] == 0
    assert row["scraped_at"]


def test_raw_search_crawls_pages_without_a_browser(monkeypatch) -> None:
    visited_urls = []

    def fake_fetch(url: str, session=None) -> str:
        visited_urls.append(url)
        return LISTING_HTML if not url.endswith(":p:2") else "<html></html>"

    monkeypatch.setattr(search_brut, "fetch", fake_fetch)
    monkeypatch.setattr(search_brut, "jittered_sleep", lambda: None)

    result = scrape_search_pages("agadir", "a-vendre", max_pages=2)

    assert result.pages_scraped == 1
    assert len(result.listings) == 1
    assert len(visited_urls) == 2
    assert "immobilier-a-vendre-all" in visited_urls[0]
    assert visited_urls[0].endswith(":p:1")
    assert visited_urls[1].endswith(":p:2")


def test_export_raw_reads_the_separate_raw_table(
    tmp_path: Path, monkeypatch
) -> None:
    from mubawab_scraper.config import settings

    db_path = tmp_path / "raw.db"
    store = RawListingStore(str(db_path))
    try:
        store.save_many(
            parse_page(LISTING_HTML, "a-vendre", "agadir", "https://example.test")
        )
    finally:
        store.close()

    monkeypatch.setattr(settings, "db_path", str(db_path))
    monkeypatch.setattr(settings, "export_dir", str(tmp_path / "exports"))
    export_path = Path(export_raw(with_time=False))

    assert export_path.exists()
    assert "mubawab_raw_export_" in export_path.name
    assert "price_raw" in export_path.read_text(encoding="utf-8-sig")


def test_export_raw_details_writes_both_data_sets(
    tmp_path: Path, monkeypatch
) -> None:
    from mubawab_scraper.config import settings

    db_path = tmp_path / "details.db"
    store = RawListingStore(str(db_path))
    try:
        store.save_many(
            parse_page(LISTING_HTML, "a-vendre", "agadir", "https://example.test")
        )
        store.save_detail(
            parse_detail_page(
                DETAIL_HTML,
                "123",
                "https://www.mubawab.ma/fr/a/123/example",
            )
        )
    finally:
        store.close()

    monkeypatch.setattr(settings, "db_path", str(db_path))
    monkeypatch.setattr(settings, "export_dir", str(tmp_path / "exports"))
    paths = [Path(path) for path in export_raw_details(with_time=False)]

    assert len(paths) == 2
    assert all(path.exists() for path in paths)
    assert "title_full" in paths[1].read_text(encoding="utf-8-sig")


def test_city_and_action_aliases_are_generalized() -> None:
    assert _normalize_action("vente") == "a-vendre"
    assert _normalize_action("vacances") == "vacational"
    assert _resolve_cities(
        "all",
        [
            {"name": "Agadir", "attrNameurl": "agadir"},
            {"name": "Fès", "attrNameurl": "fes"},
        ],
    ) == [("Agadir", "agadir"), ("Fès", "fes")]
