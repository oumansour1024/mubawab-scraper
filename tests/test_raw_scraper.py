import sqlite3
from pathlib import Path

from mubawab_scraper.parsers.card_parser_brut import parse_page
from mubawab_scraper.pipeline.orchestrator_brut import (
    _normalize_action,
    _resolve_cities,
)
from mubawab_scraper.scrapers import search_brut
from mubawab_scraper.scrapers.search_brut import build_page_url, scrape_search_pages
from mubawab_scraper.storage.csv_store import export_raw
from mubawab_scraper.storage.raw_store import RawListingStore


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
            "card_text": "123 Appartement 1 200 000 DH Agadir 80 m² Garage Texte brut de l'annonce",
            "transaction_type": "a-vendre",
            "city": "agadir",
            "source_url": "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all",
        }
    ]


def test_build_page_url_uses_mubawab_page_route() -> None:
    assert build_page_url(
        "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all", 2
    ) == "https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all:p:2"


def test_unlimited_search_visits_each_page_until_no_listings(monkeypatch) -> None:
    visited_urls = []

    def fake_fetch(url: str) -> str:
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


def test_raw_search_crawls_pages_without_a_browser(monkeypatch) -> None:
    visited_urls = []

    def fake_fetch(url: str) -> str:
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
