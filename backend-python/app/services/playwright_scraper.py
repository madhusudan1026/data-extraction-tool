"""
Shared Playwright scraper utility.
Used by V5 structured extraction and other modules.
"""
import logging

logger = logging.getLogger(__name__)


async def scrape_with_playwright(url: str) -> str:
    """Scrape a URL using Playwright with smart scrolling. Returns HTML or None."""
    try:
        from playwright.async_api import async_playwright

        logger.info(f"[Playwright] Launching browser for {url[:80]}...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
            )
            page = await browser.new_page()

            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            logger.info(f"[Playwright] Navigating to {url[:80]}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            # Quick scroll — max 8 attempts, 800ms each
            last_height = 0
            for i in range(8):
                current_height = await page.evaluate("document.body.scrollHeight")
                if current_height == last_height:
                    break
                last_height = current_height
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(800)

            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)

            html = await page.content()
            await browser.close()

            logger.info(f"[Playwright] Done: {len(html)} chars from {url[:80]}")
            return html

    except ImportError:
        logger.warning("Playwright not installed")
        return None
    except Exception as e:
        logger.error(f"[Playwright] Error for {url[:80]}: {e}")
        return None
