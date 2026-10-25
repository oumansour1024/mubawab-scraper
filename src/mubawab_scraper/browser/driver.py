from contextlib import contextmanager
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from mubawab_scraper.config import settings


def _options(headless: bool, *, performance_logging: bool = False) -> Options:
    """Configure Chrome options for Selenium WebDriver."""
    o = Options()
    o.page_load_strategy = "eager"
    if headless:
        o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    if performance_logging:
        o.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    o.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    return o

@contextmanager
def chrome_driver(
    headless: bool | None = None,
    *,
    performance_logging: bool = False,
):
    """Context manager to create and manage a Selenium Chrome WebDriver instance."""
    system_driver = Path("/usr/bin/chromedriver")
    system_browser = Path("/usr/bin/chromium")
    service = (
        Service(str(system_driver))
        if system_driver.is_file()
        else Service(ChromeDriverManager().install())
    )
    options = _options(
        settings.headless if headless is None else headless,
        performance_logging=performance_logging,
    )
    if system_browser.is_file():
        options.binary_location = str(system_browser)
    driver = webdriver.Chrome(
        service=service,
        options=options,
    )
    driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    try:
        yield driver
    finally:
        driver.quit()