import random, time
from mubawab_scraper.config import settings

def jittered_sleep(min_s: float | None = None, max_s: float | None = None) -> None:
    lo = min_s if min_s is not None else settings.min_delay
    hi = max_s if max_s is not None else settings.max_delay
    time.sleep(random.uniform(lo, hi))