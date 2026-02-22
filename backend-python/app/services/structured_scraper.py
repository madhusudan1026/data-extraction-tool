"""
Structured Scraper Service

Intelligent hierarchical scraping with:
  - Depth 0: Bank-wide card discovery with summary benefits
  - Depth 1: Card detail page sectioned parsing (at_a_glance, benefits, requirements, fees)
  - Depth 2-3: Shared benefit pages with per-benefit sectioning and card cross-referencing
  - Automatic depth 0→3, user-approved beyond depth 3

Uses hybrid approach: CSS/HTML structure first, LLM refinement second, regex fallback.
"""

import re
import json
import logging
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


# ============= DEPTH 0: BANK-WIDE CARD DISCOVERY =============

async def discover_cards_structured(
    html: str,
    base_url: str,
    bank_key: str,
    bank_name: str,
    patterns: List[str],
    exclude: List[str],
) -> List[Dict[str, Any]]:
    """
    Parse bank cards listing page. For each card, extract:
    - card_name, card_url, card_image
    - summary_benefits (text visible on listing page per card)
    - card_network, card_tier
    """
    from app.core.banks import detect_card_metadata

    soup = BeautifulSoup(html, 'html.parser')
    cards = []
    seen_urls = set()

    # Strategy 1: Find card containers (common patterns in bank sites)
    card_containers = _find_card_containers(soup)

    if card_containers:
        for container in card_containers:
            card = _parse_card_container(container, base_url, patterns, exclude, seen_urls)
            if card:
                meta = detect_card_metadata(card["name"], card["url"])
                card["card_network"] = meta["card_network"]
                card["card_tier"] = meta["card_tier"]
                card["bank_key"] = bank_key
                card["bank_name"] = bank_name
                cards.append(card)
                seen_urls.add(card["url"])

    # Strategy 2: Fallback to href pattern matching (existing approach)
    if not cards:
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
            href = match.group(1)
            if any(exc in href.lower() for exc in exclude):
                continue
            for pattern in patterns:
                if re.search(pattern, href, re.IGNORECASE):
                    full_url = href if href.startswith('http') else urljoin(base_url, href) if href.startswith('/') else None
                    if full_url and full_url not in seen_urls:
                        seen_urls.add(full_url)
                        name_match = re.search(r'/([^/]+?)(?:-credit)?-card[s]?/?$', full_url, re.IGNORECASE)
                        card_name = name_match.group(1).replace('-', ' ').title() if name_match else "Unknown Card"
                        meta = detect_card_metadata(f"{card_name} Credit Card", full_url)
                        cards.append({
                            "name": f"{card_name} Credit Card",
                            "url": full_url,
                            "image_url": None,
                            "summary_benefits": "",
                            "card_network": meta["card_network"],
                            "card_tier": meta["card_tier"],
                            "bank_key": bank_key,
                            "bank_name": bank_name,
                        })
                    break

    logger.info(f"[Structured] Depth 0: Discovered {len(cards)} cards from {base_url}")
    return cards


def _find_card_containers(soup: BeautifulSoup) -> List[Tag]:
    """Find HTML containers that represent individual cards on a listing page."""
    candidates = []

    # Common CSS patterns for card listing items
    selectors = [
        '[class*="card-item"]', '[class*="card-block"]', '[class*="card-tile"]',
        '[class*="product-card"]', '[class*="credit-card"]', '[class*="card-wrapper"]',
        '[class*="card-box"]', '[class*="cardItem"]', '[class*="card-listing"]',
        '.swiper-slide', '[class*="slider-item"]',
    ]

    for sel in selectors:
        found = soup.select(sel)
        if len(found) >= 2:  # At least 2 to be a card listing
            candidates.extend(found)
            break

    # Fallback: look for repeated structures with card links
    if not candidates:
        for tag_name in ['article', 'li', 'div']:
            items = soup.find_all(tag_name)
            # Group by parent and class similarity
            parent_groups = {}
            for item in items:
                if item.parent and item.find('a', href=True):
                    key = (id(item.parent), item.get('class', [''])[0] if item.get('class') else '')
                    if key not in parent_groups:
                        parent_groups[key] = []
                    parent_groups[key].append(item)
            # Pick the group with most items (likely the card list)
            for key, group in sorted(parent_groups.items(), key=lambda x: -len(x[1])):
                if len(group) >= 3:
                    candidates = group
                    break
            if candidates:
                break

    return candidates


