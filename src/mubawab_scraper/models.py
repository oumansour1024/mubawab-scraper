from datetime import datetime
from pydantic import BaseModel, Field

class Listing(BaseModel):
    listing_id: str | None = None
    title: str | None = None
    price: int | None = None
    price_per_sqm: float | None = None
    area_sqm: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    property_type: str | None = None
    transaction_type: str | None = None
    city: str | None = None
    neighbourhood: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    agency_name: str | None = None
    description: str | None = None
    amenities: list[str] = Field(default_factory=list)
    image_url: str | None = None
    url: str
    is_promoted: bool = False
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class Ville(BaseModel):
    name: str
    url: str
    link: str
    attrNameurl: str | None = None