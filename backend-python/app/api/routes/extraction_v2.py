"""
Enhanced Extraction API routes (V2).
Provides comprehensive extraction with deep link crawling and structured output.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

from app.services.enhanced_extraction_service import enhanced_extraction_service
from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
from app.models.extracted_data_v2 import ExtractedDataV2, ValidationStatus
from app.core.config import settings
from app.utils.logger import logger


# ============= REQUEST/RESPONSE MODELS =============

class ExtractionConfigV2(BaseModel):
    """Configuration for V2 extraction."""
    model: Optional[str] = Field(None, description="LLM model to use")
    temperature: Optional[float] = Field(None, ge=0, le=1, description="LLM temperature")
    bypass_cache: bool = Field(default=False, description="Bypass cache")
    follow_links: bool = Field(default=True, description="Follow related links on page")
    max_depth: int = Field(default=1, ge=0, le=3, description="Maximum link following depth")
    store_raw_text: bool = Field(default=True, description="Store raw extracted text")
    store_raw_response: bool = Field(default=False, description="Store raw LLM response")
    selected_urls: List[str] = Field(default_factory=list, description="User-selected URLs to process")
    process_pdfs: bool = Field(default=True, description="Process PDF documents")


class URLExtractionRequestV2(BaseModel):
    """Request model for V2 URL extraction."""
    url: HttpUrl = Field(..., description="URL to extract from")
    config: ExtractionConfigV2 = Field(default_factory=ExtractionConfigV2)


class TextExtractionRequestV2(BaseModel):
    """Request model for V2 text extraction."""
    text: str = Field(..., min_length=100, description="Text content to extract from")
    config: ExtractionConfigV2 = Field(default_factory=ExtractionConfigV2)


# Discovery models
class DiscoveredLink(BaseModel):
    """A discovered link from the page."""
    url: str = Field(..., description="Full URL")
    title: str = Field(..., description="Link title or filename")
    link_type: str = Field(..., description="Type: webpage, pdf, terms, key_facts, etc.")
    relevance: str = Field(..., description="high, medium, low")
    description: Optional[str] = Field(None, description="Brief description")


class DiscoveryRequest(BaseModel):
    """Request for URL discovery."""
    url: HttpUrl = Field(..., description="URL to discover links from")


class DiscoveryResponse(BaseModel):
    """Response from URL discovery."""
    success: bool
    main_url: str
    page_title: str
    card_name_detected: Optional[str] = None
    bank_detected: Optional[str] = None
    discovered_links: List[DiscoveredLink] = []
    pdf_links: List[DiscoveredLink] = []
    total_links_found: int = 0
    main_page_preview: Optional[str] = None
    message: Optional[str] = None


class ExtractWithSelectedURLsRequest(BaseModel):
    """Request for extraction with user-selected URLs."""
    url: HttpUrl = Field(..., description="Main URL to extract from")
    selected_urls: List[str] = Field(default_factory=list, description="URLs selected by user to include")
    config: ExtractionConfigV2 = Field(default_factory=ExtractionConfigV2)


class BenefitResponse(BaseModel):
    """Benefit in response."""
    benefit_id: str
    benefit_name: str
    benefit_type: str
    benefit_value: Optional[str] = None
    description: str
    conditions: List[str] = []
    eligible_categories: List[str] = []
    caps: List[Dict[str, Any]] = []
    frequency: Optional[str] = None
    spend_conditions: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class EntitlementResponse(BaseModel):
    """Entitlement in response."""
    entitlement_id: str
    entitlement_name: str
    entitlement_type: str
    description: str
    quantity: Optional[int] = None
    quantity_per_period: Optional[str] = None
    conditions: List[str] = []
    redemption_locations: List[str] = []
    partner_networks: List[str] = []
    geographic_coverage: Optional[str] = None
    supplementary_access: bool = False
    fallback_fee: Optional[float] = None

    class Config:
        from_attributes = True


class MerchantOfferResponse(BaseModel):
    """Merchant offer in response."""
    offer_type: str
    offer_value: str
    description: Optional[str] = None
    conditions: List[str] = []
    minimum_spend: Optional[float] = None
    promo_code: Optional[str] = None

    class Config:
        from_attributes = True


class MerchantResponse(BaseModel):
    """Merchant in response."""
    merchant_name: str
    merchant_category: str
    offers: List[MerchantOfferResponse] = []
    redemption_method: Optional[str] = None
    is_online: bool = False
    website_url: Optional[str] = None

    class Config:
        from_attributes = True


class FeesResponse(BaseModel):
    """Fees in response."""
    annual_fee: Optional[Dict[str, Any]] = None
    interest_rate_monthly: Optional[float] = None
    interest_rate_annual: Optional[float] = None
    foreign_transaction_fee: Optional[Dict[str, Any]] = None
    cash_advance_fee: Optional[Dict[str, Any]] = None
    late_payment_fee: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class EligibilityResponse(BaseModel):
    """Eligibility in response."""
    minimum_salary: Optional[Union[float, str]] = None
    minimum_salary_currency: str = "AED"
    minimum_age: Optional[Union[int, str]] = None
    maximum_age: Optional[Union[int, str]] = None
    employment_types: List[str] = []
    nationality_requirements: List[str] = []
    required_documents: List[str] = []

    class Config:
        from_attributes = True


class CardIssuerResponse(BaseModel):
    """Card issuer in response."""
    bank_name: str
    country: str = "UAE"
    website: Optional[str] = None

    class Config:
        from_attributes = True


class ExtractionMetadataResponse(BaseModel):
    """Extraction metadata in response."""
    extraction_timestamp: Optional[datetime] = None
    processing_time_ms: Optional[int] = None
    pages_scraped: int = 1
    links_followed: int = 0
    tables_extracted: int = 0
    extraction_notes: List[str] = []

    class Config:
        from_attributes = True


class ExtractedDataResponseV2(BaseModel):
    """Full extraction response for V2."""
    id: str
    source_url: Optional[str] = None
    source_urls: List[str] = []
    source_type: str
    
    # Card info
    card_name: str
    card_issuer: CardIssuerResponse
    card_network: Optional[str] = None
    card_networks: List[str] = []
    card_category: Optional[str] = None
    card_type: Optional[str] = None
    is_combo_card: bool = False
    combo_cards: List[str] = []
    
    # Benefits and entitlements
    benefits: List[BenefitResponse] = []
    entitlements: List[EntitlementResponse] = []
    
    # Merchants
    merchants_vendors: List[MerchantResponse] = []
    partner_programs: List[str] = []
    
    # Fees and eligibility
    fees: FeesResponse
    eligibility: EligibilityResponse
    
    # Insurance
    insurance_coverage: List[Dict[str, Any]] = []
    
    # Rewards
    rewards_program_name: Optional[str] = None
    rewards_earn_rate: Optional[str] = None
    
    # Scores
    confidence_score: Optional[float] = None
    completeness_score: Optional[float] = None
    validation_status: str
    
    # Metadata
    extraction_method: str
    extraction_metadata: ExtractionMetadataResponse
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExtractionResponseV2(BaseModel):
    """API response wrapper for V2 extraction."""
    success: bool = True
    data: ExtractedDataResponseV2
    message: Optional[str] = None


class ExtractedDataListResponseV2(BaseModel):
    """List response for V2 extractions."""
    success: bool = True
    data: List[ExtractedDataResponseV2]
    pagination: Dict[str, int]


class DeleteResponseV2(BaseModel):
    """Delete response."""
    success: bool = True
    message: str = "Extraction deleted successfully"


class SearchRequestV2(BaseModel):
    """Search request for V2."""
    query: Optional[str] = None
    bank_name: Optional[str] = None
    benefit_type: Optional[str] = None
    merchant_name: Optional[str] = None
    max_salary: Optional[float] = None
    card_category: Optional[str] = None


# ============= HELPER FUNCTIONS =============

def document_to_response(doc: ExtractedDataV2) -> ExtractedDataResponseV2:
    """Convert MongoDB document to response model."""
    # Build card issuer response
    issuer = CardIssuerResponse(
        bank_name=doc.card_issuer.bank_name,
        country=doc.card_issuer.country,
        website=doc.card_issuer.website,
    )
    
    # Build benefits response
    benefits = []
    for b in doc.benefits:
        benefits.append(BenefitResponse(
            benefit_id=b.benefit_id,
            benefit_name=b.benefit_name,
            benefit_type=b.benefit_type.value if hasattr(b.benefit_type, 'value') else str(b.benefit_type),
            benefit_value=b.benefit_value,
            description=b.description,
            conditions=b.conditions,
            eligible_categories=b.eligible_categories,
            caps=[cap.model_dump() for cap in b.caps],
            frequency=b.frequency.value if b.frequency and hasattr(b.frequency, 'value') else str(b.frequency) if b.frequency else None,
            spend_conditions=[sc.model_dump() for sc in b.spend_conditions],
        ))
    
    # Build entitlements response
    entitlements = []
    for e in doc.entitlements:
        entitlements.append(EntitlementResponse(
            entitlement_id=e.entitlement_id,
            entitlement_name=e.entitlement_name,
            entitlement_type=e.entitlement_type.value if hasattr(e.entitlement_type, 'value') else str(e.entitlement_type),
            description=e.description,
            quantity=e.quantity,
            quantity_per_period=e.quantity_per_period,
            conditions=e.conditions,
            redemption_locations=e.redemption_locations,
            partner_networks=e.partner_networks,
            geographic_coverage=e.geographic_coverage,
            supplementary_access=e.supplementary_access,
            fallback_fee=e.fallback_fee,
        ))
    
    # Build merchants response
    merchants = []
    for m in doc.merchants_vendors:
        offers = []
        for o in m.offers:
            offers.append(MerchantOfferResponse(
                offer_type=o.offer_type,
                offer_value=o.offer_value,
                description=o.description,
                conditions=o.conditions,
                minimum_spend=o.minimum_spend,
                promo_code=o.promo_code,
            ))
        merchants.append(MerchantResponse(
            merchant_name=m.merchant_name,
            merchant_category=m.merchant_category.value if hasattr(m.merchant_category, 'value') else str(m.merchant_category),
            offers=offers,
            redemption_method=m.redemption_method,
            is_online=m.is_online,
            website_url=m.website_url,
        ))
    
    # Build fees response
    fees = FeesResponse(
        annual_fee=doc.fees.annual_fee.model_dump() if doc.fees.annual_fee else None,
        interest_rate_monthly=doc.fees.interest_rate_monthly,
        interest_rate_annual=doc.fees.interest_rate_annual,
        foreign_transaction_fee=doc.fees.foreign_transaction_fee.model_dump() if doc.fees.foreign_transaction_fee else None,
        cash_advance_fee=doc.fees.cash_advance_fee.model_dump() if doc.fees.cash_advance_fee else None,
        late_payment_fee=doc.fees.late_payment_fee.model_dump() if doc.fees.late_payment_fee else None,
    )
    
    # Build eligibility response
    eligibility = EligibilityResponse(
        minimum_salary=doc.eligibility.minimum_salary,
        minimum_salary_currency=doc.eligibility.minimum_salary_currency.value if hasattr(doc.eligibility.minimum_salary_currency, 'value') else str(doc.eligibility.minimum_salary_currency),
        minimum_age=doc.eligibility.minimum_age,
        maximum_age=doc.eligibility.maximum_age,
        employment_types=doc.eligibility.employment_types,
        nationality_requirements=doc.eligibility.nationality_requirements,
        required_documents=doc.eligibility.required_documents,
    )
    
    # Build extraction metadata response
    metadata = ExtractionMetadataResponse(
        extraction_timestamp=doc.extraction_metadata.extraction_timestamp,
        processing_time_ms=doc.extraction_metadata.processing_time_ms,
        pages_scraped=doc.extraction_metadata.pages_scraped,
        links_followed=doc.extraction_metadata.links_followed,
        tables_extracted=doc.extraction_metadata.tables_extracted,
        extraction_notes=doc.extraction_metadata.extraction_notes,
    )
    
    return ExtractedDataResponseV2(
        id=str(doc.id),
        source_url=doc.source_url,
        source_urls=doc.source_urls,
        source_type=doc.source_type.value if hasattr(doc.source_type, 'value') else str(doc.source_type),
        card_name=doc.card_name,
        card_issuer=issuer,
        card_network=doc.card_network.value if doc.card_network and hasattr(doc.card_network, 'value') else str(doc.card_network) if doc.card_network else None,
        card_networks=[n.value if hasattr(n, 'value') else str(n) for n in doc.card_networks],
        card_category=doc.card_category.value if doc.card_category and hasattr(doc.card_category, 'value') else str(doc.card_category) if doc.card_category else None,
        card_type=doc.card_type.value if doc.card_type and hasattr(doc.card_type, 'value') else str(doc.card_type) if doc.card_type else None,
        is_combo_card=doc.is_combo_card,
        combo_cards=doc.combo_cards,
        benefits=benefits,
        entitlements=entitlements,
        merchants_vendors=merchants,
        partner_programs=doc.partner_programs,
        fees=fees,
        eligibility=eligibility,
        insurance_coverage=[ic.model_dump() for ic in doc.insurance_coverage],
        rewards_program_name=doc.rewards_program_name,
        rewards_earn_rate=doc.rewards_earn_rate,
        confidence_score=doc.confidence_score,
        completeness_score=doc.completeness_score,
        validation_status=doc.validation_status.value if hasattr(doc.validation_status, 'value') else str(doc.validation_status),
        extraction_method=doc.extraction_method.value if hasattr(doc.extraction_method, 'value') else str(doc.extraction_method),
        extraction_metadata=metadata,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


# ============= API ROUTES =============

router = APIRouter(prefix="/v2/extraction", tags=["extraction-v2"])


@router.post("/discover", response_model=DiscoveryResponse)
async def discover_urls(request: DiscoveryRequest):
    """
    Discover related URLs from a credit card page.
    
    This is step 1 of the two-step extraction process:
    1. Discover - Find all related links (PDFs, terms, benefits pages, etc.)
    2. Extract - User selects which links to include, then extract
    
    Returns a list of discovered links for user approval.
    """
    import re
    from urllib.parse import urlparse, urljoin
    
    try:
        url = str(request.url)
        logger.info(f"Starting URL discovery for: {url}")
        
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Fetch the raw HTML directly
        soup, raw_html = await enhanced_web_scraper_service._fetch_and_parse(url)
        
        # Also get scraped content for title and preview
        scraped = await enhanced_web_scraper_service.scrape_url_comprehensive(
            url,
            follow_links=False,
            max_depth=0
        )
        
        logger.info(f"Raw HTML length: {len(raw_html)}")
        logger.info(f"Scraped raw_text length: {len(scraped.raw_text)}")
        
        # DEBUG: Log first 2000 chars of HTML to see structure
        logger.info(f"HTML preview: {raw_html[:2000]}")
        
        # Get bank config for this URL
        bank_config = enhanced_web_scraper_service._get_bank_config(url)
        
        all_links = []
        
        # DEBUG: Count all <a> tags first
        all_a_tags = soup.find_all('a', href=True)
        logger.info(f"Total <a> tags found: {len(all_a_tags)}")
        
        # DEBUG: Log first 10 hrefs
        for i, a_tag in enumerate(all_a_tags[:10]):
            logger.info(f"  Link {i}: href={a_tag['href'][:100]}, text={a_tag.get_text(strip=True)[:50]}")
        
        # Method 1: Extract ALL href attributes from HTML - more permissive
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            link_text = a_tag.get_text(strip=True)
            
            # Skip empty, javascript, and anchor links
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Convert relative URLs to absolute
            if href.startswith('/'):
                full_url = urljoin(base_url, href)
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = urljoin(url, href)
            
            # Only include links from same domain
            if parsed_url.netloc not in full_url:
                continue
                
            href_lower = href.lower()
            text_lower = link_text.lower()
            
            relevant_keywords = [
                'help', 'support', 'benefit', 'feature', 'lounge', 'cinema', 'cine',
                'movie', 'golf', 'concierge', 'insurance', 'shield', 'terms', 'condition',
                'fee', 'charge', 'tariff', 'key-fact', 'pdf', 'learn-more', 'learn more',
                'airport', 'access', 'royal', 'reward', 'offer'
            ]
            
            is_relevant = any(kw in href_lower or kw in text_lower for kw in relevant_keywords)
            
            if is_relevant and full_url not in [l['url'] for l in all_links]:
                all_links.append({
                    'url': full_url,
                    'text': link_text
                })
                logger.info(f"Found HTML link: {link_text[:50]} -> {full_url}")
        
        # Method 2: Extract markdown-style links from raw HTML [text](url)
        markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        for match in re.finditer(markdown_pattern, raw_html):
            link_text = match.group(1)
            link_url = match.group(2)
            
            # Convert relative URLs to absolute
            if link_url.startswith('/'):
                link_url = urljoin(base_url, link_url)
            elif not link_url.startswith('http'):
                link_url = urljoin(url, link_url)
            
            # Only include links from same domain
            if parsed_url.netloc in link_url and link_url not in [l['url'] for l in all_links]:
                all_links.append({
                    'url': link_url,
                    'text': link_text
                })
                logger.info(f"Found markdown link: {link_text[:50]} -> {link_url}")
        
        # Method 3: Look for href patterns in raw HTML
        href_pattern = r'href=["\']([^"\']+)["\']'
        for match in re.finditer(href_pattern, raw_html, re.IGNORECASE):
            href = match.group(1)
            
            if href.startswith('/'):
                full_url = urljoin(base_url, href)
            elif href.startswith('http'):
                full_url = href
            else:
                continue
            
            if parsed_url.netloc in full_url:
                href_lower = href.lower()
                relevant_keywords = [
                    'help-and-support', 'benefit', 'lounge', 'cinema', 'cine-royal',
                    'credit-shield', 'golf', 'fee', 'terms', '.pdf'
                ]
                
                if any(kw in href_lower for kw in relevant_keywords):
                    if full_url not in [l['url'] for l in all_links]:
                        title = href.split('/')[-1].replace('-', ' ').title()
                        all_links.append({
                            'url': full_url,
                            'text': title
                        })
                        logger.info(f"Found href pattern: {title} -> {full_url}")
        
        # Method 4: Hardcoded common Emirates NBD benefit page patterns based on content keywords
        if 'emiratesnbd' in url.lower():
            text_to_check = (raw_html + scraped.raw_text).lower()
            logger.info(f"Checking Emirates NBD keywords in {len(text_to_check)} chars of text")
            
            # Check for specific keywords
            logger.info(f"  'lounge' in text: {'lounge' in text_to_check}")
            logger.info(f"  'cinema' in text: {'cinema' in text_to_check}")
            logger.info(f"  'cine' in text: {'cine' in text_to_check}")
            logger.info(f"  'shield' in text: {'shield' in text_to_check}")
            logger.info(f"  'golf' in text: {'golf' in text_to_check}")
            
            enbd_pages = [
                ('lounge', '/en/help-and-support/airport-lounge-access-mastercard', 'Airport Lounge Access (Mastercard)'),
                ('cine', '/en/help-and-support/cine-royal-cinemas-movie-benefits', 'Cine Royal Cinema Benefits'),
                ('cinema', '/en/help-and-support/cine-royal-cinemas-movie-benefits', 'Cinema Movie Benefits'),
                ('shield', '/en/cards/credit-shield-pro', 'Credit Shield Pro Insurance'),
                ('golf', '/en/help-and-support/golf-benefits', 'Golf Course Access'),
                ('concierge', '/en/help-and-support/concierge-services', 'Concierge Services'),
                ('fee', '/en/help-and-support/credit-card-fees-and-charges', 'Fees and Charges'),
            ]
            
            for keyword, path, title in enbd_pages:
                if keyword in text_to_check:
                    full_url = f"{base_url}{path}"
                    
                    if full_url not in [l['url'] for l in all_links]:
                        all_links.append({
                            'url': full_url,
                            'text': title
                        })
                        logger.info(f"Found keyword-based link: {title} -> {full_url}")
        
        logger.info(f"Total links discovered: {len(all_links)}")
        
        # Categorize links
        discovered_links = []
        pdf_links = []
        
        for link_info in all_links:
            link_url = link_info['url']
            link_text = link_info.get('text', '')
            url_lower = link_url.lower()
            
            # Skip the main URL itself
            if link_url.rstrip('/') == url.rstrip('/'):
                continue
            
            # Determine link type and relevance
            if '.pdf' in url_lower:
                link_type = "pdf"
                if 'key-fact' in url_lower or 'keyfact' in url_lower:
                    link_type = "key_facts_pdf"
                    relevance = "high"
                elif 'terms' in url_lower or 'condition' in url_lower:
                    link_type = "terms_pdf"
                    relevance = "high"
                elif 'fee' in url_lower or 'tariff' in url_lower:
                    link_type = "fee_schedule_pdf"
                    relevance = "high"
                else:
                    relevance = "medium"
                
                title = link_text or link_url.split('/')[-1].replace('.pdf', '').replace('-', ' ').replace('_', ' ').title()
                pdf_links.append(DiscoveredLink(
                    url=link_url,
                    title=title,
                    link_type=link_type,
                    relevance=relevance,
                    description=f"PDF document: {title}"
                ))
            else:
                # Webpage links
                if 'help-and-support' in url_lower or 'support' in url_lower:
                    link_type = "support_page"
                    relevance = "high"
                elif 'benefit' in url_lower or 'feature' in url_lower:
                    link_type = "benefits_page"
                    relevance = "high"
                elif 'lounge' in url_lower:
                    link_type = "lounge_info"
                    relevance = "high"
                elif 'cinema' in url_lower or 'movie' in url_lower or 'cine' in url_lower:
                    link_type = "entertainment_info"
                    relevance = "high"
                elif 'terms' in url_lower or 'condition' in url_lower:
                    link_type = "terms_page"
                    relevance = "medium"
                elif 'fee' in url_lower or 'charge' in url_lower:
                    link_type = "fees_page"
                    relevance = "high"
                elif 'insurance' in url_lower or 'shield' in url_lower:
                    link_type = "insurance_info"
                    relevance = "high"
                elif 'golf' in url_lower:
                    link_type = "golf_info"
                    relevance = "medium"
                elif 'concierge' in url_lower:
                    link_type = "concierge_info"
                    relevance = "medium"
                else:
                    link_type = "related_page"
                    relevance = "low"
                
                # Use link text if available, otherwise derive from URL
                title = link_text if link_text else link_url.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                if not title or title == '/' or title.strip() == '':
                    title = "Related Page"
                
                discovered_links.append(DiscoveredLink(
                    url=link_url,
                    title=title,
                    link_type=link_type,
                    relevance=relevance,
                    description=f"{link_type.replace('_', ' ').title()}"
                ))
        
        # Sort by relevance
        def relevance_sort(link):
            order = {"high": 0, "medium": 1, "low": 2}
            return order.get(link.relevance, 3)
        
        discovered_links.sort(key=relevance_sort)
        pdf_links.sort(key=relevance_sort)
        
        # Detect card name from title
        card_name = scraped.title if scraped.title else None
        if card_name and '|' in card_name:
            card_name = card_name.split('|')[0].strip()
        
        # Detect bank
        bank_detected = None
        for bank_name, config in enhanced_web_scraper_service.BANK_PATTERNS.items():
            if bank_name != 'default' and config['base_domain'] in url.lower():
                bank_detected = bank_name.replace('_', ' ').title()
                break
        
        return DiscoveryResponse(
            success=True,
            main_url=url,
            page_title=scraped.title or "Unknown",
            card_name_detected=card_name,
            bank_detected=bank_detected,
            discovered_links=discovered_links,
            pdf_links=pdf_links,
            total_links_found=len(discovered_links) + len(pdf_links),
            main_page_preview=scraped.raw_text[:500] if scraped.raw_text else None,
            message=f"Found {len(discovered_links)} web pages and {len(pdf_links)} PDF documents"
        )
        
    except Exception as e:
        logger.error(f"URL discovery failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-with-urls", response_model=ExtractionResponseV2)
async def extract_with_selected_urls(request: ExtractWithSelectedURLsRequest):
    """
    Extract credit card data using user-selected URLs.
    
    This is step 2 of the two-step extraction process.
    User selects which discovered URLs to include in extraction.
    """
    try:
        config = request.config.model_dump()
        config['selected_urls'] = request.selected_urls
        config['follow_links'] = True  # We'll use the selected URLs
        
        logger.info(f"Extracting from {request.url} with {len(request.selected_urls)} selected URLs")
        
        result = await enhanced_extraction_service.extract_comprehensive(
            source_type="url",
            source=str(request.url),
            config=config
        )
        
        return ExtractionResponseV2(
            success=True,
            data=document_to_response(result),
            message=f"Extraction completed with {len(request.selected_urls)} additional URLs"
        )
    except Exception as e:
        logger.error(f"Extraction with selected URLs failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/url", response_model=ExtractionResponseV2)
async def extract_from_url_v2(request: URLExtractionRequestV2):
    """
    Extract comprehensive credit card data from URL.
    
    Features:
    - Deep link crawling (follows related links)
    - Table extraction
    - Multi-stage LLM extraction
    - Structured output with benefits, entitlements, merchants, conditions
    """
    try:
        result = await enhanced_extraction_service.extract_comprehensive(
            source_type="url",
            source=str(request.url),
            config=request.config.model_dump()
        )
        
        return ExtractionResponseV2(
            success=True,
            data=document_to_response(result),
            message="Extraction completed successfully"
        )
    except Exception as e:
        logger.error(f"V2 URL extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/text", response_model=ExtractionResponseV2)
async def extract_from_text_v2(request: TextExtractionRequestV2):
    """Extract comprehensive credit card data from text content."""
    try:
        result = await enhanced_extraction_service.extract_comprehensive(
            source_type="text",
            source=request.text,
            config=request.config.model_dump()
        )
        
        return ExtractionResponseV2(
            success=True,
            data=document_to_response(result),
            message="Extraction completed successfully"
        )
    except Exception as e:
        logger.error(f"V2 text extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdf", response_model=ExtractionResponseV2)
async def extract_from_pdf_v2(
    file: UploadFile = File(...),
    follow_links: bool = Query(default=False),
    bypass_cache: bool = Query(default=False)
):
    """Extract comprehensive credit card data from PDF file."""
    try:
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        pdf_content = await file.read()
        
        if len(pdf_content) > settings.get_pdf_max_size_bytes():
            raise HTTPException(
                status_code=400,
                detail=f"PDF file too large (maximum {settings.PDF_MAX_SIZE_MB}MB)"
            )
        
        result = await enhanced_extraction_service.extract_comprehensive(
            source_type="pdf",
            source=pdf_content,
            config={
                "follow_links": follow_links,
                "bypass_cache": bypass_cache
            }
        )
        
        return ExtractionResponseV2(
            success=True,
            data=document_to_response(result),
            message="Extraction completed successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V2 PDF extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=ExtractedDataListResponseV2)
async def list_extractions_v2(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    bank_name: Optional[str] = None,
):
    """List V2 extractions with pagination and filtering."""
    try:
        query = {"is_deleted": False}
        if status:
            query["validation_status"] = status
        if source_type:
            query["source_type"] = source_type
        if bank_name:
            query["card_issuer.bank_name"] = {"$regex": bank_name, "$options": "i"}
        
        skip = (page - 1) * limit
        
        # Sort by created_at descending (newest first)
        results = await ExtractedDataV2.find(query).sort("-created_at").skip(skip).limit(limit).to_list()
        total = await ExtractedDataV2.find(query).count()
        
        data_list = [document_to_response(r) for r in results]
        
        return ExtractedDataListResponseV2(
            success=True,
            data=data_list,
            pagination={
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit
            }
        )
    except Exception as e:
        logger.error(f"List V2 extractions failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=ExtractedDataListResponseV2)
async def search_extractions_v2(
    request: SearchRequestV2,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Search V2 extractions with various filters."""
    try:
        query = {"is_deleted": False}
        
        if request.query:
            # Text search
            results = await ExtractedDataV2.search_cards(request.query, limit)
        else:
            # Build query from filters
            if request.bank_name:
                query["card_issuer.bank_name"] = {"$regex": request.bank_name, "$options": "i"}
            
            if request.benefit_type:
                query["benefits.benefit_type"] = request.benefit_type
            
            if request.merchant_name:
                query["merchants_vendors.merchant_name"] = {"$regex": request.merchant_name, "$options": "i"}
            
            if request.max_salary:
                query["$or"] = [
                    {"eligibility.minimum_salary": {"$lte": request.max_salary}},
                    {"eligibility.minimum_salary": None}
                ]
            
            if request.card_category:
                query["card_category"] = request.card_category
            
            skip = (page - 1) * limit
            results = await ExtractedDataV2.find(query).skip(skip).limit(limit).to_list()
        
        total = len(results) if request.query else await ExtractedDataV2.find(query).count()
        
        data_list = [document_to_response(r) for r in results]
        
        return ExtractedDataListResponseV2(
            success=True,
            data=data_list,
            pagination={
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit
            }
        )
    except Exception as e:
        logger.error(f"Search V2 extractions failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-bank/{bank_name}", response_model=ExtractedDataListResponseV2)
