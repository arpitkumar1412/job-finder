"""
Auto-apply to Lever job postings via Selenium.

Lever application pages follow a consistent structure:
- URL pattern: https://jobs.lever.co/{company}/{posting_id}
- Application page at: {apply_url}/apply
- Standard form fields (name, email, phone, resume, URLs)
- May include custom questions per company
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
    wait_and_find,
)

logger = logging.getLogger(__name__)


def apply_lever(job: dict[str, Any], resume_path: str) -> tuple[bool, str]:
    """
    Submit an application on a Lever job posting.

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

    # Lever application pages are at {posting_url}/apply
    if not apply_url.rstrip("/").endswith("/apply"):
        apply_url = apply_url.rstrip("/") + "/apply"

    driver = None
    try:
        driver = create_driver()
        logger.info("Navigating to Lever application: %s", apply_url)
        driver.get(apply_url)
        time.sleep(config.AUTO_APPLY_WAIT)

        # Fill standard fields
        _fill_name(driver)
        _fill_email(driver)
        _fill_phone(driver)
        _fill_org(driver)

        # Upload resume
        _upload_resume(driver, resume_path)

        # Fill URL fields (LinkedIn, GitHub, etc.)
        _fill_urls(driver)

        time.sleep(config.AUTO_APPLY_WAIT)

        # Submit the application
        submitted = _click_submit(driver)

        if submitted:
            # Wait for confirmation
            time.sleep(config.AUTO_APPLY_WAIT * 2)
            page_text = driver.page_source.lower()
            if "thank" in page_text or "submitted" in page_text or "received" in page_text or "application" in page_text:
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
        logger.error("Lever apply failed for [%s]: %s", label, exc)
        return False, f"Error: {exc}"
    finally:
        if driver:
            driver.quit()


def _fill_name(driver) -> None:
    """Fill the full name field."""
    full_name = f"{config.APPLICANT_FIRST_NAME} {config.APPLICANT_LAST_NAME}".strip()
    if not full_name:
        return
    name_selectors = [
        (By.NAME, "name"),
        (By.CSS_SELECTOR, "input[id*='name']"),
        (By.CSS_SELECTOR, "input[placeholder*='Full name']"),
        (By.CSS_SELECTOR, "input[autocomplete='name']"),
    ]
    for by, value in name_selectors:
        if safe_fill(driver, by, value, full_name):
            break


def _fill_email(driver) -> None:
    """Fill the email field."""
    email_selectors = [
        (By.NAME, "email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[id*='email']"),
        (By.CSS_SELECTOR, "input[autocomplete='email']"),
    ]
    for by, value in email_selectors:
        if safe_fill(driver, by, value, config.APPLICANT_EMAIL):
            break


def _fill_phone(driver) -> None:
    """Fill the phone field."""
    if not config.APPLICANT_PHONE:
        return
    phone_selectors = [
        (By.NAME, "phone"),
        (By.CSS_SELECTOR, "input[type='tel']"),
        (By.CSS_SELECTOR, "input[id*='phone']"),
        (By.CSS_SELECTOR, "input[autocomplete='tel']"),
    ]
    for by, value in phone_selectors:
        if safe_fill(driver, by, value, config.APPLICANT_PHONE):
            break


def _fill_org(driver) -> None:
    """Fill the current company/organization field."""
    org_selectors = [
        (By.NAME, "org"),
        (By.CSS_SELECTOR, "input[id*='org']"),
        (By.CSS_SELECTOR, "input[placeholder*='Company']"),
        (By.CSS_SELECTOR, "input[placeholder*='company']"),
    ]
    # Try to fill — if no current org, just skip
    for by, value in org_selectors:
        if safe_fill(driver, by, value, ""):
            break


def _upload_resume(driver, resume_path: str) -> None:
    """Upload the resume file."""
    resume_selectors = [
        (By.CSS_SELECTOR, "input[type='file'][name='resume']"),
        (By.CSS_SELECTOR, "input[type='file'][id*='resume']"),
        (By.CSS_SELECTOR, "input[type='file']"),
    ]
    for by, value in resume_selectors:
        if upload_file(driver, by, value, resume_path):
            logger.info("Resume uploaded successfully.")
            return
    logger.warning("Could not find resume upload field.")


def _fill_urls(driver) -> None:
    """Fill LinkedIn, GitHub, and other URL fields."""
    if config.APPLICANT_LINKEDIN:
        linkedin_selectors = [
            (By.CSS_SELECTOR, "input[name='urls[LinkedIn]']"),
            (By.CSS_SELECTOR, "input[id*='linkedin']"),
            (By.CSS_SELECTOR, "input[placeholder*='LinkedIn']"),
        ]
        for by, value in linkedin_selectors:
            if safe_fill(driver, by, value, config.APPLICANT_LINKEDIN):
                break

    if config.APPLICANT_GITHUB:
        github_selectors = [
            (By.CSS_SELECTOR, "input[name='urls[GitHub]']"),
            (By.CSS_SELECTOR, "input[id*='github']"),
            (By.CSS_SELECTOR, "input[placeholder*='GitHub']"),
        ]
        for by, value in github_selectors:
            if safe_fill(driver, by, value, config.APPLICANT_GITHUB):
                break

    if config.APPLICANT_WEBSITE:
        website_selectors = [
            (By.CSS_SELECTOR, "input[name='urls[Portfolio]']"),
            (By.CSS_SELECTOR, "input[id*='website']"),
            (By.CSS_SELECTOR, "input[placeholder*='Website']"),
            (By.CSS_SELECTOR, "input[placeholder*='Portfolio']"),
        ]
        for by, value in website_selectors:
            if safe_fill(driver, by, value, config.APPLICANT_WEBSITE):
                break


def _click_submit(driver) -> bool:
    """Click the submit/apply button."""
    submit_selectors = [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "button.postings-btn"),
        (By.XPATH, "//button[contains(text(), 'Submit')]"),
        (By.XPATH, "//button[contains(text(), 'submit')]"),
        (By.XPATH, "//button[contains(text(), 'Apply')]"),
        (By.CSS_SELECTOR, "input[type='submit']"),
    ]
    for by, value in submit_selectors:
        if safe_click(driver, by, value, timeout=5):
            logger.info("Clicked submit button.")
            return True
    return False
