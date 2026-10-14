from contextlib import contextmanager
from threading import Event

import pytest

from mubawab_scraper.config import settings
from mubawab_scraper.models import PropertyDetail
from mubawab_scraper.parsers.card_parser_brut import parse_page
from mubawab_scraper.pipeline import detail_pipeline
from mubawab_scraper.scrapers.detail import RateLimitedPageError
from mubawab_scraper.storage.raw_store import RawListingStore
from mubawab_scraper.utils.rate_limit import RequestRateLimiter

LISTING_TEMPLATE = """
<div class="listingBox" linkref="/fr/a/{ad_id}">
    <input class="adId" value="{ad_id}">
    <h2 class="listingTit"><a>Appartement</a></h2>
    <span class="listingH3">Agadir</span>
</div>
"""


def _seed_listings(db_path: str, ad_ids: list[str]) -> None:
    store = RawListingStore(db_path)
    try:
        records = []
        for ad_id in ad_ids:
            records.extend(
                parse_page(
                    LISTING_TEMPLATE.format(ad_id=ad_id),
                    "a-vendre",
                    "agadir",
                    "https://example.test",
                )
            )
        store.save_many(records)
    finally:
        store.close()


def test_rate_limiter_stops_waiting_when_cancelled() -> None:
    limiter = RequestRateLimiter(min_s=0, max_s=0)
    stop_event = Event()
    stop_event.set()

    assert limiter.wait(stop_event) is False


def test_pipeline_saves_successes_and_stops_after_first_429(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    db_path = str(tmp_path / "raw.db")
    _seed_listings(db_path, ["123", "456"])
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(detail_pipeline, "export_raw_details", lambda fmt: [])
    monkeypatch.setattr(RequestRateLimiter, "wait", lambda self, event=None: True)

    @contextmanager
    def fake_driver(**kwargs):
        assert kwargs["performance_logging"] is True
        yield object()

    monkeypatch.setattr(detail_pipeline, "chrome_driver", fake_driver)
    success_ready = Event()

    def fake_scrape_detail(
        driver,
        url: str,
        ad_id: str,
        *,
        rate_limiter,
        stop_event,
    ) -> PropertyDetail:
        if ad_id == "456":
            success_ready.set()
            raise RateLimitedPageError(url, "30")
        assert success_ready.wait(timeout=2)
        return PropertyDetail(ad_id=ad_id, url=url)

    monkeypatch.setattr(detail_pipeline, "scrape_detail", fake_scrape_detail)

    summary = detail_pipeline.run_detail_pipeline(workers=2)

    assert summary.urls_found == 2
    assert summary.details_scraped == 1
    assert summary.rate_limited is True
    assert summary.retry_after == "30"

    store = RawListingStore(db_path)
    try:
        pending = store.get_pending_details()
        assert [listing["ad_id"] for listing in pending] == ["456"]
    finally:
        store.close()


@pytest.mark.parametrize("workers", [0, 3])
def test_pipeline_rejects_worker_counts_outside_safe_range(workers: int) -> None:
    with pytest.raises(ValueError, match="workers must be between 1 and 2"):
        detail_pipeline.run_detail_pipeline(workers=workers)