async def get_by_bank(bank_name: str, limit: int = Query(50, ge=1, le=100)):
    """Get all cards from a specific bank."""
    try:
        results = await ExtractedDataV2.find_by_bank(bank_name, limit)
        data_list = [document_to_response(r) for r in results]
        
        return ExtractedDataListResponseV2(
            success=True,
            data=data_list,
            pagination={"total": len(data_list), "page": 1, "limit": limit, "pages": 1}
        )
    except Exception as e:
        logger.error(f"Get by bank failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-merchant/{merchant_name}", response_model=ExtractedDataListResponseV2)
async def get_by_merchant(merchant_name: str, limit: int = Query(50, ge=1, le=100)):
    """Get all cards with offers at a specific merchant."""
    try:
        results = await ExtractedDataV2.find_by_merchant(merchant_name, limit)
        data_list = [document_to_response(r) for r in results]
        
        return ExtractedDataListResponseV2(
            success=True,
            data=data_list,
            pagination={"total": len(data_list), "page": 1, "limit": limit, "pages": 1}
        )
    except Exception as e:
        logger.error(f"Get by merchant failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= FLEXIBLE INTELLIGENCE EXTRACTION =============

class IntelligenceExtractionRequest(BaseModel):
    """Request for flexible intelligence extraction."""
    url: HttpUrl
    selected_urls: List[str] = Field(default_factory=list)
    process_pdfs: bool = Field(default=True)
    bypass_cache: bool = Field(default=False)
    keywords: Optional[List[str]] = Field(default=None, description="Custom keywords for relevance scoring")


class IntelligenceItemResponse(BaseModel):
    """Response model for a single intelligence item."""
    item_id: str
    title: str
    description: str
    category: str
    tags: List[str] = []
    value: Optional[Dict[str, Any]] = None
    conditions: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    is_headline: bool = False
    is_conditional: bool = False
    requires_enrollment: bool = False
    source_url: Optional[str] = None


class IntelligenceExtractionResponse(BaseModel):
    """Response for flexible intelligence extraction."""
    success: bool
    card: Dict[str, Any]
    intelligence: List[IntelligenceItemResponse]
    fees: Dict[str, Any]
    eligibility: Dict[str, Any]
    
    # Summary stats
    total_items: int
    items_by_category: Dict[str, int]
    all_tags: List[str]
    all_entities: List[Dict[str, Any]]
    
    # Quality metrics
    confidence_score: float
    completeness_score: float
    
    # Sources - URLs processed
    sources_processed: List[str]
    
    # Raw extraction reference
    raw_extraction_id: Optional[str] = None
    extraction_id: Optional[str] = None  # Alias for raw_extraction_id
    detected_patterns: Optional[Dict[str, int]] = None  # Pattern type -> count
    
    # Primary URL info
    primary_url: Optional[str] = None
    primary_title: Optional[str] = None
    detected_card_name: Optional[str] = None
    detected_bank: Optional[str] = None
    
    # Full source documents for review
    sources: Optional[List[Dict[str, Any]]] = None
    
    message: Optional[str] = None


@router.post("/extract-intelligence", response_model=IntelligenceExtractionResponse)
async def extract_intelligence(request: IntelligenceExtractionRequest):
    """
    Extract flexible intelligence from a credit card URL.
    
    This endpoint:
    1. Fetches content from the URL and related links
    2. Stores ALL raw extracted data to MongoDB (before LLM processing)
    3. Uses LLM to extract structured intelligence
    
    The raw data is preserved with full metadata including:
    - Source URLs and parent relationships
    - Keywords used for relevance scoring
    - All detected patterns (fees, cashback rates, etc.)
    - Section scores and selection criteria
    """
    from app.services.intelligence_extraction_service import intelligence_extraction_service
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.core.database import get_database
    
    try:
        url = str(request.url)
        logger.info(f"Starting flexible intelligence extraction for: {url}")
        
        # Get database connection
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        # Determine keywords to use
        keywords_to_use = request.keywords if request.keywords else intelligence_extraction_service.DEFAULT_KEYWORDS
        keyword_source = "custom" if request.keywords else "default"
        
        # First, scrape the content
        scraped = await enhanced_web_scraper_service.scrape_url_comprehensive(
            url,
            follow_links=False,
            max_depth=0
        )
        
        # Extract card name and bank from title
        card_name_hint = scraped.title.split('|')[0].strip() if scraped.title else None
        bank_hint = None
        for bank_name in ['Emirates NBD', 'FAB', 'ADCB', 'Mashreq', 'RAKBANK', 'DIB']:
            if bank_name.lower() in url.lower() or (scraped.title and bank_name.lower() in scraped.title.lower()):
                bank_hint = bank_name
                break
        
        # Create raw extraction record
        raw_extraction_id = await raw_storage.create_extraction(
            primary_url=url,
            keywords=keywords_to_use,
            keyword_source=keyword_source,
            card_name_hint=card_name_hint,
            bank_hint=bank_hint
        )
        
        logger.info(f"Created raw extraction record: {raw_extraction_id}")
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "fetching")
        
        # Get bank config
        bank_config = enhanced_web_scraper_service._get_bank_config(url)
        
        # Store primary source
        await raw_storage.add_source(
            extraction_id=raw_extraction_id,
            url=url,
            source_type="web",
            parent_url=None,
            depth=0,
            raw_content=scraped.raw_text or "",
            cleaned_content=scraped.raw_text or "",  # Could apply more cleaning
            title=scraped.title,
            http_status=200
        )
        
        # Fetch selected URLs if provided
        all_content = scraped.raw_text or ""
        sources_processed = [url]
        
        if request.selected_urls:
            logger.info(f"Fetching {len(request.selected_urls)} additional URLs")
            linked_content = await enhanced_web_scraper_service._fetch_related_content(
                request.selected_urls,
                bank_config
            )
            
            for link_url, content in linked_content.items():
                # Determine source type
                source_type = "pdf" if link_url.lower().endswith('.pdf') else "web"
                
                # Store each source
                await raw_storage.add_source(
                    extraction_id=raw_extraction_id,
                    url=link_url,
                    source_type=source_type,
                    parent_url=url,
                    depth=1,
                    raw_content=content,
                    cleaned_content=content,
                    http_status=200 if content else None,
                    fetch_error=None if content else "Empty content"
                )
                
                all_content += f"\n\n--- Content from {link_url} ---\n{content}"
                sources_processed.append(link_url)
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "parsing")
        
        # Detect patterns in all content and store them
        detected_patterns = await raw_storage.detect_and_store_patterns(
            extraction_id=raw_extraction_id,
            content=all_content,
            source_url=url
        )
        
        # Store sections with their scores (this is done inside intelligence_extraction_service)
        # But we need to capture this data - let's update the preprocess step to return section data
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "extracting")
        
        # Extract intelligence using the new service with custom keywords
        intelligence_doc = await intelligence_extraction_service.extract_intelligence(
            content=all_content,
            source_url=url,
            card_name_hint=card_name_hint,
            bank_hint=bank_hint,
            custom_keywords=request.keywords,  # Pass custom keywords from request
            raw_extraction_id=raw_extraction_id,  # Pass for section storage
            raw_storage=raw_storage  # Pass storage service
        )
        
        # Convert to response format
        intelligence_items = []
        for item in intelligence_doc.intelligence:
            # Handle value - could be Pydantic model or None
            value_dict = None
            if item.value:
                if hasattr(item.value, 'model_dump'):
                    value_dict = item.value.model_dump()
                elif hasattr(item.value, '__dict__'):
                    value_dict = item.value.__dict__
                else:
                    value_dict = {"raw_value": str(item.value)}
            
            # Handle conditions
            conditions_list = []
            for c in item.conditions:
                if hasattr(c, 'model_dump'):
                    conditions_list.append(c.model_dump())
                elif hasattr(c, '__dict__'):
                    conditions_list.append(c.__dict__)
                else:
                    conditions_list.append({"description": str(c)})
            
            # Handle entities
            entities_list = []
            for e in item.entities:
                if hasattr(e, 'model_dump'):
                    entities_list.append(e.model_dump())
                elif hasattr(e, '__dict__'):
                    entities_list.append(e.__dict__)
                else:
                    entities_list.append({"name": str(e)})
            
            # Handle source
            source_url = None
            if item.source:
                if hasattr(item.source, 'url'):
                    source_url = item.source.url
            
            intelligence_items.append(IntelligenceItemResponse(
                item_id=item.item_id,
                title=item.title,
                description=item.description,
                category=item.category.value if hasattr(item.category, 'value') else str(item.category),
                tags=item.tags,
                value=value_dict,
                conditions=conditions_list,
                entities=entities_list,
                is_headline=item.is_headline,
                is_conditional=item.is_conditional,
                requires_enrollment=item.requires_enrollment,
                source_url=source_url
            ))
        
        # Build category counts
        items_by_category = {}
        for item in intelligence_doc.intelligence:
            cat = item.category.value if hasattr(item.category, 'value') else str(item.category)
            items_by_category[cat] = items_by_category.get(cat, 0) + 1
        
        # Convert card to dict
        card_dict = {}
        if hasattr(intelligence_doc.card, 'model_dump'):
            card_dict = intelligence_doc.card.model_dump()
        elif hasattr(intelligence_doc.card, '__dict__'):
            card_dict = {k: v for k, v in intelligence_doc.card.__dict__.items() if not k.startswith('_')}
        
        # Convert fees to dict
        fees_dict = {}
        if hasattr(intelligence_doc.fees, 'model_dump'):
            fees_dict = intelligence_doc.fees.model_dump()
        elif hasattr(intelligence_doc.fees, '__dict__'):
            fees_dict = {k: (v.model_dump() if hasattr(v, 'model_dump') else v) 
                        for k, v in intelligence_doc.fees.__dict__.items() if not k.startswith('_')}
        
        # Convert eligibility to dict
        elig_dict = {}
        if hasattr(intelligence_doc.eligibility, 'model_dump'):
            elig_dict = intelligence_doc.eligibility.model_dump()
        elif hasattr(intelligence_doc.eligibility, '__dict__'):
            elig_dict = {k: (v.model_dump() if hasattr(v, 'model_dump') else v) 
                        for k, v in intelligence_doc.eligibility.__dict__.items() if not k.startswith('_')}
        
        # Convert entities to list of dicts
        all_entities_list = []
        for e in intelligence_doc.all_entities:
            if hasattr(e, 'model_dump'):
                all_entities_list.append(e.model_dump())
            elif hasattr(e, '__dict__'):
                all_entities_list.append({k: v for k, v in e.__dict__.items() if not k.startswith('_')})
            else:
                all_entities_list.append({"name": str(e)})
        
        # Mark extraction as completed and link to LLM results
        await raw_storage.update_status(raw_extraction_id, "completed", "completed")
        
        # Create pattern count summary
        pattern_counts = {k: len(v) for k, v in detected_patterns.items()} if detected_patterns else {}
        
        # Get full source data for frontend review
        raw_extraction = await raw_storage.get_extraction(raw_extraction_id)
        sources_data = raw_extraction.get("sources", []) if raw_extraction else []
        
        return IntelligenceExtractionResponse(
            success=True,
            card=card_dict,
            intelligence=intelligence_items,
            fees=fees_dict,
            eligibility=elig_dict,
            total_items=len(intelligence_items),
            items_by_category=items_by_category,
            all_tags=intelligence_doc.all_tags,
            all_entities=all_entities_list,
            confidence_score=intelligence_doc.confidence_score,
            completeness_score=intelligence_doc.completeness_score,
            sources_processed=sources_processed,
            raw_extraction_id=raw_extraction_id,
            extraction_id=raw_extraction_id,
            detected_patterns=pattern_counts,
            primary_url=url,
            primary_title=scraped.title,
            detected_card_name=card_name_hint,
            detected_bank=bank_hint,
            sources=sources_data,
            message=f"Extracted {len(intelligence_items)} intelligence items from {len(sources_processed)} sources. Raw data stored with ID: {raw_extraction_id}"
        )
        
    except Exception as e:
        logger.error(f"Intelligence extraction failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Try to mark extraction as failed if we have the ID
        try:
            if 'raw_extraction_id' in locals() and raw_extraction_id:
                await raw_storage.update_status(raw_extraction_id, "failed", "error")
                await raw_storage.add_error(raw_extraction_id, "extraction_error", str(e))
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(e))


