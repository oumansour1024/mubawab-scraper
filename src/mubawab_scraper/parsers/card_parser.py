from mubawab_scraper.parsers.helpers import (
    extract_id_from_url,
    extract_number,
    extract_price,
)

FEATURE_FIELDS = {
    "icon-triangle": "area_sqm",
    "icon-house-boxes": "rooms",
    "icon-bed": "bedrooms",
    "icon-bath": "bathrooms",
}


def parse_listing_card(card) -> dict | None:
    try:
        id_element = card.select_one("input.adId")
        title_element = card.select_one("h2.listingTit a, h2.title")
        price_element = card.select_one("span.priceTag, span.price")
        title = title_element.get_text(" ", strip=True) if title_element else None
        listing_id = id_element.get("value") if id_element else None
        price_text = price_element.get_text(" ", strip=True) if price_element else None
        listing_url = card.get("linkRef") or card.get("linkref")
        if not listing_url:
            link_element = card.select_one("a.linkref[href], h2 a[href]")
            listing_url = link_element.get("href") if link_element else None
        if listing_url and listing_url.startswith("/"):
            listing_url = f"https://www.mubawab.ma{listing_url}"

        if not listing_url:
            return None

        listing = {
            "listing_id": listing_id or extract_id_from_url(listing_url),
            "title": title,
            "price": extract_price(price_text),
            "url": listing_url,
            "is_promoted": bool(
                {"sPremium", "spotlightBox", "adBoostBox"} & set(card.get("class", []))
            ),
        }

        for feature in card.select(".adDetailFeature"):
            icon = feature.select_one("i[class]")
            value = feature.select_one("span")
            if not icon or not value:
                continue
            field = next(
                (field for icon_class, field in FEATURE_FIELDS.items()
                 if icon_class in icon.get("class", [])),
                None,
            )
            if field:
                parsed = extract_number(value.get_text(" ", strip=True))
                if parsed is not None:
                    listing[field] = int(parsed) if field != "area_sqm" else parsed

        location = card.select_one("span.listingH3")
        if location:
            location_parts = [
                part.strip() for part in location.get_text(" ", strip=True).split(",", 1)
            ]
            listing["neighbourhood"] = location_parts[0] or None

        image = card.select_one(
            "img.firstPicture[data-lazy], img.firstPicture[src], .photoMask img[data-lazy]"
        )
        if image:
            listing["image_url"] = image.get("data-lazy") or image.get("src")

        return listing
    except (AttributeError, KeyError, TypeError, ValueError):
        return None