def _parse_card_container(container: Tag, base_url: str, patterns: List[str], exclude: List[str], seen: set) -> Optional[Dict]:
    """Extract card info from a single card container element."""
    # Find card link
    link = container.find('a', href=True)
    if not link:
        return None

    href = link['href']
    if any(exc in href.lower() for exc in exclude):
        return None

    # Check if URL matches card patterns
    url_matches = not patterns  # If no patterns, accept all
    for pattern in patterns:
        if re.search(pattern, href, re.IGNORECASE):
            url_matches = True
            break
    if not url_matches:
        return None

    full_url = href if href.startswith('http') else urljoin(base_url, href) if href.startswith('/') else None
    if not full_url or full_url in seen:
        return None

    # Extract card name
    # Priority: aria-label > title attr > heading inside > link text > URL
    name = (link.get('aria-label') or link.get('title') or '')
    if not name:
        heading = container.find(['h2', 'h3', 'h4', 'h5'])
        if heading:
            name = heading.get_text(strip=True)
    if not name:
        name = link.get_text(strip=True)
    if not name or len(name) < 3:
        name_match = re.search(r'/([^/]+?)(?:-credit)?-card[s]?/?$', full_url, re.IGNORECASE)
        name = name_match.group(1).replace('-', ' ').title() + " Credit Card" if name_match else "Unknown Card"

    # Extract image
    img = container.find('img')
    image_url = None
    if img:
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or ''
        if src:
            image_url = src if src.startswith('http') else urljoin(base_url, src)

    # Extract summary benefits text (text within the container excluding the name)
    summary = ""
    text_elements = container.find_all(['p', 'span', 'li', 'div'])
    benefit_texts = []
    for el in text_elements:
        text = el.get_text(strip=True)
        if text and text != name and len(text) > 10 and len(text) < 500:
            benefit_texts.append(text)
    summary = " | ".join(benefit_texts[:5])  # Keep first 5 text snippets

    return {
        "name": name.strip(),
        "url": full_url,
        "image_url": image_url,
        "summary_benefits": summary,
    }


# ============= DEPTH 1: CARD DETAIL PAGE SECTIONING =============