# ============== Text Intelligence Extraction ==============

class TextIntelligenceExtractionRequest(BaseModel):
    """Request for text-based intelligence extraction."""
    text: str = Field(..., min_length=50, description="Text content to extract from")
    source_name: Optional[str] = Field(None, description="Name/title for the text source")
    keywords: Optional[List[str]] = Field(None, description="Custom keywords for relevance scoring")


@router.post("/extract-intelligence-text", response_model=IntelligenceExtractionResponse)
async def extract_intelligence_from_text(request: TextIntelligenceExtractionRequest):
    """
    Extract flexible intelligence from text content.
    
    This endpoint:
    1. Stores the text as a raw source in MongoDB
    2. Uses LLM to extract structured intelligence
    3. Returns sources for review before approval
    """
    from app.services.intelligence_extraction_service import intelligence_extraction_service
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.core.database import get_database
    
    try:
        text = request.text
        source_name = request.source_name or "Pasted Text"
        logger.info(f"Starting text intelligence extraction: {len(text)} chars")
        
        # Get database connection
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        # Determine keywords to use
        keywords_to_use = request.keywords if request.keywords else intelligence_extraction_service.DEFAULT_KEYWORDS
        keyword_source = "custom" if request.keywords else "default"
        
        # Try to detect card name and bank from text
        card_name_hint = None
        bank_hint = None
        for bank_name in ['Emirates NBD', 'FAB', 'ADCB', 'Mashreq', 'RAKBANK', 'DIB']:
            if bank_name.lower() in text.lower():
                bank_hint = bank_name
                break
        
        # Create raw extraction record
        raw_extraction_id = await raw_storage.create_extraction(
            primary_url=f"text://{source_name}",
            keywords=keywords_to_use,
            keyword_source=keyword_source,
            card_name_hint=card_name_hint,
            bank_hint=bank_hint
        )
        
        logger.info(f"Created raw extraction record: {raw_extraction_id}")
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "fetching")
        
        # Store the text as a source
        await raw_storage.add_source(
            extraction_id=raw_extraction_id,
            url=f"text://{source_name}",
            source_type="text",
            parent_url=None,
            depth=0,
            raw_content=text,
            cleaned_content=text,
            title=source_name,
            http_status=200
        )
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "parsing")
        
        # Detect patterns
        detected_patterns = await raw_storage.detect_and_store_patterns(
            extraction_id=raw_extraction_id,
            content=text,
            source_url=f"text://{source_name}"
        )
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "extracting")
        
        # Extract intelligence using LLM
        intelligence_doc = await intelligence_extraction_service.extract_intelligence(
            content=text,
            source_url=f"text://{source_name}",
            card_name_hint=card_name_hint,
            bank_hint=bank_hint,
            custom_keywords=request.keywords,
            raw_extraction_id=raw_extraction_id,
            raw_storage=raw_storage
        )
        
        # Convert to response format
        intelligence_items = []
        items_by_category = {}
        
        for item in intelligence_doc.intelligence:
            value_str = None
            if item.value:
                if hasattr(item.value, 'model_dump'):
                    value_str = str(item.value.model_dump())
                else:
                    value_str = str(item.value)
            
            conditions_list = []
            if item.conditions:
                for cond in item.conditions:
                    if hasattr(cond, 'model_dump'):
                        conditions_list.append(cond.model_dump())
                    elif hasattr(cond, '__dict__'):
                        conditions_list.append({k: v for k, v in cond.__dict__.items() if not k.startswith('_')})
            
            entities_list = []
            if item.entities:
                for ent in item.entities:
                    if hasattr(ent, 'model_dump'):
                        entities_list.append(ent.model_dump())
                    elif hasattr(ent, '__dict__'):
                        entities_list.append({k: v for k, v in ent.__dict__.items() if not k.startswith('_')})
            
            intelligence_items.append(IntelligenceItemResponse(
                item_id=item.item_id,
                category=item.category,
                item_type=item.item_type,
                title=item.title,
                description=item.description,
                value=value_str,
                unit=item.unit,
                conditions=conditions_list,
                entities=entities_list,
                tags=item.tags,
                confidence=item.confidence,
                source_text=item.source_text,
                importance=item.importance
            ))
            
            items_by_category[item.category] = items_by_category.get(item.category, 0) + 1
        
        # Convert card to dict
        card_dict = {}
        if hasattr(intelligence_doc.card, 'model_dump'):
            card_dict = intelligence_doc.card.model_dump()
        elif hasattr(intelligence_doc.card, '__dict__'):
            card_dict = {k: v for k, v in intelligence_doc.card.__dict__.items() if not k.startswith('_')}
        
        # Convert fees to dict
        fees_dict = {}
        if hasattr(intelligence_doc.fees, 'model_dump'):
            fees_dict = intelligence_doc.fees.model_dump()
        elif hasattr(intelligence_doc.fees, '__dict__'):
            fees_dict = {k: (v.model_dump() if hasattr(v, 'model_dump') else v) 
                        for k, v in intelligence_doc.fees.__dict__.items() if not k.startswith('_')}
        
        # Convert eligibility to dict
        elig_dict = {}
        if hasattr(intelligence_doc.eligibility, 'model_dump'):
            elig_dict = intelligence_doc.eligibility.model_dump()
        elif hasattr(intelligence_doc.eligibility, '__dict__'):
            elig_dict = {k: (v.model_dump() if hasattr(v, 'model_dump') else v) 
                        for k, v in intelligence_doc.eligibility.__dict__.items() if not k.startswith('_')}
        
        # Convert entities to list
        all_entities_list = []
        for e in intelligence_doc.all_entities:
            if hasattr(e, 'model_dump'):
                all_entities_list.append(e.model_dump())
            elif hasattr(e, '__dict__'):
                all_entities_list.append({k: v for k, v in e.__dict__.items() if not k.startswith('_')})
            else:
                all_entities_list.append({"name": str(e)})
        
        # Mark extraction as completed
        await raw_storage.update_status(raw_extraction_id, "completed", "completed")
        
        # Create pattern count summary
        pattern_counts = {k: len(v) for k, v in detected_patterns.items()} if detected_patterns else {}
        
        # Get full source data for frontend review
        raw_extraction = await raw_storage.get_extraction(raw_extraction_id)
        sources_data = raw_extraction.get("sources", []) if raw_extraction else []
        
        return IntelligenceExtractionResponse(
            success=True,
            card=card_dict,
            intelligence=intelligence_items,
            fees=fees_dict,
            eligibility=elig_dict,
            total_items=len(intelligence_items),
            items_by_category=items_by_category,
            all_tags=intelligence_doc.all_tags,
            all_entities=all_entities_list,
            confidence_score=intelligence_doc.confidence_score,
            completeness_score=intelligence_doc.completeness_score,
            sources_processed=[f"text://{source_name}"],
            raw_extraction_id=raw_extraction_id,
            extraction_id=raw_extraction_id,
            detected_patterns=pattern_counts,
            primary_url=f"text://{source_name}",
            primary_title=source_name,
            detected_card_name=card_name_hint,
            detected_bank=bank_hint,
            sources=sources_data,
            message=f"Extracted {len(intelligence_items)} intelligence items from text. Raw data stored with ID: {raw_extraction_id}"
        )
        
    except Exception as e:
        logger.error(f"Text intelligence extraction failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        try:
            if 'raw_extraction_id' in locals() and raw_extraction_id:
                await raw_storage.update_status(raw_extraction_id, "failed", "error")
                await raw_storage.add_error(raw_extraction_id, "extraction_error", str(e))
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(e))


