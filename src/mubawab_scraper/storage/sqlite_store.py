import json
import sqlite3
from pathlib import Path

from mubawab_scraper.models import Ville

SCHEMA = Path(__file__).parent / "schemas.sql"

class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        self._migrate_villes_schema()
        self._migrate_scraping_metadata_schema()
        self.conn.commit()

    def _migrate_villes_schema(self) -> None:
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(villes)")
        }
        if "attrNameurl" not in columns:
            self.conn.execute("ALTER TABLE villes ADD COLUMN attrNameurl TEXT")

    def _migrate_scraping_metadata_schema(self) -> None:
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(scraping_metadata)")
        }
        for column in ("total_pages", "total_results", "page_size", "pages_scraped"):
            if column not in columns:
                self.conn.execute(
                    f"ALTER TABLE scraping_metadata ADD COLUMN {column} INTEGER"
                )

    def save_many(self, listings: list[dict]) -> None:
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO listings
            (listing_id, title, price, price_per_sqm, area_sqm, rooms,
             bedrooms, bathrooms, property_type, transaction_type, city,
             neighbourhood, url, image_url, description, agency_name,
             latitude, longitude, amenities, is_promoted)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    listing.get("listing_id"),
                    listing.get("title"),
                    listing.get("price"),
                    listing.get("price_per_sqm"),
                    listing.get("area_sqm"),
                    listing.get("rooms"),
                    listing.get("bedrooms"),
                    listing.get("bathrooms"),
                    listing.get("property_type"),
                    listing.get("transaction_type"),
                    listing.get("city"),
                    listing.get("neighbourhood"),
                    listing.get("url"),
                    listing.get("image_url"),
                    listing.get("description"),
                    listing.get("agency_name"),
                    listing.get("latitude"),
                    listing.get("longitude"),
                    json.dumps(listing.get("amenities", []), ensure_ascii=False),
                    listing.get("is_promoted", False),
                )
                for listing in listings
            ],
        )
        self.conn.commit()

    def save_villes(self, villes: list[Ville]) -> None:
        self.conn.executemany(
            """
            INSERT INTO villes (name, url, link, attrNameurl)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                name = excluded.name,
                link = excluded.link,
                attrNameurl = excluded.attrNameurl
            """,
            [(ville.name, ville.url, ville.link, ville.attrNameurl) for ville in villes],
        )
        self.conn.commit()

    def save_scraping_metadata(
        self,
        city: str,
        transaction_type: str,
        total_pages: int,
        total_results: int,
        page_size: int,
        pages_scraped: int,
    ) -> None:
        values = (total_pages, total_results, page_size, pages_scraped)
        cursor = self.conn.execute(
            """
            UPDATE scraping_metadata
            SET total_pages = ?, total_results = ?, page_size = ?,
                pages_scraped = ?, last_scraped_at = CURRENT_TIMESTAMP
            WHERE city = ? AND transaction_type = ?
            """,
            (*values, city, transaction_type),
        )
        if cursor.rowcount == 0:
            self.conn.execute(
                """
                INSERT INTO scraping_metadata
                    (city, transaction_type, total_pages, total_results,
                     page_size, pages_scraped)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (city, transaction_type, *values),
            )
        self.conn.commit()

    def get_all_villes(self) -> list[dict[str, str | None]]:
        cursor = self.conn.execute("""
            SELECT name, attrNameurl FROM villes ORDER BY name;
        """)
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        self.conn.close()