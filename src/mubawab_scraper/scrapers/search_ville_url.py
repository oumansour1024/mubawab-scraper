import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from mubawab_scraper.browser.waits import wait_for_id
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.models import Ville

log = get_logger(__name__)


def _normalize_city_name(raw_name: str) -> str:
    cleaned = re.sub(r"^\s*Immobilier\s+", "", raw_name, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _extract_city_name(url: str, text: str) -> str:
    text_name = _normalize_city_name(text)
    if text_name:
        return text_name

    try:
        segments = [segment for segment in urlparse(url).path.split("/") if segment]
        for index, segment in enumerate(segments):
            if segment in {"t", "ct"} and index + 1 < len(segments):
                city_slug = unquote(segments[index + 1])
                if city_slug and city_slug not in {"immobilier-a-louer"}:
                    return city_slug.replace("-", " ").replace("_", " ").title()
    except Exception:
        pass

    return text_name

def extract_city_attr_name_from_url(url: str) -> str | None:
    try:
        segments = [segment for segment in urlparse(url).path.split("/") if segment]
        for index, segment in enumerate(segments):
            if segment in {"t", "ct"} and index + 1 < len(segments):
                city_slug = segments[index + 1]
                if city_slug and city_slug not in {"immobilier-a-louer"}:
                    return unquote(city_slug)
    except Exception:
        pass

    return None


def parse_footer_listing_links(html: str) -> list[Ville]:
    soup = BeautifulSoup(html, "lxml")
    footer = soup.select_one("#footerListingLinks")
    if footer is None:
        return []

    cities: list[Ville] = []
    seen: set[tuple[str, str, str]] = set()

    for link in footer.select("a[href]"):
        url = (link.get("href") or "").strip()
        if not url or url.startswith("javascript:"):
            continue

        city_name = _extract_city_name(url, link.get_text(" ", strip=True))
        attrNameurl = extract_city_attr_name_from_url(url)
        if not city_name:
            continue

        entry = Ville(name=city_name, url=url, link=url,attrNameurl=attrNameurl)
        key = (city_name, url, attrNameurl)
        if key in seen:
            continue
        seen.add(key)
        cities.append(entry)

    return cities


def get_url_ville(driver, base_url: str, max_pages: int = 1) -> list[Ville]:
    all_cities: list[Ville] = []

    driver.get(base_url)
    try:
        wait_for_id(driver, "footerListingLinks", timeout=20)
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script(
                "return document.querySelectorAll('#footerListingLinks a[href]').length > 0"
            )
        )
    except Exception:
        log.info("no_listings found")
        return all_cities

    return parse_footer_listing_links(driver.page_source)