async def parse_card_detail_page(
    html: str,
    url: str,
    card_name: str,
    ollama_client=None,
) -> List[Dict[str, Any]]:
    """
    Parse a card's detail page into named sections.
    
    Priority 1: CSS/HTML structure (headings, sections, tabs)
    Priority 2: LLM refinement if available
    
    Returns list of sections: [{section_name, content, section_type}]
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove scripts, styles, nav, footer, boilerplate
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg', 'iframe']):
        tag.decompose()
    for sel in ['[class*="cookie"]', '[class*="popup"]', '[class*="modal"]', '[class*="menu"]',
                '[class*="navbar"]', '[class*="footer"]', '[class*="sidebar"]']:
        for tag in soup.select(sel):
            tag.decompose()

    # Find main content area
    main_content = (
        soup.find('main') or
        soup.find('[role="main"]') or
        soup.find('[class*="main-content"]') or
        soup.find('[class*="page-content"]') or
        soup.find('article') or
        soup
    )

    sections = []

    # Strategy 1: Find sections by headings (h2, h3) — includes per-section links
    sections = _extract_sections_by_headings(main_content, url)

    # Strategy 2: Find tab panels / accordion sections
    if len(sections) < 2:
        tab_sections = _extract_tab_sections(main_content)
        if tab_sections:
            sections = tab_sections

    # Strategy 3: Find by common CSS class patterns
    if len(sections) < 2:
        css_sections = _extract_sections_by_css(main_content)
        if css_sections:
            sections = css_sections

    # Strategy 4: LLM-based sectioning (if previous strategies found too few sections)
    if len(sections) < 3 and ollama_client:
        try:
            plain_text = main_content.get_text(separator='\n', strip=True)
            llm_sections = await _llm_section_content(plain_text[:4000], card_name, ollama_client)
            if llm_sections and len(llm_sections) > len(sections):
                sections = llm_sections
        except Exception as e:
            logger.warning(f"[Structured] LLM sectioning failed for {card_name}: {e}")

    # Fallback: single section with all text
    if not sections:
        text = main_content.get_text(separator='\n', strip=True)
        if text:
            sections = [{"section_name": "overview", "content": text[:5000], "section_type": "general"}]

    # Classify section types and ensure links array exists
    for sec in sections:
        sec["section_type"] = _classify_section(sec["section_name"], sec["content"])
        if "links" not in sec:
            sec["links"] = []

    # ---- BUILD DISCOVERED URLs FROM SECTIONS FIRST ----
    # This ensures every URL is mapped to its source section
    all_discovered_urls = []
    seen_urls = set()

    for sec in sections:
        for link in sec.get("links", []):
            link_url = link.get("url", "")
            if not link_url or link_url in seen_urls:
                continue
            seen_urls.add(link_url)
            # Apply relevance filter
            is_relevant = _is_relevant_link(link_url, link.get("title", ""))
            if is_relevant:
                all_discovered_urls.append({
                    "url": link_url,
                    "title": link.get("title", ""),
                    "url_type": "pdf" if '.pdf' in link_url.lower() else "web",
                    "is_relevant": True,
                    "source_section": sec["section_name"],
                })

    # Supplement with page-wide scan for links NOT already captured by sections
    page_wide_links = _extract_links_from_soup(main_content if main_content != soup else soup, url)
    for link in page_wide_links:
        if link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            link["source_section"] = "_unassigned"
            all_discovered_urls.append(link)

    logger.info(f"[Structured] Depth 1: {len(sections)} sections, {len(all_discovered_urls)} links ({len(all_discovered_urls) - len([u for u in all_discovered_urls if u.get('source_section') == '_unassigned'])} mapped) from {card_name}")
    return sections, all_discovered_urls



def _extract_sections_by_headings(soup: BeautifulSoup, base_url: str = "") -> List[Dict]:
    """
    Extract sections using h2/h3 headings as delimiters.
    
    Handles modern bank sites where headings are wrapped in sub-divs:
    1. Try sibling traversal first (traditional heading-content pattern)
    2. If no content found, walk UP to find the section container (parent/grandparent)
       that holds both the heading and its associated content
    3. Extract text with proper line breaks between elements
    4. Capture all links within the section container
    """
    sections = []
    headings = soup.find_all(['h2', 'h3'])
    used_containers = set()  # Track containers to avoid duplicate content

    for i, heading in enumerate(headings):
        name = heading.get_text(strip=True)
        if not name or len(name) < 2 or len(name) > 200:
            continue

        content_parts = []
        section_links = []

        # ---- Strategy A: Sibling traversal ----
        sibling = heading.find_next_sibling()
        while sibling:
            if sibling.name in ['h2', 'h3']:
                break
            if hasattr(sibling, 'get_text'):
                _collect_text_with_breaks(sibling, content_parts)
                _collect_links(sibling, section_links, base_url)
            sibling = sibling.find_next_sibling()

        # ---- Strategy B: Container walk-up ----
        # If siblings yielded little content, look at parent containers
        if len(content_parts) < 2 or not section_links:
            # Walk up to find a meaningful container
            container = _find_section_container(heading)
            if container and id(container) not in used_containers:
                used_containers.add(id(container))
                container_parts = []
                container_links = []
                
                # Get all content from container EXCEPT the heading itself
                for child in container.descendants:
                    if child == heading:
                        continue
                    if hasattr(child, 'name'):
                        # Skip nested headings (they'll be their own sections)
                        if child.name in ['h2', 'h3'] and child != heading:
                            continue
                        _collect_links_single(child, container_links, base_url)

                _collect_text_with_breaks(container, container_parts)
                # Remove the heading text from content
                if container_parts and name in container_parts[0]:
                    container_parts[0] = container_parts[0].replace(name, '', 1).strip()

                # Use container content if it's richer
                if len(container_parts) > len(content_parts) or len(container_links) > len(section_links):
                    content_parts = container_parts if len(container_parts) > len(content_parts) else content_parts
                    section_links = container_links if len(container_links) > len(section_links) else section_links

        # Deduplicate links
        seen_link_urls = set()
        deduped_links = []
        for lnk in section_links:
            if lnk["url"] not in seen_link_urls:
                seen_link_urls.add(lnk["url"])
                deduped_links.append(lnk)
        section_links = deduped_links

        content = _clean_section_text('\n'.join(p for p in content_parts if p.strip()))
        if content and len(content) > 20:
            sections.append({
                "section_name": _normalize_section_name(name),
                "content": content,
                "section_type": "general",
                "heading_text": name,
                "links": section_links,
            })

    return sections


def _find_section_container(heading: Tag) -> Optional[Tag]:
    """
    Walk up from a heading to find the section/container that holds
    both the heading and its associated content.
    
    Looks for: <section>, <div> with section-like classes, or any parent
    that has significantly more content than just the heading.
    """
    section_indicators = [
        'section', 'block', 'container', 'wrapper', 'module',
        'feature', 'benefit', 'advantage', 'card-detail', 'content-area',
    ]

    current = heading.parent
    for _ in range(5):  # Walk up max 5 levels
        if not current or current.name in ['body', 'main', 'html', '[document]']:
            break

        # Check if this is a section-like container
        classes = ' '.join(current.get('class', [])).lower()
        tag_name = current.name or ''

        is_section = (
            tag_name == 'section' or
            any(ind in classes for ind in section_indicators) or
            current.get('role') == 'region'
        )

        # Also check: does this container have links that siblings don't?
        container_links = len(current.find_all('a', href=True))
        heading_sibling_links = 0
        sib = heading.find_next_sibling()
        while sib and sib.name not in ['h2', 'h3']:
            if hasattr(sib, 'find_all'):
                heading_sibling_links += len(sib.find_all('a', href=True))
            sib = sib.find_next_sibling()

        if is_section or (container_links > heading_sibling_links + 1):
            return current

        current = current.parent

    return None


def _collect_text_with_breaks(element: Tag, parts: List[str], depth: int = 0):
    """
    Extract text from an element with proper line breaks.
    Uses leaf-block strategy: only extract text from block elements that
    have NO block children (leaf blocks). This prevents duplication where
    a parent div's text includes all child divs' text.
    """
    if depth > 20:
        return

    if not hasattr(element, 'children'):
        text = re.sub(r'\s+', ' ', str(element)).strip()
        if text and len(text) > 1:
            parts.append(text)
        return

    block_tags = {'div', 'p', 'li', 'h4', 'h5', 'h6', 'tr', 'dt', 'dd',
                  'article', 'section', 'blockquote', 'figcaption'}
    list_tags = {'li', 'dt', 'dd'}
    skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'svg', 'noscript', 'iframe'}

    for child in element.children:
        if not hasattr(child, 'name') or not child.name:
            # Text node
            text = re.sub(r'\s+', ' ', str(child)).strip()
            if text and len(text) > 1:
                parts.append(text)
            continue

        if child.name in skip_tags:
            continue

        if child.name == 'br':
            parts.append('')
            continue

        if child.name in ['ul', 'ol', 'dl']:
            for item in child.find_all(['li', 'dt', 'dd'], recursive=False):
                text = re.sub(r'\s+', ' ', item.get_text(strip=True))
                if text:
                    parts.append(f"• {text}")
            continue

        if child.name == 'table':
            for row in child.find_all('tr'):
                cells = [re.sub(r'\s+', ' ', td.get_text(strip=True)) for td in row.find_all(['td', 'th'])]
                cells = [c for c in cells if c]
                if cells:
                    parts.append(' | '.join(cells))
            continue

        if child.name in block_tags:
            # Check if this is a leaf block (no block children)
            has_block_child = any(
                hasattr(gc, 'name') and gc.name in block_tags
                for gc in (child.children if hasattr(child, 'children') else [])
            )
            if not has_block_child:
                # Leaf block — get its text as one clean line
                text = re.sub(r'\s+', ' ', child.get_text(strip=True))
                if text and len(text) > 1:
                    prefix = '• ' if child.name in list_tags else ''
                    parts.append(prefix + text)
            else:
                # Has block children — recurse
                _collect_text_with_breaks(child, parts, depth + 1)
        else:
            # Inline element — recurse
            _collect_text_with_breaks(child, parts, depth + 1)


def _collect_links(element: Tag, links: List[Dict], base_url: str):
    """Collect all links from an element tree."""
    if not hasattr(element, 'find_all'):
        return
    for a_tag in element.find_all('a', href=True):
        _collect_links_single(a_tag, links, base_url)


def _collect_links_single(element: Tag, links: List[Dict], base_url: str):
    """Collect a link if the element is an <a> tag."""
    if element.name != 'a':
        return
    href = element.get('href', '')
    if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
        return
    full = href if href.startswith('http') else urljoin(base_url, href) if base_url else href
    link_text = element.get_text(strip=True)
    links.append({"url": full, "title": link_text})


def _extract_tab_sections(soup: BeautifulSoup) -> List[Dict]:
    """Extract content from tab panels or accordions."""
    sections = []

    # Tab panels
    tab_panels = soup.select('[role="tabpanel"], .tab-pane, [class*="tab-content"], [class*="tabPanel"]')
    tab_buttons = soup.select('[role="tab"], .nav-tab, [class*="tab-btn"], [class*="tabButton"]')

    if tab_panels:
        for i, panel in enumerate(tab_panels):
            text = panel.get_text(separator='\n', strip=True)
            if not text or len(text) < 20:
                continue
            # Try to find matching tab label
            label = tab_buttons[i].get_text(strip=True) if i < len(tab_buttons) else f"Section {i+1}"
            sections.append({
                "section_name": _normalize_section_name(label),
                "content": text,
                "section_type": "general",
            })

    # Accordions
    if not sections:
        accordion_items = soup.select('[class*="accordion"], [class*="collapse"], details')
        for item in accordion_items:
            summary = item.find(['summary', '[class*="accordion-header"]', 'button'])
            label = summary.get_text(strip=True) if summary else ""
            content = item.get_text(separator='\n', strip=True)
            # Remove the label from content
            if label and content.startswith(label):
                content = content[len(label):].strip()
            if content and len(content) > 20:
                sections.append({
                    "section_name": _normalize_section_name(label or f"Section {len(sections)+1}"),
                    "content": content,
                    "section_type": "general",
                })

    return sections


def _extract_sections_by_css(soup: BeautifulSoup) -> List[Dict]:
    """Extract sections by common CSS class patterns."""
    sections = []
    selectors = [
        '[class*="section"]', '[class*="block"]', '[class*="feature"]',
        '[class*="benefit"]', '[class*="overview"]', '[class*="detail"]',
    ]
    for sel in selectors:
        items = soup.select(sel)
        for item in items:
            heading = item.find(['h2', 'h3', 'h4'])
            label = heading.get_text(strip=True) if heading else ""
            text = item.get_text(separator='\n', strip=True)
            if text and len(text) > 50 and len(text) < 5000:
                sections.append({
                    "section_name": _normalize_section_name(label or f"section_{len(sections)+1}"),
                    "content": text,
                    "section_type": "general",
                })
        if len(sections) >= 3:
            break

    return sections


async def _llm_section_content(text: str, card_name: str, ollama_client) -> List[Dict]:
    """Use LLM to identify and extract named sections from page text."""
    # Truncate aggressively for small models
    text = text[:4000]
    prompt = f"""Extract sections from this credit card page. Output JSON only.