# ============== PDF Intelligence Extraction ==============

@router.post("/extract-intelligence-pdf", response_model=IntelligenceExtractionResponse)
async def extract_intelligence_from_pdf(
    file: UploadFile = File(...),
    keywords: Optional[str] = Query(None, description="Comma-separated keywords")
):
    """
    Extract flexible intelligence from a PDF file.
    
    This endpoint:
    1. Extracts text from PDF
    2. Stores as raw source in MongoDB
    3. Uses LLM to extract structured intelligence
    4. Returns sources for review before approval
    """
    from app.services.intelligence_extraction_service import intelligence_extraction_service
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.services.pdf_service import pdf_service
    from app.core.database import get_database
    
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        pdf_content = await file.read()
        
        if len(pdf_content) > settings.get_pdf_max_size_bytes():
            raise HTTPException(
                status_code=400,
                detail=f"PDF file too large (maximum {settings.PDF_MAX_SIZE_MB}MB)"
            )
        
        logger.info(f"Starting PDF intelligence extraction: {file.filename}, {len(pdf_content)} bytes")
        
        # Extract text from PDF
        text = await pdf_service.extract_text_from_pdf(pdf_content)
        
        if not text or len(text) < 50:
            raise HTTPException(status_code=400, detail="Could not extract meaningful text from PDF")
        
        logger.info(f"Extracted {len(text)} chars from PDF")
        
        # Get database connection
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        # Parse keywords
        keywords_list = None
        if keywords:
            keywords_list = [k.strip() for k in keywords.split(',') if k.strip()]
        
        keywords_to_use = keywords_list if keywords_list else intelligence_extraction_service.DEFAULT_KEYWORDS
        keyword_source = "custom" if keywords_list else "default"
        
        # Try to detect card name and bank from text
        card_name_hint = None
        bank_hint = None
        for bank_name in ['Emirates NBD', 'FAB', 'ADCB', 'Mashreq', 'RAKBANK', 'DIB']:
            if bank_name.lower() in text.lower():
                bank_hint = bank_name
                break
        
        # Create raw extraction record
        raw_extraction_id = await raw_storage.create_extraction(
            primary_url=f"pdf://{file.filename}",
            keywords=keywords_to_use,
            keyword_source=keyword_source,
            card_name_hint=card_name_hint,
            bank_hint=bank_hint
        )
        
        logger.info(f"Created raw extraction record: {raw_extraction_id}")
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "fetching")
        
        # Store the extracted text as a source
        await raw_storage.add_source(
            extraction_id=raw_extraction_id,
            url=f"pdf://{file.filename}",
            source_type="pdf",
            parent_url=None,
            depth=0,
            raw_content=text,
            cleaned_content=text,
            title=file.filename.replace('.pdf', '').replace('-', ' ').replace('_', ' ').title(),
            http_status=200
        )
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "parsing")
        
        # Detect patterns
        detected_patterns = await raw_storage.detect_and_store_patterns(
            extraction_id=raw_extraction_id,
            content=text,
            source_url=f"pdf://{file.filename}"
        )
        
        # Update status
        await raw_storage.update_status(raw_extraction_id, "processing", "extracting")
        
        # Extract intelligence using LLM
        intelligence_doc = await intelligence_extraction_service.extract_intelligence(
            content=text,
            source_url=f"pdf://{file.filename}",
            card_name_hint=card_name_hint,
            bank_hint=bank_hint,
            custom_keywords=keywords_list,
            raw_extraction_id=raw_extraction_id,
            raw_storage=raw_storage
        )
        
        # Convert to response format (same as text extraction)
        intelligence_items = []
        items_by_category = {}
        
        for item in intelligence_doc.intelligence:
            value_str = None
            if item.value:
                if hasattr(item.value, 'model_dump'):
                    value_str = str(item.value.model_dump())
                else:
                    value_str = str(item.value)
            
            conditions_list = []
            if item.conditions:
                for cond in item.conditions:
                    if hasattr(cond, 'model_dump'):
                        conditions_list.append(cond.model_dump())
                    elif hasattr(cond, '__dict__'):
                        conditions_list.append({k: v for k, v in cond.__dict__.items() if not k.startswith('_')})
            
            entities_list = []
            if item.entities:
                for ent in item.entities:
                    if hasattr(ent, 'model_dump'):
                        entities_list.append(ent.model_dump())
                    elif hasattr(ent, '__dict__'):
                        entities_list.append({k: v for k, v in ent.__dict__.items() if not k.startswith('_')})
            
            intelligence_items.append(IntelligenceItemResponse(
                item_id=item.item_id,
                category=item.category,
                item_type=item.item_type,
                title=item.title,
                description=item.description,
                value=value_str,
                unit=item.unit,
                conditions=conditions_list,
                entities=entities_list,
                tags=item.tags,
                confidence=item.confidence,
                source_text=item.source_text,
                importance=item.importance
            ))
            
            items_by_category[item.category] = items_by_category.get(item.category, 0) + 1
        
        # Convert card to dict
        card_dict = {}
        if hasattr(intelligence_doc.card, 'model_dump'):
            card_dict = intelligence_doc.card.model_dump()
        elif hasattr(intelligence_doc.card, '__dict__'):
            card_dict = {k: v for k, v in intelligence_doc.card.__dict__.items() if not k.startswith('_')}
        
        # Convert fees to dict
        fees_dict = {}
        if hasattr(intelligence_doc.fees, 'model_dump'):
            fees_dict = intelligence_doc.fees.model_dump()
        elif hasattr(intelligence_doc.fees, '__dict__'):
            fees_dict = {k: (v.model_dump() if hasattr(v, 'model_dump') else v) 
                        for k, v in intelligence_doc.fees.__dict__.items() if not k.startswith('_')}
        
        # Convert eligibility to dict
        elig_dict = {}
        if hasattr(intelligence_doc.eligibility, 'model_dump'):
            elig_dict = intelligence_doc.eligibility.model_dump()
        elif hasattr(intelligence_doc.eligibility, '__dict__'):
            elig_dict = {k: (v.model_dump() if hasattr(v, 'model_dump') else v) 
                        for k, v in intelligence_doc.eligibility.__dict__.items() if not k.startswith('_')}
        
        # Convert entities to list
        all_entities_list = []
        for e in intelligence_doc.all_entities:
            if hasattr(e, 'model_dump'):
                all_entities_list.append(e.model_dump())
            elif hasattr(e, '__dict__'):
                all_entities_list.append({k: v for k, v in e.__dict__.items() if not k.startswith('_')})
            else:
                all_entities_list.append({"name": str(e)})
        
        # Mark extraction as completed
        await raw_storage.update_status(raw_extraction_id, "completed", "completed")
        
        # Create pattern count summary
        pattern_counts = {k: len(v) for k, v in detected_patterns.items()} if detected_patterns else {}
        
        # Get full source data for frontend review
        raw_extraction = await raw_storage.get_extraction(raw_extraction_id)
        sources_data = raw_extraction.get("sources", []) if raw_extraction else []
        
        return IntelligenceExtractionResponse(
            success=True,
            card=card_dict,
            intelligence=intelligence_items,
            fees=fees_dict,
            eligibility=elig_dict,
            total_items=len(intelligence_items),
            items_by_category=items_by_category,
            all_tags=intelligence_doc.all_tags,
            all_entities=all_entities_list,
            confidence_score=intelligence_doc.confidence_score,
            completeness_score=intelligence_doc.completeness_score,
            sources_processed=[f"pdf://{file.filename}"],
            raw_extraction_id=raw_extraction_id,
            extraction_id=raw_extraction_id,
            detected_patterns=pattern_counts,
            primary_url=f"pdf://{file.filename}",
            primary_title=file.filename.replace('.pdf', '').replace('-', ' ').replace('_', ' ').title(),
            detected_card_name=card_name_hint,
            detected_bank=bank_hint,
            sources=sources_data,
            message=f"Extracted {len(intelligence_items)} intelligence items from PDF. Raw data stored with ID: {raw_extraction_id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF intelligence extraction failed: {str(e)}")
        import traceback
        traceback.print_exc()
        
        try:
            if 'raw_extraction_id' in locals() and raw_extraction_id:
                await raw_storage.update_status(raw_extraction_id, "failed", "error")
                await raw_storage.add_error(raw_extraction_id, "extraction_error", str(e))
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(e))


