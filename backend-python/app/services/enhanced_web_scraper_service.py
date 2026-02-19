"""
Enhanced Web Scraper Service for Credit Card Data Extraction.
Features:
- Deep link crawling (follows related links on the page)
- JavaScript rendering support via Playwright
- Structured content extraction (tables, lists, sections)
- PDF/document link detection and extraction
- Bank-specific parsing strategies
"""
from typing import Optional, List, Dict, Any, Set, Tuple
from urllib.parse import urljoin, urlparse
import asyncio
import re
import httpx
from bs4 import BeautifulSoup, Tag
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.exceptions import WebScraperError
from app.core.banks import detect_bank_from_url
from app.utils.logger import logger


@dataclass
class ExtractedSection:
    """Represents a structured section of content."""
    title: str
    content: str
    section_type: str  # 'benefit', 'fee', 'eligibility', 'merchant', 'terms', 'general'
    subsections: List['ExtractedSection'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedTable:
    """Represents a table extracted from the page."""
    headers: List[str]
    rows: List[List[str]]
    context: str  # surrounding text/title
    table_type: str  # 'cashback', 'fees', 'eligibility', 'merchants', 'benefits'


@dataclass
class ScrapedContent:
    """Complete scraped content from a URL."""
    url: str
    title: str
    raw_text: str
    structured_sections: List[ExtractedSection]
    tables: List[ExtractedTable]
    linked_content: Dict[str, str]  # url -> content from followed links
    pdf_links: List[str]
    metadata: Dict[str, Any]


class EnhancedWebScraperService:
    """Enhanced service for comprehensive web scraping of credit card pages."""

    # Bank-specific URL patterns for identifying related content
    # Bank-specific scraping configs (selectors, paths - NOT bank identity)
    SCRAPER_CONFIGS = {
        'emiratesnbd': {
            'base_domain': 'emiratesnbd.com',
            'related_paths': [
                r'/help-and-support/',
                r'/terms-and-conditions',
                r'/key-facts',
                r'/fee-schedule',
                r'/tariff',
                r'/-/media/.*\.pdf',
                r'/cards/.*benefit',
                r'/cards/.*feature',
                r'/cards/credit-shield',
            ],
            'content_selectors': [
                'main', '.content', '[class*="card"]', '[class*="benefit"]',
                '[class*="feature"]', '[class*="offer"]', '.rich-text',
                '[class*="accordion"]', '[class*="tab-content"]'
            ],
            'ignore_selectors': [
                'nav', 'footer', 'header', '.breadcrumb', '.mega-menu'
            ]
        },
        'bankfab': {
            'base_domain': 'bankfab.com',
            'related_paths': [
                r'/terms-and-conditions',
                r'/-/media/.*\.pdf',
                r'/help-and-support/',
                r'/personal/promotions/',
            ],
            'content_selectors': [
                'main', '.content-wrapper', '[class*="card-"]', '[class*="benefit"]',
                '[class*="cashback"]', '[class*="feature"]'
            ],
            'ignore_selectors': [
                'nav', 'footer', '.breadcrumb', '.social-icons'
            ]
        },
        'adcb': {
            'base_domain': 'adcb.com',
            'related_paths': [
                r'/personal/cards/',
                r'/credit-cards/',
                r'/key-facts',
                r'/terms',
                r'\.pdf$',
            ],
            'content_selectors': [
                'main', '.content', '[class*="card"]', '[class*="benefit"]',
                '[class*="feature"]'
            ],
            'ignore_selectors': [
                'nav', 'footer', 'header'
            ]
        },
        'mashreq': {
            'base_domain': 'mashreq.com',
            'related_paths': [
                r'/personal/cards/',
                r'/credit-cards/',
                r'/key-facts',
                r'\.pdf$',
            ],
            'content_selectors': [
                'main', '.content', '[class*="card"]', '[class*="benefit"]'
            ],
            'ignore_selectors': [
                'nav', 'footer', 'header'
            ]
        },
        'default': {
            'base_domain': '',
            'related_paths': [
                r'/terms',
                r'/conditions',
                r'/benefits',
                r'/features',
                r'/key-facts',
                r'/fee',
                r'/tariff',
                r'\.pdf$',
            ],
            'content_selectors': [
                'main', 'article', '.content', '#content', '[role="main"]'
            ],
            'ignore_selectors': [
                'nav', 'footer', 'header', '.sidebar', '.advertisement'
            ]
        }
    }

    # Keywords for identifying section types
    SECTION_KEYWORDS = {
        'benefit': ['benefit', 'reward', 'cashback', 'discount', 'offer', 'perk', 'privilege'],
        'entitlement': ['entitlement', 'complimentary', 'free', 'lounge', 'access', 'concierge'],
        'fee': ['fee', 'charge', 'rate', 'interest', 'annual', 'cost', 'price'],
        'eligibility': ['eligibility', 'requirement', 'criteria', 'qualify', 'minimum salary', 'income'],
        'merchant': ['merchant', 'partner', 'retailer', 'store', 'restaurant', 'vendor', 'outlet'],
        'terms': ['terms', 'condition', 'limitation', 'restriction', 'valid', 'expiry'],
    }

    def __init__(self):
        self.user_agent = getattr(settings, 'SCRAPER_USER_AGENT', 
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        self.timeout = getattr(settings, 'SCRAPER_TIMEOUT', 30)
        self.max_redirects = getattr(settings, 'SCRAPER_MAX_REDIRECTS', 10)
        self.retry_attempts = getattr(settings, 'SCRAPER_RETRY_ATTEMPTS', 3)
        self.max_deep_links = getattr(settings, 'SCRAPER_MAX_DEEP_LINKS', 10)  # Increased from 5
        self.max_content_length = getattr(settings, 'MAX_CONTENT_LENGTH', 80000)  # Increased from 50000

    def _get_bank_config(self, url: str) -> Dict[str, Any]:
        """Get bank-specific configuration based on URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        for bank_name, config in self.SCRAPER_CONFIGS.items():
            if bank_name != 'default' and config['base_domain'] in domain:
                logger.info(f"Using bank-specific config for: {bank_name}")
                return config
        
        return self.SCRAPER_CONFIGS['default']

    def _identify_section_type(self, text: str) -> str:
        """Identify the type of a section based on keywords."""
        text_lower = text.lower()
        
        for section_type, keywords in self.SECTION_KEYWORDS.items():
            if any(keyword in text_lower for keyword in keywords):
                return section_type
        
        return 'general'

    async def scrape_url_comprehensive(
        self,
        url: str,
        follow_links: bool = True,
        max_depth: int = 1,
        use_playwright: bool = True
    ) -> ScrapedContent:
        """
        Comprehensively scrape a URL with deep link following.

        Args:
            url: URL to scrape.
            follow_links: Whether to follow related links.
            max_depth: Maximum depth for link following.
            use_playwright: Use Playwright/Chromium for JavaScript rendering.

        Returns:
            ScrapedContent with all extracted data.

        Raises:
            WebScraperError: If scraping fails.
        """
        logger.info(f"Starting comprehensive scrape of: {url} (playwright={use_playwright}, depth={max_depth})")
        
        bank_config = self._get_bank_config(url)
        
        # Check if URL is a PDF
        is_pdf = url.lower().endswith('.pdf') or '/pdf/' in url.lower() or '.pdf?' in url.lower()
        
        if is_pdf:
            # Handle PDF URL directly
            logger.info(f"URL is a PDF, using PDF extraction service")
            try:
                from app.services.pdf_service import pdf_service
                pdf_text = await pdf_service.extract_text_from_url(url)
                
                # Extract title from filename or first line
                title = url.split('/')[-1].replace('.pdf', '').replace('-', ' ').replace('_', ' ').title()
                if pdf_text:
                    first_line = pdf_text.split('\n')[0].strip()
                    if first_line and len(first_line) < 100:
                        title = first_line
                
                return ScrapedContent(
                    url=url,
                    title=title,
                    raw_text=pdf_text or "",
                    structured_sections=[],
                    tables=[],
                    linked_content={},
                    pdf_links=[url],
                    metadata={
                        'scraped_at': asyncio.get_event_loop().time(),
                        'bank_detected': detect_bank_from_url(url) or 'unknown',
                        'source_type': 'pdf',
                        'content_length': len(pdf_text) if pdf_text else 0
                    }
                )
            except Exception as e:
                logger.error(f"PDF extraction failed for {url}: {str(e)}")
                raise WebScraperError(f"Failed to extract PDF: {str(e)}")
        
        # First, scrape the main page (HTML)
        main_soup, main_html = await self._fetch_and_parse(url, use_playwright=use_playwright)
        
        # Extract page title
        title = self._extract_title(main_soup)
        
        # Extract structured content
        raw_text = self._extract_clean_text(main_soup, bank_config)
        structured_sections = self._extract_sections(main_soup, bank_config)
        tables = self._extract_tables(main_soup)
        
        # Find and extract PDF links
        pdf_links = self._find_pdf_links(main_soup, url)
        
        # Find and follow related links
        linked_content = {}
        if follow_links and max_depth > 0:
            # Get links from HTML
            related_links = self._find_related_links(main_soup, url, bank_config)
            
            # Also extract links from text content (markdown-style links)
            text_links = self._extract_links_from_text(raw_text, url)
            for link in text_links:
                if link not in related_links:
                    related_links.append(link)
            
            logger.info(f"Found {len(related_links)} related links to follow")
            for link in related_links[:5]:  # Log first 5
                logger.info(f"  - {link}")
            
            if related_links:
                linked_content = await self._fetch_related_content(
                    related_links[:self.max_deep_links],
                    bank_config
                )
                logger.info(f"Successfully fetched content from {len(linked_content)} links")
        else:
            logger.info(f"Not following links: follow_links={follow_links}, max_depth={max_depth}")
        
        # Build metadata
        metadata = {
            'scraped_at': asyncio.get_event_loop().time(),
            'bank_detected': detect_bank_from_url(url) or 'unknown',
            'links_followed': len(linked_content),
            'pdfs_found': len(pdf_links),
            'tables_found': len(tables),
            'sections_found': len(structured_sections),
        }
        
        return ScrapedContent(
            url=url,
            title=title,
            raw_text=raw_text,
            structured_sections=structured_sections,
            tables=tables,
            linked_content=linked_content,
            pdf_links=pdf_links,
            metadata=metadata
        )

    async def _fetch_and_parse(self, url: str, use_playwright: bool = False) -> Tuple[BeautifulSoup, str]:
        """Fetch URL and return parsed BeautifulSoup object.
        
        Args:
            url: URL to fetch
            use_playwright: Use Playwright/Chromium for JavaScript rendering
        """
        # Try Playwright first if requested
        if use_playwright:
            html = await self._fetch_with_playwright(url)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                return soup, html
            else:
                logger.warning(f"Playwright failed for {url}, falling back to httpx")
        
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            # Explicitly exclude Brotli (br) as it may cause decoding issues
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }

        last_error = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=True,
                    max_redirects=self.max_redirects,
                ) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    
                    # Get content - httpx should auto-decompress
                    html = response.text
                    
                    # Check if we got valid HTML
                    if html and '<' in html[:100]:
                        soup = BeautifulSoup(html, "html.parser")
                        return soup, html
                    else:
                        # Try to get raw content and decode
                        content = response.content
                        
                        # Try to decompress if needed
                        import gzip
                        import zlib
                        
                        try:
                            # Try gzip
                            html = gzip.decompress(content).decode('utf-8')
                        except:
                            try:
                                # Try zlib/deflate
                                html = zlib.decompress(content, zlib.MAX_WBITS | 16).decode('utf-8')
                            except:
                                try:
                                    # Try raw deflate
                                    html = zlib.decompress(content, -zlib.MAX_WBITS).decode('utf-8')
                                except:
                                    # Try brotli if available
                                    try:
                                        import brotli
                                        html = brotli.decompress(content).decode('utf-8')
                                    except:
                                        # Last resort - just decode as utf-8
                                        html = content.decode('utf-8', errors='ignore')
                        
                        soup = BeautifulSoup(html, "html.parser")
                        return soup, html

            except httpx.HTTPStatusError as e:
                last_error = WebScraperError(f"HTTP error {e.response.status_code}: {str(e)}")
                logger.warning(f"Fetch attempt {attempt} failed: {str(e)}")
            except httpx.RequestError as e:
                last_error = WebScraperError(f"Request error: {str(e)}")
                logger.warning(f"Fetch attempt {attempt} failed: {str(e)}")
            except Exception as e:
                last_error = WebScraperError(f"Unexpected error: {str(e)}")
                logger.warning(f"Fetch attempt {attempt} failed: {str(e)}")
            
            if attempt < self.retry_attempts:
                await asyncio.sleep(2 ** attempt)

        raise last_error
    
    async def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Fetch URL using Playwright with smart scrolling for JavaScript-rendered content."""
        try:
            from playwright.async_api import async_playwright
            
            logger.info(f"Using Playwright to fetch: {url}")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Smart scrolling to load lazy content
                last_height = 0
                scroll_attempts = 0
                max_scrolls = 20
                
                while scroll_attempts < max_scrolls:
                    current_height = await page.evaluate("document.body.scrollHeight")
                    if current_height == last_height:
                        break
                    last_height = current_height
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=3000)
                    except:
                        pass
                    scroll_attempts += 1
                
                # Scroll back to top
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(500)
                
                html = await page.content()
                await browser.close()
                
                logger.info(f"Playwright scraped {len(html)} chars from {url}")
                return html
                
        except ImportError:
            logger.warning("Playwright not installed, falling back to httpx")
            return None
        except Exception as e:
            logger.error(f"Playwright error for {url}: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title."""
        # Try meta title first
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content'].strip()
        
        # Then regular title
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        # Then h1
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        return "Unknown Card"

    def _extract_clean_text(self, soup: BeautifulSoup, bank_config: Dict) -> str:
        """Extract clean text content from soup."""
        # Create a copy to avoid modifying original
        soup_copy = BeautifulSoup(str(soup), 'html.parser')
        
        # Remove unwanted elements
        for selector in bank_config.get('ignore_selectors', []):
            for element in soup_copy.select(selector):
                element.decompose()
        
        # Remove scripts, styles, etc.
        for tag in soup_copy(['script', 'style', 'noscript', 'svg', 'path']):
            tag.decompose()
        
        # Try to find main content area
        main_content = None
        for selector in bank_config.get('content_selectors', []):
            main_content = soup_copy.select_one(selector)
            if main_content:
                break
        
        if not main_content:
            main_content = soup_copy.body or soup_copy
        
        # Get text with proper spacing
        text = main_content.get_text(separator='\n', strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)
        
        # Truncate if too long
        if len(text) > self.max_content_length:
            text = text[:self.max_content_length] + "\n[Content truncated...]"
        
        return text

    def _extract_sections(
        self,
        soup: BeautifulSoup,
        bank_config: Dict
    ) -> List[ExtractedSection]:
        """Extract structured sections from the page."""
        sections = []
        
        # Find all heading elements and their following content
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for heading in headings:
            heading_text = heading.get_text(strip=True)
            if not heading_text or len(heading_text) < 3:
                continue
            
            # Get content following the heading
            content_parts = []
            sibling = heading.find_next_sibling()
            
            while sibling and sibling.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                if sibling.name in ['p', 'div', 'ul', 'ol', 'span']:
                    text = sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                sibling = sibling.find_next_sibling()
            
            if content_parts:
                section_type = self._identify_section_type(heading_text + ' ' + ' '.join(content_parts[:3]))
                sections.append(ExtractedSection(
                    title=heading_text,
                    content='\n'.join(content_parts),
                    section_type=section_type,
                    metadata={'heading_level': heading.name}
                ))
        
        # Also look for sections by class patterns
        benefit_patterns = [
            '[class*="benefit"]', '[class*="feature"]', '[class*="offer"]',
            '[class*="cashback"]', '[class*="reward"]', '[class*="perk"]'
        ]
        
        for pattern in benefit_patterns:
            elements = soup.select(pattern)
            for elem in elements:
                title = ''
                # Try to find a title within the element
                title_elem = elem.find(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                
                content = elem.get_text(strip=True)
                if content and len(content) > 20:
                    section_type = self._identify_section_type(content)
                    sections.append(ExtractedSection(
                        title=title or f"Section from {pattern}",
                        content=content,
                        section_type=section_type,
                        metadata={'source_selector': pattern}
                    ))
        
        # Deduplicate sections
        seen = set()
        unique_sections = []
        for section in sections:
            key = (section.title, section.content[:100])
            if key not in seen:
                seen.add(key)
                unique_sections.append(section)
        
        return unique_sections

    def _extract_tables(self, soup: BeautifulSoup) -> List[ExtractedTable]:
        """Extract and parse tables from the page."""
        tables = []
        
        for table in soup.find_all('table'):
            # Get context (nearby heading or caption)
            context = ''
            caption = table.find('caption')
            if caption:
                context = caption.get_text(strip=True)
            else:
                prev = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'p'])
                if prev:
                    context = prev.get_text(strip=True)
            
            # Extract headers
            headers = []
            header_row = table.find('thead')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            else:
                first_row = table.find('tr')
                if first_row:
                    headers = [cell.get_text(strip=True) for cell in first_row.find_all(['th', 'td'])]
            
            # Extract rows
            rows = []
            tbody = table.find('tbody') or table
            for tr in tbody.find_all('tr')[1:] if not header_row else tbody.find_all('tr'):
                row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if row and any(cell for cell in row):
                    rows.append(row)
            
            if headers or rows:
                # Identify table type
                all_text = ' '.join(headers + [cell for row in rows for cell in row]).lower()
                table_type = self._identify_section_type(all_text)
                
                tables.append(ExtractedTable(
                    headers=headers,
                    rows=rows,
                    context=context,
                    table_type=table_type
                ))
        
        return tables

    def _find_pdf_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Find all PDF links on the page."""
        pdf_links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '.pdf' in href.lower():
                full_url = urljoin(base_url, href)
                if full_url not in pdf_links:
                    pdf_links.append(full_url)
        
        return pdf_links

    def _find_related_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
        bank_config: Dict
    ) -> List[str]:
        """Find related links worth following."""
        related_links = []
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        
        # Important keywords that indicate valuable content
        important_keywords = [
            'terms', 'condition', 'benefit', 'feature', 'detail',
            'learn more', 'more info', 'eligibility', 'key facts',
            'fee schedule', 'tariff', 'important', 'document',
            'lounge', 'reward', 'offer', 'cashback', 'cinema',
            'golf', 'concierge', 'insurance', 'credit shield',
            'apply now', 'how to', 'faq', 'help'
        ]
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            
            # Must be same domain or related domain
            if base_domain not in parsed.netloc:
                continue
            
            # Skip anchors and javascript
            if href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Skip if already added
            if full_url in related_links:
                continue
            
            should_add = False
            
            # Check if path matches related patterns
            for pattern in bank_config.get('related_paths', []):
                if re.search(pattern, parsed.path, re.IGNORECASE):
                    should_add = True
                    break
            
            # Check link text for relevance
            if not should_add:
                link_text = link.get_text(strip=True).lower()
                if any(kw in link_text for kw in important_keywords):
                    should_add = True
            
            # Check href for keywords
            if not should_add:
                href_lower = href.lower()
                path_keywords = ['benefit', 'feature', 'offer', 'reward', 'lounge', 
                               'key-fact', 'terms', 'condition', 'help-and-support',
                               'cinema', 'golf', 'concierge', 'insurance']
                if any(kw in href_lower for kw in path_keywords):
                    should_add = True
            
            if should_add:
                related_links.append(full_url)
        
        # Sort by importance - PDFs and key-facts first
        def link_priority(url):
            url_lower = url.lower()
            if '.pdf' in url_lower:
                return 0
            if 'key-fact' in url_lower:
                return 1
            if 'terms' in url_lower or 'condition' in url_lower:
                return 2
            if 'benefit' in url_lower or 'feature' in url_lower:
                return 3
            return 4
        
        related_links.sort(key=link_priority)
        
        return related_links

    def _extract_links_from_text(self, text: str, base_url: str) -> List[str]:
        """Extract URLs from text content (markdown links, plain URLs)."""
        links = []
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc
        base_root = f"{parsed_base.scheme}://{parsed_base.netloc}"
        
        # Markdown-style links: [text](url)
        markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        for match in re.finditer(markdown_pattern, text):
            url = match.group(2)
            if url.startswith('/'):
                url = urljoin(base_root, url)
            if base_domain in url or url.startswith('/'):
                links.append(url)
        
        # Plain URLs
        url_pattern = r'https?://[^\s<>"\']+(?:emiratesnbd|bankfab|adcb|mashreq)[^\s<>"\']*'
        for match in re.finditer(url_pattern, text, re.IGNORECASE):
            url = match.group(0)
            # Clean up trailing punctuation
            url = re.sub(r'[.,;:!?\)\]]+$', '', url)
            if url not in links:
                links.append(url)
        
        # Relative paths mentioned in text
        path_pattern = r'(?:href|link|url)[=:]\s*["\']?(/[^\s"\'<>]+)'
        for match in re.finditer(path_pattern, text, re.IGNORECASE):
            path = match.group(1)
            full_url = urljoin(base_root, path)
            if full_url not in links:
                links.append(full_url)
        
        logger.info(f"Extracted {len(links)} links from text content")
        return links
    async def _fetch_related_content(
        self,
        urls: List[str],
        bank_config: Dict
    ) -> Dict[str, str]:
        """Fetch content from related URLs, handling both web pages and PDFs."""
        content = {}
        
        for url in urls:
            try:
                logger.info(f"Fetching related link: {url}")
                
                # Check if it's a PDF
                if url.lower().endswith('.pdf') or '/pdf/' in url.lower() or '.pdf?' in url.lower():
                    # Use PDF service for PDF files
                    try:
                        from app.services.pdf_service import pdf_service
                        pdf_text = await pdf_service.extract_text_from_url(url)
                        if pdf_text and len(pdf_text) > 50:
                            content[url] = pdf_text[:50000]  # Allow more content from PDFs
                            logger.info(f"Extracted {len(pdf_text)} chars from PDF: {url}")
                        else:
                            logger.warning(f"PDF extraction yielded little content: {url}")
                    except Exception as pdf_error:
                        logger.warning(f"PDF extraction failed for {url}: {str(pdf_error)}")
                        continue
                else:
                    # Regular web page
                    soup, _ = await self._fetch_and_parse(url)
                    text = self._extract_clean_text(soup, bank_config)
                    if text and len(text) > 100:
                        content[url] = text[:10000]  # Limit per link
                        
            except Exception as e:
                logger.warning(f"Failed to fetch related link {url}: {str(e)}")
                continue
        
        return content

    async def scrape_url(self, url: str) -> str:
        """
        Simple scrape for backward compatibility.
        Returns just the raw text content.
        """
        content = await self.scrape_url_comprehensive(url, follow_links=False)
        return content.raw_text

    def format_for_llm(self, content: ScrapedContent) -> str:
        """
        Format scraped content optimally for LLM extraction.
        
        Args:
            content: ScrapedContent object
            
        Returns:
            Formatted string optimized for LLM processing
        """
        parts = []
        
        # Title and URL
        parts.append(f"=== CREDIT CARD: {content.title} ===")
        parts.append(f"Source: {content.url}\n")
        
        # Structured sections by type
        sections_by_type = {}
        for section in content.structured_sections:
            if section.section_type not in sections_by_type:
                sections_by_type[section.section_type] = []
            sections_by_type[section.section_type].append(section)
        
        # Output sections in priority order
        priority_order = ['benefit', 'entitlement', 'merchant', 'fee', 'eligibility', 'terms', 'general']
        
        for section_type in priority_order:
            if section_type in sections_by_type:
                parts.append(f"\n=== {section_type.upper()} SECTIONS ===")
                for section in sections_by_type[section_type]:
                    parts.append(f"\n## {section.title}")
                    parts.append(section.content)
        
        # Tables
        if content.tables:
            parts.append("\n=== EXTRACTED TABLES ===")
            for i, table in enumerate(content.tables):
                parts.append(f"\n--- Table {i+1}: {table.context} (Type: {table.table_type}) ---")
                if table.headers:
                    parts.append(" | ".join(table.headers))
                    parts.append("-" * 50)
                for row in table.rows:
                    parts.append(" | ".join(row))
        
        # Linked content
        if content.linked_content:
            parts.append("\n=== ADDITIONAL DETAILS FROM LINKED PAGES ===")
            for url, text in content.linked_content.items():
                parts.append(f"\n--- From: {url} ---")
                parts.append(text[:5000])  # Limit per link
        
        # Raw text as fallback
        parts.append("\n=== FULL PAGE TEXT ===")
        parts.append(content.raw_text)
        
        return '\n'.join(parts)


# Global instance
enhanced_web_scraper_service = EnhancedWebScraperService()