TEXT: {text}

Output format: {{"sections": [{{"section_name": "benefits", "content": "text...", "section_type": "benefits"}}]}}
Valid section_types: overview, benefits, requirements, fees, rewards, general"""

    try:
        result = await ollama_client.generate_json(prompt, timeout=30, num_predict=2000)
        if isinstance(result, list):
            return [s for s in result if isinstance(s, dict) and s.get("content")]
        if isinstance(result, dict) and "sections" in result:
            return [s for s in result["sections"] if isinstance(s, dict) and s.get("content")]
    except Exception as e:
        logger.warning(f"[Structured] LLM section failed: {e}")
    return []


# ============= DEPTH 2-3: SHARED BENEFIT PAGES =============

async def parse_shared_benefit_page(
    html: str,
    url: str,
    all_card_names: List[str],
    bank_name: str = "",
    ollama_client=None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parse a shared benefit page (e.g. mastercard-benefits, airport-lounge-access).
    
    Sections the content into individual benefit blocks, each with:
    - benefit_name, benefit_text, benefit_category
    - eligible_card_names (cross-referenced against all_card_names)
    - conditions, validity
    - deeper_links (URLs to follow at next depth)
    
    Returns: (benefit_sections, discovered_urls)
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Remove scripts, styles, nav, footer, header, cookie banners
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'svg', 'iframe']):
        tag.decompose()
    # Remove common boilerplate containers
    for sel in ['[class*="cookie"]', '[class*="popup"]', '[class*="modal"]', '[class*="menu"]',
                '[class*="navbar"]', '[class*="footer"]', '[class*="sidebar"]', '[id*="menu"]']:
        for tag in soup.select(sel):
            tag.decompose()

    # Try to find the main content area to reduce noise
    main_content = (
        soup.find('main') or
        soup.find('[role="main"]') or
        soup.find('[class*="main-content"]') or
        soup.find('[class*="page-content"]') or
        soup.find('[class*="content-area"]') or
        soup.find('article') or
        soup
    )

    # Strategy 1: HTML-based benefit sectioning
    benefit_sections = _extract_benefit_blocks(main_content, all_card_names)
    logger.info(f"[Structured] HTML extraction found {len(benefit_sections)} benefits from {url[:60]}")

    # Strategy 2: LLM-based sectioning if HTML parsing found too few
    if len(benefit_sections) < 2 and ollama_client:
        try:
            plain_text = main_content.get_text(separator='\n', strip=True)
            # Limit to reasonable size for LLM
            plain_text = plain_text[:6000]
            llm_benefits = await _llm_extract_benefits(plain_text, all_card_names, bank_name, ollama_client)
            if llm_benefits and len(llm_benefits) > len(benefit_sections):
                logger.info(f"[Structured] LLM found {len(llm_benefits)} benefits (vs {len(benefit_sections)} from HTML)")
                benefit_sections = llm_benefits
        except Exception as e:
            logger.warning(f"[Structured] LLM benefit extraction failed for {url}: {e}")

    # Strategy 3: Regex-based benefit extraction (fallback)
    if len(benefit_sections) < 2:
        plain_text = main_content.get_text(separator='\n', strip=True)
        regex_benefits = _regex_extract_benefits(plain_text[:10000], all_card_names)
        if regex_benefits:
            logger.info(f"[Structured] Regex found {len(regex_benefits)} benefits")
            benefit_sections = regex_benefits

    # If still nothing, create a single section with card cross-referencing
    if not benefit_sections:
        text = main_content.get_text(separator='\n', strip=True)
        if text:
            eligible = _find_eligible_cards(text[:5000], all_card_names)
            benefit_sections = [{
                "benefit_name": _infer_benefit_name_from_url(url),
                "benefit_text": text[:5000],
                "benefit_category": _categorize_benefit(url, text),
                "eligible_card_names": eligible,
                "conditions": _extract_conditions(text[:3000]),
                "validity": _extract_validity(text[:3000]),
            }]

    # Extract deeper links
    discovered_urls = _extract_links_from_soup(main_content, url)

    logger.info(f"[Structured] Depth 2+: {len(benefit_sections)} benefits, {len(discovered_urls)} links from {url[:60]}")
    return benefit_sections, discovered_urls


def _extract_benefit_blocks(soup: BeautifulSoup, all_card_names: List[str]) -> List[Dict]:
    """Extract individual benefit blocks from HTML structure."""
    benefits = []

    # Strategy A: Find benefit containers by common CSS patterns
    container_selectors = [
        '[class*="benefit"]', '[class*="feature"]', '[class*="offer"]',
        '[class*="advantage"]', '[class*="perk"]', '[class*="card-benefit"]',
        '[class*="accordion-item"]', '[class*="collapse-item"]',
        '[class*="service-card"]', '[class*="info-card"]',
    ]
    containers = []
    for sel in container_selectors:
        found = soup.select(sel)
        if found and len(found) >= 2:
            containers = found
            break

    # Strategy B: Heading-delimited blocks (h2, h3, h4)
    if len(containers) < 2:
        containers = _heading_delimited_blocks(soup)

    # Strategy C: Text-block splitting from plain text
    if len(containers) < 2:
        plain = soup.get_text(separator='\n', strip=True)
        text_benefits = _split_text_into_benefit_blocks(plain, all_card_names)
        if text_benefits:
            return text_benefits

    for container in containers:
        heading = container.find(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])
        name = heading.get_text(strip=True) if heading else ""
        text = container.get_text(separator='\n', strip=True)

        if not text or len(text) < 20:
            continue
        # Skip if it's just navigation or boilerplate
        if len(text) < 30 and not name:
            continue

        eligible = _find_eligible_cards(text, all_card_names)
        conditions = _extract_conditions(text)
        validity = _extract_validity(text)

        benefits.append({
            "benefit_name": name or _infer_benefit_name_from_text(text),
            "benefit_text": text,
            "benefit_category": _categorize_benefit("", text),
            "eligible_card_names": eligible,
            "conditions": conditions,
            "validity": validity,
        })

    return benefits


def _heading_delimited_blocks(soup: BeautifulSoup) -> List[Tag]:
    """Build pseudo-containers by collecting content between headings."""
    from bs4 import NavigableString
    blocks = []
    headings = soup.find_all(['h2', 'h3', 'h4'])

    for heading in headings:
        name = heading.get_text(strip=True)
        if not name or len(name) < 3 or len(name) > 200:
            continue

        # Collect siblings until next heading
        content_parts = []
        sibling = heading.next_sibling
        while sibling:
            if hasattr(sibling, 'name') and sibling.name in ['h2', 'h3', 'h4']:
                break
            if hasattr(sibling, 'get_text'):
                t = sibling.get_text(strip=True)
                if t:
                    content_parts.append(t)
            elif isinstance(sibling, NavigableString):
                t = str(sibling).strip()
                if t:
                    content_parts.append(t)
            sibling = sibling.next_sibling

        if content_parts:
            # Create a fake container for uniform processing
            block = Tag(name='div')
            block.string = name + '\n' + '\n'.join(content_parts)
            blocks.append(block)

    return blocks


def _split_text_into_benefit_blocks(text: str, all_card_names: List[str]) -> List[Dict]:
    """
    Split plain text into benefit blocks using multiple heuristics:
    1. Look for "Eligible Cards:" patterns that separate benefits
    2. Look for title-like lines followed by description
    3. Split by double newlines with card name detection
    """
    benefits = []

    # Pattern 1: Split by "Eligible Cards:" sections — this is the most reliable
    # for Emirates NBD style pages
    eligible_pattern = re.compile(
        r'((?:^|\n)(.+?)\n(?:.*?\n)*?Eligible\s+Cards?\s*:\s*\n((?:\s*[\*\-•]\s*.+\n?)+))',
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(eligible_pattern.finditer(text))
    if matches:
        for m in matches:
            full_block = m.group(0).strip()
            # Extract benefit name from the first non-empty line before eligible cards
            block_lines = full_block.split('\n')
            name = ""
            desc_lines = []
            in_eligible = False
            eligible_lines = []

            for line in block_lines:
                line_stripped = line.strip()
                if re.match(r'^Eligible\s+Cards?\s*:', line_stripped, re.IGNORECASE):
                    in_eligible = True
                    continue
                if in_eligible:
                    card_line = line_stripped.lstrip('*-• ')
                    if card_line:
                        eligible_lines.append(card_line)
                else:
                    if not name and line_stripped and len(line_stripped) > 3:
                        name = line_stripped
                    elif line_stripped:
                        desc_lines.append(line_stripped)

            # Cross-reference eligible cards
            eligible = []
            for el in eligible_lines:
                for card_name in all_card_names:
                    if card_name.lower() in el.lower() or el.lower() in card_name.lower():
                        eligible.append(card_name)
                        break
                else:
                    eligible.append(el)  # Keep original name even if not in our list

            benefits.append({
                "benefit_name": name or "Unnamed Benefit",
                "benefit_text": '\n'.join(desc_lines) if desc_lines else full_block,
                "benefit_category": _categorize_benefit("", full_block),
                "eligible_card_names": eligible,
                "conditions": _extract_conditions(full_block),
                "validity": _extract_validity(full_block),
            })

    # Pattern 2: If no "Eligible Cards" found, split by double newlines
    if not benefits:
        blocks = re.split(r'\n{2,}', text)
        current_benefit = None

        for block in blocks:
            block = block.strip()
            if len(block) < 30:
                continue

            lines = block.split('\n')
            first_line = lines[0].strip()

            # Heuristic: if first line is short and title-like, treat as new benefit
            if len(first_line) < 100 and not first_line.endswith('.'):
                if current_benefit:
                    benefits.append(current_benefit)
                eligible = _find_eligible_cards(block, all_card_names)
                current_benefit = {
                    "benefit_name": first_line,
                    "benefit_text": '\n'.join(lines[1:]).strip(),
                    "benefit_category": _categorize_benefit("", block),
                    "eligible_card_names": eligible,
                    "conditions": _extract_conditions(block),
                    "validity": _extract_validity(block),
                }
            elif current_benefit:
                # Append to current benefit
                current_benefit["benefit_text"] += '\n' + block
                more_eligible = _find_eligible_cards(block, all_card_names)
                for ce in more_eligible:
                    if ce not in current_benefit["eligible_card_names"]:
                        current_benefit["eligible_card_names"].append(ce)

        if current_benefit:
            benefits.append(current_benefit)

    return benefits


async def _llm_extract_benefits(
    text: str,
    all_card_names: List[str],
    bank_name: str,
    ollama_client,
) -> List[Dict]:
    """Use LLM to extract and section benefits with card cross-referencing."""
    # Truncate for small models
    text = text[:6000]
    cards_str = ', '.join(all_card_names[:20])

    prompt = f"""Extract each credit card benefit from this text. Output JSON only.