# ============== Raw Extraction Endpoints ==============

@router.get("/raw-extractions")
async def list_raw_extractions(
    limit: int = 20,
    skip: int = 0,
    status: Optional[str] = None,
    bank: Optional[str] = None
):
    """
    List all raw extraction records.
    
    These contain the full extracted data BEFORE LLM processing.
    """
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.core.database import get_database
    
    try:
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        extractions = await raw_storage.list_extractions(
            limit=limit,
            skip=skip,
            status=status,
            bank=bank
        )
        
        # Convert MongoDB ObjectId to string
        for ext in extractions:
            if '_id' in ext:
                ext['_id'] = str(ext['_id'])
        
        # Get total count
        query = {}
        if status:
            query["status"] = status
        if bank:
            query["detected_bank"] = {"$regex": bank, "$options": "i"}
        total = await db.raw_extractions.count_documents(query)
        
        return {
            "success": True,
            "total": total,
            "count": len(extractions),
            "extractions": extractions
        }
        
    except Exception as e:
        logger.error(f"Failed to list raw extractions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/raw-extractions/{extraction_id}")
async def get_raw_extraction(extraction_id: str, include_content: bool = False):
    """
    Get a specific raw extraction by ID.
    
    Args:
        extraction_id: The extraction ID
        include_content: If True, includes full raw content (can be large)
    """
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.core.database import get_database
    
    try:
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        if include_content:
            extraction = await raw_storage.get_extraction(extraction_id)
        else:
            extraction = await raw_storage.get_extraction_summary(extraction_id)
        
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Extraction {extraction_id} not found")
        
        # Convert MongoDB ObjectId to string
        if '_id' in extraction:
            extraction['_id'] = str(extraction['_id'])
        
        return {
            "success": True,
            "extraction": extraction
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get raw extraction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/raw-extractions/{extraction_id}/patterns")
async def get_extraction_patterns(extraction_id: str):
    """
    Get detected patterns from a raw extraction.
    
    Patterns include:
    - Annual fees
    - Cashback rates
    - Minimum salary requirements
    - Lounge access details
    - Insurance coverage
    - And more...
    """
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.core.database import get_database
    
    try:
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        extraction = await raw_storage.get_extraction(extraction_id)
        
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Extraction {extraction_id} not found")
        
        patterns = extraction.get("detected_patterns", {})
        
        # Calculate summary
        summary = {}
        for pattern_type, matches in patterns.items():
            summary[pattern_type] = {
                "count": len(matches),
                "examples": [m.get("raw_text", "") for m in matches[:3]]  # First 3 examples
            }
        
        return {
            "success": True,
            "extraction_id": extraction_id,
            "patterns": patterns,
            "summary": summary,
            "total_patterns": sum(len(v) for v in patterns.values())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/raw-extractions/{extraction_id}/sections")
async def get_extraction_sections(
    extraction_id: str,
    selected_only: bool = False,
    min_score: float = 0
):
    """
    Get sections from a raw extraction.
    
    Args:
        extraction_id: The extraction ID
        selected_only: If True, only returns sections that were selected for LLM
        min_score: Minimum relevance score filter
    """
    from app.services.raw_extraction_storage_service import RawExtractionStorageService
    from app.core.database import get_database
    
    try:
        db = await get_database()
        raw_storage = RawExtractionStorageService(db)
        
        extraction = await raw_storage.get_extraction(extraction_id)
        
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Extraction {extraction_id} not found")
        
        sections = extraction.get("sections", [])
        
        # Filter sections
        if selected_only:
            sections = [s for s in sections if s.get("is_selected", False)]
        
        if min_score > 0:
            sections = [s for s in sections if s.get("relevance_score", 0) >= min_score]
        
        return {
            "success": True,
            "extraction_id": extraction_id,
            "total_sections": len(extraction.get("sections", [])),
            "filtered_sections": len(sections),
            "sections": sections
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get extraction sections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Approved Intelligence Storage ==============

class ApprovedIntelligenceRequest(BaseModel):
    """Request to save approved intelligence data."""
    card: Dict[str, Any]
    intelligence: List[Dict[str, Any]]
    fees: Dict[str, Any] = {}
    eligibility: Dict[str, Any] = {}
    raw_extraction_id: Optional[str] = None
    total_items: int = 0
    approved_at: Optional[str] = None


@router.post("/save-approved")
async def save_approved_intelligence(request: ApprovedIntelligenceRequest):
    """
    Save approved/edited intelligence to the database.
    
    This endpoint is called after the user reviews, edits, and approves
    the extracted intelligence data.
    """
    from app.core.database import get_database
    from datetime import datetime
    import uuid
    
    try:
        db = await get_database()
        collection = db.approved_intelligence
        
        # Build the document to save
        doc = {
            "saved_id": str(uuid.uuid4()),
            "card": request.card,
            "intelligence": request.intelligence,
            "fees": request.fees,
            "eligibility": request.eligibility,
            "raw_extraction_id": request.raw_extraction_id,
            "total_items": len(request.intelligence),
            "approved_at": request.approved_at or datetime.utcnow().isoformat(),
            "saved_at": datetime.utcnow(),
            
            # Summary fields for easier querying
            "card_name": request.card.get("name", "Unknown"),
            "bank_name": request.card.get("bank", "Unknown"),
            
            # Category breakdown
            "items_by_category": {},
            
            # Extract all tags for search
            "all_tags": [],
            
            # Status
            "status": "approved"
        }
        
        # Calculate category breakdown
        for item in request.intelligence:
            cat = item.get("category", "other")
            doc["items_by_category"][cat] = doc["items_by_category"].get(cat, 0) + 1
            
            # Collect tags
            tags = item.get("tags", [])
            doc["all_tags"].extend(tags)
        
        # Deduplicate tags
        doc["all_tags"] = list(set(doc["all_tags"]))
        
        # Insert into database
        result = await collection.insert_one(doc)
        
        logger.info(f"Saved approved intelligence: {doc['saved_id']} with {doc['total_items']} items")
        
        # Update raw extraction to mark as approved
        if request.raw_extraction_id:
            try:
                raw_collection = db.raw_extractions
                await raw_collection.update_one(
                    {"extraction_id": request.raw_extraction_id},
                    {
                        "$set": {
                            "approved": True,
                            "approved_id": doc["saved_id"],
                            "approved_at": datetime.utcnow()
                        }
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to update raw extraction: {e}")
        
        return {
            "success": True,
            "saved_id": doc["saved_id"],
            "total_items": doc["total_items"],
            "card_name": doc["card_name"],
            "bank_name": doc["bank_name"],
            "message": f"Successfully saved {doc['total_items']} intelligence items"
        }
        
    except Exception as e:
        logger.error(f"Failed to save approved intelligence: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approved")
async def list_approved_intelligence(
    limit: int = 20,
    skip: int = 0,
    bank: Optional[str] = None,
    card_name: Optional[str] = None
):
    """List all approved intelligence records."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_intelligence
        
        # Build query
        query = {}
        if bank:
            query["bank_name"] = {"$regex": bank, "$options": "i"}
        if card_name:
            query["card_name"] = {"$regex": card_name, "$options": "i"}
        
        # Fetch records
        cursor = collection.find(query).sort("saved_at", -1).skip(skip).limit(limit)
        records = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string
        for rec in records:
            rec["_id"] = str(rec["_id"])
        
        # Get total count
        total = await collection.count_documents(query)
        
        return {
            "success": True,
            "total": total,
            "count": len(records),
            "records": records
        }
        
    except Exception as e:
        logger.error(f"Failed to list approved intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approved/{saved_id}")
async def get_approved_intelligence(saved_id: str):
    """Get a specific approved intelligence record."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_intelligence
        
        record = await collection.find_one({"saved_id": saved_id})
        
        if not record:
            raise HTTPException(status_code=404, detail=f"Record {saved_id} not found")
        
        record["_id"] = str(record["_id"])
        
        return {
            "success": True,
            "record": record
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get approved intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/approved/{saved_id}")
async def delete_approved_intelligence(saved_id: str):
    """Delete an approved intelligence record."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_intelligence
        
        result = await collection.delete_one({"saved_id": saved_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"Record {saved_id} not found")
        
        return {
            "success": True,
            "message": f"Deleted record {saved_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete approved intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Approved Raw Data Storage ==============

class ApprovedRawDataRequest(BaseModel):
    """Request to save approved raw data."""
    primary_url: str
    primary_title: Optional[str] = None
    detected_card_name: Optional[str] = None
    detected_bank: Optional[str] = None
    keywords_used: List[str] = []
    sources: List[Dict[str, Any]]
    total_sources: int = 0
    total_content_length: int = 0
    raw_extraction_id: Optional[str] = None


@router.post("/save-approved-raw")
async def save_approved_raw_data(request: ApprovedRawDataRequest):
    """
    Save approved raw extracted data to the database.
    
    This stores the raw content from each source (web page, PDF) 
    BEFORE any LLM processing. This data can later be used to
    create prompts and extract intelligence.
    
    Each source includes:
    - URL and source type
    - Parent URL relationship
    - Raw and cleaned content
    - Keywords matched
    - Extraction timestamp
    """
    from app.core.database import get_database
    from datetime import datetime
    import uuid
    
    try:
        db = await get_database()
        collection = db.approved_raw_data
        
        # Build the document to save
        doc = {
            "saved_id": str(uuid.uuid4()),
            "primary_url": request.primary_url,
            "primary_title": request.primary_title,
            "detected_card_name": request.detected_card_name,
            "detected_bank": request.detected_bank,
            "keywords_used": request.keywords_used,
            "sources": request.sources,
            "total_sources": request.total_sources or len(request.sources),
            "total_content_length": request.total_content_length,
            "raw_extraction_id": request.raw_extraction_id,
            "stored_at": datetime.utcnow(),
            "status": "pending_processing",  # pending_processing, processed, failed
            "processed_at": None,
            "intelligence_id": None,  # Will be set when LLM processes this
        }
        
        # Calculate content length if not provided
        if not doc["total_content_length"]:
            doc["total_content_length"] = sum(
                s.get("cleaned_content_length", 0) or len(s.get("cleaned_content", ""))
                for s in request.sources
            )
        
        # Insert into database
        result = await collection.insert_one(doc)
        
        logger.info(f"Saved approved raw data: {doc['saved_id']} with {doc['total_sources']} sources, {doc['total_content_length']} chars")
        
        # Update raw extraction to mark as approved if exists
        if request.raw_extraction_id:
            try:
                raw_collection = db.raw_extractions
                await raw_collection.update_one(
                    {"extraction_id": request.raw_extraction_id},
                    {
                        "$set": {
                            "approved": True,
                            "approved_raw_id": doc["saved_id"],
                            "approved_at": datetime.utcnow()
                        }
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to update raw extraction: {e}")
        
        return {
            "success": True,
            "saved_id": doc["saved_id"],
            "total_sources": doc["total_sources"],
            "total_content_length": doc["total_content_length"],
            "primary_url": doc["primary_url"],
            "message": f"Successfully stored {doc['total_sources']} sources ({doc['total_content_length']} characters)"
        }
        
    except Exception as e:
        logger.error(f"Failed to save approved raw data: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approved-raw")
async def list_approved_raw_data(
    limit: int = 20,
    skip: int = 0,
    status: Optional[str] = None,
    bank: Optional[str] = None
):
    """List all approved raw data records."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_raw_data
        
        # Build query
        query = {}
        if status:
            query["status"] = status
        if bank:
            query["detected_bank"] = {"$regex": bank, "$options": "i"}
        
        # Fetch records (exclude large content fields for listing)
        cursor = collection.find(
            query,
            {
                "sources.raw_content": 0,
                "sources.cleaned_content": 0
            }
        ).sort("stored_at", -1).skip(skip).limit(limit)
        
        records = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string
        for rec in records:
            rec["_id"] = str(rec["_id"])
        
        # Get total count
        total = await collection.count_documents(query)
        
        return {
            "success": True,
            "total": total,
            "count": len(records),
            "records": records
        }
        
    except Exception as e:
        logger.error(f"Failed to list approved raw data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approved-raw/{saved_id}")
async def get_approved_raw_data(saved_id: str, include_content: bool = True):
    """Get a specific approved raw data record."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_raw_data
        
        # Build projection
        projection = None
        if not include_content:
            projection = {
                "sources.raw_content": 0,
                "sources.cleaned_content": 0
            }
        
        record = await collection.find_one({"saved_id": saved_id}, projection)
        
        if not record:
            raise HTTPException(status_code=404, detail=f"Record {saved_id} not found")
        
        record["_id"] = str(record["_id"])
        
        return {
            "success": True,
            "record": record
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get approved raw data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/approved-raw/{saved_id}")
async def delete_approved_raw_data(saved_id: str):
    """Delete an approved raw data record."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_raw_data
        
        result = await collection.delete_one({"saved_id": saved_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"Record {saved_id} not found")
        
        return {
            "success": True,
            "message": f"Deleted record {saved_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete approved raw data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approved-raw/{saved_id}/mark-processed")
async def mark_raw_data_processed(saved_id: str, intelligence_id: Optional[str] = None):
    """Mark a raw data record as processed by LLM."""
    from app.core.database import get_database
    from datetime import datetime
    
    try:
        db = await get_database()
        collection = db.approved_raw_data
        
        result = await collection.update_one(
            {"saved_id": saved_id},
            {
                "$set": {
                    "status": "processed",
                    "processed_at": datetime.utcnow(),
                    "intelligence_id": intelligence_id
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Record {saved_id} not found")
        
        return {
            "success": True,
            "message": f"Marked record {saved_id} as processed"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark raw data as processed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Pipeline Endpoints ==============

@router.get("/pipelines")
async def list_pipelines():
    """List all available benefit extraction pipelines."""
    try:
        from app.pipelines import pipeline_registry
        
        pipelines = pipeline_registry.list_pipelines()
        return {
            "success": True,
            "count": len(pipelines),
            "pipelines": pipelines
        }
    except Exception as e:
        logger.error(f"Failed to list pipelines: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipelines/{pipeline_name}")
async def get_pipeline_info(pipeline_name: str):
    """Get detailed info about a specific pipeline."""
    try:
        from app.pipelines import pipeline_registry
        
        info = pipeline_registry.get_pipeline_info(pipeline_name)
        if not info:
            raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' not found")
        
        return {
            "success": True,
            "pipeline": info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pipeline info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipelines/run/{pipeline_name}/{raw_data_id}")
async def run_single_pipeline(
    pipeline_name: str,
    raw_data_id: str,
    save_results: bool = True
):
    """
    Run a specific pipeline on approved raw data.
    
    Args:
        pipeline_name: Name of the pipeline to run (e.g., 'cashback', 'lounge_access')
        raw_data_id: The saved_id of the approved raw data
        save_results: Whether to save results to MongoDB
    """
    from app.pipelines import pipeline_registry
    from app.core.database import get_database
    
    try:
        db = await get_database()
        
        result = await pipeline_registry.run_pipeline(
            pipeline_name, 
            db, 
            raw_data_id, 
            save_results
        )
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail=f"Pipeline '{pipeline_name}' not found"
            )
        
        return {
            "success": True,
            "result": result.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class RunPipelinesRequest(BaseModel):
    """Request body for running pipelines."""
    pipeline_names: Optional[List[str]] = None
    source_indices: Optional[List[int]] = None


@router.post("/pipelines/run-all/{raw_data_id}")
async def run_all_pipelines(
    raw_data_id: str,
    request: Optional[RunPipelinesRequest] = None,
    save_results: bool = True,
    parallel: bool = True
):
    """
    Run all (or selected) pipelines on approved raw data.
    
    Args:
        raw_data_id: The saved_id of the approved raw data
        request: Optional body with pipeline_names and source_indices
        save_results: Whether to save results to MongoDB
        parallel: Run pipelines in parallel (faster) or sequential
    """
    from app.pipelines import pipeline_registry
    from app.core.database import get_database
    
    # Extract from request body if provided
    pipeline_names = request.pipeline_names if request else None
    source_indices = request.source_indices if request else None
    
    try:
        db = await get_database()
        
        # Log what we're about to process
        logger.info(f"========== RUN ALL PIPELINES REQUEST ==========")
        logger.info(f"raw_data_id: {raw_data_id}")
        logger.info(f"pipeline_names: {pipeline_names}")
        logger.info(f"source_indices: {source_indices}")
        logger.info(f"parallel: {parallel}")
        
        # Verify the raw data exists and log its source count
        collection = db.approved_raw_data
        raw_data = await collection.find_one({"saved_id": raw_data_id})
        if raw_data:
            total_sources = len(raw_data.get('sources', []))
            logger.info(f"Found raw_data with {total_sources} total sources")
            logger.info(f"primary_url: {raw_data.get('primary_url')}")
            
            # If source_indices provided, filter sources
            if source_indices is not None and len(source_indices) > 0:
                logger.info(f"Filtering to {len(source_indices)} selected sources: {source_indices}")
        else:
            logger.error(f"raw_data_id {raw_data_id} NOT FOUND in database!")
        
        result = await pipeline_registry.run_all_pipelines(
            db,
            raw_data_id,
            save_results=save_results,
            parallel=parallel,
            pipeline_names=pipeline_names,
            source_indices=source_indices
        )
        
        return {
            "success": True,
            "result": result.to_dict()
        }
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipelines/results/{raw_data_id}")
async def get_pipeline_results(
    raw_data_id: str,
    pipeline_name: Optional[str] = None
):
    """
    Get stored pipeline results for a raw data record.
    
    Args:
        raw_data_id: The saved_id of the approved raw data
        pipeline_name: Optional - filter by specific pipeline
    """
    from app.pipelines import pipeline_registry
    from app.core.database import get_database
    
    try:
        db = await get_database()
        
        results = await pipeline_registry.get_pipeline_results(
            db, 
            raw_data_id, 
            pipeline_name
        )
        
        return {
            "success": True,
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Failed to get pipeline results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipelines/aggregated/{raw_data_id}")
async def get_aggregated_results(raw_data_id: str):
    """
    Get aggregated results from all pipelines for a raw data record.
    
    This returns a combined view of all benefits extracted by all pipelines.
    """
    from app.pipelines import pipeline_registry
    from app.core.database import get_database
    
    try:
        db = await get_database()
        
        result = await pipeline_registry.get_aggregated_results(db, raw_data_id)
        
        if not result:
            return {
                "success": True,
                "message": "No aggregated results found. Run pipelines first.",
                "result": None
            }
        
        return {
            "success": True,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Failed to get aggregated results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-approved-benefits")
async def save_approved_benefits(request: Request):
    """
    Save approved/selected benefits from pipeline extraction to MongoDB.
    
    This creates a final processed record with the user-approved benefits.
    """
    from app.core.database import get_database
    from datetime import datetime
    import uuid
    
    try:
        body = await request.json()
        db = await get_database()
        
        raw_data_id = body.get('raw_data_id')
        benefits = body.get('benefits', [])
        card_name = body.get('card_name', 'Unknown Card')
        bank_name = body.get('bank_name', 'Unknown Bank')
        pipelines_used = body.get('pipelines_used', [])
        
        if not raw_data_id:
            raise HTTPException(status_code=400, detail="raw_data_id is required")
        
        if not benefits:
            raise HTTPException(status_code=400, detail="No benefits to save")
        
        # Create the approved benefits document
        approved_id = str(uuid.uuid4())
        
        doc = {
            "approved_id": approved_id,
            "raw_data_id": raw_data_id,
            "card_name": card_name,
            "bank_name": bank_name,
            "benefits": benefits,
            "total_benefits": len(benefits),
            "pipelines_used": pipelines_used,
            "benefit_types": list(set(b.get('benefit_type') for b in benefits)),
            "high_confidence_count": sum(1 for b in benefits if b.get('confidence_level') == 'high'),
            "medium_confidence_count": sum(1 for b in benefits if b.get('confidence_level') == 'medium'),
            "low_confidence_count": sum(1 for b in benefits if b.get('confidence_level') == 'low'),
            "approved_at": datetime.utcnow(),
            "status": "approved"
        }
        
        # Save to approved_benefits collection
        collection = db.approved_benefits
        await collection.insert_one(doc)
        
        # Update the raw_data record status
        await db.approved_raw_data.update_one(
            {"saved_id": raw_data_id},
            {"$set": {"status": "processed", "processed_at": datetime.utcnow()}}
        )
        
        logger.info(f"Saved {len(benefits)} approved benefits for {raw_data_id}")
        
        return {
            "success": True,
            "approved_id": approved_id,
            "total_saved": len(benefits),
            "message": f"Successfully saved {len(benefits)} benefits"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save approved benefits: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approved-benefits")
async def list_approved_benefits(limit: int = 50, skip: int = 0):
    """List all approved benefit records."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_benefits
        
        cursor = collection.find({}).sort("approved_at", -1).skip(skip).limit(limit)
        records = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string
        for record in records:
            record['_id'] = str(record['_id'])
        
        total = await collection.count_documents({})
        
        return {
            "success": True,
            "total": total,
            "count": len(records),
            "records": records
        }
        
    except Exception as e:
        logger.error(f"Failed to list approved benefits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approved-benefits/{approved_id}")
async def get_approved_benefits(approved_id: str):
    """Get specific approved benefits record."""
    from app.core.database import get_database
    
    try:
        db = await get_database()
        collection = db.approved_benefits
        
        record = await collection.find_one({"approved_id": approved_id})
        
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        
        record['_id'] = str(record['_id'])
        
        return {
            "success": True,
            "record": record
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get approved benefits: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pipelines/benefit/{raw_data_id}/{benefit_id}")
async def delete_pipeline_benefit(raw_data_id: str, benefit_id: str):
    """
    Delete a specific benefit from pipeline results.
    
    This removes a single benefit from both the aggregated results and the 
    individual pipeline results stored in MongoDB.
    
    Args:
        raw_data_id: The saved_id of the approved raw data record
        benefit_id: The unique benefit_id to delete
    """
    from app.core.database import get_database
    from datetime import datetime
    
    try:
        db = await get_database()
        
        # 1. Remove from aggregated_pipeline_results collection
        aggregated_collection = db.aggregated_pipeline_results
        
        # Pull the benefit from all_benefits array
        aggregated_result = await aggregated_collection.update_one(
            {"raw_data_id": raw_data_id},
            {
                "$pull": {"all_benefits": {"benefit_id": benefit_id}},
                "$set": {"updated_at": datetime.utcnow()},
                "$push": {
                    "deleted_benefits": {
                        "benefit_id": benefit_id,
                        "deleted_at": datetime.utcnow()
                    }
                }
            }
        )
        
        # 2. Also remove from individual pipeline_results collection
        pipeline_collection = db.pipeline_results
        
        # Find and update any pipeline result that contains this benefit
        pipeline_result = await pipeline_collection.update_many(
            {"raw_data_id": raw_data_id},
            {
                "$pull": {"benefits": {"benefit_id": benefit_id}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # Check if any updates were made
        if aggregated_result.modified_count == 0 and pipeline_result.modified_count == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"Benefit {benefit_id} not found in results for {raw_data_id}"
            )
        
        # 3. Update the total count in aggregated results
        await aggregated_collection.update_one(
            {"raw_data_id": raw_data_id},
            [
                {"$set": {"total_benefits": {"$size": {"$ifNull": ["$all_benefits", []]}}}}
            ]
        )
        
        logger.info(f"Deleted benefit {benefit_id} from raw_data {raw_data_id}")
        
        return {
            "success": True,
            "message": f"Successfully deleted benefit {benefit_id}",
            "benefit_id": benefit_id,
            "raw_data_id": raw_data_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete benefit: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============== Generic ID Routes (MUST BE LAST) ==============
# These catch-all routes must be defined after all specific routes
# to prevent them from intercepting requests like /approved-raw, /raw-extractions, etc.

@router.get("/{extraction_id}", response_model=ExtractionResponseV2)
async def get_extraction_v2(extraction_id: str):
    """Get extraction by ID. This route must be last to not catch other routes."""
    try:
        result = await enhanced_extraction_service.get_by_id(extraction_id)
        return ExtractionResponseV2(
            success=True,
            data=document_to_response(result)
        )
    except Exception as e:
        logger.error(f"Get V2 extraction failed: {str(e)}")
        raise HTTPException(status_code=404, detail="Extraction not found")


@router.delete("/{extraction_id}", response_model=DeleteResponseV2)
async def delete_extraction_v2(extraction_id: str):
    """Delete extraction by ID. This route must be last to not catch other routes."""
    try:
        await enhanced_extraction_service.delete(extraction_id)
        return DeleteResponseV2()
    except Exception as e:
        logger.error(f"Delete V2 extraction failed: {str(e)}")
        raise HTTPException(status_code=404, detail="Extraction not found")
