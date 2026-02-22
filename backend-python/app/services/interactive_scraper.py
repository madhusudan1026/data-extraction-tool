"""
Interactive Playwright Scraper

Handles modern bank websites with expandable/accordion content:
1. Loads page with smart scrolling
2. Detects expandable tiles, accordions, tabs
3. Clicks each to reveal hidden content
4. Captures expanded content per-section with links
5. Returns structured section data directly (not raw HTML)

Designed for Emirates NBD, FAB, ADCB style credit card pages.
"""

import re
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


async def scrape_card_page_interactive(url: str, card_name: str = "") -> Dict[str, Any]:
    """
    Scrape a credit card detail page interactively.
    
    Returns:
    {
        "full_html": str,           # Full page HTML after all expansions
        "sections": [               # Pre-extracted sections with content & links
            {
                "heading": str,
                "content": str,       # Text with line breaks preserved
                "links": [{"url": str, "title": str}],
                "is_expandable": bool,
                "sub_sections": [     # For expandable sections like "More advantages"
                    {
                        "title": str,
                        "content": str,
                        "links": [{"url": str, "title": str}],
                    }
                ]
            }
        ],
        "page_title": str,
    }
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed")
        return {"full_html": "", "sections": [], "page_title": ""}

    result = {"full_html": "", "sections": [], "page_title": ""}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage'],
            )
            page = await browser.new_page()
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })

            # Navigate
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Smart scroll to load lazy content
            await _smart_scroll(page)

            result["page_title"] = await page.title()

            # ---- PHASE 1: Extract initial page sections ----
            initial_sections = await page.evaluate('''(baseUrl) => {
                const sections = [];
                const headings = document.querySelectorAll('main h2, main h3, [role="main"] h2, [role="main"] h3, h2, h3');
                
                headings.forEach((h, idx) => {
                    const text = h.textContent?.trim();
                    if (!text || text.length < 3 || text.length > 200) return;
                    
                    // Find section container
                    let container = h.closest('section') || h.closest('[class*="section"]') || h.closest('[class*="block"]');
                    if (!container) {
                        // Walk up to find a reasonable container
                        let parent = h.parentElement;
                        for (let i = 0; i < 5 && parent; i++) {
                            const cls = parent.className?.toLowerCase() || '';
                            const tag = parent.tagName?.toLowerCase();
                            if (tag === 'section' || cls.includes('section') || cls.includes('block') || 
                                cls.includes('wrapper') || cls.includes('module') || cls.includes('container')) {
                                container = parent;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                    }
                    if (!container) container = h.parentElement;
                    
                    // Extract text with line breaks — clean and readable
                    const getTextWithBreaks = (el) => {
                        const lines = [];
                        const blockTags = new Set(['DIV','P','LI','H4','H5','H6','TR','DT','DD','SECTION','ARTICLE','BLOCKQUOTE','FIGCAPTION']);
                        const listTags = new Set(['LI','DT','DD']);
                        const skipTags = new Set(['SCRIPT','STYLE','NAV','FOOTER','HEADER','SVG','NOSCRIPT','IFRAME']);
                        
                        const walk = (node, depth) => {
                            if (depth > 20) return;  // Safety limit
                            if (node.nodeType === 3) {  // Text node
                                const t = node.textContent?.replace(/\s+/g, ' ').trim();
                                if (t && t.length > 1) lines.push(t);
                                return;
                            }
                            if (node.nodeType !== 1) return;
                            if (skipTags.has(node.tagName)) return;
                            
                            // BR = force line break
                            if (node.tagName === 'BR') { lines.push(''); return; }
                            
                            // For leaf block elements (no block children), get their text directly
                            if (blockTags.has(node.tagName)) {
                                const hasBlockChild = Array.from(node.children).some(c => blockTags.has(c.tagName));
                                if (!hasBlockChild) {
                                    // Leaf block — get its text as one line
                                    const t = node.innerText?.replace(/\s+/g, ' ').trim();
                                    if (t && t.length > 1) {
                                        const prefix = listTags.has(node.tagName) ? '• ' : '';
                                        lines.push(prefix + t);
                                    }
                                    return;
                                }
                            }
                            
                            // Recurse into children
                            for (const child of node.childNodes) walk(child, depth + 1);
                        };
                        
                        walk(el, 0);
                        
                        // Clean up: remove duplicate consecutive lines, collapse empty lines
                        const cleaned = [];
                        let prevLine = '';
                        for (const line of lines) {
                            const trimmed = line.trim();
                            if (trimmed === prevLine) continue;  // Skip exact duplicates
                            if (trimmed === '' && (cleaned.length === 0 || cleaned[cleaned.length-1] === '')) continue;  // Collapse empty lines
                            cleaned.push(trimmed);
                            prevLine = trimmed;
                        }
                        
                        return cleaned.join('\\n').replace(/\\n{3,}/g, '\\n\\n').trim();
                    };
                    
                    // Extract links
                    const getLinks = (el) => {
                        const links = [];
                        const seen = new Set();
                        el.querySelectorAll('a[href]').forEach(a => {
                            let href = a.href || a.getAttribute('href');
                            if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
                            if (!href.startsWith('http')) href = new URL(href, baseUrl).href;
                            if (!seen.has(href)) {
                                seen.add(href);
                                links.push({url: href, title: a.textContent?.trim() || ''});
                            }
                        });
                        return links;
                    };
                    
                    // Check for expandable/clickable children
                    const expandables = container ? container.querySelectorAll(
                        '[role="button"], [aria-expanded], [class*="accordion"], [class*="Accordion"], ' +
                        '[class*="collapse"], [class*="expand"], [class*="toggle"], details > summary, ' +
                        '[class*="card-click"], [class*="clickable"], [class*="tile"], [class*="Tile"], ' +
                        '[class*="advantage-item"], [class*="feature-item"], [class*="benefit-item"], ' +
                        '[data-toggle], [class*="slider-item"], [class*="swiper-slide"]'
                    ) : [];
                    
                    sections.push({
                        heading: text,
                        content: container ? getTextWithBreaks(container) : '',
                        links: container ? getLinks(container) : [],
                        is_expandable: expandables.length >= 2,
                        expandable_count: expandables.length,
                        container_selector: container ? _buildSelector(container) : null,
                    });
                });
                
                // Helper to build a CSS selector for an element
                function _buildSelector(el) {
                    if (el.id) return '#' + el.id;
                    let path = el.tagName.toLowerCase();
                    if (el.className) {
                        const cls = el.className.split(' ').filter(c => c && !c.includes('active') && !c.includes('open')).slice(0, 2).join('.');
                        if (cls) path += '.' + cls;
                    }
                    // Add nth-child for uniqueness
                    if (el.parentElement) {
                        const siblings = Array.from(el.parentElement.children).filter(s => s.tagName === el.tagName);
                        if (siblings.length > 1) {
                            const idx = siblings.indexOf(el) + 1;
                            path += ':nth-of-type(' + idx + ')';
                        }
                    }
                    return path;
                }
                
                return sections;
            }''', url)

            logger.info(f"[Interactive] Found {len(initial_sections)} sections, "
                        f"{sum(1 for s in initial_sections if s.get('is_expandable'))} expandable")

            # ---- PHASE 2: Click expandable sections to reveal hidden content ----
            for section in initial_sections:
                if not section.get('is_expandable'):
                    result["sections"].append({
                        "heading": section["heading"],
                        "content": section.get("content", ""),
                        "links": section.get("links", []),
                        "is_expandable": False,
                        "sub_sections": [],
                    })
                    continue

                logger.info(f"[Interactive] Expanding '{section['heading'][:50]}' ({section['expandable_count']} items)")

                # Click each expandable item and capture content
                sub_sections = await _expand_section_items(page, section, url)

                result["sections"].append({
                    "heading": section["heading"],
                    "content": section.get("content", ""),
                    "links": section.get("links", []),
                    "is_expandable": True,
                    "sub_sections": sub_sections,
                })

            # ---- PHASE 3: Get final full HTML after all expansions ----
            result["full_html"] = await page.content()

            await browser.close()

            total_subs = sum(len(s.get("sub_sections", [])) for s in result["sections"])
            logger.info(f"[Interactive] Complete: {len(result['sections'])} sections, {total_subs} sub-sections from {url[:60]}")

    except Exception as e:
        logger.error(f"[Interactive] Failed for {url[:60]}: {e}")
        import traceback
        traceback.print_exc()

    return result


async def _smart_scroll(page) -> None:
    """Scroll the page to trigger lazy loading."""
    try:
        last_height = 0
        for _ in range(15):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == last_height:
                break
            last_height = current_height
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            try:
                await page.wait_for_load_state("networkidle", timeout=2000)
            except:
                pass
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(500)
    except Exception as e:
        logger.warning(f"[Interactive] Scroll error: {e}")


async def _expand_section_items(page, section: Dict, base_url: str) -> List[Dict]:
    """
    Find and click expandable items within a section container.
    After each click, capture the revealed content and links.
    """
    sub_sections = []

    try:
        # Use JS to find all clickable items in the section and click them one by one
        expandable_data = await page.evaluate('''(sectionHeading) => {
            // Find the heading element
            const headings = document.querySelectorAll('h2, h3');
            let targetH = null;
            for (const h of headings) {
                if (h.textContent?.trim() === sectionHeading) {
                    targetH = h;
                    break;
                }
            }
            if (!targetH) return {items: [], error: 'Heading not found'};
            
            // Find container
            let container = targetH.closest('section') || targetH.closest('[class*="section"]');
            if (!container) {
                let parent = targetH.parentElement;
                for (let i = 0; i < 5 && parent; i++) {
                    const cls = parent.className?.toLowerCase() || '';
                    if (cls.includes('section') || cls.includes('block') || cls.includes('wrapper') || 
                        cls.includes('advantage') || cls.includes('benefit') || cls.includes('module') ||
                        parent.tagName === 'SECTION') {
                        container = parent;
                        break;
                    }
                    parent = parent.parentElement;
                }
            }
            if (!container) return {items: [], error: 'Container not found'};
            
            // Find clickable items — broad selector covering many patterns
            const clickSelectors = [
                '[role="button"]', '[aria-expanded]',
                '[class*="accordion"]', '[class*="Accordion"]',
                '[class*="collapse"]', '[class*="expand"]',
                '[class*="toggle"]', 'details > summary',
                '[class*="card-click"]', '[class*="clickable"]',
                '[class*="tile"]', '[class*="Tile"]',
                '[class*="advantage"]', '[class*="feature"]',
                '[class*="benefit"]', '[class*="item"]',
                '[data-toggle]',
            ].join(', ');
            
            let clickables = Array.from(container.querySelectorAll(clickSelectors));
            
            // Filter to only direct children or near-surface elements (avoid deeply nested)
            // Also filter out items that are too small to be real tiles
            clickables = clickables.filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.width > 50 && rect.height > 20;
            });
            
            // Deduplicate: if a parent and child are both clickable, keep the parent
            const deduped = [];
            for (const el of clickables) {
                const isChild = clickables.some(other => other !== el && other.contains(el));
                if (!isChild) deduped.push(el);
            }
            
            return {
                items: deduped.map((el, i) => ({
                    index: i,
                    tag: el.tagName,
                    class: el.className?.substring(0, 80),
                    text: el.textContent?.trim().substring(0, 60),
                    ariaExpanded: el.getAttribute('aria-expanded'),
                    rect: el.getBoundingClientRect(),
                })),
                containerTag: container.tagName,
                containerClass: container.className?.substring(0, 80),
            };
        }''', section["heading"])

        items = expandable_data.get("items", [])
        if not items:
            logger.info(f"[Interactive] No clickable items found for '{section['heading'][:40]}'")
            return sub_sections

        logger.info(f"[Interactive] Found {len(items)} clickable items in '{section['heading'][:40]}'")

        # Click each item and capture the revealed content
        for item in items:
            try:
                sub = await _click_and_capture(page, section["heading"], item, base_url)
                if sub and sub.get("content"):
                    sub_sections.append(sub)
            except Exception as e:
                logger.warning(f"[Interactive] Click failed for item '{item.get('text', '')[:30]}': {e}")

    except Exception as e:
        logger.error(f"[Interactive] Expand error for '{section['heading'][:40]}': {e}")

    return sub_sections


async def _click_and_capture(page, section_heading: str, item: Dict, base_url: str) -> Optional[Dict]:
    """Click a single expandable item and capture the revealed content."""
    item_text = item.get("text", "")
    item_index = item.get("index", 0)

    try:
        # Click the item using JS (more reliable than Playwright click)
        click_result = await page.evaluate('''(args) => {
            const {sectionHeading, itemIndex} = args;
            
            // Re-find the container and clickable items
            const headings = document.querySelectorAll('h2, h3');
            let container = null;
            for (const h of headings) {
                if (h.textContent?.trim() === sectionHeading) {
                    container = h.closest('section') || h.closest('[class*="section"]');
                    if (!container) {
                        let parent = h.parentElement;
                        for (let i = 0; i < 5 && parent; i++) {
                            const cls = parent.className?.toLowerCase() || '';
                            if (cls.includes('section') || cls.includes('block') || cls.includes('wrapper') || 
                                cls.includes('advantage') || cls.includes('benefit') || cls.includes('module') ||
                                parent.tagName === 'SECTION') {
                                container = parent;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                    }
                    break;
                }
            }
            if (!container) return {error: 'Container not found'};
            
            const clickSelectors = [
                '[role="button"]', '[aria-expanded]',
                '[class*="accordion"]', '[class*="Accordion"]',
                '[class*="collapse"]', '[class*="expand"]',
                '[class*="toggle"]', 'details > summary',
                '[class*="card-click"]', '[class*="clickable"]',
                '[class*="tile"]', '[class*="Tile"]',
                '[class*="advantage"]', '[class*="feature"]',
                '[class*="benefit"]', '[class*="item"]',
                '[data-toggle]',
            ].join(', ');
            
            let clickables = Array.from(container.querySelectorAll(clickSelectors))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 50 && rect.height > 20;
                });
            const deduped = clickables.filter(el => !clickables.some(o => o !== el && o.contains(el)));
            
            if (itemIndex >= deduped.length) return {error: 'Item index out of range'};
            
            const target = deduped[itemIndex];
            
            // Get content BEFORE click for comparison
            const beforeHTML = container.innerHTML.length;
            
            // Click
            target.click();
            
            return {
                clicked: true,
                targetText: target.textContent?.trim().substring(0, 60),
                beforeHTML: beforeHTML,
            };
        }''', {"sectionHeading": section_heading, "itemIndex": item_index})

        if click_result.get("error"):
            return None

        # Wait for expansion animation
        await page.wait_for_timeout(800)

        # Now capture the expanded content
        expanded = await page.evaluate('''(args) => {
            const {sectionHeading, itemIndex} = args;
            
            const headings = document.querySelectorAll('h2, h3');
            let container = null;
            for (const h of headings) {
                if (h.textContent?.trim() === sectionHeading) {
                    container = h.closest('section') || h.closest('[class*="section"]');
                    if (!container) {
                        let parent = h.parentElement;
                        for (let i = 0; i < 5 && parent; i++) {
                            const cls = parent.className?.toLowerCase() || '';
                            if (cls.includes('section') || cls.includes('block') || cls.includes('wrapper') || 
                                cls.includes('advantage') || cls.includes('benefit') || cls.includes('module') ||
                                parent.tagName === 'SECTION') {
                                container = parent;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                    }
                    break;
                }
            }
            if (!container) return null;
            
            // Find newly visible/expanded content
            // Look for: aria-expanded="true" panels, visible collapse panels, modal/drawer content
            const expandedPanels = container.querySelectorAll(
                '[aria-expanded="true"], [class*="show"], [class*="open"], [class*="active"], ' +
                '[class*="expanded"], [style*="display: block"], [style*="height: auto"], ' +
                'details[open], [class*="panel"]:not([hidden])'
            );
            
            // Also look for any newly visible content near the clicked item
            const clickSelectors = [
                '[role="button"]', '[aria-expanded]',
                '[class*="accordion"]', '[class*="tile"]',
                '[class*="advantage"]', '[class*="feature"]',
                '[class*="benefit"]', '[class*="item"]',
                '[data-toggle]',
            ].join(', ');
            
            let clickables = Array.from(container.querySelectorAll(clickSelectors))
                .filter(el => el.getBoundingClientRect().width > 50 && el.getBoundingClientRect().height > 20);
            const deduped = clickables.filter(el => !clickables.some(o => o !== el && o.contains(el)));
            
            const clickedEl = deduped[itemIndex];
            
            // Collect content from the clicked item's expanded area
            const getTextWithBreaks = (el) => {
                const lines = [];
                const blockTags = new Set(['DIV','P','LI','H4','H5','H6','TR','DT','DD','SECTION','ARTICLE','BLOCKQUOTE','FIGCAPTION']);
                const listTags = new Set(['LI','DT','DD']);
                const skipTags = new Set(['SCRIPT','STYLE','NAV','SVG','NOSCRIPT']);
                
                const walk = (node, depth) => {
                    if (depth > 20) return;
                    if (node.nodeType === 3) {
                        const t = node.textContent?.replace(/\s+/g, ' ').trim();
                        if (t && t.length > 1) lines.push(t);
                        return;
                    }
                    if (node.nodeType !== 1) return;
                    if (skipTags.has(node.tagName)) return;
                    if (node.tagName === 'BR') { lines.push(''); return; }
                    
                    if (blockTags.has(node.tagName)) {
                        const hasBlockChild = Array.from(node.children).some(c => blockTags.has(c.tagName));
                        if (!hasBlockChild) {
                            const t = node.innerText?.replace(/\s+/g, ' ').trim();
                            if (t && t.length > 1) {
                                const prefix = listTags.has(node.tagName) ? '• ' : '';
                                lines.push(prefix + t);
                            }
                            return;
                        }
                    }
                    for (const child of node.childNodes) walk(child, depth + 1);
                };
                
                walk(el, 0);
                
                const cleaned = [];
                let prevLine = '';
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (trimmed === prevLine) continue;
                    if (trimmed === '' && (cleaned.length === 0 || cleaned[cleaned.length-1] === '')) continue;
                    cleaned.push(trimmed);
                    prevLine = trimmed;
                }
                return cleaned.join('\\n').replace(/\\n{3,}/g, '\\n\\n').trim();
            };
            
            const getLinks = (el) => {
                const links = [];
                const seen = new Set();
                el.querySelectorAll('a[href]').forEach(a => {
                    let href = a.href || a.getAttribute('href');
                    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:')) return;
                    if (!seen.has(href)) {
                        seen.add(href);
                        links.push({url: href, title: a.textContent?.trim() || ''});
                    }
                });
                return links;
            };
            
            // Strategy 1: Content from the clicked element's next sibling or associated panel
            let contentEl = null;
            if (clickedEl) {
                // Check aria-controls
                const controlsId = clickedEl.getAttribute('aria-controls');
                if (controlsId) {
                    contentEl = document.getElementById(controlsId);
                }
                // Check next sibling
                if (!contentEl) {
                    contentEl = clickedEl.nextElementSibling;
                }
                // Check parent's next sibling
                if (!contentEl || contentEl.textContent?.trim().length < 20) {
                    contentEl = clickedEl.parentElement?.nextElementSibling;
                }
                // Check for expanded panel within parent
                if (!contentEl || contentEl.textContent?.trim().length < 20) {
                    const parent = clickedEl.closest('[class*="accordion-item"]') || 
                                   clickedEl.closest('[class*="tile"]') ||
                                   clickedEl.parentElement;
                    if (parent) {
                        const panel = parent.querySelector('[class*="panel"], [class*="content"], [class*="body"], [class*="collapse"]');
                        if (panel && panel.textContent?.trim().length > 20) {
                            contentEl = panel;
                        }
                    }
                }
            }
            
            // Strategy 2: Get the largest newly visible panel
            if (!contentEl || contentEl.textContent?.trim().length < 20) {
                let maxLen = 0;
                for (const panel of expandedPanels) {
                    const len = panel.textContent?.trim().length || 0;
                    if (len > maxLen) {
                        maxLen = len;
                        contentEl = panel;
                    }
                }
            }
            
            if (!contentEl) return null;
            
            return {
                title: clickedEl?.querySelector('h3, h4, h5, strong, [class*="title"]')?.textContent?.trim() 
                       || clickedEl?.textContent?.trim().substring(0, 60) || '',
                content: getTextWithBreaks(contentEl),
                links: getLinks(contentEl),
                contentLength: contentEl.textContent?.trim().length || 0,
            };
        }''', {"sectionHeading": section_heading, "itemIndex": item_index})

        if expanded and expanded.get("content"):
            logger.info(f"[Interactive]   Item {item_index}: '{expanded.get('title', '')[:40]}' → {expanded.get('contentLength', 0)} chars, {len(expanded.get('links', []))} links")
            return {
                "title": expanded.get("title", item_text[:60]),
                "content": expanded["content"],
                "links": expanded.get("links", []),
            }

    except Exception as e:
        logger.warning(f"[Interactive] Click+capture failed for item {item_index}: {e}")

    return None
