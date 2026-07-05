import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page
from playwright_stealth import Stealth

from config import HEADLESS, BROWSER_DATA_DIR, PAGE_URL
from site_selectors import SITES, SiteSelectors

logger = logging.getLogger(__name__)


class BrowserManager:
    def __init__(self):
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._selectors: SiteSelectors = SITES["doubao"]

    @property
    def selectors(self) -> SiteSelectors:
        return self._selectors

    @property
    def page(self) -> Page | None:
        return self._page

    async def start(self) -> Page:
        playwright = await async_playwright().start()
        data_dir = Path(BROWSER_DATA_DIR)
        data_dir.mkdir(parents=True, exist_ok=True)

        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(data_dir),
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-web-security",
            ],
        )

        page = await context.new_page()
        await page.set_viewport_size({"width": 1280, "height": 800})

        timeout_ms = 60000
        page.set_default_navigation_timeout(timeout_ms)
        page.set_default_timeout(timeout_ms)

        await Stealth().apply_stealth_async(page)
        logger.info(f"Navigating to {self._selectors.url}")
        await page.goto(self._selectors.url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        try:
            await page.wait_for_selector(self._selectors.input_field, timeout=30000)
            logger.info("Page loaded - input field detected")
        except Exception:
            logger.warning("Input field not found after navigation, page may still be loading")

        self._browser = context
        self._page = page
        logger.info("Browser started, waiting for login...")
        return page

    async def wait_for_login(self, timeout: float = 300) -> None:
        if self._page is None:
            raise RuntimeError("Browser not started")
        try:
            await self._page.wait_for_selector(
                self._selectors.login_indicator,
                timeout=int(timeout * 1000),
            )
            logger.info("Login detected")
        except Exception:
            raise TimeoutError(
                f"Login not detected within {timeout}s. "
                f"Please log in manually at {self._selectors.url}"
            )

    async def ensure_page_alive(self) -> Page:
        if self._page is None:
            return await self.start()
        try:
            current_url = self._page.url
            if not current_url.startswith(self._selectors.url):
                logger.info("Page navigated away, navigating back to chat")
                await self._page.goto(self._selectors.url, wait_until="domcontentloaded")
                await self.wait_for_login(timeout=30)
            return self._page
        except Exception as e:
            logger.warning(f"Page check failed, restarting: {e}")
            return await self.start()

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
