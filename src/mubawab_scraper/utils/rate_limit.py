import random
import time
from threading import Event, Lock

from mubawab_scraper.config import settings


def jittered_sleep(min_s: float | None = None, max_s: float | None = None) -> None:
    lo = min_s if min_s is not None else settings.min_delay
    hi = max_s if max_s is not None else settings.max_delay
    time.sleep(random.uniform(lo, hi))


class RequestRateLimiter:
    """Apply a shared minimum interval between requests across worker threads."""

    def __init__(self, min_s: float | None = None, max_s: float | None = None) -> None:
        self.min_s = min_s if min_s is not None else settings.min_delay
        self.max_s = max_s if max_s is not None else settings.max_delay
        if self.min_s < 0 or self.max_s < self.min_s:
            raise ValueError("Rate-limit delays must satisfy 0 <= min_s <= max_s")
        self._lock = Lock()
        self._next_request_at = 0.0

    def wait(self, stop_event: Event | None = None) -> bool:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_request_at - now)
            if stop_event is not None and stop_event.is_set():
                return False
            if delay and stop_event is not None:
                if stop_event.wait(delay):
                    return False
            elif delay:
                time.sleep(delay)
            if stop_event is not None and stop_event.is_set():
                return False
            self._next_request_at = time.monotonic() + random.uniform(
                self.min_s,
                self.max_s,
            )
            return True