from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


def wait_for_selector(driver: WebDriver, css: str, timeout: int = 15) -> WebElement:
    """Wait for an element to be present in the DOM.
    Args:
        driver: Selenium WebDriver instance.
        css: CSS selector of the element to wait for.
        timeout: Maximum time to wait for the element (in seconds)."""
    return WebDriverWait(driver, timeout).until(
        expected_conditions.presence_of_element_located((By.CSS_SELECTOR, css))
    )


def wait_for_id(driver: WebDriver, id: str, timeout: int = 15) -> WebElement:
    """Wait for an element to be present in the DOM.
    Args:
        driver: Selenium WebDriver instance.
        id: ID of the element to wait for.
        timeout: Maximum time to wait for the element (in seconds)."""
    return WebDriverWait(driver, timeout).until(
        expected_conditions.presence_of_element_located((By.ID, id))
    )
