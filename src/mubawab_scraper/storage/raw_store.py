"""SQLite storage for the unnormalized listing-card records."""

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mubawab_scraper.models import PropertyDetail
from mubawab_scraper.storage.raw_models import RawListing

RAW_LISTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_listings (
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
    scraped_at TEXT DEFAULT (datetime('now')),
    detail_scraped INTEGER NOT NULL DEFAULT 0,
    UNIQUE (city, transaction_type, ad_id)
);
"""

RAW_LISTING_DETAILS_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_listing_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    title_full TEXT,
    description_full TEXT,
    property_type TEXT,
    land_surface_raw TEXT,
    condition_raw TEXT,
    age_raw TEXT,
    orientation_raw TEXT,
    floor_type_raw TEXT,
    num_floors_raw TEXT,
    latitude REAL,
    longitude REAL,
    location_id TEXT,
    waze_url TEXT,
    surface_raw TEXT,
    rooms_raw TEXT,
    bedrooms_raw TEXT,
    bathrooms_raw TEXT,
    price_detail_raw TEXT,
    features_full TEXT,
    images_json TEXT,
    image_count INTEGER NOT NULL DEFAULT 0,
    agency_name TEXT,
    agency_url TEXT,
    agency_logo TEXT,
    agency_ref TEXT,
    raw_json TEXT,
    scraped_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_listing_details_ad_id
    ON raw_listing_details(ad_id);
"""


class RawListingStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            f"{RAW_LISTINGS_SCHEMA}\n{RAW_LISTING_DETAILS_SCHEMA}"
        )
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(raw_listings)")
        }
        if "detail_scraped" not in columns:
            self.conn.execute(
                "ALTER TABLE raw_listings ADD COLUMN detail_scraped "
                "INTEGER NOT NULL DEFAULT 0"
            )
        if "scraped_at" not in columns:
            self.conn.execute("ALTER TABLE raw_listings ADD COLUMN scraped_at TEXT")
            self.conn.execute(
                "UPDATE raw_listings SET scraped_at = datetime('now') "
                "WHERE scraped_at IS NULL"
            )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_listings_ad_id "
            "ON raw_listings(ad_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_listings_transaction "
            "ON raw_listings(transaction_type)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_listings_detail_scraped "
            "ON raw_listings(detail_scraped)"
        )
        self.conn.commit()

    def save_many(
        self,
        listings: Sequence[RawListing | Mapping[str, Any]],
    ) -> None:
        records = [
            listing
            if isinstance(listing, RawListing)
            else RawListing.model_validate(listing)
            for listing in listings
        ]
        self.conn.executemany(
            """
            INSERT INTO raw_listings (
                ad_id, url, is_premium, title, price_raw, location, details,
                features, description, image_url, card_text, transaction_type,
                city, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(city, transaction_type, ad_id) DO UPDATE SET
                url = excluded.url,
                is_premium = excluded.is_premium,
                title = excluded.title,
                price_raw = excluded.price_raw,
                location = excluded.location,
                details = excluded.details,
                features = excluded.features,
                description = excluded.description,
                image_url = excluded.image_url,
                card_text = excluded.card_text,
                source_url = excluded.source_url
            """,
            [
                (
                    listing.ad_id,
                    listing.url,
                    listing.is_premium,
                    listing.title,
                    listing.price_raw,
                    listing.location,
                    listing.details,
                    listing.features,
                    listing.description,
                    listing.image_url,
                    listing.card_text,
                    listing.transaction_type,
                    listing.city,
                    listing.source_url,
                )
                for listing in records
            ],
        )
        self.conn.execute(
            """
            UPDATE raw_listings
            SET detail_scraped = 1
            WHERE detail_scraped = 0
              AND EXISTS (
                  SELECT 1 FROM raw_listing_details d
                  WHERE d.ad_id = raw_listings.ad_id
              )
            """
        )
        self.conn.commit()

    def get_pending_details(
        self,
        transaction_type: str | Sequence[str] | None = None,
        city: str | None = None,
        limit: int = 0,
    ) -> list[dict[str, str]]:
        if limit < 0:
            raise ValueError("limit must be zero (unlimited) or a positive integer")
        query = """
            SELECT ad_id, url, city, transaction_type
            FROM raw_listings
            WHERE detail_scraped = 0
              AND url IS NOT NULL AND url != ''
              AND NOT EXISTS (
                  SELECT 1 FROM raw_listing_details d
                  WHERE d.ad_id = raw_listings.ad_id
              )
        """
        params: list[str | int] = []
        if transaction_type:
            actions = (
                [transaction_type]
                if isinstance(transaction_type, str)
                else list(transaction_type)
            )
            placeholders = ", ".join("?" for _ in actions)
            query += f" AND transaction_type IN ({placeholders})"
            params.extend(actions)
        if city:
            query += " AND city = ? COLLATE NOCASE"
            params.append(city)
        query += " GROUP BY ad_id ORDER BY MIN(id)"
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        return [
            dict(row)
            for row in self.conn.execute(query, params).fetchall()
        ]

    def save_detail(self, detail: PropertyDetail) -> None:
        self.save_details([detail])

    def save_details(self, details: Sequence[PropertyDetail]) -> None:
        if not details:
            return

        columns = (
            "ad_id", "url", "title_full", "description_full", "property_type",
            "land_surface_raw", "condition_raw", "age_raw", "orientation_raw",
            "floor_type_raw", "num_floors_raw", "latitude", "longitude",
            "location_id", "waze_url", "surface_raw", "rooms_raw", "bedrooms_raw",
            "bathrooms_raw", "price_detail_raw", "features_full", "images_json",
            "image_count", "agency_name", "agency_url", "agency_logo", "agency_ref",
            "raw_json", "scraped_at",
        )
        updates = ", ".join(
            f"{column} = excluded.{column}" for column in columns if column != "ad_id"
        )
        sql = (
            f"""
            INSERT INTO raw_listing_details ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            ON CONFLICT(ad_id) DO UPDATE SET {updates}
            """
        )
        rows = []
        for detail in details:
            data = detail.model_dump(mode="json")
            values = {**data}
            values["images_json"] = json.dumps(
                values.pop("images"),
                ensure_ascii=False,
            )
            values["scraped_at"] = detail.scraped_at.isoformat()
            rows.append(tuple(values.get(column) for column in columns))

        self.conn.executemany(sql, rows)
        self.conn.executemany(
            "UPDATE raw_listings SET detail_scraped = 1 WHERE ad_id = ?",
            [(detail.ad_id,) for detail in details],
        )
        self.conn.commit()

    def count_raw_listings(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM raw_listings").fetchone()
        return int(row["n"])

    def close(self) -> None:
        self.conn.close()
