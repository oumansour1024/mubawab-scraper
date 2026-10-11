import sqlite3
from contextlib import closing
from pathlib import Path

from mubawab_scraper.scrapers.search_ville_url import parse_footer_listing_links
from mubawab_scraper.models import Ville
from mubawab_scraper.storage.sqlite_store import SQLiteStore


HTML = """
<div id="footerListingLinks">
    <a href="https://www.mubawab.ma/fr/t/casablanca">Immobilier Casablanca</a>
    <a href="https://www.mubawab.ma/fr/t/marrakech">Immobilier Marrakech</a>
</div>
"""


def test_parse_footer_listing_links() -> None:
    assert parse_footer_listing_links(HTML) == [
        Ville(
            name="Casablanca",
            url="https://www.mubawab.ma/fr/t/casablanca",
            link="https://www.mubawab.ma/fr/t/casablanca",
            attrNameurl="casablanca",
        ),
        Ville(
            name="Marrakech",
            url="https://www.mubawab.ma/fr/t/marrakech",
            link="https://www.mubawab.ma/fr/t/marrakech",
            attrNameurl="marrakech",
        ),
    ]


def test_city_attribute_decodes_slug_without_changing_url() -> None:
    html = """
    <div id="footerListingLinks">
        <a href="https://www.mubawab.ma/fr/t/k%C3%A9nitra">Immobilier Kenitra</a>
    </div>
    """

    ville = parse_footer_listing_links(html)[0]

    assert ville.attrNameurl == "kénitra"
    assert ville.url == "https://www.mubawab.ma/fr/t/k%C3%A9nitra"
    assert ville.link == ville.url


def test_save_villes_persists_city_links(tmp_path: Path) -> None:
    db_path = tmp_path / "mubawab.db"
    villes = parse_footer_listing_links(HTML)
    store = SQLiteStore(str(db_path))
    try:
        store.save_villes(villes)
        assert store.get_all_villes() == [
            {"name": "Casablanca", "attrNameurl": "casablanca"},
            {"name": "Marrakech", "attrNameurl": "marrakech"},
        ]
        store.save_villes(
            [
                Ville(
                    name="Fès",
                    url=villes[0].url,
                    link=villes[0].url,
                    attrNameurl="fes",
                )
            ]
        )
    finally:
        store.close()

    with closing(sqlite3.connect(db_path)) as conn:
        saved = conn.execute(
            "SELECT name, url, link, attrNameurl FROM villes ORDER BY id"
        ).fetchall()

    assert saved == [
        ("Fès", villes[0].url, villes[0].url, "fes"),
        ("Marrakech", villes[1].url, villes[1].url, "marrakech"),
    ]


def test_existing_villes_table_gets_attr_name_url_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE villes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                link TEXT NOT NULL
            )
            """
        )

    store = SQLiteStore(str(db_path))
    try:
        columns = {
            row[1] for row in store.conn.execute("PRAGMA table_info(villes)")
        }
    finally:
        store.close()

    assert "attrNameurl" in columns
