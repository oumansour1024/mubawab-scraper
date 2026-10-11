from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from mubawab_scraper.config import settings

def _options(headless: bool) -> Options:
    """Configure Chrome options for Selenium WebDriver."""
    o = Options()
    if headless:
        o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    return o

@contextmanager
def chrome_driver(headless: bool | None = None):
    """Context manager to create and manage a Selenium Chrome WebDriver instance."""
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=_options(settings.headless if headless is None else headless),
    )
    driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
    )
    try:
        yield driver
    finally:
        driver.quit()