"""Headless Chromium for JS-heavy pages and screenshots. Optional: needs the `browser` extra."""

import asyncio
import logging
from typing import Any

from smriti.config import get_settings

log = logging.getLogger(__name__)
_browser: Any = None
_lock = asyncio.Lock()


def available() -> bool:
    if not get_settings().browser_enabled:
        return False
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


async def _get_browser() -> Any:
    global _browser
    async with _lock:
        if _browser is None or not _browser.is_connected():
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            _browser = await pw.chromium.launch()
    return _browser


async def render(
    url: str | None = None,
    html: str | None = None,
    *,
    screenshot: bool = False,
    timeout_s: float = 30,
) -> tuple[str, bytes | None]:
    """Load a URL (or set raw HTML) and return the rendered DOM and, optionally, a full-page PNG."""
    browser = await _get_browser()
    page = await browser.new_page(
        user_agent=get_settings().user_agent, viewport={"width": 1280, "height": 900}
    )
    try:
        if url:
            await page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
        else:
            await page.set_content(html or "", wait_until="networkidle", timeout=timeout_s * 1000)
        # Scroll once to trigger lazy-loaded images.
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(500)
        content = await page.content()
        shot = (
            await page.screenshot(full_page=True, type="jpeg", quality=70) if screenshot else None
        )
        return content, shot
    finally:
        await page.close()
