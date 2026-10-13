import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

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
        ad_listings = [
            listing
            for listing in listings
            if not self._is_city_url(listing.get("url"))
        ]
        self.conn.executemany(
            """
            INSERT INTO listings
            (listing_id, title, price, price_per_sqm, area_sqm, rooms,
             bedrooms, bathrooms, property_type, transaction_type, city,
             neighbourhood, url, image_url, description, agency_name,
             latitude, longitude, amenities, is_promoted)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET
                listing_id = COALESCE(excluded.listing_id, listings.listing_id),
                title = COALESCE(excluded.title, listings.title),
                price = COALESCE(excluded.price, listings.price),
                price_per_sqm = COALESCE(excluded.price_per_sqm, listings.price_per_sqm),
                area_sqm = COALESCE(excluded.area_sqm, listings.area_sqm),
                rooms = COALESCE(excluded.rooms, listings.rooms),
                bedrooms = COALESCE(excluded.bedrooms, listings.bedrooms),
                bathrooms = COALESCE(excluded.bathrooms, listings.bathrooms),
                property_type = COALESCE(excluded.property_type, listings.property_type),
                transaction_type = COALESCE(excluded.transaction_type, listings.transaction_type),
                city = COALESCE(excluded.city, listings.city),
                neighbourhood = COALESCE(excluded.neighbourhood, listings.neighbourhood),
                image_url = COALESCE(excluded.image_url, listings.image_url),
                description = COALESCE(excluded.description, listings.description),
                agency_name = COALESCE(excluded.agency_name, listings.agency_name),
                latitude = COALESCE(excluded.latitude, listings.latitude),
                longitude = COALESCE(excluded.longitude, listings.longitude),
                amenities = CASE
                    WHEN excluded.amenities = '[]' THEN listings.amenities
                    ELSE excluded.amenities
                END,
                is_promoted = excluded.is_promoted,
                scraped_at = CURRENT_TIMESTAMP
            ON CONFLICT(listing_id) DO UPDATE SET
                url = COALESCE(excluded.url, listings.url),
                title = COALESCE(excluded.title, listings.title),
                price = COALESCE(excluded.price, listings.price),
                price_per_sqm = COALESCE(excluded.price_per_sqm, listings.price_per_sqm),
                area_sqm = COALESCE(excluded.area_sqm, listings.area_sqm),
                rooms = COALESCE(excluded.rooms, listings.rooms),
                bedrooms = COALESCE(excluded.bedrooms, listings.bedrooms),
                bathrooms = COALESCE(excluded.bathrooms, listings.bathrooms),
                property_type = COALESCE(excluded.property_type, listings.property_type),
                transaction_type = COALESCE(excluded.transaction_type, listings.transaction_type),
                city = COALESCE(excluded.city, listings.city),
                neighbourhood = COALESCE(excluded.neighbourhood, listings.neighbourhood),
                image_url = COALESCE(excluded.image_url, listings.image_url),
                description = COALESCE(excluded.description, listings.description),
                agency_name = COALESCE(excluded.agency_name, listings.agency_name),
                latitude = COALESCE(excluded.latitude, listings.latitude),
                longitude = COALESCE(excluded.longitude, listings.longitude),
                amenities = CASE
                    WHEN excluded.amenities = '[]' THEN listings.amenities
                    ELSE excluded.amenities
                END,
                is_promoted = excluded.is_promoted,
                scraped_at = CURRENT_TIMESTAMP
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
                for listing in ad_listings
            ],
        )
        self.conn.commit()

    @staticmethod
    def _is_city_url(url: str | None) -> bool:
        if not url:
            return False
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        return len(path_parts) >= 3 and path_parts[0:2] == ["fr", "t"]

    def remove_city_urls_from_listings(self) -> int:
        cursor = self.conn.execute(
            """
            DELETE FROM listings
            WHERE url IS NOT NULL
              AND listing_id IS NULL
              AND title IS NULL
              AND url LIKE '%/fr/t/%'
            """
        )
        self.conn.commit()
        return cursor.rowcount

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