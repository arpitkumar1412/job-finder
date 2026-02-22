"""
Auto-apply to Greenhouse job postings via Selenium.

Greenhouse application pages follow a consistent structure:
- URL pattern: https://boards.greenhouse.io/{company}/jobs/{job_id}
- Application form with standard fields (name, email, phone, resume)
- May include custom questions that vary by company
"""

from __future__ import annotations

import logging
import time
from typing import Any

from selenium.webdriver.common.by import By

import config
from applier.driver import (
    create_driver,
    safe_click,
    safe_fill,
    upload_file,
)

logger = logging.getLogger(__name__)


def apply_greenhouse(job: dict[str, Any], resume_path: str) -> tuple[bool, str]:
    """
    Submit an application on a Greenhouse job posting.

    Parameters
    ----------
    job : dict
        Job data from the Google Sheet (must include ``apply_url``).
    resume_path : str
        Local path to the resume PDF file.

    Returns
    -------
    (success, message) : tuple[bool, str]
        Whether the application was submitted and a status message.
    """
    apply_url = job.get("apply_url", "")
    company = job.get("company", "unknown")
    title = job.get("title", "unknown")
    label = f"{company} — {title}"

    if not apply_url:
        return False, "No apply_url provided"

    driver = None
    try:
        driver = create_driver()
        logger.info("Navigating to Greenhouse application: %s", apply_url)
        driver.get(apply_url)
        time.sleep(config.AUTO_APPLY_WAIT)

        # Greenhouse embeds the application form in the page or via an iframe.
        # Try to find and switch to the application iframe if present.
        _switch_to_app_iframe(driver)

        # Fill standard fields
        _fill_name_fields(driver)
        _fill_email(driver)
        _fill_phone(driver)

        # Upload resume
        _upload_resume(driver, resume_path)

        # Fill LinkedIn / website if fields exist
        _fill_optional_urls(driver)

        time.sleep(config.AUTO_APPLY_WAIT)

        # Submit the application
        submitted = _click_submit(driver)

        if submitted:
            # Wait for confirmation
            time.sleep(config.AUTO_APPLY_WAIT * 2)
            page_text = driver.page_source.lower()
            if "thank" in page_text or "submitted" in page_text or "received" in page_text:
                logger.info("Successfully applied to [%s]", label)
                return True, "Application submitted successfully"
            else:
                logger.warning(
                    "Submit clicked for [%s] but confirmation not detected.",
                    label,
                )
                return True, "Submit clicked — confirmation unclear"
        else:
            return False, "Could not find or click submit button"

    except Exception as exc:
        logger.error("Greenhouse apply failed for [%s]: %s", label, exc)
        return False, f"Error: {exc}"
    finally:
        if driver:
            driver.quit()


def _switch_to_app_iframe(driver) -> None:
    """Switch to the Greenhouse application iframe if present."""
    try:
        iframe = driver.find_element(By.ID, "grnhse_iframe")
        driver.switch_to.frame(iframe)
        logger.debug("Switched to Greenhouse iframe.")
        time.sleep(1)
    except Exception:
        # No iframe — form is directly on the page
        logger.debug("No Greenhouse iframe found, form is on main page.")


def _fill_name_fields(driver) -> None:
    """Fill first name and last name fields."""
    # Greenhouse uses various ID/name patterns for name fields
    first_name_selectors = [
        (By.ID, "first_name"),
        (By.NAME, "job_application[first_name]"),
        (By.CSS_SELECTOR, "input[autocomplete='given-name']"),
        (By.CSS_SELECTOR, "input[id*='first_name']"),
    ]
    last_name_selectors = [
        (By.ID, "last_name"),
        (By.NAME, "job_application[last_name]"),
        (By.CSS_SELECTOR, "input[autocomplete='family-name']"),
        (By.CSS_SELECTOR, "input[id*='last_name']"),
    ]

    for by, value in first_name_selectors:
        if safe_fill(driver, by, value, config.APPLICANT_FIRST_NAME):
            break

    for by, value in last_name_selectors:
        if safe_fill(driver, by, value, config.APPLICANT_LAST_NAME):
            break


def _fill_email(driver) -> None:
    """Fill the email field."""
    email_selectors = [
        (By.ID, "email"),
        (By.NAME, "job_application[email]"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[autocomplete='email']"),
        (By.CSS_SELECTOR, "input[id*='email']"),
    ]
    for by, value in email_selectors:
        if safe_fill(driver, by, value, config.APPLICANT_EMAIL):
            break


def _fill_phone(driver) -> None:
    """Fill the phone field."""
    if not config.APPLICANT_PHONE:
        return
    phone_selectors = [
        (By.ID, "phone"),
        (By.NAME, "job_application[phone]"),
        (By.CSS_SELECTOR, "input[type='tel']"),
        (By.CSS_SELECTOR, "input[autocomplete='tel']"),
        (By.CSS_SELECTOR, "input[id*='phone']"),
    ]
    for by, value in phone_selectors:
        if safe_fill(driver, by, value, config.APPLICANT_PHONE):
            break


def _upload_resume(driver, resume_path: str) -> None:
    """Upload the resume file."""
    resume_selectors = [
        (By.CSS_SELECTOR, "input[type='file'][id*='resume']"),
        (By.CSS_SELECTOR, "input[type='file'][name*='resume']"),
        (By.CSS_SELECTOR, "input[type='file']"),
    ]
    for by, value in resume_selectors:
        if upload_file(driver, by, value, resume_path):
            logger.info("Resume uploaded successfully.")
            return
    logger.warning("Could not find resume upload field.")


def _fill_optional_urls(driver) -> None:
    """Fill LinkedIn and website/GitHub fields if present."""
    if config.APPLICANT_LINKEDIN:
        linkedin_selectors = [
            (By.CSS_SELECTOR, "input[id*='linkedin']"),
            (By.CSS_SELECTOR, "input[name*='linkedin']"),
            (By.CSS_SELECTOR, "input[placeholder*='LinkedIn']"),
        ]
        for by, value in linkedin_selectors:
            if safe_fill(driver, by, value, config.APPLICANT_LINKEDIN):
                break

    if config.APPLICANT_WEBSITE:
        website_selectors = [
            (By.CSS_SELECTOR, "input[id*='website']"),
            (By.CSS_SELECTOR, "input[name*='website']"),
            (By.CSS_SELECTOR, "input[placeholder*='Website']"),
        ]
        for by, value in website_selectors:
            if safe_fill(driver, by, value, config.APPLICANT_WEBSITE):
                break


def _click_submit(driver) -> bool:
    """Click the submit/apply button."""
    submit_selectors = [
        (By.ID, "submit_app"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (By.CSS_SELECTOR, "button[id*='submit']"),
        (By.XPATH, "//button[contains(text(), 'Submit')]"),
        (By.XPATH, "//button[contains(text(), 'Apply')]"),
        (By.XPATH, "//input[@value='Submit Application']"),
    ]
    for by, value in submit_selectors:
        if safe_click(driver, by, value, timeout=5):
            logger.info("Clicked submit button.")
            return True
    return False
