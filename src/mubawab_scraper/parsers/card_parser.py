from mubawab_scraper.parsers.helpers import (
    extract_price, extract_number, extract_id_from_url,
)


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

        area = None
        for feature in card.select(".adDetailFeature span, span.area"):
            area_text = feature.get_text(" ", strip=True)
            if "m²" in area_text or "m2" in area_text.lower():
                area = extract_number(area_text)
                break

        if not listing_url:
            return None

        return {
            "listing_id": listing_id or extract_id_from_url(listing_url),
            "title": title,
            "price": extract_price(price_text),
            "area_sqm": area,
            "url": listing_url,
        }
    except (AttributeError, KeyError, TypeError, ValueError):
        return None