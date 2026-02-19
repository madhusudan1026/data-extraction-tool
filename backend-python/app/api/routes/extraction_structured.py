"""
Structured Extraction Routes (V5)

New intelligent scraping flow with hierarchical depth levels:
  Depth 0: Bank-wide card discovery with summary benefits
  Depth 1: Card detail page sectioned parsing
  Depth 2-3: Shared benefit pages with card cross-referencing (automatic)
  Depth 4+: User-approved deeper crawling

Coexists with V4 (old flow) - selectable in the UI.
"""

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urljoin

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_database
from app.core.config import settings
from app.core.banks import BANKS as BANK_CONFIGS, detect_bank_from_url, get_bank_name, detect_card_metadata

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v5/extraction", tags=["Structured Extraction V5"])


# ============= MODELS =============

class CreateStructuredSessionRequest(BaseModel):
    bank_key: Optional[str] = None
    custom_bank_url: Optional[str] = None
    custom_bank_name: Optional[str] = None
    use_playwright: bool = True
    max_depth: int = Field(3, ge=1, le=5)


class SelectCardsRequest(BaseModel):
    card_ids: List[str]


class ApproveDeepLinksRequest(BaseModel):
    url_ids: List[str]


# ============= COLLECTIONS =============

SESSIONS = "v5_sessions"
CARDS = "v5_cards"
CARD_SECTIONS = "v5_card_sections"
BENEFIT_SECTIONS = "v5_benefit_sections"
SCRAPED_URLS = "v5_scraped_urls"
DISCOVERED_URLS = "v5_discovered_urls"


def _gen_id(prefix: str) -> str:
    import hashlib, time, random
    data = f"{prefix}_{time.time()}_{random.random()}"
    return f"{prefix}_{hashlib.md5(data.encode()).hexdigest()[:12]}"


def _hash_url(url: str) -> str:
    import hashlib
    return hashlib.md5(url.rstrip('/').lower().encode()).hexdigest()


# ============= STEP 1: CREATE SESSION & DISCOVER CARDS (DEPTH 0) =============

