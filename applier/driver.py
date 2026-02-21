"""
Selenium WebDriver setup and shared browser helpers.

Uses webdriver-manager to auto-download the correct ChromeDriver.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

import config

logger = logging.getLogger(__name__)


def create_driver() -> webdriver.Chrome:
    """Create and return a configured Chrome WebDriver instance."""
    options = Options()
    if config.SELENIUM_HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # Reduce bot-detection signals
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(config.AUTO_APPLY_PAGE_LOAD_WAIT)
    return driver


def wait_and_find(
    driver: webdriver.Chrome,
    by: str,
    value: str,
    timeout: float | None = None,
):
    """Wait for an element to be present and return it."""
    wait_time = timeout or config.AUTO_APPLY_PAGE_LOAD_WAIT
    wait = WebDriverWait(driver, wait_time)
    return wait.until(EC.presence_of_element_located((by, value)))


def safe_fill(
    driver: webdriver.Chrome,
    by: str,
    value: str,
    text: str,
    *,
    clear_first: bool = True,
) -> bool:
    """Find an element and fill it with text. Returns True on success."""
    try:
        element = wait_and_find(driver, by, value, timeout=5)
        if clear_first:
            element.clear()
        element.send_keys(text)
        time.sleep(0.3)
        return True
    except Exception as exc:
        logger.debug("Could not fill field (%s=%s): %s", by, value, exc)
        return False


def safe_click(
    driver: webdriver.Chrome,
    by: str,
    value: str,
    *,
    timeout: float | None = None,
) -> bool:
    """Find an element and click it. Returns True on success."""
    try:
        wait_time = timeout or config.AUTO_APPLY_PAGE_LOAD_WAIT
        wait = WebDriverWait(driver, wait_time)
        element = wait.until(EC.element_to_be_clickable((by, value)))
        element.click()
        time.sleep(config.AUTO_APPLY_WAIT)
        return True
    except Exception as exc:
        logger.debug("Could not click element (%s=%s): %s", by, value, exc)
        return False


def upload_file(
    driver: webdriver.Chrome,
    by: str,
    value: str,
    file_path: str,
) -> bool:
    """Upload a file to a file input element. Returns True on success."""
    try:
        element = driver.find_element(by, value)
        element.send_keys(file_path)
        time.sleep(config.AUTO_APPLY_WAIT)
        return True
    except Exception as exc:
        logger.debug("Could not upload file (%s=%s): %s", by, value, exc)
        return False


def download_resume_from_drive(resume_id: str) -> str | None:
    """
    Download a resume PDF from Google Drive to a temporary file.

    Uses the same OAuth2 credentials as drive_uploader.

    Parameters
    ----------
    resume_id : str
        The Google Drive file ID.

    Returns
    -------
    str or None
        Path to the downloaded temporary PDF file, or None on failure.
    """
    try:
        from resume.drive_uploader import _get_drive_service
        service = _get_drive_service()

        # Download file content
        request = service.files().get_media(fileId=resume_id)
        content = request.execute()

        # Write to temp file
        tmp = tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix="resume_", delete=False,
        )
        tmp.write(content)
        tmp.close()

        logger.info("Downloaded resume %s to %s", resume_id, tmp.name)
        return tmp.name

    except Exception as exc:
        logger.error("Failed to download resume %s: %s", resume_id, exc)
        return None
