from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def wait_for_selector(driver, css: str, timeout: int = 15):
    """ Wait for an element to be present in the DOM and visible on the page.
    Args:
        driver: Selenium WebDriver instance.
        css: CSS selector of the element to wait for.
        timeout: Maximum time to wait for the element (in seconds)."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css))
    )

def wait_for_id(driver,id:str, timeout:int = 15):
    """ Wait for an element to be present in the DOM and visible on the page.
    Args:
        driver: Selenium WebDriver instance.
        id: ID of the element to wait for.
        timeout: Maximum time to wait for the element (in seconds)."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, id))
    )