CARDS: {cards_str}

TEXT: {text}

Output format: {{"benefits": [{{"benefit_name": "...", "benefit_text": "...", "benefit_category": "cashback", "eligible_card_names": ["card1"], "conditions": ["..."], "validity": ""}}]}}
Valid categories: cashback, lounge, golf, dining, travel, insurance, rewards, movie, fee, lifestyle, general"""

    try:
        result = await ollama_client.generate_json(prompt, timeout=60, num_predict=3000)
        if isinstance(result, list):
            return [b for b in result if isinstance(b, dict) and b.get("benefit_name")]
        if isinstance(result, dict) and "benefits" in result:
            return [b for b in result["benefits"] if isinstance(b, dict) and b.get("benefit_name")]
    except Exception as e:
        logger.warning(f"[Structured] LLM benefit extraction failed: {e}")
    return []


def _regex_extract_benefits(text: str, all_card_names: List[str]) -> List[Dict]:
    """Regex-based benefit extraction as fallback."""
    benefits = []

    # Split by double newlines or horizontal rules
    blocks = re.split(r'\n{3,}|_{5,}|-{5,}|={5,}', text)

    for block in blocks:
        block = block.strip()
        if len(block) < 50:
            continue

        # Check if this looks like a benefit block (has a title-like first line)
        lines = block.split('\n')
        first_line = lines[0].strip()
        if len(first_line) < 5 or len(first_line) > 200:
            continue

        eligible = _find_eligible_cards(block, all_card_names)
        category = _categorize_benefit("", block)

        benefits.append({
            "benefit_name": first_line,
            "benefit_text": block,
            "benefit_category": category,
            "eligible_card_names": eligible,
            "conditions": _extract_conditions(block),
            "validity": _extract_validity(block),
        })

    return benefits


# ============= CROSS-REFERENCING HELPERS =============

def _find_eligible_cards(text: str, all_card_names: List[str]) -> List[str]:
    """Find which cards are mentioned in text, especially in 'Eligible Cards' sections."""
    text_lower = text.lower()
    eligible = []

    for card_name in all_card_names:
        # Check exact name
        if card_name.lower() in text_lower:
            eligible.append(card_name)
            continue

        # Check partial match (without "Credit Card" suffix)
        short_name = re.sub(r'\s*credit\s*card[s]?\s*$', '', card_name, flags=re.IGNORECASE).strip()
        if short_name and len(short_name) > 4 and short_name.lower() in text_lower:
            eligible.append(card_name)

    return list(set(eligible))


def _extract_conditions(text: str) -> List[str]:
    """Extract condition/restriction bullet points."""
    conditions = []

    # Look for bullet points after condition-related keywords
    cond_pattern = re.compile(
        r'(?:conditions?|terms?|restrictions?|requirements?|eligib|note|important|disclaimer).*?[:]\s*(.*?)(?:\n\n|\Z)',
        re.IGNORECASE | re.DOTALL,
    )
    for match in cond_pattern.finditer(text):
        block = match.group(1)
        for line in block.split('\n'):
            line = line.strip().lstrip('•*-– ')
            if line and len(line) > 10:
                conditions.append(line)

    return conditions[:10]


def _extract_validity(text: str) -> str:
    """Extract validity/date range."""
    patterns = [
        r'[Vv]alidity[:\s]+(.+?)(?:\n|$)',
        r'[Vv]alid\s+(?:from|until|till)\s+(.+?)(?:\n|$)',
        r'(\d{1,2}\s+\w+\s+\d{4})\s*[-–]\s*(\d{1,2}\s+\w+\s+\d{4})',
        r'[Oo]ffer\s+(?:valid|period|ends?)\s*[:\s]+(.+?)(?:\n|$)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0).strip()
    return ""


def _categorize_benefit(url: str, text: str) -> str:
    """Categorize a benefit based on URL and text content."""
    combined = (url + " " + text).lower()

    categories = {
        'cashback': ['cashback', 'cash back', 'cash-back', '% back', 'wallet credit'],
        'lounge': ['lounge', 'airport', 'priority pass', 'dragonpass'],
        'golf': ['golf', 'green fee', 'tee time'],
        'dining': ['dining', 'restaurant', 'food', 'dine'],
        'travel': ['travel', 'hotel', 'booking.com', 'miles', 'flight'],
        'insurance': ['insurance', 'shield', 'protection', 'cover'],
        'rewards': ['reward', 'points', 'earn', 'redeem'],
        'movie': ['movie', 'cinema', 'theatre', 'vox', 'reel', 'novo'],
        'fee': ['fee', 'waiver', 'annual', 'interest rate', 'apr'],
        'lifestyle': ['lifestyle', 'valet', 'concierge', 'spa', 'fitness'],
    }

    for cat, keywords in categories.items():
        if any(kw in combined for kw in keywords):
            return cat
    return 'general'


def _clean_section_text(text: str) -> str:
    """
    Clean up extracted section text to be readable:
    - Collapse multiple blank lines to max one
    - Normalize whitespace within lines  
    - Remove duplicate/near-duplicate consecutive lines
    - Remove lines that are substrings of nearby lines (nested extraction artifacts)
    - Strip excessive Unicode whitespace
    """
    if not text:
        return ""

    # First pass: normalize all whitespace characters
    # Replace non-breaking spaces, zero-width chars, etc.
    text = re.sub(r'[\u00a0\u200b\u200c\u200d\ufeff]', ' ', text)
    # Collapse runs of spaces/tabs within lines (but preserve \n)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Collapse 3+ newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    lines = text.split('\n')
    cleaned = []
    prev_line = ''
    prev_nonempty = ''

    for line in lines:
        line = line.strip()

        # Skip empty lines if previous was also empty
        if not line:
            if cleaned and cleaned[-1] == '':
                continue
            cleaned.append('')
            prev_line = ''
            continue

        # Skip exact duplicate of previous line
        if line == prev_line:
            continue

        # Skip if this line is contained within the previous non-empty line
        # (artifact of extracting both parent and child text)
        if prev_nonempty and line in prev_nonempty and len(line) < len(prev_nonempty) * 0.9:
            continue

        # Skip if previous line is contained within this one
        # (keep the longer one — replace previous)
        if prev_nonempty and prev_nonempty in line and len(prev_nonempty) < len(line) * 0.9:
            if cleaned and cleaned[-1] == prev_nonempty:
                cleaned[-1] = line
                prev_line = line
                prev_nonempty = line
                continue

        cleaned.append(line)
        prev_line = line
        if line:
            prev_nonempty = line

    # Remove leading/trailing empty lines
    while cleaned and cleaned[0] == '':
        cleaned.pop(0)
    while cleaned and cleaned[-1] == '':
        cleaned.pop()

    result = '\n'.join(cleaned)
    
    # Final safety: collapse any remaining excessive blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result


def _normalize_section_name(name: str) -> str:
    """Normalize a heading into a section key."""
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name.lower().strip())
    name = re.sub(r'\s+', '_', name)
    return name[:50] or "unnamed"


def _classify_section(name: str, content: str) -> str:
    """Classify section type from name and content."""
    combined = (name + " " + content[:200]).lower()
    if any(w in combined for w in ['glance', 'overview', 'summary', 'highlight']):
        return 'overview'
    if any(w in combined for w in ['benefit', 'feature', 'advantage', 'perk']):
        return 'benefits'
    if any(w in combined for w in ['require', 'eligib', 'criteria', 'qualify']):
        return 'requirements'
    if any(w in combined for w in ['fee', 'charge', 'rate', 'annual', 'interest', 'apr']):
        return 'fees'
    if any(w in combined for w in ['reward', 'point', 'earn', 'redeem', 'program']):
        return 'rewards'
    return 'general'


def _infer_benefit_name_from_url(url: str) -> str:
    """Infer benefit name from URL path."""
    path = urlparse(url).path
    last_segment = path.rstrip('/').split('/')[-1]
    return last_segment.replace('-', ' ').replace('_', ' ').title()


def _infer_benefit_name_from_text(text: str) -> str:
    """Infer benefit name from first line of text."""
    first_line = text.split('\n')[0].strip()
    return first_line[:100] if first_line else "Unnamed Benefit"


def _is_relevant_link(url: str, title: str = "") -> bool:
    """Check if a link is relevant for credit card benefit extraction."""
    combined = (url + " " + title).lower()

    # Skip common non-benefit pages
    skip_keywords = [
        'apply-now', 'apply-online', 'login', 'sign-in', 'register',
        'contact-us', 'about-us', 'career', 'investor', 'press',
        'privacy', 'cookie', 'sitemap', 'faq', 'download-app',
        'locate-us', 'atm-locator', 'branch', 'customer-service',
    ]
    if any(kw in combined for kw in skip_keywords):
        return False

    # Relevant keywords
    relevant_keywords = [
        'benefit', 'feature', 'lounge', 'golf', 'cinema', 'movie', 'insurance',
        'shield', 'reward', 'offer', 'dining', 'travel', 'cashback', 'terms',
        'condition', 'fee', 'charge', 'learn-more', 'airport',
        'concierge', 'lifestyle', 'valet', 'points', 'miles', 'privilege',
        'discount', 'mastercard', 'visa', 'plus-points', 'activate',
        'earn', 'redeem', 'booking', 'hotel', 'spa', 'fitness',
    ]
    return any(kw in combined for kw in relevant_keywords)


def _extract_links_from_soup(soup: BeautifulSoup, base_url: str) -> List[Dict]:
    """Extract all relevant links from a page for deeper crawling."""
    parsed = urlparse(base_url)
    base_domain = parsed.netloc
    links = []
    seen = set()

    relevant_keywords = [
        'benefit', 'feature', 'lounge', 'golf', 'cinema', 'movie', 'insurance',
        'shield', 'reward', 'offer', 'dining', 'travel', 'cashback', 'terms',
        'condition', 'fee', 'charge', 'help', 'support', 'learn-more', 'airport',
        'concierge', 'lifestyle', 'valet',
    ]

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:'):
            continue

        full_url = href if href.startswith('http') else urljoin(base_url, href)

        # Same domain only
        if base_domain not in full_url:
            continue

        # Skip if same as current page
        if full_url.rstrip('/') == base_url.rstrip('/'):
            continue

        if full_url in seen:
            continue

        link_text = a_tag.get_text(strip=True)
        href_lower = href.lower()
        text_lower = link_text.lower() if link_text else ''

        is_relevant = any(kw in href_lower or kw in text_lower for kw in relevant_keywords)
        is_pdf = '.pdf' in href_lower

        if is_relevant or is_pdf:
            seen.add(full_url)
            links.append({
                "url": full_url,
                "title": link_text or "",
                "url_type": "pdf" if is_pdf else "web",
                "is_relevant": is_relevant,
            })

    return links


# ============= URL DEDUP REGISTRY =============

def hash_url(url: str) -> str:
    """Create a hash for URL-based dedup."""
    normalized = url.rstrip('/').lower()
    return hashlib.md5(normalized.encode()).hexdigest()
