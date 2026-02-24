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

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # Many bank sites never reach networkidle due to analytics

            # Smart scrolling to trigger lazy-loaded content
            last_height = 0
            scroll_attempts = 0
            while scroll_attempts < 20:
                current_height = await page.evaluate("document.body.scrollHeight")
                if current_height == last_height:
                    break
                last_height = current_height
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
                scroll_attempts += 1

            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)

            html = await page.content()
            await browser.close()

            logger.info(f"Playwright scraped {len(html)} chars from {url}")
            return html

    except ImportError:
        logger.warning("Playwright not installed")
        return None
    except Exception as e:
        logger.error(f"Playwright error for {url}: {e}")
        return None
