"""Parse listing cards while retaining their unnormalized text values."""

from bs4 import BeautifulSoup
from bs4.element import Tag

from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.storage.raw_models import RawListing

log = get_logger(__name__)


def extract_raw_fields(box: Tag) -> dict[str, str | bool]:
    """Extract the raw values from one Mubawab listing card."""
    ad_id_el = box.select_one("input.adId")
    ad_id = str(ad_id_el.get("value") or "") if ad_id_el else ""
    url = str(box.get("linkref") or "")
    is_premium = "premium" in box.get("class", [])

    title_el = box.select_one("h2.listingTit a")
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = box.select_one("span.priceTag bdi") or box.select_one(
        "h3.orangeTit bdi"
    )
    currency_el = box.select_one("span.priceCurrency")
    price_raw = price_el.get_text(strip=True) if price_el else ""
    if price_raw and currency_el:
        price_raw += " " + currency_el.get_text(strip=True)

    location_el = box.select_one("span.listingH3")
    details = [
        detail.get_text(strip=True)
        for detail in box.select("div.adDetailFeature span")
    ]
    features = [
        feature.get_text(strip=True)
        for feature in box.select("div.adFeatures div.adFeature span")
    ]
    description_el = box.select_one("p.listingP")
    image_el = box.select_one("img.sliderImage.firstPicture") or box.select_one(
        "img.sliderImage"
    )

    return {
        "ad_id": ad_id,
        "url": url,
        "is_premium": is_premium,
        "title": title,
        "price_raw": price_raw,
        "location": location_el.get_text(strip=True) if location_el else "",
        "details": " | ".join(details),
        "features": " | ".join(features),
        "description": (
            description_el.get_text(" ", strip=True) if description_el else ""
        ),
        "image_url": str(image_el.get("src") or "") if image_el else "",
        "card_text": box.get_text(" ", strip=True),
    }


def parse_page(
    html: str,
    transaction_type: str,
    city: str,
    source_url: str,
) -> list[dict[str, str | bool]]:
    """Return raw records for valid listing cards found on a page."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str | bool]] = []
    for box in soup.select("div.listingBox"):
        try:
            fields = extract_raw_fields(box)
            if not fields["ad_id"]:
                continue
            rows.append(
                RawListing(
                    **fields,
                    transaction_type=transaction_type,
                    city=city,
                    source_url=source_url,
                ).model_dump()
            )
        except (TypeError, ValueError) as exc:
            log.warning("raw_listing_card_parse_failed", error=str(exc))
    return rows
