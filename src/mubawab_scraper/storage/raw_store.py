"""SQLite storage for the unnormalized listing-card records."""

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

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
    UNIQUE (city, transaction_type, ad_id)
);
"""


class RawListingStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(RAW_LISTINGS_SCHEMA)
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
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
