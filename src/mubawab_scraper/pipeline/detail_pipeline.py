"""Enrich raw listing cards with values from their detail pages."""

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event
from time import monotonic

from tqdm import tqdm

from mubawab_scraper.browser.driver import chrome_driver
from mubawab_scraper.application.services.transaction_normalization import (
    DETAIL_ACTION_ALIASES,
    DETAIL_ACTIONS,
    normalize_detail_transaction,
)
from mubawab_scraper.config import settings
from mubawab_scraper.logging_config import get_logger
from mubawab_scraper.models import PropertyDetail
from mubawab_scraper.scrapers.detail import RateLimitedPageError, scrape_detail
from mubawab_scraper.storage.csv_store import export_raw_details
from mubawab_scraper.storage.raw_store import RawListingStore
from mubawab_scraper.utils.rate_limit import RequestRateLimiter
from mubawab_scraper.utils.urls import ACTION_ALIASES

log = get_logger(__name__)
MAX_DETAIL_WORKERS = 4
DETAIL_DB_BATCH_SIZE = 20

DETAIL_STORAGE_ACTIONS = {
    "a-vendre": ("a-vendre", "a-vendre-all", "vente"),
    "a-louer": ("a-louer", "a-louer-all", "location"),
    "vacational": ("vacational", "vacational-all", "vacances"),
}


@dataclass
class DetailPipelineSummary:
    transaction_type: str | None
    city: str | None
    urls_found: int
    details_scraped: int
    details_failed: int
    duration_sec: float
    rate_limited: bool = False
    retry_after: str | None = None


@dataclass
class _WorkerResult:
    failed: int
    rate_limited: bool = False
    retry_after: str | None = None


def _normalize_transaction(transaction_type: str | None) -> str | None:
    return normalize_detail_transaction(transaction_type)


def _detail_worker(
    worker_id: int,
    urls: list[dict[str, str]],
    headless: bool | None,
    stop_event: Event,
    rate_limiter: RequestRateLimiter,
    result_queue: Queue[list[PropertyDetail]],
) -> _WorkerResult:
    batch: list[PropertyDetail] = []
    failed = 0
    rate_limited = False
    retry_after = None
    try:
        with chrome_driver(
            headless=headless,
            performance_logging=True,
        ) as driver:
            for listing in tqdm(urls, desc=f"[details-{worker_id}]"):
                if stop_event.is_set():
                    break
                try:
                    detail = scrape_detail(
                        driver,
                        listing["url"],
                        listing["ad_id"],
                        rate_limiter=rate_limiter,
                        stop_event=stop_event,
                    )
                except RateLimitedPageError as exc:
                    stop_event.set()
                    rate_limited = True
                    retry_after = exc.retry_after
                    log.error(
                        "detail_rate_limited_stopping",
                        worker=worker_id,
                        ad_id=listing["ad_id"],
                        retry_after=retry_after,
                    )
                    break
                if detail is None:
                    if stop_event.is_set():
                        break
                    failed += 1
                else:
                    batch.append(detail)
                    if len(batch) >= DETAIL_DB_BATCH_SIZE:
                        result_queue.put(batch)
                        batch = []
    finally:
        if batch:
            result_queue.put(batch)
    return _WorkerResult(failed, rate_limited, retry_after)


def run_detail_pipeline(
    transaction_type: str | None = None,
    limit: int = 0,
    headless: bool | None = None,
    city: str | None = None,
    workers: int = 1,
) -> DetailPipelineSummary:
    """Scrape unprocessed detail URLs, persist successes, and export results."""
    if limit < 0:
        raise ValueError("limit must be zero (unlimited) or a positive integer")
    if not 1 <= workers <= MAX_DETAIL_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_DETAIL_WORKERS}")
    action = _normalize_transaction(transaction_type)
    start = monotonic()
    store = RawListingStore(settings.db_path)
    worker_errors: list[tuple[int, Exception]] = []
    try:
        city_filter = None if not city or city.strip().lower() == "all" else city.strip()
        urls = store.get_pending_details(
            transaction_type=(
                DETAIL_STORAGE_ACTIONS[action] if action is not None else None
            ),
            city=city_filter,
            limit=limit,
        )
        total_cards = store.count_raw_listings()
        log.info(
            "detail_pipeline_started",
            transaction_type=action or "all",
            city=city_filter or "all",
            urls_found=len(urls),
            raw_listings=total_cards,
            limit=limit or "unlimited",
            workers=workers,
        )
        scraped = 0
        failed = 0
        rate_limited = False
        retry_after = None
        if urls:
            chunks = [
                urls[index::workers]
                for index in range(workers)
                if urls[index::workers]
            ]
            stop_event = Event()
            rate_limiter = RequestRateLimiter()
            result_queue: Queue[list[PropertyDetail]] = Queue()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        _detail_worker,
                        worker_id,
                        chunk,
                        headless,
                        stop_event,
                        rate_limiter,
                        result_queue,
                    ): worker_id
                    for worker_id, chunk in enumerate(chunks, start=1)
                }
                pending: set[Future[_WorkerResult]] = set(futures)
                with tqdm(total=len(urls), desc="[details]") as progress:
                    while pending:
                        try:
                            batch = result_queue.get(timeout=0.1)
                        except Empty:
                            pass
                        else:
                            store.save_details(batch)
                            scraped += len(batch)
                            progress.update(len(batch))

                        completed, pending = wait(
                            pending,
                            timeout=0,
                            return_when=FIRST_COMPLETED,
                        )
                        for future in completed:
                            worker_id = futures[future]
                            try:
                                result = future.result()
                            except Exception as exc:
                                stop_event.set()
                                worker_errors.append((worker_id, exc))
                                log.exception(
                                    "detail_worker_failed",
                                    worker=worker_id,
                                    error=str(exc),
                                )
                                continue
                            failed += result.failed
                            if result.rate_limited:
                                rate_limited = True
                                retry_after = result.retry_after

                    while True:
                        try:
                            batch = result_queue.get_nowait()
                        except Empty:
                            break
                        store.save_details(batch)
                        scraped += len(batch)
                        progress.update(len(batch))
    finally:
        store.close()

    export_paths = export_raw_details(fmt="csv")
    duration = monotonic() - start
    summary = DetailPipelineSummary(
        transaction_type=action,
        city=city_filter,
        urls_found=len(urls),
        details_scraped=scraped,
        details_failed=failed,
        duration_sec=duration,
        rate_limited=rate_limited,
        retry_after=retry_after,
    )
    log.info(
        "detail_pipeline_finished",
        details_scraped=scraped,
        details_failed=failed,
        rate_limited=rate_limited,
        retry_after=retry_after,
        duration_sec=round(duration, 1),
        exports=export_paths,
    )
    if worker_errors:
        worker_id, error = worker_errors[0]
        raise RuntimeError(f"Detail worker {worker_id} failed") from error
    return summary
