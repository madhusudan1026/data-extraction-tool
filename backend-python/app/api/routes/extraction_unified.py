"""
Unified Extraction API (V4)
Combines V2 (single-card) and V3 (bank-wide) into a seamless step-by-step workflow.

Workflow Steps:
1. Input Mode Selection (single card URL or bank-wide)
2. Card Selection
3. URL Discovery
4. URL Selection
5. Content Fetching
6. Raw Data Review & Approval
7. Pipeline Selection
8. Pipeline Execution
9. Results Review & Export
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, File, Form, UploadFile
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from enum import Enum
import hashlib
import uuid
import asyncio
import re
import base64
import httpx

from app.core.database import get_database
from app.core.banks import BANKS as BANK_CONFIGS, detect_bank_from_url, get_bank_name, list_banks_summary, detect_card_metadata
from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
from app.pipelines import pipeline_registry
from app.utils.logger import logger

router = APIRouter(prefix="/api/v4/extraction", tags=["Unified Extraction V4"])

# ============= CONSTANTS =============

SESSIONS_COLLECTION = "extraction_sessions"
CARDS_COLLECTION = "session_cards"
URLS_COLLECTION = "session_urls"
SOURCES_COLLECTION = "session_sources"
RESULTS_COLLECTION = "session_results"

# Default relevance keywords
DEFAULT_KEYWORDS = [
    'benefit', 'reward', 'cashback', 'discount', 'lounge', 'airport',
    'travel', 'insurance', 'annual fee', 'interest rate', 'eligibility',
    'minimum salary', 'points', 'miles', 'complimentary', 'free',
    'cinema', 'golf', 'concierge', 'valet', 'dining', 'shopping',
    'partner', 'merchant', 'offer', 'promotion', 'feature',
    'aed', 'usd', '%', 'per month', 'per year', 'waived',
    'mastercard', 'visa', 'diners', 'platinum', 'signature', 'world',
    'credit limit', 'supplementary', 'apply', 'requirement'
]


# ============= ENUMS =============

class SessionMode(str, Enum):
    SINGLE_CARD = "single_card"
    BANK_WIDE = "bank_wide"


class SessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ============= REQUEST/RESPONSE MODELS =============

class ExtractionOptions(BaseModel):
    process_pdfs: bool = True
    bypass_cache: bool = False
    max_depth: int = 2
    follow_links: bool = True
    use_playwright: bool = True


class CreateSessionRequest(BaseModel):
    mode: SessionMode = Field(..., description="Single card or bank-wide extraction")
    bank_key: Optional[str] = Field(None, description="Bank key for bank-wide mode")
    single_card_url: Optional[str] = Field(None, description="Card URL for single card mode")
    custom_bank_url: Optional[str] = Field(None, description="Custom bank cards page URL")
    custom_bank_name: Optional[str] = Field(None, description="Custom bank name")
    text_content: Optional[str] = Field(None, description="Direct text content")
    source_type: Optional[str] = Field("url", description="Source type: url, text, pdf")
    options: Optional[ExtractionOptions] = Field(default_factory=ExtractionOptions)


class SessionResponse(BaseModel):
    session_id: str
    mode: str
    current_step: int
    status: str
    bank_name: Optional[str] = None
    stats: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class SelectCardsRequest(BaseModel):
    card_ids: List[str] = Field(..., description="List of card IDs to select")


class SelectUrlsRequest(BaseModel):
    selected_urls: List[str] = Field(..., description="List of URLs to process")
    keywords: Optional[List[str]] = Field(None, description="Custom keywords for relevance")


class ApproveSourcesRequest(BaseModel):
    approved_source_ids: List[str] = Field(default_factory=list)
    rejected_source_ids: List[str] = Field(default_factory=list)


class RunPipelinesRequest(BaseModel):
    pipeline_names: List[str] = Field(..., description="Pipelines to run")
    card_ids: Optional[List[str]] = Field(None, description="Specific cards (optional)")


class ExportRequest(BaseModel):
    format: str = Field("json", description="Export format: json or csv")
    card_ids: Optional[List[str]] = Field(None, description="Specific cards to export")


# ============= HELPER FUNCTIONS =============

def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def calculate_relevance(text: str, url: str, keywords: List[str]) -> tuple:
    text_lower = (text + " " + url).lower()
    matches = [kw for kw in keywords if kw.lower() in text_lower]
    score = len(matches) / max(len(keywords), 1)
    
    if score >= 0.15:
        level = "high"
    elif score >= 0.05:
        level = "medium"
    else:
        level = "low"
    
    return score, level, matches


async def scrape_with_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Smart scrolling
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
                except:
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
        logger.error(f"Playwright error: {e}")
        return None


async def extract_card_image(html: str, card_url: str, card_name: str) -> Optional[Dict[str, Any]]:
    """
    Extract credit card image from a page.
    
    Looks for card images using multiple strategies:
    1. Images with 'card' in alt, class, or src
    2. Images near the card name text
    3. Product/hero images
    
    Returns:
        Dict with image_url, image_base64, and image_type, or None
    """
    from urllib.parse import urljoin, urlparse
    
    if not html:
        return None
    
    # Extract base URL
    parsed = urlparse(card_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # Patterns to find card images
    img_patterns = [
        # Pattern 1: img tag with card-related attributes
        r'<img[^>]+(?:class|id)=["\'][^"\']*card[^"\']*["\'][^>]*src=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*(?:class|id)=["\'][^"\']*card[^"\']*["\']',
        # Pattern 2: img with alt containing card
        r'<img[^>]+alt=["\'][^"\']*card[^"\']*["\'][^>]*src=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*alt=["\'][^"\']*card[^"\']*["\']',
        # Pattern 3: img with card name in alt
        r'<img[^>]+alt=["\'][^"\']*' + re.escape(card_name.split()[0]) + r'[^"\']*["\'][^>]*src=["\']([^"\']+)["\']',
        # Pattern 4: Common credit card image patterns
        r'<img[^>]+src=["\']([^"\']+(?:credit|platinum|signature|world|mastercard|visa)[^"\']*\.(?:png|jpg|jpeg|webp))["\']',
        # Pattern 5: Product images
        r'<img[^>]+(?:class|id)=["\'][^"\']*(?:product|hero|main)[^"\']*["\'][^>]*src=["\']([^"\']+)["\']',
    ]
    
    found_images = []
    
    for pattern in img_patterns:
        matches = re.finditer(pattern, html, re.IGNORECASE)
        for match in matches:
            img_src = match.group(1)
            
            # Skip tiny images, icons, logos
            if any(skip in img_src.lower() for skip in ['icon', 'logo', 'favicon', '1x1', 'pixel', 'tracking', 'spacer']):
                continue
            
            # Build full URL
            if img_src.startswith('http'):
                full_url = img_src
            elif img_src.startswith('//'):
                full_url = f"https:{img_src}"
            elif img_src.startswith('/'):
                full_url = urljoin(base_url, img_src)
            else:
                full_url = urljoin(card_url, img_src)
            
            # Score the image based on relevance
            score = 0
            img_lower = img_src.lower()
            
            if 'card' in img_lower:
                score += 3
            if 'credit' in img_lower:
                score += 2
            if any(kw in img_lower for kw in ['platinum', 'signature', 'world', 'infinite', 'gold']):
                score += 2
            if any(kw in img_lower for kw in ['mastercard', 'visa', 'amex', 'diners']):
                score += 1
            if 'product' in img_lower or 'hero' in img_lower:
                score += 1
            if img_src.endswith('.png') or img_src.endswith('.webp'):
                score += 1  # Prefer PNG/WebP for card images (often have transparency)
            
            found_images.append((score, full_url))
    
    if not found_images:
        logger.info(f"No card images found for: {card_name}")
        return None
    
    # Sort by score descending
    found_images.sort(key=lambda x: x[0], reverse=True)
    best_image_url = found_images[0][1]
    
    logger.info(f"Best card image for '{card_name}': {best_image_url}")
    
    # Download the image
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(best_image_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "image/png")
                image_data = response.content
                
                # Validate it's actually an image
                if len(image_data) < 1000:  # Too small to be a real card image
                    logger.warning(f"Image too small ({len(image_data)} bytes): {best_image_url}")
                    return None
                
                # Convert to base64
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                
                # Determine image type
                if 'png' in content_type:
                    image_type = 'image/png'
                elif 'webp' in content_type:
                    image_type = 'image/webp'
                elif 'jpeg' in content_type or 'jpg' in content_type:
                    image_type = 'image/jpeg'
                else:
                    # Guess from URL
                    if best_image_url.endswith('.png'):
                        image_type = 'image/png'
                    elif best_image_url.endswith('.webp'):
                        image_type = 'image/webp'
                    else:
                        image_type = 'image/jpeg'
                
                logger.info(f"Downloaded card image: {len(image_data)} bytes, type: {image_type}")
                
                return {
                    "image_url": best_image_url,
                    "image_base64": image_base64,
                    "image_type": image_type,
                    "image_size": len(image_data)
                }
            else:
                logger.warning(f"Failed to download image: HTTP {response.status_code}")
                return {"image_url": best_image_url}  # Return URL even if download failed
                
    except Exception as e:
        logger.error(f"Error downloading card image: {e}")
        return {"image_url": best_image_url}  # Return URL even if download failed


def extract_card_urls(html: str, base_url: str, patterns: List[str], exclude: List[str]) -> List[Dict]:
    from urllib.parse import urljoin
    
    cards = []
    seen_urls = set()
    
    href_pattern = r'href=["\']([^"\']+)["\']'
    
    for match in re.finditer(href_pattern, html, re.IGNORECASE):
        href = match.group(1)
        
        if any(exc in href.lower() for exc in exclude):
            continue
        
        for pattern in patterns:
            if re.search(pattern, href, re.IGNORECASE):
                if href.startswith('http'):
                    full_url = href
                elif href.startswith('/'):
                    full_url = urljoin(base_url, href)
                else:
                    continue
                
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    name_match = re.search(r'/([^/]+?)(?:-credit)?-card/?$', full_url, re.IGNORECASE)
                    card_name = name_match.group(1).replace('-', ' ').title() if name_match else "Unknown Card"
                    
                    cards.append({
                        "url": full_url,
                        "name": f"{card_name} Credit Card"
                    })
                break
    
    return cards


def detect_patterns(content: str) -> List[Dict]:
    patterns = []
    if not content:
        return patterns
    
    # Percentage patterns
    for match in re.finditer(r'(\d+(?:\.\d+)?)\s*%', content):
        context_start = max(0, match.start() - 50)
        context_end = min(len(content), match.end() + 50)
        patterns.append({
            "type": "percentage",
            "value": f"{match.group(1)}%",
            "context": content[context_start:context_end].strip()
        })
    
    # Currency patterns
    for match in re.finditer(r'(AED|USD|Dhs?\.?)\s*([\d,]+(?:\.\d{2})?)', content, re.IGNORECASE):
        context_start = max(0, match.start() - 50)
        context_end = min(len(content), match.end() + 50)
        patterns.append({
            "type": "currency",
            "value": f"{match.group(1)} {match.group(2)}",
            "context": content[context_start:context_end].strip()
        })
    
    # Count patterns
    for match in re.finditer(r'(\d+)\s*(times?|visits?|guests?|rounds?|nights?)', content, re.IGNORECASE):
        context_start = max(0, match.start() - 50)
        context_end = min(len(content), match.end() + 50)
        patterns.append({
            "type": "count",
            "value": f"{match.group(1)} {match.group(2)}",
            "context": content[context_start:context_end].strip()
        })
    
    return patterns[:50]


# ============= SESSION MANAGEMENT =============

@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """STEP 1: Create a new extraction session."""
    db = await get_database()
    
    if request.mode == SessionMode.SINGLE_CARD:
        if not request.single_card_url:
            raise HTTPException(status_code=400, detail="single_card_url required for single card mode")
    elif request.mode == SessionMode.BANK_WIDE:
        if not request.bank_key and not request.custom_bank_url:
            raise HTTPException(status_code=400, detail="bank_key or custom_bank_url required")
        if request.bank_key and request.bank_key not in BANK_CONFIGS:
            raise HTTPException(status_code=400, detail=f"Unknown bank: {request.bank_key}")
    
    bank_name = None
    if request.bank_key:
        bank_name = BANK_CONFIGS[request.bank_key]["name"]
    elif request.custom_bank_name:
        bank_name = request.custom_bank_name
    
    session_id = generate_id("sess")
    now = datetime.utcnow()
    
    session = {
        "session_id": session_id,
        "mode": request.mode.value,
        "bank_key": request.bank_key,
        "bank_name": bank_name,
        "single_card_url": request.single_card_url,
        "custom_bank_url": request.custom_bank_url,
        "source_type": request.source_type or "url",
        "text_content": request.text_content,
        "current_step": 1,
        "status": SessionStatus.IN_PROGRESS.value,
        "steps_completed": {f"step_{i}": False for i in range(1, 10)},
        "keywords": DEFAULT_KEYWORDS.copy(),
        "selected_pipelines": [],
        "options": {
            "process_pdfs": request.options.process_pdfs if request.options else True,
            "bypass_cache": request.options.bypass_cache if request.options else False,
            "max_depth": request.options.max_depth if request.options else 2,
            "follow_links": request.options.follow_links if request.options else True,
            "use_playwright": request.options.use_playwright if request.options else True,
        },
        "stats": {
            "cards_discovered": 0, "cards_selected": 0,
            "urls_discovered": 0, "urls_selected": 0, "urls_unique": 0,
            "sources_fetched": 0, "sources_approved": 0, "benefits_extracted": 0
        },
        "created_at": now,
        "updated_at": now
    }
    session["steps_completed"]["step_1"] = True
    
    await db[SESSIONS_COLLECTION].insert_one(session)
    logger.info(f"Created session {session_id} in {request.mode.value} mode")
    
    return SessionResponse(
        session_id=session_id, mode=request.mode.value, current_step=1,
        status=SessionStatus.IN_PROGRESS.value, bank_name=bank_name,
        stats=session["stats"], created_at=now, updated_at=now
    )


@router.post("/sessions/upload")
async def create_session_with_upload(
    file: UploadFile = File(...),
    mode: str = Form("single_card"),
    source_type: str = Form("pdf"),
    options: str = Form("{}"),
):
    """
    STEP 1 (PDF variant): Create a session by uploading a PDF file.
    The PDF content is extracted and stored as a source.
    """
    import json
    from io import BytesIO
    
    db = await get_database()
    now = datetime.utcnow()
    session_id = f"v4_sess_{uuid.uuid4().hex[:12]}"
    
    # Parse options
    try:
        opts = json.loads(options)
    except json.JSONDecodeError:
        opts = {}
    
    # Read and extract text from PDF
    pdf_bytes = await file.read()
    pdf_text = ""
    
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
        pdf_text = "\n\n".join(pages)
        doc.close()
        logger.info(f"[V4] Extracted {len(pdf_text)} chars from PDF: {file.filename}")
    except ImportError:
        logger.warning("[V4] PyMuPDF not installed, trying pdfplumber")
        try:
            import pdfplumber
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
                pdf_text = "\n\n".join(pages)
        except ImportError:
            raise HTTPException(status_code=500, detail="No PDF library available. Install pymupdf or pdfplumber.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract PDF text: {str(e)}")
    
    if not pdf_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract any text from the PDF")
    
    # Detect bank from content
    bank_name = ""
    bank_key = ""
    for bk, cfg in BANK_CONFIGS.items():
        if cfg["name"].lower() in pdf_text[:2000].lower():
            bank_key = bk
            bank_name = cfg["name"]
            break
    
    # Create session
    session = {
        "session_id": session_id,
        "mode": mode,
        "source_type": source_type,
        "bank_key": bank_key,
        "bank_name": bank_name,
        "options": opts,
        "current_step": 1,
        "status": "in_progress",
        "stats": {
            "cards_found": 0, "cards_selected": 0,
            "urls_discovered": 0, "urls_selected": 0, "urls_unique": 0,
            "sources_fetched": 0, "sources_cached": 0,
            "sources_saved": 0, "total_content_length": 0,
        },
        "steps_completed": {},
        "created_at": now,
        "updated_at": now,
    }
    await db[SESSIONS_COLLECTION].insert_one(session)
    
    # Store the PDF content as a source
    source_id = f"src_{uuid.uuid4().hex[:12]}"
    source_doc = {
        "source_id": source_id,
        "session_id": session_id,
        "url": f"upload://{file.filename}",
        "url_hash": hashlib.md5(file.filename.encode()).hexdigest()[:16],
        "title": file.filename,
        "source_type": "pdf",
        "depth": 0,
        "raw_content": pdf_text,
        "cleaned_content": pdf_text,
        "content_length": len(pdf_text),
        "fetch_status": "success",
        "approval_status": "approved",
        "fetched_at": now,
    }
    await db[SOURCES_COLLECTION].insert_one(source_doc)
    
    # Create a URL entry for the PDF
    url_doc = {
        "session_id": session_id,
        "url": f"upload://{file.filename}",
        "url_hash": source_doc["url_hash"],
        "title": file.filename,
        "source_type": "pdf",
        "depth": 0,
        "is_selected": True,
        "relevance_score": 1.0,
    }
    await db[URLS_COLLECTION].insert_one(url_doc)
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {
            "stats.urls_discovered": 1, "stats.urls_selected": 1,
            "stats.sources_fetched": 1, "stats.total_content_length": len(pdf_text),
            "updated_at": now,
        }}
    )
    
    session.pop("_id", None)
    return SessionResponse(
        session_id=session_id, mode=mode, current_step=1,
        status="in_progress", bank_name=bank_name,
        stats=session["stats"], created_at=now, updated_at=now,
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    db = await get_database()
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.pop("_id", None)
    return session


@router.get("/sessions")
async def list_sessions(status: Optional[str] = None, limit: int = 20, offset: int = 0):
    db = await get_database()
    query = {"status": status} if status else {}
    cursor = db[SESSIONS_COLLECTION].find(query).sort("created_at", -1).skip(offset).limit(limit)
    sessions = await cursor.to_list(length=limit)
    for s in sessions:
        s.pop("_id", None)
    total = await db[SESSIONS_COLLECTION].count_documents(query)
    return {"sessions": sessions, "total": total, "limit": limit, "offset": offset}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    db = await get_database()
    for coll in [SESSIONS_COLLECTION, CARDS_COLLECTION, URLS_COLLECTION, SOURCES_COLLECTION, RESULTS_COLLECTION]:
        await db[coll].delete_many({"session_id": session_id})
    return {"deleted": True, "session_id": session_id}


# ============= STEP 2: CARD DISCOVERY =============

@router.post("/sessions/{session_id}/discover-cards")
async def discover_cards(session_id: str):
    """STEP 2a: Discover cards for the session and extract card images."""
    db = await get_database()
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    cards = []
    cards_html = {}  # Store HTML for image extraction
    
    if session["mode"] == SessionMode.SINGLE_CARD.value:
        card_url = session["single_card_url"]
        try:
            scraped = await enhanced_web_scraper_service.scrape_url(card_url)
            title_match = re.search(r'<title>([^<]+)</title>', scraped, re.IGNORECASE)
            card_name = title_match.group(1).split('|')[0].strip() if title_match else "Credit Card"
            cards_html[card_url] = scraped  # Store for image extraction
        except:
            card_name = "Credit Card"
            scraped = ""
        cards.append({"url": card_url, "name": card_name})
    else:
        bank_key = session.get("bank_key")
        custom_url = session.get("custom_bank_url")
        
        if bank_key:
            config = BANK_CONFIGS[bank_key]
            cards_page, base_url = config["cards_page"], config["base_url"]
            patterns, exclude = config["card_url_patterns"], config["exclude_patterns"]
            requires_js = config["requires_javascript"]
        else:
            from urllib.parse import urlparse
            cards_page = custom_url
            parsed = urlparse(custom_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            patterns = [r'/credit-cards?/[\w-]+$', r'/cards/[\w-]+$']
            exclude = ['business', 'corporate', 'apply', 'compare']
            requires_js = True
        
        html = None
        if requires_js:
            html = await scrape_with_playwright(cards_page)
        if not html:
            try:
                html = await enhanced_web_scraper_service.scrape_url(cards_page)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to fetch: {str(e)}")
        
        cards = extract_card_urls(html, base_url, patterns, exclude)
        logger.info(f"Discovered {len(cards)} cards")
        
        # Store listing page HTML for potential image extraction
        cards_html["_listing"] = html
    
    now = datetime.utcnow()
    images_found = 0
    
    for card in cards:
        # Detect card network and tier from the card name and URL
        card_meta = detect_card_metadata(card["name"], card["url"])
        
        card_doc = {
            "card_id": generate_id("card"), 
            "session_id": session_id,
            "card_name": card["name"], 
            "card_url": card["url"],
            "card_network": card_meta["card_network"],   # Visa, Mastercard, etc.
            "card_tier": card_meta["card_tier"],           # Infinite, Platinum, etc.
            "is_selected": True, 
            "discovered_urls": [], 
            "selected_urls": [],
            "card_image": None,  # Will be populated with image data
            "created_at": now
        }
        
        if card_meta["card_network"] or card_meta["card_tier"]:
            logger.info(f"[V4] Card metadata: {card['name']} → network={card_meta['card_network']}, tier={card_meta['card_tier']}")
        
        # Try to extract card image
        try:
            # First try from the card's own page (for single card mode)
            if card["url"] in cards_html:
                image_data = await extract_card_image(
                    cards_html[card["url"]], 
                    card["url"], 
                    card["name"]
                )
                if image_data:
                    card_doc["card_image"] = image_data
                    images_found += 1
                    logger.info(f"Found image for {card['name']} from card page")
            
            # If no image yet, try from the listing page
            if not card_doc["card_image"] and "_listing" in cards_html:
                image_data = await extract_card_image(
                    cards_html["_listing"], 
                    card["url"], 
                    card["name"]
                )
                if image_data:
                    card_doc["card_image"] = image_data
                    images_found += 1
                    logger.info(f"Found image for {card['name']} from listing page")
                    
        except Exception as e:
            logger.warning(f"Failed to extract image for {card['name']}: {e}")
        
        await db[CARDS_COLLECTION].insert_one(card_doc)
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"current_step": 2, "stats.cards_discovered": len(cards),
                  "stats.cards_selected": len(cards), "stats.card_images_found": images_found,
                  "updated_at": now}}
    )
    
    return {"success": True, "cards_discovered": len(cards), "images_found": images_found,
            "cards": [{"name": c["name"], "url": c["url"],
                       "card_network": detect_card_metadata(c["name"], c["url"])["card_network"],
                       "card_tier": detect_card_metadata(c["name"], c["url"])["card_tier"]}
                      for c in cards]}


@router.get("/sessions/{session_id}/cards")
async def get_session_cards(session_id: str):
    db = await get_database()
    cards = await db[CARDS_COLLECTION].find({"session_id": session_id}).to_list(length=200)
    for card in cards:
        card.pop("_id", None)
    return {"cards": cards, "total": len(cards),
            "selected_count": sum(1 for c in cards if c.get("is_selected"))}


@router.post("/sessions/{session_id}/select-cards")
async def select_cards(session_id: str, request: SelectCardsRequest):
    """STEP 2b: Select which cards to process."""
    db = await get_database()
    
    await db[CARDS_COLLECTION].update_many(
        {"session_id": session_id}, {"$set": {"is_selected": False}}
    )
    await db[CARDS_COLLECTION].update_many(
        {"session_id": session_id, "card_id": {"$in": request.card_ids}},
        {"$set": {"is_selected": True}}
    )
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"stats.cards_selected": len(request.card_ids),
                  "steps_completed.step_2": True, "updated_at": datetime.utcnow()}}
    )
    
    return {"success": True, "selected_count": len(request.card_ids)}


# ============= STEP 3: URL DISCOVERY =============

class DiscoverUrlsRequest(BaseModel):
    follow_links: bool = True
    max_depth: int = 2
    process_pdfs: bool = True
    use_playwright: bool = True


@router.post("/sessions/{session_id}/discover-urls")
async def discover_urls(session_id: str, request: Optional[DiscoverUrlsRequest] = None):
    """
    STEP 3: Discover benefit URLs for all selected cards.
    
    Uses V2's comprehensive link discovery which:
    1. Fetches raw HTML (with Playwright if enabled)
    2. Parses all <a> tags with BeautifulSoup
    3. Extracts markdown-style links
    4. Uses regex for href patterns
    5. Has bank-specific benefit page patterns
    6. Categorizes links by type and relevance
    """
    db = await get_database()
    
    # Use request options or session defaults
    follow_links = request.follow_links if request else True
    max_depth = request.max_depth if request else 2
    process_pdfs = request.process_pdfs if request else True
    use_playwright = request.use_playwright if request else True
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update session with options
    options = session.get("options", {})
    options.update({
        "follow_links": follow_links,
        "max_depth": max_depth,
        "process_pdfs": process_pdfs,
        "use_playwright": use_playwright
    })
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"options": options}}
    )
    
    cards = await db[CARDS_COLLECTION].find(
        {"session_id": session_id, "is_selected": True}
    ).to_list(length=200)
    
    if not cards:
        raise HTTPException(status_code=400, detail="No cards selected")
    
    keywords = session.get("keywords", DEFAULT_KEYWORDS)
    url_to_cards: Dict[str, List[str]] = {}
    url_info: Dict[str, Dict] = {}
    total_urls_found = 0
    
    # Relevant keywords for link discovery (from V2)
    relevant_keywords = [
        'help', 'support', 'benefit', 'feature', 'lounge', 'cinema', 'cine',
        'movie', 'golf', 'concierge', 'insurance', 'shield', 'terms', 'condition',
        'fee', 'charge', 'tariff', 'key-fact', 'pdf', 'learn-more', 'learn more',
        'airport', 'access', 'royal', 'reward', 'offer', 'dining', 'travel',
        'cashback', 'points', 'miles', 'valet', 'lifestyle'
    ]
    
    for card in cards:
        card_id, card_url, card_name = card["card_id"], card["card_url"], card["card_name"]
        logger.info(f"Discovering URLs for: {card_name} (depth={max_depth}, playwright={use_playwright})")
        
        try:
            from urllib.parse import urlparse, urljoin
            from bs4 import BeautifulSoup
            
            parsed_url = urlparse(card_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Step 1: Fetch raw HTML (with Playwright if enabled)
            soup, raw_html = await enhanced_web_scraper_service._fetch_and_parse(card_url, use_playwright=use_playwright)
            
            # Also get scraped content for title and preview
            scraped = await enhanced_web_scraper_service.scrape_url_comprehensive(
                card_url,
                follow_links=False,
                max_depth=0,
                use_playwright=use_playwright
            )
            
            logger.info(f"Raw HTML length: {len(raw_html)}, Scraped text length: {len(scraped.raw_text)}")
            
            all_links = []
            discovered = []
            
            # Add main page as depth 0
            discovered.append({
                "url": card_url,
                "title": card_name,
                "url_type": "web",
                "depth": 0,
                "relevance_score": 1.0,
                "relevance_level": "high",
                "keyword_matches": []
            })
            
            # Method 1: Extract ALL href attributes from <a> tags
            all_a_tags = soup.find_all('a', href=True)
            logger.info(f"Total <a> tags found: {len(all_a_tags)}")
            
            for a_tag in all_a_tags:
                href = a_tag['href']
                link_text = a_tag.get_text(strip=True)
                
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                
                # Convert relative URLs to absolute
                if href.startswith('/'):
                    full_url = urljoin(base_url, href)
                elif href.startswith('http'):
                    full_url = href
                else:
                    full_url = urljoin(card_url, href)
                
                # Only include links from same domain
                if parsed_url.netloc not in full_url:
                    continue
                
                href_lower = href.lower()
                text_lower = link_text.lower()
                
                is_relevant = any(kw in href_lower or kw in text_lower for kw in relevant_keywords)
                is_pdf = '.pdf' in href_lower
                
                if (is_relevant or is_pdf) and full_url not in [l['url'] for l in all_links]:
                    all_links.append({
                        'url': full_url,
                        'text': link_text,
                        'is_pdf': is_pdf
                    })
            
            # Method 2: Extract markdown-style links [text](url)
            markdown_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
            for match in re.finditer(markdown_pattern, raw_html):
                link_text = match.group(1)
                link_url = match.group(2)
                
                if link_url.startswith('/'):
                    link_url = urljoin(base_url, link_url)
                elif not link_url.startswith('http'):
                    link_url = urljoin(card_url, link_url)
                
                if parsed_url.netloc in link_url and link_url not in [l['url'] for l in all_links]:
                    all_links.append({
                        'url': link_url,
                        'text': link_text,
                        'is_pdf': '.pdf' in link_url.lower()
                    })
            
            # Method 3: Regex for href patterns in raw HTML
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
                    is_relevant = any(kw in href_lower for kw in relevant_keywords)
                    is_pdf = '.pdf' in href_lower
                    
                    if (is_relevant or is_pdf) and full_url not in [l['url'] for l in all_links]:
                        title = href.split('/')[-1].replace('-', ' ').replace('_', ' ').replace('.pdf', '').title()
                        all_links.append({
                            'url': full_url,
                            'text': title,
                            'is_pdf': is_pdf
                        })
            
            # Method 4: Bank-specific benefit page patterns (Emirates NBD)
            if 'emiratesnbd' in card_url.lower():
                text_to_check = (raw_html + scraped.raw_text).lower()
                
                enbd_pages = [
                    ('lounge', '/en/help-and-support/airport-lounge-access-mastercard', 'Airport Lounge Access (Mastercard)'),
                    ('lounge', '/en/help-and-support/airport-lounge-access-visa', 'Airport Lounge Access (Visa)'),
                    ('cine', '/en/help-and-support/cine-royal-cinemas-movie-benefits', 'Cine Royal Cinema Benefits'),
                    ('cinema', '/en/help-and-support/cine-royal-cinemas-movie-benefits', 'Cinema Movie Benefits'),
                    ('shield', '/en/cards/credit-shield-pro', 'Credit Shield Pro Insurance'),
                    ('golf', '/en/help-and-support/golf-benefits', 'Golf Course Access'),
                    ('concierge', '/en/help-and-support/concierge-services', 'Concierge Services'),
                    ('fee', '/en/help-and-support/credit-card-fees-and-charges', 'Fees and Charges'),
                    ('valet', '/en/help-and-support/valet-parking', 'Valet Parking'),
                    ('dining', '/en/help-and-support/dining-benefits', 'Dining Benefits'),
                ]
                
                for keyword, path, title in enbd_pages:
                    if keyword in text_to_check:
                        full_url = f"{base_url}{path}"
                        if full_url not in [l['url'] for l in all_links]:
                            all_links.append({
                                'url': full_url,
                                'text': title,
                                'is_pdf': False
                            })
                            logger.info(f"Found keyword-based link: {title}")
            
            # Add PDF links from scraper
            if process_pdfs and hasattr(scraped, 'pdf_links'):
                for pdf_url in scraped.pdf_links:
                    if pdf_url not in [l['url'] for l in all_links]:
                        all_links.append({
                            'url': pdf_url,
                            'text': pdf_url.split('/')[-1].replace('.pdf', '').replace('-', ' ').title(),
                            'is_pdf': True
                        })
            
            logger.info(f"Total links discovered: {len(all_links)}")
            
            # Categorize and add to discovered list
            for link_info in all_links:
                link_url = link_info['url']
                link_text = link_info.get('text', '')
                is_pdf = link_info.get('is_pdf', False)
                url_lower = link_url.lower()
                
                # Skip the main URL itself
                if link_url.rstrip('/') == card_url.rstrip('/'):
                    continue
                
                # Skip if not processing PDFs
                if is_pdf and not process_pdfs:
                    continue
                
                # Determine relevance
                if is_pdf:
                    url_type = "pdf"
                    if 'key-fact' in url_lower or 'keyfact' in url_lower:
                        relevance_level = "high"
                    elif 'terms' in url_lower or 'condition' in url_lower:
                        relevance_level = "high"
                    elif 'fee' in url_lower or 'tariff' in url_lower:
                        relevance_level = "high"
                    else:
                        relevance_level = "medium"
                else:
                    url_type = "web"
                    if any(kw in url_lower for kw in ['help-and-support', 'benefit', 'feature', 'lounge', 'cinema', 'movie', 'fee', 'insurance', 'shield']):
                        relevance_level = "high"
                    elif any(kw in url_lower for kw in ['golf', 'concierge', 'terms', 'dining', 'valet']):
                        relevance_level = "medium"
                    else:
                        relevance_level = "low"
                
                # Calculate keyword matches
                text_to_check = (link_url + " " + link_text).lower()
                keyword_matches = [kw for kw in keywords if kw.lower() in text_to_check]
                relevance_score = len(keyword_matches) / max(len(keywords), 1)
                
                title = link_text if link_text else link_url.split('/')[-1].replace('-', ' ').replace('_', ' ').replace('.pdf', '').title()
                if not title or title == '/' or title.strip() == '':
                    title = "Related Page"
                
                discovered.append({
                    "url": link_url,
                    "title": title,
                    "url_type": url_type,
                    "depth": 1,
                    "relevance_score": relevance_score,
                    "relevance_level": relevance_level,
                    "keyword_matches": keyword_matches[:10]
                })
            
            await db[CARDS_COLLECTION].update_one(
                {"card_id": card_id}, {"$set": {"discovered_urls": discovered}}
            )
            
            for url_data in discovered:
                url = url_data["url"]
                if url not in url_to_cards:
                    url_to_cards[url] = []
                    url_info[url] = url_data
                url_to_cards[url].append(card_id)
            
            total_urls_found += len(discovered)
            logger.info(f"Found {len(discovered)} URLs for {card_name} ({len([d for d in discovered if d['url_type'] == 'pdf'])} PDFs)")
            
        except Exception as e:
            logger.error(f"Error discovering URLs for {card_name}: {e}")
            import traceback
            traceback.print_exc()
    
    now = datetime.utcnow()
    unique_count = 0
    
    for url, card_ids in url_to_cards.items():
        info = url_info[url]
        url_doc = {
            "url_id": generate_id("url"), "session_id": session_id,
            "url": url, "url_hash": hash_url(url), "card_ids": card_ids,
            "title": info["title"], "url_type": info["url_type"],
            "depth": info.get("depth", 1),  # Preserve depth from discovery
            "relevance_score": info["relevance_score"],
            "relevance_level": info["relevance_level"],
            "keyword_matches": info["keyword_matches"],
            "is_selected": info["relevance_level"] in ["high", "medium"],
            "created_at": now
        }
        await db[URLS_COLLECTION].update_one(
            {"session_id": session_id, "url_hash": url_doc["url_hash"]},
            {"$set": url_doc}, upsert=True
        )
        unique_count += 1
    
    dedup_savings = ((total_urls_found - unique_count) / max(total_urls_found, 1)) * 100
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"current_step": 3, "stats.urls_discovered": total_urls_found,
                  "stats.urls_unique": unique_count, "steps_completed.step_3": True,
                  "updated_at": now}}
    )
    
    return {"success": True, "total_urls_found": total_urls_found,
            "unique_urls": unique_count, "dedup_savings_percent": round(dedup_savings, 1),
            "cards_processed": len(cards)}


@router.get("/sessions/{session_id}/urls")
async def get_session_urls(session_id: str, view_by: str = "card"):
    db = await get_database()
    urls = await db[URLS_COLLECTION].find({"session_id": session_id}).to_list(length=1000)
    for url in urls:
        url.pop("_id", None)
    
    cards = await db[CARDS_COLLECTION].find({"session_id": session_id}).to_list(length=200)
    card_map = {c["card_id"]: c["card_name"] for c in cards}
    
    for url in urls:
        url["card_names"] = [card_map.get(cid, "Unknown") for cid in url.get("card_ids", [])]
    
    return {"view": view_by, "urls": urls, "total": len(urls),
            "selected_count": sum(1 for u in urls if u.get("is_selected"))}


@router.post("/sessions/{session_id}/select-urls")
async def select_urls(session_id: str, request: SelectUrlsRequest):
    """STEP 4: Select which URLs to process."""
    db = await get_database()
    
    if request.keywords:
        await db[SESSIONS_COLLECTION].update_one(
            {"session_id": session_id}, {"$set": {"keywords": request.keywords}}
        )
    
    await db[URLS_COLLECTION].update_many(
        {"session_id": session_id}, {"$set": {"is_selected": False}}
    )
    await db[URLS_COLLECTION].update_many(
        {"session_id": session_id, "url": {"$in": request.selected_urls}},
        {"$set": {"is_selected": True}}
    )
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"current_step": 4, "stats.urls_selected": len(request.selected_urls),
                  "steps_completed.step_4": True, "updated_at": datetime.utcnow()}}
    )
    
    return {"success": True, "selected_count": len(request.selected_urls)}


# ============= STEP 5: CONTENT FETCHING =============

@router.post("/sessions/{session_id}/fetch-content")
async def fetch_content(session_id: str, request: Optional[Dict] = None):
    """
    STEP 5: Fetch content from all selected URLs.
    
    NEW FEATURE: Checks V2's raw_extractions and approved_raw_data collections
    for previously scraped content. Reuses cached data when available.
    """
    db = await get_database()
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get options from session or request
    options = session.get("options", {})
    use_playwright = options.get("use_playwright", True)
    bypass_cache = options.get("bypass_cache", False)
    
    if request:
        use_playwright = request.get("use_playwright", use_playwright)
        bypass_cache = request.get("bypass_cache", bypass_cache)
    
    urls = await db[URLS_COLLECTION].find(
        {"session_id": session_id, "is_selected": True}
    ).to_list(length=1000)
    
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs selected")
    
    # Get card URLs for depth 0
    cards = await db[CARDS_COLLECTION].find({
        "session_id": session_id, "is_selected": True
    }).to_list(length=200)
    
    keywords = session.get("keywords", DEFAULT_KEYWORDS)
    now = datetime.utcnow()
    fetched_count = 0
    cached_count = 0
    error_count = 0
    
    logger.info(f"[V4] Fetching content for {len(urls)} URLs (Playwright={use_playwright}, bypass_cache={bypass_cache})")
    
    # ====================================================
    # FEATURE: Look up existing scraped data in V2 collections
    # ====================================================
    async def find_cached_content(url: str) -> Optional[Dict]:
        """Search V2 collections for previously scraped content."""
        if bypass_cache:
            return None
        
        # 1. Check approved_raw_data sources
        cursor = db.approved_raw_data.find({
            "sources.url": url
        })
        async for doc in cursor:
            for src in doc.get("sources", []):
                if src.get("url") == url:
                    content = src.get("raw_content") or src.get("cleaned_content")
                    if content and len(content) > 100:
                        logger.info(f"[V4] Found cached content in approved_raw_data: {url[:50]}...")
                        return {
                            "raw_content": src.get("raw_content", ""),
                            "cleaned_content": src.get("cleaned_content", ""),
                            "title": src.get("title", ""),
                            "cached_from": "approved_raw_data",
                            "cached_at": doc.get("stored_at")
                        }
        
        # 2. Check raw_extractions collection
        raw_ext = await db.raw_extractions.find_one({
            "sources.url": url
        })
        if raw_ext:
            for src in raw_ext.get("sources", []):
                if src.get("url") == url:
                    content = src.get("raw_content") or src.get("content")
                    if content and len(content) > 100:
                        logger.info(f"[V4] Found cached content in raw_extractions: {url[:50]}...")
                        return {
                            "raw_content": content,
                            "cleaned_content": src.get("cleaned_content", content),
                            "title": src.get("title", ""),
                            "cached_from": "raw_extractions",
                            "cached_at": raw_ext.get("extracted_at")
                        }
        
        return None
    
    # Process card pages (depth 0)
    card_urls_processed = set()
    for card in cards:
        card_url = card.get("card_url")
        card_id = card["card_id"]
        card_name = card["card_name"]
        has_image = card.get("card_image") is not None
        
        if not card_url or card_url in card_urls_processed:
            continue
        
        card_urls_processed.add(card_url)
        url_hash = hash_url(card_url)
        
        try:
            # Check if already in this session's sources
            existing = await db[SOURCES_COLLECTION].find_one({
                "session_id": session_id, "url_hash": url_hash
            })
            
            if existing and existing.get("raw_content") and not bypass_cache:
                # Merge card_id into existing source's card_ids
                existing_card_ids = existing.get("card_ids", [])
                if card_id not in existing_card_ids:
                    existing_card_ids.append(card_id)
                    await db[SOURCES_COLLECTION].update_one(
                        {"_id": existing["_id"]},
                        {"$set": {"card_ids": existing_card_ids}}
                    )
                    logger.info(f"[V4] Merged card_id into cached source for {card_name}: now {len(existing_card_ids)} cards")
                
                fetched_count += 1
                
                # Still try to extract image if card doesn't have one
                if not has_image:
                    try:
                        # Need to get raw HTML for image extraction
                        raw_html = await enhanced_web_scraper_service.scrape_url(card_url)
                        image_data = await extract_card_image(raw_html, card_url, card_name)
                        if image_data:
                            await db[CARDS_COLLECTION].update_one(
                                {"card_id": card_id},
                                {"$set": {"card_image": image_data}}
                            )
                            logger.info(f"[V4] Extracted image for {card_name} during content check")
                    except Exception as e:
                        logger.warning(f"[V4] Failed to extract image for {card_name}: {e}")
                
                continue
            
            # Check V2 collections for cached content
            cached = await find_cached_content(card_url)
            
            raw_html = None  # Store raw HTML for image extraction
            
            if cached:
                raw_content = cached["raw_content"]
                cleaned_content = cached["cleaned_content"]
                logger.info(f"[V4] Reusing cached content from {cached['cached_from']}: {card_name} ({len(raw_content)} chars)")
                cached_count += 1
            else:
                # Fetch fresh content
                logger.info(f"[V4] Fetching fresh content for card page: {card_name}")
                scraped = await enhanced_web_scraper_service.scrape_url_comprehensive(
                    card_url,
                    follow_links=False,
                    max_depth=0,
                    use_playwright=use_playwright
                )
                raw_content = scraped.raw_text or ""
                cleaned_content = enhanced_web_scraper_service.format_for_llm(scraped) if scraped else raw_content
                
                # Get raw HTML for image extraction if card doesn't have image
                if not has_image and hasattr(scraped, 'raw_html') and scraped.raw_html:
                    raw_html = scraped.raw_html
            
            # Extract card image if card doesn't have one
            if not has_image:
                try:
                    if not raw_html:
                        raw_html = await enhanced_web_scraper_service.scrape_url(card_url)
                    
                    image_data = await extract_card_image(raw_html, card_url, card_name)
                    if image_data:
                        await db[CARDS_COLLECTION].update_one(
                            {"card_id": card_id},
                            {"$set": {"card_image": image_data}}
                        )
                        logger.info(f"[V4] Extracted and saved image for {card_name}")
                except Exception as e:
                    logger.warning(f"[V4] Failed to extract image for {card_name}: {e}")
            
            detected = detect_patterns(raw_content)
            score, level, matches = calculate_relevance(raw_content, card_url, keywords)
            
            source_doc = {
                "source_id": generate_id("src"),
                "session_id": session_id,
                "url": card_url,
                "url_hash": url_hash,
                "card_ids": [card_id],
                "source_type": "web",
                "title": card_name,
                "depth": 0,
                "raw_content": raw_content,
                "cleaned_content": cleaned_content,
                "content_length": len(raw_content),
                "detected_patterns": detected,
                "relevance_score": 1.0,
                "relevance_level": "high",
                "keyword_matches": matches,
                "http_status": 200,
                "fetch_error": None,
                "approval_status": ApprovalStatus.PENDING.value,
                "fetched_at": now,
                "cached_from": cached["cached_from"] if cached else None,
                "scraped_with_playwright": use_playwright if not cached else False
            }
            
            await db[SOURCES_COLLECTION].update_one(
                {"session_id": session_id, "url_hash": url_hash},
                {"$set": source_doc},
                upsert=True
            )
            
            fetched_count += 1
            logger.info(f"[V4] Stored card page: {card_name} ({len(raw_content)} chars)")
            
        except Exception as e:
            logger.error(f"[V4] Error fetching card page {card_name}: {e}")
            error_count += 1
    
    # Process all selected URLs (depth 1+)
    for url_doc in urls:
        url = url_doc["url"]
        url_type = url_doc.get("url_type", "web")
        url_hash = url_doc.get("url_hash") or hash_url(url)
        
        if url in card_urls_processed:
            continue
        
        try:
            # Check if already in this session
            existing = await db[SOURCES_COLLECTION].find_one({
                "session_id": session_id, "url_hash": url_hash
            })
            
            if existing and existing.get("raw_content") and not bypass_cache:
                # Update card_ids on existing source (merge, don't replace)
                existing_card_ids = existing.get("card_ids", [])
                url_card_ids = url_doc.get("card_ids", [])
                merged_card_ids = list(set(existing_card_ids + url_card_ids))
                if len(merged_card_ids) > len(existing_card_ids):
                    await db[SOURCES_COLLECTION].update_one(
                        {"_id": existing["_id"]},
                        {"$set": {"card_ids": merged_card_ids}}
                    )
                    logger.info(f"[V4] Updated card_ids on cached source {url[:50]}: {len(existing_card_ids)} → {len(merged_card_ids)} cards")
                fetched_count += 1
                continue
            
            # Check V2 collections for cached content
            cached = await find_cached_content(url)
            
            raw_content = ""
            cleaned_content = ""
            fetch_error = None
            http_status = None
            
            if cached:
                raw_content = cached["raw_content"]
                cleaned_content = cached["cleaned_content"]
                http_status = 200
                logger.info(f"[V4] Reusing cached content from {cached['cached_from']}: {url[:50]}... ({len(raw_content)} chars)")
                cached_count += 1
            elif url_type == "pdf":
                from app.services.pdf_service import pdf_service
                try:
                    raw_content = await pdf_service.extract_text_from_url(url)
                    cleaned_content = raw_content
                    http_status = 200
                    logger.info(f"[V4] Extracted PDF: {len(raw_content)} chars")
                except Exception as e:
                    fetch_error = str(e)
                    logger.error(f"[V4] PDF extraction failed: {e}")
            else:
                try:
                    logger.info(f"[V4] Fetching fresh content: {url[:50]}...")
                    scraped = await enhanced_web_scraper_service.scrape_url_comprehensive(
                        url,
                        follow_links=False,
                        max_depth=0,
                        use_playwright=use_playwright
                    )
                    raw_content = scraped.raw_text or ""
                    cleaned_content = enhanced_web_scraper_service.format_for_llm(scraped) if scraped else raw_content
                    http_status = 200
                    logger.info(f"[V4] Scraped: {len(raw_content)} chars")
                except Exception as e:
                    fetch_error = str(e)
                    logger.error(f"[V4] Scrape failed: {e}")
            
            detected = detect_patterns(raw_content) if raw_content else []
            score, level, matches = calculate_relevance(raw_content, url, keywords)
            
            source_doc = {
                "source_id": generate_id("src"),
                "session_id": session_id,
                "url": url,
                "url_hash": url_hash,
                "card_ids": url_doc.get("card_ids", []),
                "source_type": url_type,
                "title": url_doc.get("title", ""),
                "depth": url_doc.get("depth", 1),
                "raw_content": raw_content,
                "cleaned_content": cleaned_content,
                "content_length": len(raw_content),
                "detected_patterns": detected,
                "relevance_score": score,
                "relevance_level": level,
                "keyword_matches": matches,
                "http_status": http_status,
                "fetch_error": fetch_error,
                "approval_status": ApprovalStatus.PENDING.value,
                "fetched_at": now,
                "cached_from": cached["cached_from"] if cached else None,
                "scraped_with_playwright": use_playwright if url_type == "web" and not cached else False
            }
            
            await db[SOURCES_COLLECTION].update_one(
                {"session_id": session_id, "url_hash": url_hash},
                {"$set": source_doc},
                upsert=True
            )
            
            fetched_count += 1
            
        except Exception as e:
            logger.error(f"[V4] Error fetching {url}: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
    
    # Enrich card metadata using fetched content
    # Some card names are generic; the actual page content reveals network/tier
    enriched_cards = 0
    cards = await db[CARDS_COLLECTION].find({"session_id": session_id, "is_selected": True}).to_list(length=200)
    for card in cards:
        # Skip if already fully detected
        if card.get("card_network") and card.get("card_tier"):
            continue
        
        # Get parent page content (depth 0) for this card
        parent_source = await db[SOURCES_COLLECTION].find_one({
            "session_id": session_id,
            "card_ids": card["card_id"],
            "depth": 0,
        })
        content = ""
        if parent_source:
            content = parent_source.get("cleaned_content") or parent_source.get("raw_content") or ""
        
        meta = detect_card_metadata(card["card_name"], card["card_url"], content)
        updates = {}
        if meta["card_network"] and not card.get("card_network"):
            updates["card_network"] = meta["card_network"]
        if meta["card_tier"] and not card.get("card_tier"):
            updates["card_tier"] = meta["card_tier"]
        
        if updates:
            await db[CARDS_COLLECTION].update_one({"card_id": card["card_id"]}, {"$set": updates})
            enriched_cards += 1
            logger.info(f"[V4] Enriched card metadata: {card['card_name']} → {updates}")
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 5,
            "stats.sources_fetched": fetched_count,
            "stats.sources_cached": cached_count,
            "steps_completed.step_5": True,
            "updated_at": now
        }}
    )
    
    return {
        "success": True,
        "sources_fetched": fetched_count,
        "sources_from_cache": cached_count,
        "sources_fresh": fetched_count - cached_count,
        "errors": error_count,
        "total_urls": len(urls) + len(card_urls_processed),
        "used_playwright": use_playwright,
        "cards_metadata_enriched": enriched_cards
    }


# ============= STEP 6: RAW DATA REVIEW =============

@router.get("/sessions/{session_id}/sources")
async def get_session_sources(session_id: str, status: Optional[str] = None, include_content: bool = False):
    """
    Get all sources for a session.
    
    Args:
        session_id: Session ID
        status: Filter by approval status (pending, approved, rejected)
        include_content: If True, include full raw_content (for preview it's truncated)
    """
    db = await get_database()
    query = {"session_id": session_id}
    if status:
        query["approval_status"] = status
    
    sources = await db[SOURCES_COLLECTION].find(query).to_list(length=1000)
    cards = await db[CARDS_COLLECTION].find({"session_id": session_id}).to_list(length=200)
    card_map = {c["card_id"]: c["card_name"] for c in cards}
    
    for source in sources:
        source.pop("_id", None)
        source["card_names"] = [card_map.get(cid, "Unknown") for cid in source.get("card_ids", [])]
        
        # Content preview - truncate for list view unless full content requested
        content = source.get("raw_content", "")
        if not include_content:
            source["content_preview"] = content[:500] + "..." if len(content) > 500 else content
            # Don't send full content in list view to reduce payload
            source["raw_content"] = None
            source["cleaned_content"] = None
    
    return {
        "sources": sources,
        "total": len(sources),
        "pending_count": sum(1 for s in sources if s.get("approval_status") == "pending"),
        "approved_count": sum(1 for s in sources if s.get("approval_status") == "approved"),
        "rejected_count": sum(1 for s in sources if s.get("approval_status") == "rejected")
    }


@router.get("/sessions/{session_id}/sources/{source_id}")
async def get_source_detail(session_id: str, source_id: str):
    """
    Get full source details including complete raw_content.
    
    This endpoint returns the FULL content for preview/review.
    Use this when user clicks to view source details.
    """
    db = await get_database()
    source = await db[SOURCES_COLLECTION].find_one({
        "session_id": session_id, "source_id": source_id
    })
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    source.pop("_id", None)
    
    # Get card names
    cards = await db[CARDS_COLLECTION].find({
        "session_id": session_id,
        "card_id": {"$in": source.get("card_ids", [])}
    }).to_list(length=100)
    source["card_names"] = [c["card_name"] for c in cards]
    
    # Return FULL content - no truncation
    # This is used when user clicks to view full source
    return source


@router.get("/sessions/{session_id}/sources/{source_id}/content")
async def get_source_full_content(session_id: str, source_id: str):
    """
    Get FULL raw content for a source.
    
    Separate endpoint for fetching just the content (for lazy loading).
    """
    db = await get_database()
    source = await db[SOURCES_COLLECTION].find_one(
        {"session_id": session_id, "source_id": source_id},
        {"raw_content": 1, "cleaned_content": 1, "content_length": 1, "detected_patterns": 1}
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return {
        "raw_content": source.get("raw_content", ""),
        "cleaned_content": source.get("cleaned_content", ""),
        "content_length": source.get("content_length", 0),
        "detected_patterns": source.get("detected_patterns", [])
    }


@router.post("/sessions/{session_id}/sources/{source_id}/approve")
async def approve_source(session_id: str, source_id: str):
    db = await get_database()
    result = await db[SOURCES_COLLECTION].update_one(
        {"session_id": session_id, "source_id": source_id},
        {"$set": {"approval_status": ApprovalStatus.APPROVED.value,
                  "approved_at": datetime.utcnow()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Source not found")
    
    approved_count = await db[SOURCES_COLLECTION].count_documents({
        "session_id": session_id, "approval_status": ApprovalStatus.APPROVED.value
    })
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id}, {"$set": {"stats.sources_approved": approved_count}}
    )
    return {"approved": True, "source_id": source_id}


@router.post("/sessions/{session_id}/sources/{source_id}/reject")
async def reject_source(session_id: str, source_id: str):
    db = await get_database()
    result = await db[SOURCES_COLLECTION].update_one(
        {"session_id": session_id, "source_id": source_id},
        {"$set": {"approval_status": ApprovalStatus.REJECTED.value,
                  "rejected_at": datetime.utcnow()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"rejected": True, "source_id": source_id}


@router.post("/sessions/{session_id}/approve-all-sources")
async def approve_all_sources(session_id: str):
    """STEP 6: Approve all pending sources for extraction."""
    db = await get_database()
    result = await db[SOURCES_COLLECTION].update_many(
        {"session_id": session_id, "approval_status": ApprovalStatus.PENDING.value},
        {"$set": {"approval_status": ApprovalStatus.APPROVED.value,
                  "approved_at": datetime.utcnow()}}
    )
    
    approved_count = await db[SOURCES_COLLECTION].count_documents({
        "session_id": session_id, "approval_status": ApprovalStatus.APPROVED.value
    })
    
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"current_step": 6, "stats.sources_approved": approved_count,
                  "steps_completed.step_6": True, "updated_at": datetime.utcnow()}}
    )
    
    return {"approved": True, "approved_count": result.modified_count,
            "total_approved": approved_count}


# ============= STEP 7: SAVE APPROVED RAW DATA =============

@router.post("/sessions/{session_id}/save-approved-raw")
async def save_approved_raw_data(session_id: str):
    """
    STEP 7: Save approved sources to approved_raw_data collection.
    
    This is the final step before pipeline execution. It:
    1. Collects all approved sources with their content
    2. Saves them to the approved_raw_data collection (V2 compatible format)
    3. Returns a saved_id that can be used to run pipelines
    
    This matches V2's workflow where raw data is saved and reviewed
    before any LLM processing.
    """
    db = await get_database()
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get all approved sources
    sources = await db[SOURCES_COLLECTION].find({
        "session_id": session_id,
        "approval_status": ApprovalStatus.APPROVED.value
    }).to_list(length=1000)
    
    if not sources:
        raise HTTPException(status_code=400, detail="No approved sources found. Please approve sources first.")
    
    # Get cards for naming
    cards = await db[CARDS_COLLECTION].find({
        "session_id": session_id, "is_selected": True
    }).to_list(length=200)
    
    primary_card = cards[0] if cards else None
    card_name = primary_card["card_name"] if primary_card else "Unknown Card"
    card_url = primary_card.get("card_url", "") if primary_card else ""
    card_network = primary_card.get("card_network") if primary_card else None
    card_tier = primary_card.get("card_tier") if primary_card else None
    
    # Build card_id → card_info map for per-source card attribution
    card_map = {c["card_id"]: c for c in cards}
    
    now = datetime.utcnow()
    
    # Build V2-compatible sources array
    v2_sources = []
    for src in sources:
        raw_content = src.get("raw_content", "") or ""
        cleaned_content = src.get("cleaned_content", "") or raw_content
        
        if not raw_content:
            continue
        
        # Resolve card names for this source
        src_card_ids = src.get("card_ids", [])
        if isinstance(src_card_ids, str):
            src_card_ids = [src_card_ids]
        src_card_names = []
        src_card_url = ""
        src_card_network = None
        src_card_tier = None
        for cid in src_card_ids:
            c = card_map.get(cid)
            if c:
                src_card_names.append(c["card_name"])
                if not src_card_url:
                    src_card_url = c.get("card_url", "")
                if not src_card_network:
                    src_card_network = c.get("card_network")
                if not src_card_tier:
                    src_card_tier = c.get("card_tier")
        
        v2_sources.append({
            "url": src.get("url", ""),
            "title": src.get("title", ""),
            "source_type": src.get("source_type", "web"),
            "parent_url": card_url if src.get("depth", 1) > 0 else None,
            "depth": src.get("depth", 1),
            "raw_content": raw_content,
            "cleaned_content": cleaned_content,
            "cleaned_content_length": len(cleaned_content),
            "keywords_matched": src.get("keyword_matches", []),
            "extracted_at": now.isoformat(),
            # Per-source card context
            "card_ids": src_card_ids,
            "card_names": src_card_names,
            "card_url": src_card_url or card_url,
            "card_network": src_card_network or card_network,
            "card_tier": src_card_tier or card_tier,
        })
    
    if not v2_sources:
        raise HTTPException(status_code=400, detail="All approved sources have empty content.")
    
    # Calculate totals
    total_content_length = sum(len(s.get("cleaned_content", "")) for s in v2_sources)
    
    # Create saved_id
    saved_id = f"v4_{session_id}"
    
    # Build the approved_raw_data document (V2 compatible format)
    approved_raw_doc = {
        "saved_id": saved_id,
        "primary_url": card_url,
        "primary_title": card_name,
        "detected_card_name": card_name,
        "detected_bank": session.get("bank_name", ""),
        "bank_key": session.get("bank_key", ""),
        "bank_name": session.get("bank_name", ""),
        "card_network": card_network,
        "card_tier": card_tier,
        "keywords_used": session.get("keywords", DEFAULT_KEYWORDS),
        "sources": v2_sources,
        "total_sources": len(v2_sources),
        "total_content_length": total_content_length,
        "raw_extraction_id": None,
        "stored_at": now,
        "status": "pending_processing",  # pending_processing, processed, failed
        "processed_at": None,
        "intelligence_id": None,
        # V4 metadata
        "v4_session_id": session_id,
    }
    
    # Save to approved_raw_data collection
    await db.approved_raw_data.update_one(
        {"saved_id": saved_id},
        {"$set": approved_raw_doc},
        upsert=True
    )
    
    logger.info(f"[V4] Saved approved raw data: {saved_id} with {len(v2_sources)} sources, {total_content_length} chars")
    
    # Update session
    await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 7,
            "approved_raw_id": saved_id,
            "stats.sources_saved": len(v2_sources),
            "stats.total_content_length": total_content_length,
            "steps_completed.step_7": True,
            "updated_at": now
        }}
    )
    
    return {
        "success": True,
        "saved_id": saved_id,
        "total_sources": len(v2_sources),
        "total_content_length": total_content_length,
        "primary_url": card_url,
        "detected_card_name": card_name,
        "bank_name": session.get("bank_name", ""),
        "card_network": card_network,
        "card_tier": card_tier,
        "message": f"Successfully saved {len(v2_sources)} sources ({total_content_length:,} characters). Proceed to vectorize."
    }


@router.get("/sessions/{session_id}/approved-raw")
async def get_session_approved_raw(session_id: str, include_content: bool = False):
    """
    Get the approved raw data for a session.
    
    This retrieves the saved approved_raw_data document that was created
    in Step 7, ready for pipeline execution.
    """
    db = await get_database()
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    saved_id = session.get("approved_raw_id")
    if not saved_id:
        raise HTTPException(status_code=404, detail="No approved raw data found. Please complete Step 7 first.")
    
    doc = await db.approved_raw_data.find_one({"saved_id": saved_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Approved raw data not found: {saved_id}")
    
    doc.pop("_id", None)
    
    # Optionally strip content to reduce payload
    if not include_content:
        for src in doc.get("sources", []):
            content_len = len(src.get("raw_content", ""))
            src["content_preview"] = src.get("raw_content", "")[:500] + "..." if content_len > 500 else src.get("raw_content", "")
            src["raw_content"] = None
            src["cleaned_content"] = None
    
    return {
        "success": True,
        "approved_raw": doc
    }



# ============= STEP 9-10: PIPELINE EXECUTION =============

@router.get("/pipelines")
async def list_pipelines():
    pipeline_info = {
        "golf": {"icon": "🏌️", "desc": "Golf courses, green fees, guest policies"},
        "movie": {"icon": "🎬", "desc": "Cinema chains, ticket offers"},
        "lounge_access": {"icon": "✈️", "desc": "Airport lounges, visit limits"},
        "dining": {"icon": "🍽️", "desc": "Restaurants, discounts"},
        "cashback": {"icon": "💰", "desc": "Rates, categories, caps"},
        "rewards_points": {"icon": "🎁", "desc": "Earn rates, redemption"},
        "insurance": {"icon": "🛡️", "desc": "Coverage types, limits"},
        "fee_waiver": {"icon": "💳", "desc": "Annual fee, waivers"},
        "travel_benefits": {"icon": "🌴", "desc": "Hotel, airline benefits"},
        "lifestyle": {"icon": "🎭", "desc": "Spa, fitness, entertainment"}
    }
    
    pipelines = []
    for p in pipeline_registry.list_pipelines():
        name = p["name"]
        info = pipeline_info.get(name, {"icon": "📋", "desc": p.get("description", "Extracts benefits")})
        pipelines.append({
            "name": name, "display_name": name.replace("_", " ").title(),
            "icon": info["icon"], "description": info["desc"]
        })
    return {"pipelines": pipelines}


@router.post("/sessions/{session_id}/run-pipelines")
async def run_pipelines(session_id: str, request: RunPipelinesRequest):
    """
    STEP 8-9: Run selected extraction pipelines.
    
    PREREQUISITE: Step 7 (save-approved-raw) must be completed first.
    
    This REUSES V2's battle-tested pipeline logic:
    1. Load approved_raw_data saved in Step 7
    2. Call pipeline_registry.run_all_pipelines() - SAME as V2
    3. Store results
    """
    db = await get_database()
    
    logger.info(f"[V4] ========== RUN PIPELINES ==========")
    logger.info(f"[V4] Session: {session_id}")
    logger.info(f"[V4] Pipelines: {request.pipeline_names}")
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check that Step 7 was completed
    saved_id = session.get("approved_raw_id")
    if not saved_id:
        raise HTTPException(
            status_code=400, 
            detail="Step 7 not completed. Please save approved raw data first using /save-approved-raw"
        )
    
    # Verify approved_raw_data exists
    approved_raw = await db.approved_raw_data.find_one({"saved_id": saved_id})
    if not approved_raw:
        raise HTTPException(status_code=404, detail=f"Approved raw data not found: {saved_id}")
    
    logger.info(f"[V4] Using approved_raw_data: {saved_id} ({approved_raw.get('total_sources', 0)} sources)")
    
    # Validate pipeline names
    available = [p["name"] for p in pipeline_registry.list_pipelines()]
    for name in request.pipeline_names:
        if name not in available:
            raise HTTPException(status_code=400, detail=f"Unknown pipeline: {name}")
    
    now = datetime.utcnow()
    
    # Get card info for result storage
    cards = await db[CARDS_COLLECTION].find({
        "session_id": session_id, "is_selected": True
    }).to_list(length=200)
    primary_card = cards[0] if cards else None
    card_name = approved_raw.get("detected_card_name", "Unknown Card")
    
    # ============================================
    # CALL V2's PIPELINE LOGIC - REUSE, NOT REBUILD
    # ============================================
    try:
        logger.info(f"[V4] Calling pipeline_registry.run_all_pipelines({saved_id})")
        
        result = await pipeline_registry.run_all_pipelines(
            db,
            saved_id,
            save_results=True,
            parallel=False,
            pipeline_names=request.pipeline_names,
            source_indices=None
        )
        
        logger.info(f"[V4] Pipeline result:")
        logger.info(f"[V4]   total_benefits: {result.total_benefits}")
        logger.info(f"[V4]   pipelines_run: {result.pipelines_run}")
        logger.info(f"[V4]   failed_pipelines: {result.failed_pipelines}")
        logger.info(f"[V4]   errors: {result.errors}")
        
        # Log individual pipeline results
        for pname, presult in result.pipeline_results.items():
            logger.info(f"[V4]   {pname}: {presult.total_found} benefits, sources_processed={presult.sources_processed}")
        
        total_benefits = result.total_benefits
        
        # Store results in V4 collection
        if result.total_benefits > 0:
            benefits_list = [b.to_dict() for b in result.all_benefits]
            
            result_doc = {
                "result_id": generate_id("res"),
                "session_id": session_id,
                "card_id": primary_card["card_id"] if primary_card else None,
                "card_name": card_name,
                "raw_data_id": saved_id,
                "pipelines_run": result.pipelines_run,
                "benefits": benefits_list,
                "total_benefits": result.total_benefits,
                "quality_metrics": {
                    "high_confidence": result.high_confidence_total,
                    "medium_confidence": result.medium_confidence_total,
                    "low_confidence": result.low_confidence_total,
                },
                "duration_seconds": result.total_duration_seconds,
                "executed_at": now
            }
            
            await db[RESULTS_COLLECTION].insert_one(result_doc)
            logger.info(f"[V4] Saved {result.total_benefits} benefits to results collection")
        
        # Update approved_raw_data status
        await db.approved_raw_data.update_one(
            {"saved_id": saved_id},
            {"$set": {"status": "processed", "processed_at": now}}
        )
        
        # Update session
        await db[SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {"$set": {
                "current_step": 9,
                "stats.benefits_extracted": total_benefits,
                "steps_completed.step_8": True,
                "steps_completed.step_9": True,
                "updated_at": now
            }}
        )
        
        logger.info(f"[V4] ========== COMPLETE: {total_benefits} benefits ==========")
        
        return {
            "success": True,
            "total_benefits": total_benefits,
            "pipelines_run": result.pipelines_run,
            "failed_pipelines": result.failed_pipelines,
            "quality_metrics": {
                "high_confidence": result.high_confidence_total,
                "medium_confidence": result.medium_confidence_total,
                "low_confidence": result.low_confidence_total,
            },
            "duration_seconds": result.total_duration_seconds,
            "errors": result.errors
        }
        
    except Exception as e:
        logger.error(f"[V4] Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Update status to failed
        await db.approved_raw_data.update_one(
            {"saved_id": saved_id},
            {"$set": {"status": "failed", "processed_at": now}}
        )
        
        raise HTTPException(status_code=500, detail=str(e))


# ============= STEP 10: RESULTS =============

@router.get("/sessions/{session_id}/results")
async def get_session_results(session_id: str, view_by: str = "card"):
    """Get extraction results with various view options."""
    db = await get_database()
    results = await db[RESULTS_COLLECTION].find({"session_id": session_id}).to_list(length=5000)
    
    for r in results:
        r.pop("_id", None)
    
    total_benefits = 0
    confidence_counts = {"high": 0, "medium": 0, "low": 0}
    
    for result in results:
        for benefit in result.get("benefits", []):
            if not benefit.get("is_deleted"):
                total_benefits += 1
                level = str(benefit.get("confidence_level", "low")).lower()
                # Normalize confidence level
                if level in ["high", "medium", "low"]:
                    confidence_counts[level] = confidence_counts.get(level, 0) + 1
    
    # Get unique pipelines from benefits
    all_pipelines = set()
    for result in results:
        for benefit in result.get("benefits", []):
            if not benefit.get("is_deleted"):
                all_pipelines.add(benefit.get("benefit_type", "unknown"))
    
    summary = {
        "total_benefits": total_benefits,
        "confidence_breakdown": confidence_counts,
        "cards_with_results": len(set(r.get("card_id") for r in results if r.get("card_id"))),
        "pipelines_run": len(all_pipelines)
    }
    
    if view_by == "card":
        by_card = {}
        for result in results:
            card_id = result.get("card_id")
            if not card_id:
                continue
            if card_id not in by_card:
                by_card[card_id] = {
                    "card_id": card_id,
                    "card_name": result.get("card_name", "Unknown"),
                    "pipelines": {}
                }
            
            # Group benefits by type (pipeline)
            for benefit in result.get("benefits", []):
                if benefit.get("is_deleted"):
                    continue
                benefit_type = benefit.get("benefit_type", "unknown")
                if benefit_type not in by_card[card_id]["pipelines"]:
                    by_card[card_id]["pipelines"][benefit_type] = []
                by_card[card_id]["pipelines"][benefit_type].append(benefit)
        
        return {"view": "by_card", "data": list(by_card.values()), "summary": summary}
    
    return {"view": "flat", "results": results, "summary": summary}


@router.delete("/sessions/{session_id}/benefits/{benefit_id}")
async def delete_benefit(session_id: str, benefit_id: str):
    db = await get_database()
    result = await db[RESULTS_COLLECTION].update_one(
        {"session_id": session_id, "benefits.benefit_id": benefit_id},
        {"$set": {"benefits.$.is_deleted": True, "benefits.$.deleted_at": datetime.utcnow()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Benefit not found")
    return {"deleted": True, "benefit_id": benefit_id}


@router.post("/sessions/{session_id}/export")
async def export_results(session_id: str, request: ExportRequest):
    db = await get_database()
    
    session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    query = {"session_id": session_id}
    if request.card_ids:
        query["card_id"] = {"$in": request.card_ids}
    
    results = await db[RESULTS_COLLECTION].find(query).to_list(length=5000)
    cards = await db[CARDS_COLLECTION].find({"session_id": session_id}).to_list(length=200)
    card_map = {c["card_id"]: c for c in cards}
    
    export_data = {
        "session_id": session_id, "bank_name": session.get("bank_name"),
        "exported_at": datetime.utcnow().isoformat(), "cards": []
    }
    
    cards_data = {}
    for result in results:
        card_id = result["card_id"]
        if card_id not in cards_data:
            card_info = card_map.get(card_id, {})
            cards_data[card_id] = {
                "card_id": card_id,
                "card_name": result.get("card_name", card_info.get("card_name", "Unknown")),
                "card_url": card_info.get("card_url", ""),
                "benefits": []
            }
        
        for benefit in result.get("benefits", []):
            if not benefit.get("is_deleted"):
                cards_data[card_id]["benefits"].append({
                    "benefit_id": benefit["benefit_id"],
                    "title": benefit["title"],
                    "description": benefit["description"],
                    "type": benefit["benefit_type"],
                    "conditions": benefit.get("conditions", []),
                    "confidence": benefit["confidence"]
                })
    
    export_data["cards"] = list(cards_data.values())
    export_data["total_cards"] = len(export_data["cards"])
    export_data["total_benefits"] = sum(len(c["benefits"]) for c in export_data["cards"])
    
    return {"format": request.format, "data": export_data,
            "total_cards": export_data["total_cards"],
            "total_benefits": export_data["total_benefits"]}


@router.post("/sessions/{session_id}/finalize")
async def finalize_session(session_id: str):
    db = await get_database()
    result = await db[SESSIONS_COLLECTION].update_one(
        {"session_id": session_id},
        {"$set": {"current_step": 9, "status": SessionStatus.COMPLETED.value,
                  "steps_completed.step_9": True, "completed_at": datetime.utcnow(),
                  "updated_at": datetime.utcnow()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"finalized": True, "session_id": session_id}


# ============= UTILITY ENDPOINTS =============

@router.get("/banks")
async def list_banks():
    banks = [{"key": k, "name": v["name"], "cards_page": v["cards_page"],
              "requires_javascript": v["requires_javascript"]}
             for k, v in BANK_CONFIGS.items()]
    return {"banks": banks}


@router.get("/keywords/defaults")
async def get_default_keywords():
    return {"keywords": DEFAULT_KEYWORDS}


# ============= DIAGNOSTIC ENDPOINTS =============

@router.get("/sessions/{session_id}/debug-raw-data")
async def debug_raw_data(session_id: str):
    """
    Debug endpoint to verify approved_raw_data is correctly stored.
    Returns content lengths and source details.
    """
    db = await get_database()
    
    # Find all approved_raw_data for this session
    approved_raw = await db.approved_raw_data.find(
        {"v4_session_id": session_id}
    ).to_list(length=100)
    
    debug_info = []
    for raw in approved_raw:
        sources_info = []
        for i, src in enumerate(raw.get("sources", [])):
            raw_content = src.get("raw_content", "")
            cleaned_content = src.get("cleaned_content", "")
            sources_info.append({
                "index": i,
                "url": src.get("url", "")[:80],
                "title": src.get("title", "")[:50],
                "depth": src.get("depth", "?"),
                "raw_content_length": len(raw_content),
                "cleaned_content_length": len(cleaned_content),
                "raw_preview": raw_content[:200] if raw_content else "EMPTY",
                "has_content": len(raw_content) > 100
            })
        
        debug_info.append({
            "saved_id": raw.get("saved_id"),
            "card_name": raw.get("detected_card_name"),
            "total_sources": raw.get("total_sources"),
            "total_content_length": raw.get("total_content_length"),
            "status": raw.get("status"),
            "sources": sources_info
        })
    
    return {
        "session_id": session_id,
        "raw_data_count": len(approved_raw),
        "debug_info": debug_info
    }


@router.post("/sessions/{session_id}/test-pipeline/{pipeline_name}")
async def test_single_pipeline(session_id: str, pipeline_name: str):
    """
    Test a single pipeline with detailed logging.
    Returns step-by-step execution details.
    """
    db = await get_database()
    
    # Find approved_raw_data for this session
    approved_raw = await db.approved_raw_data.find_one({"v4_session_id": session_id})
    
    if not approved_raw:
        return {"error": "No approved_raw_data found for session", "session_id": session_id}
    
    saved_id = approved_raw.get("saved_id")
    
    # Get pipeline
    pipeline = pipeline_registry.get_pipeline(pipeline_name, db)
    if not pipeline:
        return {"error": f"Pipeline {pipeline_name} not found"}
    
    # Run single pipeline
    try:
        result = await pipeline.run(saved_id, source_indices=None)
        
        return {
            "success": True,
            "pipeline": pipeline_name,
            "saved_id": saved_id,
            "sources_total": result.sources_total,
            "sources_relevant": result.sources_relevant,
            "sources_processed": result.sources_processed,
            "total_found": result.total_found,
            "high_confidence": result.high_confidence_count,
            "medium_confidence": result.medium_confidence_count,
            "low_confidence": result.low_confidence_count,
            "llm_extractions": result.llm_extractions,
            "pattern_extractions": result.pattern_extractions,
            "duration_seconds": result.duration_seconds,
            "errors": result.errors,
            "warnings": result.warnings,
            "benefits": [b.to_dict() for b in result.benefits] if result.benefits else []
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/sessions/{session_id}/sources-summary")
async def get_sources_summary(session_id: str):
    """
    Get a quick summary of sources and their content status.
    """
    db = await get_database()
    
    sources = await db[SOURCES_COLLECTION].find(
        {"session_id": session_id}
    ).to_list(length=1000)
    
    summary = {
        "total": len(sources),
        "by_status": {},
        "by_depth": {},
        "content_status": {
            "has_content": 0,
            "empty": 0,
            "total_chars": 0
        },
        "sources": []
    }
    
    for src in sources:
        # By status
        status = src.get("approval_status", "unknown")
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
        
        # By depth
        depth = src.get("depth", "unknown")
        summary["by_depth"][str(depth)] = summary["by_depth"].get(str(depth), 0) + 1
        
        # Content status
        content_len = len(src.get("raw_content", ""))
        if content_len > 100:
            summary["content_status"]["has_content"] += 1
        else:
            summary["content_status"]["empty"] += 1
        summary["content_status"]["total_chars"] += content_len
        
        summary["sources"].append({
            "source_id": src.get("source_id"),
            "title": src.get("title", "")[:50],
            "depth": depth,
            "status": status,
            "content_length": content_len,
            "url": src.get("url", "")[:60]
        })
    
    return summary
