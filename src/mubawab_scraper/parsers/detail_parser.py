def parse_detail(soup) -> dict:
    detail: dict = {}

    desc = soup.select_one(
        "div.propertyDescription, div.description, p.listingP.descLi"
    )
    description_meta = soup.select_one("meta[name='description']")
    detail["description"] = (
        desc.get_text(" ", strip=True)
        if desc
        else description_meta.get("content")
        if description_meta
        else None
    )

    agency = soup.select_one(
        "span.agencyName, div.agency, span.businessName a, span.businessName"
    )
    detail["agency_name"] = agency.get_text(" ", strip=True) if agency else None

    map_el = soup.select_one("[data-latitude][data-longitude]")
    if map_el:
        try:
            detail["latitude"] = float(map_el["data-latitude"])
            detail["longitude"] = float(map_el["data-longitude"])
        except (ValueError, KeyError):
            pass

    detail["amenities"] = [
        el.get_text(strip=True)
        for el in soup.select(
            "ul.amenities li, div.features span, div.adFeature span.fSize11"
        )
    ]
    return detail