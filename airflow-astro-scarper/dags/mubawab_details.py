from airflow.sdk import dag, task
from pendulum import datetime
import logging
from datetime import timedelta
from airflow.exceptions import AirflowException

DETAIL_LIMIT = 100
DETAIL_WORKERS = 1
logger = logging.getLogger(__name__)


@dag(
    dag_id="mubawab_detail_scraper",
    start_date=datetime(2025, 1, 1, tz="UTC"),
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    default_args={
        "owner": "mubawab",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=30),
    },
    tags=["mubawab", "scraping", "details"],
)
def mubawab_detail_scraper():
    @task
    def scrape_pending_details() -> None:
        from mubawab_scraper.pipeline.detail_pipeline import run_detail_pipeline

        summary = run_detail_pipeline(limit=DETAIL_LIMIT, workers=DETAIL_WORKERS)
        logger.info(
            "Mubawab details run finished: found=%s scraped=%s failed=%s",
            summary.urls_found,
            summary.details_scraped,
            summary.details_failed,
        )
        if summary.rate_limited:
            retry_after = summary.retry_after or "not provided"
            raise AirflowException(
                "Mubawab returned HTTP 429; retrying after Airflow backoff. "
                f"Retry-After: {retry_after}"
            )
        if summary.details_failed:
            raise AirflowException(
                f"{summary.details_failed} detail pages failed; "
                "the task will retry the remaining pending listings."
            )

    scrape_pending_details()


mubawab_detail_scraper()
