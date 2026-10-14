from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

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
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Ville(BaseModel):
    name: str
    url: str
    link: str
    attrNameurl: str | None = None


class PropertyDetail(BaseModel):
    """Raw values extracted from a Mubawab listing detail page."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    ad_id: str
    url: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    title_full: str = ""
    description_full: str = ""
    property_type: str = ""
    land_surface_raw: str = ""
    condition_raw: str = ""
    age_raw: str = ""
    orientation_raw: str = ""
    floor_type_raw: str = ""
    num_floors_raw: str = ""
    latitude: float | None = None
    longitude: float | None = None
    location_id: str = ""
    waze_url: str = ""
    surface_raw: str = ""
    rooms_raw: str = ""
    bedrooms_raw: str = ""
    bathrooms_raw: str = ""
    price_detail_raw: str = ""
    features_full: str = ""
    images: list[str] = Field(default_factory=list)
    image_count: int = 0
    agency_name: str = ""
    agency_url: str = ""
    agency_logo: str = ""
    agency_ref: str = ""
    raw_json: str = ""