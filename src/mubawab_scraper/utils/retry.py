from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
from selenium.common.exceptions import WebDriverException

selenium_retry = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=15),
    retry=retry_if_exception_type(WebDriverException),
)
