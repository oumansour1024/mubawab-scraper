"""Data models used for preserving raw scraped listing fields."""

from pydantic import BaseModel


class RawListing(BaseModel):
    ad_id: str
    url: str
    is_premium: bool
    title: str
    price_raw: str
    location: str
    details: str
    features: str
    description: str
    image_url: str
    card_text: str
    transaction_type: str
    city: str
    source_url: str
