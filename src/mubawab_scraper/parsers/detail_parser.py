import json
from contextlib import suppress
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from mubawab_scraper.models import PropertyDetail


def _value(element: Tag | None) -> str:
    return str(element.get("value") or "") if element else ""


def _coordinate(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def parse_detail_page(html: str, ad_id: str, url: str) -> PropertyDetail:
    """Parse unnormalized listing detail values from a Mubawab page."""
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one("h1.searchTitle")
    description_el = soup.select_one("div.blockProp > p")

    general: dict[str, Any] = {
        "property_type": "",
        "land_surface_raw": "",
        "condition_raw": "",
        "age_raw": "",
        "orientation_raw": "",
        "floor_type_raw": "",
        "num_floors_raw": "",
    }
    labels = {
        "Type de bien": "property_type",
        "Surface de la parcelle": "land_surface_raw",
        "Etat": "condition_raw",
        "État": "condition_raw",
        "Années": "age_raw",
        "Orientation": "orientation_raw",
        "Type du sol": "floor_type_raw",
        "Nombre d'étages": "num_floors_raw",
    }
    for feature in soup.select("div.adMainFeature"):
        label_el = feature.select_one("p.adMainFeatureContentLabel")
        value_el = feature.select_one("p.adMainFeatureContentValue")
        if label_el is None or value_el is None:
            continue
        field_name = labels.get(label_el.get_text(strip=True))
        if field_name:
            general[field_name] = value_el.get_text(strip=True)

    latitude = _coordinate(_value(soup.select_one("input#latField")))
    longitude = _coordinate(_value(soup.select_one("input#lngField")))
    location_id = _value(soup.select_one("input#locationId"))
    waze_url = (
        f"https://waze.com/ul?ll={latitude}%2C{longitude}&zoom=17"
        if latitude is not None and longitude is not None
        else ""
    )

    composition: dict[str, Any] = {
        "surface_raw": "",
        "rooms_raw": "",
        "bedrooms_raw": "",
        "bathrooms_raw": "",
    }
    for element in soup.select("div.adDetails div.adDetailFeature span"):
        text = element.get_text(strip=True)
        lower_text = text.casefold()
        if ("m²" in text or "m2" in lower_text) and not composition["surface_raw"]:
            composition["surface_raw"] = text
        elif "pièce" in lower_text and not composition["rooms_raw"]:
            composition["rooms_raw"] = text
        elif (
            "chambre" in lower_text
            and "salle" not in lower_text
            and not composition["bedrooms_raw"]
        ):
            composition["bedrooms_raw"] = text
        elif "salle" in lower_text and "bain" in lower_text and not composition["bathrooms_raw"]:
            composition["bathrooms_raw"] = text

    price_el = soup.select_one("h3.orangeTit bdi")
    currency_el = soup.select_one("h3.orangeTit span.priceCurrency")
    price_detail_raw = price_el.get_text(strip=True) if price_el else ""
    if price_detail_raw and currency_el:
        price_detail_raw += " " + currency_el.get_text(strip=True)

    features = [
        element.get_text(strip=True)
        for element in soup.select("div.caractBlockProp div.adFeature p")
        if element.get_text(strip=True)
    ]
    images = list(
        dict.fromkeys(
            str(image.get("src"))
            for image in soup.select("div.picturesGallery img[src]")
            if image.get("src")
        )
    )
    image_count = len(images)
    gallery = soup.select_one("div.flipsnap[numpics]")
    if gallery:
        with suppress(TypeError, ValueError):
            image_count = int(str(gallery.get("numpics")))

    agency_el = soup.select_one("span.businessName a")
    logo_el = soup.select_one("div.businessInfo img.image")
    ref_el = soup.select_one("div.refBox > span")
    detail = PropertyDetail(
        ad_id=ad_id,
        url=url,
        title_full=title_el.get_text(strip=True) if title_el else "",
        description_full=(description_el.get_text("\n", strip=True) if description_el else ""),
        **general,
        latitude=latitude,
        longitude=longitude,
        location_id=location_id,
        waze_url=waze_url,
        **composition,
        price_detail_raw=price_detail_raw,
        features_full=" | ".join(features),
        images=images,
        image_count=image_count,
        agency_name=agency_el.get_text(strip=True) if agency_el else "",
        agency_url=str(agency_el.get("href") or "") if agency_el else "",
        agency_logo=str(logo_el.get("src") or "") if logo_el else "",
        agency_ref=ref_el.get_text(strip=True) if ref_el else "",
    )
    detail.raw_json = json.dumps(
        detail.model_dump(mode="json", exclude={"raw_json"}),
        ensure_ascii=False,
    )
    return detail


def parse_detail(soup: Any) -> dict[str, Any]:
    """Extract optional normalized detail fields from a parsed HTML document."""
    detail: dict[str, Any] = {}

    desc = soup.select_one("div.propertyDescription, div.description, p.listingP.descLi")
    description_meta = soup.select_one("meta[name='description']")
    detail["description"] = (
        desc.get_text(" ", strip=True)
        if desc
        else description_meta.get("content")
        if description_meta
        else None
    )

    agency = soup.select_one("span.agencyName, div.agency, span.businessName a, span.businessName")
    detail["agency_name"] = agency.get_text(" ", strip=True) if agency else None

    map_el = soup.select_one("[data-latitude][data-longitude]")
    if map_el:
        try:
            detail["latitude"] = float(map_el["data-latitude"])
            detail["longitude"] = float(map_el["data-longitude"])
        except ValueError, KeyError:
            pass

    detail["amenities"] = [
        el.get_text(strip=True)
        for el in soup.select("ul.amenities li, div.features span, div.adFeature span.fSize11")
    ]
    return detail
