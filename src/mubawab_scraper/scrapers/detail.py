
import time
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.parsers.detail_parser import parse_detail
from mubawab_scraper.utils.rate_limit import jittered_sleep
from mubawab_scraper.utils.retry import selenium_retry

log = get_logger(__name__)


# Sélecteurs de la page détail Mubawab (du plus fiable au plus permissif)
DETAIL_READY_SELECTORS = (
    "div.adDetails, "
    "div.propertyDescription, "
    "p.listingP.descLi, "
    "h1.listingTit, "
    "meta[property='og:title']"
)


class EnrichStats:
    """Compteur de progression pour enrich_listings."""
    def __init__(self, total: int) -> None:
        self.total = total
        self.ok = 0
        self.skipped = 0
        self.failed = 0
        self.start_ts = time.monotonic()

    def tick(self, status: str, url: str = "") -> None:
        if status == "ok":
            self.ok += 1
        elif status == "skipped":
            self.skipped += 1
        else:
            self.failed += 1

    @property
    def done(self) -> int:
        return self.ok + self.failed + self.skipped

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_ts

    @property
    def eta(self) -> float:
        if self.done == 0:
            return 0.0
        rate = self.done / self.elapsed
        return (self.total - self.done) / rate if rate else 0.0

    def as_dict(self) -> dict:
        return {
            "ok": self.ok, "skipped": self.skipped, "failed": self.failed,
            "done": self.done, "total": self.total,
            "elapsed_s": round(self.elapsed, 1),
            "eta_s": round(self.eta, 1),
        }


def _is_same_domain(url: str, base: str = "mubawab.ma") -> bool:
    return base in urlparse(url).netloc


def _is_listing_url(url: str) -> bool:
    """Vérifie que l'URL correspond bien à une annonce ou promotion."""
    return any(f"/fr/{kind}/" in url for kind in ("a", "pa", "p"))


def _page_is_404(driver) -> bool:
    """Détecte une page 404 via le titre ou l'URL de redirection."""
    try:
        title = driver.title.lower()
        if "404" in title or "introuvable" in title or "not found" in title:
            return True
        cur = driver.current_url.lower()
        if "404" in cur or "error" in cur:
            return True
    except Exception:
        pass
    return False


@selenium_retry
def _load_detail_page(driver, url: str, timeout: int = 12) -> str:
    """
    Charge une page détail et attend qu'un sélecteur clé apparaisse.
    Lève une exception si échec (→ retry via tenacity).
    """
    driver.get(url)
    WebDriverWait(driver, timeout).until(
        expected_conditions.presence_of_element_located(
            (By.CSS_SELECTOR, DETAIL_READY_SELECTORS)
        )
    )
    return driver.page_source


def enrich_listings(
    driver,
    listings: list[dict],
    *,
    skip_enriched: bool = True,
    save_errors: bool = True,
    error_dir: str = "data/raw/enrich_errors",
    rate_limit: tuple[float, float] = (1.0, 2.5),
) -> list[dict]:
    """
    Enrichit chaque annonce avec les données de la page détail.

    Args:
        driver        : instance Selenium
        listings      : liste de dict (chacun doit avoir 'url')
        skip_enriched : ignore les dicts ayant déjà 'description' non vide
        save_errors   : sauvegarde le HTML des pages en échec pour debug
        error_dir     : répertoire des dumps d'erreur
        rate_limit    : (min_delay, max_delay) entre chaque page

    Returns:
        La même liste, mutée en place, avec les champs détail ajoutés
        + '_enrich_status' ('ok'|'failed'|'skipped'|'invalid_url')
    """
    stats = EnrichStats(total=len(listings))
    error_path = Path(error_dir)
    if save_errors:
        error_path.mkdir(parents=True, exist_ok=True)

    log.info("enrich_start", total=len(listings))

    for i, lst in enumerate(listings, 1):
        url = lst.get("url")

        # --- Cas 1 : URL manquante ou invalide ---
        if not url:
            lst["_enrich_status"] = "invalid_url"
            stats.tick("failed", "")
            log.warning("enrich_no_url", idx=i, listing_id=lst.get("listing_id"))
            continue

        if not _is_same_domain(url) or not _is_listing_url(url):
            lst["_enrich_status"] = "invalid_url"
            stats.tick("failed", url)
            log.warning("enrich_bad_url", idx=i, url=url)
            continue

        # --- Cas 2 : déjà enrichi (idempotence) ---
        if skip_enriched and lst.get("description"):
            lst["_enrich_status"] = "skipped"
            stats.tick("skipped", url)
            continue

        # --- Cas 3 : chargement + parsing ---
        try:
            html = _load_detail_page(driver, url)

            if _page_is_404(driver):
                lst["_enrich_status"] = "not_found"
                stats.tick("failed", url)
                log.warning("enrich_404", idx=i, url=url)
                continue

            soup = BeautifulSoup(html, "lxml")
            detail = parse_detail(soup)

            # Ne pas écraser par du vide
            for k, v in detail.items():
                if v not in (None, "", [], {}):
                    lst[k] = v

            lst["_enrich_status"] = "ok"
            stats.tick("ok", url)

        except (TimeoutException, NoSuchWindowException) as e:
            lst["_enrich_status"] = "failed"
            stats.tick("failed", url)
            log.warning("enrich_timeout", idx=i, url=url, err=type(e).__name__)
            if save_errors:
                _dump_error(driver, error_path, lst.get("listing_id"), "timeout")

        except WebDriverException as e:
            lst["_enrich_status"] = "failed"
            stats.tick("failed", url)
            log.error("enrich_driver", idx=i, url=url, err=str(e)[:200])

        except Exception as e:
            lst["_enrich_status"] = "failed"
            stats.tick("failed", url)
            log.warning(
                "enrich_failed", idx=i, url=url,
                err_type=type(e).__name__, err=str(e)[:200],
            )
            if save_errors:
                _dump_error(driver, error_path, lst.get("listing_id"), "exception")

        # --- Progression ---
        if i % 10 == 0 or i == len(listings):
            log.info("enrich_progress", **stats.as_dict())

        # --- Rate limit ---
        jittered_sleep(*rate_limit)

    log.info("enrich_done", **stats.as_dict())
    return listings


def _dump_error(driver, out_dir: Path, listing_id: str | None, kind: str) -> None:
    """Sauvegarde le HTML courant pour debug."""
    try:
        name = f"{listing_id or 'unknown'}_{kind}.html"
        path = out_dir / name
        path.write_text(driver.page_source, encoding="utf-8")
        log.debug("error_dump_saved", path=str(path))
    except Exception:
        pass