@router.post("/sessions")
async def create_structured_session(request: CreateStructuredSessionRequest):
    """
    Create session and immediately run Depth 0: discover all cards from bank listing page.
    """
    db = await get_database()

    bank_key = request.bank_key
    bank_name = request.custom_bank_name or ""
    cards_page = request.custom_bank_url or ""

    if bank_key:
        if bank_key not in BANK_CONFIGS:
            raise HTTPException(status_code=400, detail=f"Unknown bank: {bank_key}")
        config = BANK_CONFIGS[bank_key]
        bank_name = config["name"]
        cards_page = config["cards_page"]
        patterns = config["card_url_patterns"]
        exclude = config["exclude_patterns"]
        requires_js = config["requires_javascript"]
    else:
        if not cards_page:
            raise HTTPException(status_code=400, detail="bank_key or custom_bank_url required")
        parsed = urlparse(cards_page)
        bank_key = detect_bank_from_url(cards_page) or "custom"
        bank_name = bank_name or parsed.netloc
        patterns = [r'/credit-cards?/[\w-]+$', r'/cards/[\w-]+$']
        exclude = ['business', 'corporate', 'apply', 'compare']
        requires_js = True

    session_id = _gen_id("v5sess")
    now = datetime.utcnow()

    session = {
        "session_id": session_id,
        "bank_key": bank_key,
        "bank_name": bank_name,
        "cards_page": cards_page,
        "use_playwright": request.use_playwright,
        "max_depth": request.max_depth,
        "current_step": 0,
        "status": "discovering_cards",
        "card_url_patterns": patterns,
        "exclude_patterns": exclude,
        "stats": {},
        "created_at": now,
        "updated_at": now,
    }
    await db[SESSIONS].insert_one(session)

    # ----- Depth 0: Discover cards -----
    from app.api.routes.extraction_unified import scrape_with_playwright
    from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
    from app.services.structured_scraper import discover_cards_structured

    html = None
    if requires_js or request.use_playwright:
        html = await scrape_with_playwright(cards_page)
    if not html:
        try:
            html = await enhanced_web_scraper_service.scrape_url(cards_page)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch cards page: {e}")

    cards = await discover_cards_structured(html, cards_page, bank_key, bank_name, patterns, exclude)

    # Store cards
    card_docs = []
    for card in cards:
        card_doc = {
            "card_id": _gen_id("card"),
            "session_id": session_id,
            "bank_key": bank_key,
            "bank_name": bank_name,
            "card_name": card["name"],
            "card_url": card["url"],
            "card_image_url": card.get("image_url"),
            "card_network": card.get("card_network", ""),
            "card_tier": card.get("card_tier", ""),
            "summary_benefits": card.get("summary_benefits", ""),
            "is_selected": False,
            "depth1_processed": False,
            "created_at": now,
        }
        card_docs.append(card_doc)

    if card_docs:
        await db[CARDS].insert_many(card_docs)

    # Mark URL as scraped
    await db[SCRAPED_URLS].update_one(
        {"url_hash": _hash_url(cards_page)},
        {"$set": {
            "url": cards_page, "url_hash": _hash_url(cards_page),
            "session_id": session_id, "depth": 0,
            "scraped_at": now, "content_type": "card_listing",
        }},
        upsert=True,
    )

    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 1, "status": "cards_discovered",
            "stats.cards_discovered": len(card_docs),
            "updated_at": now,
        }},
    )

    return {
        "success": True,
        "session_id": session_id,
        "bank_name": bank_name,
        "cards_discovered": len(card_docs),
        "cards": [{
            "card_id": c["card_id"], "card_name": c["card_name"],
            "card_url": c["card_url"], "card_image_url": c.get("card_image_url"),
            "card_network": c["card_network"], "card_tier": c["card_tier"],
            "summary_benefits": c["summary_benefits"],
        } for c in card_docs],
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session status and stats."""
    db = await get_database()
    session = await db[SESSIONS].find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/cards")
async def get_session_cards(session_id: str):
    """Get all cards for the session."""
    db = await get_database()
    cards = await db[CARDS].find(
        {"session_id": session_id}, {"_id": 0}
    ).to_list(length=200)
    return {"cards": cards, "total": len(cards)}


# ============= STEP 2: SELECT CARDS =============

@router.post("/sessions/{session_id}/select-cards")
async def select_cards(session_id: str, request: SelectCardsRequest):
    """Select which cards to process at depth 1+."""
    db = await get_database()
    await db[CARDS].update_many(
        {"session_id": session_id},
        {"$set": {"is_selected": False}},
    )
    result = await db[CARDS].update_many(
        {"session_id": session_id, "card_id": {"$in": request.card_ids}},
        {"$set": {"is_selected": True}},
    )
    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 2, "status": "cards_selected",
            "stats.cards_selected": result.modified_count,
            "updated_at": datetime.utcnow(),
        }},
    )
    return {"success": True, "cards_selected": result.modified_count}


# ============= STEP 3: PROCESS DEPTH 1 (CARD DETAIL PAGES) =============

@router.post("/sessions/{session_id}/process-depth1")
async def process_depth1(session_id: str):
    """
    Depth 1: For each selected card, scrape and section its detail page.
    Also discovers depth-2 URLs.
    """
    db = await get_database()
    session = await db[SESSIONS].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cards = await db[CARDS].find(
        {"session_id": session_id, "is_selected": True}
    ).to_list(length=200)

    if not cards:
        raise HTTPException(status_code=400, detail="No cards selected")

    use_playwright = session.get("use_playwright", True)

    from app.api.routes.extraction_unified import scrape_with_playwright
    from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
    from app.services.structured_scraper import parse_card_detail_page

    # Try to get ollama client for LLM sectioning
    ollama_client = None
    try:
        from app.services.ollama_client import OllamaClient
        ollama_client = OllamaClient()
    except Exception:
        logger.warning("[V5] Ollama client not available, using HTML-only sectioning")

    now = datetime.utcnow()
    total_sections = 0
    total_urls_discovered = 0
    results = []

    for card in cards:
        card_url = card["card_url"]
        card_name = card["card_name"]
        card_id = card["card_id"]

        # Check if already scraped
        url_hash = _hash_url(card_url)
        already_scraped = await db[SCRAPED_URLS].find_one({"url_hash": url_hash, "depth": {"$gte": 1}})

        if already_scraped:
            logger.info(f"[V5] Depth 1: Reusing cached scrape for {card_name}")
            # Load existing sections
            existing = await db[CARD_SECTIONS].find(
                {"card_id": card_id}
            ).to_list(length=100)
            results.append({
                "card_id": card_id, "card_name": card_name,
                "sections": len(existing), "urls_discovered": 0,
                "cached": True,
            })
            continue

        # Scrape the card page
        html = None
        if use_playwright:
            html = await scrape_with_playwright(card_url)
        if not html:
            try:
                html = await enhanced_web_scraper_service.scrape_url(card_url)
            except Exception as e:
                logger.error(f"[V5] Failed to scrape {card_name}: {e}")
                results.append({
                    "card_id": card_id, "card_name": card_name,
                    "sections": 0, "urls_discovered": 0, "error": str(e),
                })
                continue

        # Parse into sections
        sections, discovered_urls = await parse_card_detail_page(html, card_url, card_name, ollama_client)

        # Store sections
        section_docs = []
        for sec in sections:
            section_docs.append({
                "section_id": _gen_id("sec"),
                "session_id": session_id,
                "card_id": card_id,
                "card_name": card_name,
                "bank_key": card.get("bank_key", ""),
                "bank_name": card.get("bank_name", ""),
                "source_url": card_url,
                "depth": 1,
                "section_name": sec["section_name"],
                "section_type": sec.get("section_type", "general"),
                "content": sec["content"],
                "heading_text": sec.get("heading_text", ""),
                "created_at": now,
            })
        if section_docs:
            await db[CARD_SECTIONS].insert_many(section_docs)
        total_sections += len(section_docs)

        # Store discovered URLs for depth 2
        url_docs = []
        for link in discovered_urls:
            link_hash = _hash_url(link["url"])
            url_docs.append({
                "url_id": _gen_id("url"),
                "session_id": session_id,
                "source_card_id": card_id,
                "source_card_name": card_name,
                "url": link["url"],
                "url_hash": link_hash,
                "title": link.get("title", ""),
                "url_type": link.get("url_type", "web"),
                "depth": 2,
                "is_relevant": link.get("is_relevant", False),
                "status": "pending",  # pending, processing, completed, skipped
                "card_ids": [card_id],  # Will accumulate if shared
                "card_names": [card_name],
                "created_at": now,
            })
        # Upsert URLs (merge card_ids if URL already exists)
        for url_doc in url_docs:
            existing = await db[DISCOVERED_URLS].find_one({
                "session_id": session_id, "url_hash": url_doc["url_hash"],
            })
            if existing:
                # Merge card references
                ex_ids = existing.get("card_ids", [])
                ex_names = existing.get("card_names", [])
                if card_id not in ex_ids:
                    ex_ids.append(card_id)
                if card_name not in ex_names:
                    ex_names.append(card_name)
                await db[DISCOVERED_URLS].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"card_ids": ex_ids, "card_names": ex_names}},
                )
            else:
                await db[DISCOVERED_URLS].insert_one(url_doc)
        total_urls_discovered += len(url_docs)

        # Mark card as depth1 processed
        await db[CARDS].update_one(
            {"card_id": card_id},
            {"$set": {"depth1_processed": True}},
        )

        # Mark URL as scraped
        await db[SCRAPED_URLS].update_one(
            {"url_hash": url_hash},
            {"$set": {
                "url": card_url, "url_hash": url_hash,
                "session_id": session_id, "depth": 1,
                "scraped_at": now, "content_type": "card_detail",
            }},
            upsert=True,
        )

        results.append({
            "card_id": card_id, "card_name": card_name,
            "sections": len(section_docs), "urls_discovered": len(url_docs),
        })

    # Deduplicate discovered URLs count
    unique_d2_urls = await db[DISCOVERED_URLS].count_documents({
        "session_id": session_id, "depth": 2,
    })

    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 3, "status": "depth1_complete",
            "stats.depth1_sections": total_sections,
            "stats.depth2_urls_discovered": unique_d2_urls,
            "updated_at": now,
        }},
    )

    return {
        "success": True,
        "cards_processed": len(results),
        "total_sections": total_sections,
        "depth2_urls_discovered": unique_d2_urls,
        "results": results,
    }


@router.get("/sessions/{session_id}/card-sections/{card_id}")
async def get_card_sections(session_id: str, card_id: str):
    """Get parsed sections for a specific card."""
    db = await get_database()
    sections = await db[CARD_SECTIONS].find(
        {"session_id": session_id, "card_id": card_id}, {"_id": 0}
    ).to_list(length=100)
    return {"card_id": card_id, "sections": sections, "total": len(sections)}


@router.get("/sessions/{session_id}/depth2-urls")
async def get_depth2_urls(session_id: str):
    """Get discovered depth 2 URLs with card associations."""
    db = await get_database()
    urls = await db[DISCOVERED_URLS].find(
        {"session_id": session_id, "depth": 2}, {"_id": 0}
    ).to_list(length=500)
    return {"urls": urls, "total": len(urls)}


# ============= STEP 4: PROCESS DEPTH 2-3 (SHARED BENEFIT PAGES) =============

@router.post("/sessions/{session_id}/process-depth2")
async def process_depth2(session_id: str, max_urls: int = 50):
    """
    Depth 2: Process discovered URLs from depth 1.
    Intelligent benefit sectioning with card cross-referencing.
    Auto-continues to depth 3 for discovered deeper links.
    """
    db = await get_database()
    session = await db[SESSIONS].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get all discovered cards for cross-referencing
    all_cards = await db[CARDS].find(
        {"session_id": session_id}
    ).to_list(length=200)
    all_card_names = [c["card_name"] for c in all_cards]
    bank_name = session.get("bank_name", "")
    use_playwright = session.get("use_playwright", True)
    session_max_depth = session.get("max_depth", 3)

    from app.api.routes.extraction_unified import scrape_with_playwright
    from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
    from app.services.structured_scraper import parse_shared_benefit_page

    ollama_client = None
    try:
        from app.services.ollama_client import OllamaClient
        ollama_client = OllamaClient()
    except Exception:
        pass

    now = datetime.utcnow()
    total_benefits = 0
    total_depth3_urls = 0
    processed_count = 0
    skipped_count = 0

    # Process depth 2 and depth 3
    for current_depth in [2, 3]:
        if current_depth > session_max_depth:
            break

        urls_to_process = await db[DISCOVERED_URLS].find({
            "session_id": session_id,
            "depth": current_depth,
            "status": "pending",
        }).to_list(length=max_urls)

        logger.info(f"[V5] Processing {len(urls_to_process)} URLs at depth {current_depth}")

        for url_doc in urls_to_process:
            url = url_doc["url"]
            url_hash = _hash_url(url)

            # Check global scrape cache
            cached = await db[SCRAPED_URLS].find_one({"url_hash": url_hash})
            if cached:
                # URL already scraped - associate cards but don't re-scrape
                logger.info(f"[V5] Depth {current_depth}: Reusing cached {url[:60]}")
                # Find existing benefits from this URL and associate cards
                existing_benefits = await db[BENEFIT_SECTIONS].find(
                    {"source_url": url}
                ).to_list(length=100)
                for eb in existing_benefits:
                    # Merge card names
                    eb_cards = eb.get("eligible_card_names", [])
                    for cn in url_doc.get("card_names", []):
                        if cn not in eb_cards:
                            eb_cards.append(cn)
                    await db[BENEFIT_SECTIONS].update_one(
                        {"_id": eb["_id"]},
                        {"$set": {"eligible_card_names": eb_cards}},
                    )
                await db[DISCOVERED_URLS].update_one(
                    {"_id": url_doc["_id"]},
                    {"$set": {"status": "completed_cached"}},
                )
                skipped_count += 1
                continue

            # Scrape the page
            html = None
            if use_playwright:
                html = await scrape_with_playwright(url)
            if not html:
                try:
                    html = await enhanced_web_scraper_service.scrape_url(url)
                except Exception as e:
                    logger.error(f"[V5] Failed to scrape {url[:60]}: {e}")
                    await db[DISCOVERED_URLS].update_one(
                        {"_id": url_doc["_id"]},
                        {"$set": {"status": "failed", "error": str(e)}},
                    )
                    continue

            # Parse benefits
            benefit_sections, deeper_links = await parse_shared_benefit_page(
                html, url, all_card_names, bank_name, ollama_client,
            )

            # Store benefit sections
            for benefit in benefit_sections:
                benefit_doc = {
                    "benefit_id": _gen_id("ben"),
                    "session_id": session_id,
                    "source_url": url,
                    "source_depth": current_depth,
                    "source_card_ids": url_doc.get("card_ids", []),
                    "source_card_names": url_doc.get("card_names", []),
                    "bank_key": session.get("bank_key", ""),
                    "bank_name": bank_name,
                    "benefit_name": benefit.get("benefit_name", ""),
                    "benefit_text": benefit.get("benefit_text", ""),
                    "benefit_category": benefit.get("benefit_category", "general"),
                    "eligible_card_names": benefit.get("eligible_card_names", []),
                    "conditions": benefit.get("conditions", []),
                    "validity": benefit.get("validity", ""),
                    "created_at": now,
                }
                await db[BENEFIT_SECTIONS].insert_one(benefit_doc)
            total_benefits += len(benefit_sections)

            # Store deeper links for next depth (auto up to depth 3)
            next_depth = current_depth + 1
            if next_depth <= session_max_depth:
                for link in deeper_links:
                    link_hash = _hash_url(link["url"])
                    existing_link = await db[DISCOVERED_URLS].find_one({
                        "session_id": session_id, "url_hash": link_hash,
                    })
                    if not existing_link:
                        await db[DISCOVERED_URLS].insert_one({
                            "url_id": _gen_id("url"),
                            "session_id": session_id,
                            "source_card_id": url_doc.get("source_card_id", ""),
                            "source_card_name": url_doc.get("source_card_name", ""),
                            "url": link["url"],
                            "url_hash": link_hash,
                            "title": link.get("title", ""),
                            "url_type": link.get("url_type", "web"),
                            "depth": next_depth,
                            "status": "pending" if next_depth <= 3 else "needs_approval",
                            "card_ids": url_doc.get("card_ids", []),
                            "card_names": url_doc.get("card_names", []),
                            "parent_url": url,
                            "created_at": now,
                        })
                        total_depth3_urls += 1

            # Mark as scraped
            await db[SCRAPED_URLS].update_one(
                {"url_hash": url_hash},
                {"$set": {
                    "url": url, "url_hash": url_hash,
                    "session_id": session_id, "depth": current_depth,
                    "scraped_at": now, "content_type": "shared_benefits",
                    "benefits_extracted": len(benefit_sections),
                }},
                upsert=True,
            )

            await db[DISCOVERED_URLS].update_one(
                {"_id": url_doc["_id"]},
                {"$set": {"status": "completed", "benefits_found": len(benefit_sections)}},
            )

            processed_count += 1
            logger.info(f"[V5] Depth {current_depth}: {url[:60]} → {len(benefit_sections)} benefits")

    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 4, "status": "depth2_complete",
            "stats.benefits_extracted": total_benefits,
            "stats.urls_processed": processed_count,
            "stats.urls_cached": skipped_count,
            "stats.depth3_urls_discovered": total_depth3_urls,
            "updated_at": now,
        }},
    )

    return {
        "success": True,
        "urls_processed": processed_count,
        "urls_cached": skipped_count,
        "benefits_extracted": total_benefits,
        "depth3_urls_discovered": total_depth3_urls,
    }


# ============= VIEW BENEFIT SECTIONS =============

@router.get("/sessions/{session_id}/benefits")
async def get_session_benefits(session_id: str, card_name: Optional[str] = None, category: Optional[str] = None):
    """Get all extracted benefit sections, optionally filtered by card or category."""
    db = await get_database()
    query = {"session_id": session_id}
    if card_name:
        query["eligible_card_names"] = card_name
    if category:
        query["benefit_category"] = category

    benefits = await db[BENEFIT_SECTIONS].find(query, {"_id": 0}).to_list(length=500)

    # Also include card-specific sections from depth 1
    card_query = {"session_id": session_id}
    if card_name:
        card_query["card_name"] = card_name
    card_sections = await db[CARD_SECTIONS].find(card_query, {"_id": 0}).to_list(length=500)

    # Category breakdown
    categories = {}
    for b in benefits:
        cat = b.get("benefit_category", "general")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "benefits": benefits,
        "card_sections": card_sections,
        "total_benefits": len(benefits),
        "total_card_sections": len(card_sections),
        "category_breakdown": categories,
    }


@router.get("/sessions/{session_id}/benefits/by-card/{card_name}")
async def get_benefits_for_card(session_id: str, card_name: str):
    """Get all benefits applicable to a specific card."""
    db = await get_database()

    # Depth 1 sections (card-specific)
    card_sections = await db[CARD_SECTIONS].find(
        {"session_id": session_id, "card_name": card_name}, {"_id": 0}
    ).to_list(length=100)

    # Depth 2-3 benefits mentioning this card
    benefits = await db[BENEFIT_SECTIONS].find(
        {"session_id": session_id, "eligible_card_names": card_name}, {"_id": 0}
    ).to_list(length=500)

    return {
        "card_name": card_name,
        "card_sections": card_sections,
        "shared_benefits": benefits,
        "total": len(card_sections) + len(benefits),
    }


# ============= DEEP LINK APPROVAL (DEPTH 4+) =============

@router.get("/sessions/{session_id}/pending-approvals")
async def get_pending_approvals(session_id: str):
    """Get URLs that need user approval before crawling (depth 4+)."""
    db = await get_database()
    urls = await db[DISCOVERED_URLS].find(
        {"session_id": session_id, "status": "needs_approval"}, {"_id": 0}
    ).to_list(length=200)
    return {"urls": urls, "total": len(urls)}


@router.post("/sessions/{session_id}/approve-deep-links")
async def approve_deep_links(session_id: str, request: ApproveDeepLinksRequest):
    """Approve selected deep links for crawling."""
    db = await get_database()
    result = await db[DISCOVERED_URLS].update_many(
        {"session_id": session_id, "url_id": {"$in": request.url_ids}},
        {"$set": {"status": "pending"}},
    )
    return {"success": True, "approved": result.modified_count}


# ============= SESSION MANAGEMENT =============

@router.get("/sessions")
async def list_sessions(limit: int = 20):
    """List all V5 structured extraction sessions."""
    db = await get_database()
    sessions = await db[SESSIONS].find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(length=limit)
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all associated data."""
    db = await get_database()
    for coll in [SESSIONS, CARDS, CARD_SECTIONS, BENEFIT_SECTIONS, DISCOVERED_URLS]:
        await db[coll].delete_many({"session_id": session_id})
    # Don't delete SCRAPED_URLS as they're shared across sessions
    return {"success": True}
