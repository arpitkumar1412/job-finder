"""
Fetch job postings from LinkedIn's public job search using Playwright.

LinkedIn does not expose a public JSON API like Greenhouse / Lever,
so we render the page in a headless browser and parse the HTML.

Stealth measures
----------------
* Navigate via LinkedIn homepage first (avoids direct-URL bot signal).
* Custom User-Agent, viewport, locale, and timezone.
* JS patches to remove ``navigator.webdriver`` flag.
* Randomised mouse movements (bezier-like curves) before clicks.
* Random delays between page loads (5–15 s) and micro-actions (2–5 s).
* Optional residential proxy (``config.LINKEDIN_PROXY``).
* Configurable headless mode (default ``False`` for stealth).
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
import time
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

import config

logger = logging.getLogger(__name__)

# CSS selectors for LinkedIn's public job search page.
_JOB_CARD_SEL = "ul.jobs-search__results-list > li"
_TITLE_SEL = "h3.base-search-card__title"
_COMPANY_SEL = "h4.base-search-card__subtitle a"
_COMPANY_FALLBACK_SEL = "h4.base-search-card__subtitle"
_LOCATION_SEL = "span.job-search-card__location"
_LINK_SEL = "a.base-card__full-link"
_SHOW_MORE_SEL = "button.infinite-scroller__show-more-button"

# Selectors for the full job description shown in the detail panel / page.
_DESC_SEL = "div.show-more-less-html__markup"

# Stealth headers
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# JS snippet injected into every new page to remove bot-detectable flags.
_STEALTH_JS = """\
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = {runtime: {}};
"""


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _stealth_delay() -> None:
    """Sleep for a random interval to mimic human browsing (page-level)."""
    delay = random.uniform(config.LINKEDIN_MIN_DELAY, config.LINKEDIN_MAX_DELAY)
    logger.debug("Stealth delay: %.1fs", delay)
    time.sleep(delay)


def _action_delay() -> None:
    """Short random pause between micro-actions (clicks, scrolls)."""
    delay = random.uniform(
        config.LINKEDIN_ACTION_MIN_DELAY, config.LINKEDIN_ACTION_MAX_DELAY
    )
    logger.debug("Action delay: %.1fs", delay)
    time.sleep(delay)


def _human_mouse_move(page: Page, target_x: float, target_y: float) -> None:
    """Move the mouse to (*target_x*, *target_y*) via a randomised quadratic
    bezier curve, simulating a human hand."""
    vp = page.viewport_size or {"width": 1920, "height": 1080}
    start_x = random.uniform(0, vp["width"] * 0.5)
    start_y = random.uniform(0, vp["height"] * 0.5)

    # Single control point for a smooth quadratic bezier curve.
    ctrl_x = (start_x + target_x) / 2 + random.uniform(-80, 80)
    ctrl_y = (start_y + target_y) / 2 + random.uniform(-80, 80)

    steps = random.randint(8, 15)
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * ctrl_x + t ** 2 * target_x
        y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * ctrl_y + t ** 2 * target_y
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.01, 0.04))


def _make_job_id(url: str, title: str, company: str) -> str:
    """Derive a stable job ID from the URL (or a hash fallback)."""
    # LinkedIn URLs contain a numeric job ID after /view/
    match = re.search(r"/view/(\d+)", url)
    if match:
        return f"li-{match.group(1)}"
    # Fallback: hash of url + title + company
    raw = f"{url}|{title}|{company}"
    return "li-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _launch_browser(pw: Playwright) -> tuple[Browser, BrowserContext]:
    """Launch a Chromium browser with stealth settings."""
    launch_kwargs: dict[str, Any] = {"headless": config.LINKEDIN_HEADLESS}
    if config.LINKEDIN_PROXY:
        launch_kwargs["proxy"] = {"server": config.LINKEDIN_PROXY}

    browser = pw.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="America/New_York",
    )
    # Inject stealth JS into every new page / frame.
    context.add_init_script(_STEALTH_JS)
    return browser, context


def _scroll_and_load(page: Page, max_pages: int) -> None:
    """Scroll down and click 'See more jobs' to load additional results."""
    for i in range(max_pages):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _action_delay()

        btn = page.query_selector(_SHOW_MORE_SEL)
        if btn and btn.is_visible():
            logger.info("  Clicking 'See more jobs' (%d/%d) …", i + 1, max_pages)
            box = btn.bounding_box()
            if box:
                _human_mouse_move(
                    page,
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )
            _action_delay()
            btn.click()
            _stealth_delay()
        else:
            logger.info("  No more 'See more jobs' button — done scrolling.")
            break


def _fetch_description(page: Page, job_url: str) -> str:
    """Navigate to a single job page and extract the full description."""
    try:
        page.goto(job_url, wait_until="domcontentloaded", timeout=config.LINKEDIN_JOB_TIMEOUT)
        _stealth_delay()
        desc_el = page.query_selector(_DESC_SEL)
        if desc_el:
            return _strip_html(desc_el.inner_html())
    except Exception as exc:
        logger.warning("Failed to fetch description from %s: %s", job_url, exc)
    return ""


def _parse_cards(page: Page) -> list[dict[str, str]]:
    """Parse job cards from the current search-results page."""
    cards = page.query_selector_all(_JOB_CARD_SEL)
    logger.info("  Found %d job cards on the page.", len(cards))

    results: list[dict[str, str]] = []
    for card in cards:
        try:
            title_el = card.query_selector(_TITLE_SEL)
            company_el = card.query_selector(_COMPANY_SEL) or card.query_selector(
                _COMPANY_FALLBACK_SEL
            )
            location_el = card.query_selector(_LOCATION_SEL)
            link_el = card.query_selector(_LINK_SEL)

            title = (title_el.inner_text().strip()) if title_el else ""
            company = (company_el.inner_text().strip()) if company_el else ""
            location = (location_el.inner_text().strip()) if location_el else ""
            href = (link_el.get_attribute("href") or "") if link_el else ""

            if not title or not href:
                continue

            results.append(
                {
                    "title": title,
                    "company": company,
                    "location": location,
                    "href": href.split("?")[0],  # strip tracking params
                }
            )
        except Exception as exc:
            logger.debug("Skipping card due to parse error: %s", exc)
            continue

    return results


def fetch_linkedin_jobs() -> list[dict[str, Any]]:
    """
    Scrape LinkedIn's public job search for SDE2 Backend roles in India.

    Returns a list of normalised job dicts matching the schema used by the
    Greenhouse and Lever fetchers (``job_id``, ``title``, ``company``,
    ``location``, ``description``, ``apply_url``, ``source``).
    """
    url = config.LINKEDIN_SEARCH_URL
    logger.info("Fetching LinkedIn jobs from: %s", url)

    jobs: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser, context = _launch_browser(pw)
        try:
            page = context.new_page()

            # --- Warm-up: land on LinkedIn homepage first (avoids direct-URL
            # bot signal), then navigate to the jobs search page. ---
            logger.info("  Warming up: visiting LinkedIn homepage …")
            page.goto(
                "https://www.linkedin.com/",
                wait_until="domcontentloaded",
                timeout=config.LINKEDIN_PAGE_TIMEOUT,
            )
            _stealth_delay()

            logger.info("  Navigating to job search URL …")
            page.goto(url, wait_until="domcontentloaded", timeout=config.LINKEDIN_PAGE_TIMEOUT)
            _stealth_delay()

            # Load more results by scrolling / clicking "See more"
            _scroll_and_load(page, config.LINKEDIN_MAX_PAGES)

            # Parse all visible cards
            cards = _parse_cards(page)
            logger.info("  Parsed %d unique job cards.", len(cards))

            # Fetch full descriptions one-by-one (each in a new tab)
            for idx, card in enumerate(cards):
                logger.info(
                    "  [%d/%d] Fetching description for: %s at %s",
                    idx + 1,
                    len(cards),
                    card["title"],
                    card["company"],
                )
                desc_page = context.new_page()
                description = _fetch_description(desc_page, card["href"])
                desc_page.close()

                job_id = _make_job_id(card["href"], card["title"], card["company"])

                jobs.append(
                    {
                        "job_id": job_id,
                        "title": card["title"],
                        "company": card["company"],
                        "location": card["location"],
                        "description": description,
                        "apply_url": card["href"],
                        "source": "linkedin",
                    }
                )

        finally:
            context.close()
            browser.close()

    logger.info("LinkedIn total: %d jobs with descriptions.", len(jobs))
    return jobs
