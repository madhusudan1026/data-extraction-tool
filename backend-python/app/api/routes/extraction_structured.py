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
    # Mode: bank_wide (discover cards from bank) or single_card (direct card URL)
    mode: str = Field("bank_wide", pattern="^(bank_wide|single_card)$")
    # Bank-wide mode
    bank_key: Optional[str] = None
    custom_bank_url: Optional[str] = None
    custom_bank_name: Optional[str] = None
    # Single card mode
    single_card_url: Optional[str] = None
    single_card_name: Optional[str] = None
    # Options
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
    Create session.
    - bank_wide mode: Depth 0 discovers all cards from bank listing page.
    - single_card mode: Skip depth 0, create one card from direct URL, jump to card selection.
    """
    db = await get_database()

    # ---- SINGLE CARD MODE ----
    if request.mode == "single_card":
        if not request.single_card_url:
            raise HTTPException(status_code=400, detail="single_card_url required for single_card mode")

        card_url = request.single_card_url.strip()
        parsed = urlparse(card_url)
        bank_key = detect_bank_from_url(card_url) or request.bank_key or "custom"
        bank_name = request.custom_bank_name or get_bank_name(bank_key) or parsed.netloc
        card_name = request.single_card_name or ""

        session_id = _gen_id("v5sess")
        now = datetime.utcnow()

        session = {
            "session_id": session_id,
            "mode": "single_card",
            "bank_key": bank_key,
            "bank_name": bank_name,
            "cards_page": "",
            "use_playwright": request.use_playwright,
            "max_depth": request.max_depth,
            "current_step": 1,
            "status": "cards_discovered",
            "card_url_patterns": [],
            "exclude_patterns": [],
            "stats": {"cards_discovered": 1},
            "created_at": now,
            "updated_at": now,
        }
        await db[SESSIONS].insert_one(session)

        # Auto-detect card name from URL if not provided
        if not card_name:
            # Try to get page title
            try:
                from app.services.playwright_scraper import scrape_with_playwright
                html = await scrape_with_playwright(card_url)
                if html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    title_tag = soup.find('title')
                    if title_tag:
                        card_name = title_tag.get_text(strip=True)
                        # Clean up common suffixes
                        for suffix in [' | Emirates NBD', ' - Emirates NBD', ' | FAB', ' | ADCB', ' | Mashreq']:
                            card_name = card_name.replace(suffix, '').strip()
            except Exception:
                pass
            if not card_name:
                # Derive from URL path
                path_parts = parsed.path.rstrip('/').split('/')
                card_name = path_parts[-1].replace('-', ' ').title() if path_parts else "Unknown Card"

        # Detect card metadata
        meta = detect_card_metadata(card_name, card_url)

        card_doc = {
            "card_id": _gen_id("card"),
            "session_id": session_id,
            "bank_key": bank_key,
            "bank_name": bank_name,
            "card_name": card_name,
            "card_url": card_url,
            "card_image_url": None,
            "card_network": meta.get("network", ""),
            "card_tier": meta.get("tier", ""),
            "summary_benefits": "",
            "is_selected": False,
            "depth1_processed": False,
            "created_at": now,
        }
        await db[CARDS].insert_one(card_doc)

        return {
            "success": True,
            "session_id": session_id,
            "mode": "single_card",
            "bank_name": bank_name,
            "cards_discovered": 1,
            "cards": [{
                "card_id": card_doc["card_id"],
                "card_name": card_doc["card_name"],
                "card_url": card_doc["card_url"],
                "card_image_url": None,
                "card_network": card_doc["card_network"],
                "card_tier": card_doc["card_tier"],
                "summary_benefits": "",
            }],
        }

    # ---- BANK-WIDE MODE ----
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
        "mode": "bank_wide",
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
    from app.services.playwright_scraper import scrape_with_playwright
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

    from app.services.playwright_scraper import scrape_with_playwright
    from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
    from app.services.structured_scraper import parse_card_detail_page, _clean_section_text

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

        # Check if THIS card already has sections in THIS session
        existing_sections = await db[CARD_SECTIONS].find(
            {"session_id": session_id, "card_id": card_id}
        ).to_list(length=100)

        if existing_sections:
            logger.info(f"[V5] Depth 1: Card {card_name} already has {len(existing_sections)} sections in this session")
            results.append({
                "card_id": card_id, "card_name": card_name,
                "sections": len(existing_sections), "urls_discovered": 0,
                "cached": True,
            })
            continue

        # Scrape the card page INTERACTIVELY (clicks expandable tiles)
        url_hash = _hash_url(card_url)
        sections = []
        discovered_urls = []

        if use_playwright:
            try:
                from app.services.interactive_scraper import scrape_card_page_interactive
                interactive_result = await scrape_card_page_interactive(card_url, card_name)
                
                if interactive_result.get("sections"):
                    logger.info(f"[V5] Interactive scrape: {len(interactive_result['sections'])} sections for {card_name}")
                    
                    # Convert interactive sections to our format
                    for isec in interactive_result["sections"]:
                        heading = isec.get("heading", "")
                        sec_links = isec.get("links", [])
                        from app.services.structured_scraper import _normalize_section_name, _classify_section, _is_relevant_link, _clean_section_text
                        
                        content = _clean_section_text(isec.get("content", ""))
                        
                        sec_name = _normalize_section_name(heading)
                        sec_type = _classify_section(sec_name, content)
                        
                        # Filter links to relevant ones
                        relevant_links = [l for l in sec_links if _is_relevant_link(l.get("url", ""), l.get("title", ""))]
                        
                        sections.append({
                            "section_name": sec_name,
                            "section_type": sec_type,
                            "content": content,
                            "heading_text": heading,
                            "links": relevant_links,
                            "is_expandable": isec.get("is_expandable", False),
                        })
                        
                        # Add section links to discovered URLs
                        for link in relevant_links:
                            link["source_section"] = sec_name
                            discovered_urls.append(link)
                        
                        # Process sub-sections (from expanded accordion items)
                        for sub in isec.get("sub_sections", []):
                            sub_title = sub.get("title", "")
                            sub_content = _clean_section_text(sub.get("content", ""))
                            sub_links = sub.get("links", [])
                            sub_name = _normalize_section_name(f"{heading} - {sub_title}")
                            sub_type = _classify_section(sub_name, sub_content)
                            
                            relevant_sub_links = [l for l in sub_links if _is_relevant_link(l.get("url", ""), l.get("title", ""))]
                            
                            sections.append({
                                "section_name": sub_name,
                                "section_type": sub_type,
                                "content": sub_content,
                                "heading_text": f"{heading} → {sub_title}",
                                "links": relevant_sub_links,
                                "parent_section": sec_name,
                            })
                            
                            for link in relevant_sub_links:
                                link["source_section"] = sub_name
                                discovered_urls.append(link)
                    
                    logger.info(f"[V5] Interactive: {len(sections)} total sections (incl. sub), {len(discovered_urls)} URLs")
                
                # Fallback: if interactive returned no sections, use the full HTML
                if not sections and interactive_result.get("full_html"):
                    html = interactive_result["full_html"]
                    logger.info(f"[V5] Interactive sections empty, falling back to HTML parse ({len(html)} chars)")
                    from app.services.structured_scraper import parse_card_detail_page
                    sections, discovered_urls = await parse_card_detail_page(html, card_url, card_name, ollama_client)
                    
            except Exception as e:
                logger.warning(f"[V5] Interactive scrape failed for {card_name}: {e}")
                import traceback
                traceback.print_exc()
        
        # Fallback: plain Playwright + HTML parsing
        if not sections:
            try:
                html = await scrape_with_playwright(card_url)
                if html and len(html) > 100:
                    logger.info(f"[V5] Fallback Playwright scraped {len(html)} chars for {card_name}")
                    from app.services.structured_scraper import parse_card_detail_page
                    sections, discovered_urls = await parse_card_detail_page(html, card_url, card_name, ollama_client)
            except Exception as e:
                logger.error(f"[V5] All scraping failed for {card_name}: {e}")
                results.append({
                    "card_id": card_id, "card_name": card_name,
                    "sections": 0, "urls_discovered": 0, "error": str(e),
                })
                continue

        if not sections:
            results.append({
                "card_id": card_id, "card_name": card_name,
                "sections": 0, "urls_discovered": 0, "error": "No sections extracted",
            })
            continue

        # Deduplicate discovered URLs
        seen_d_urls = set()
        deduped_discovered = []
        for du in discovered_urls:
            u = du.get("url", "")
            if u and u not in seen_d_urls:
                seen_d_urls.add(u)
                deduped_discovered.append(du)
        discovered_urls = deduped_discovered

        # Store sections
        section_docs = []
        for sec in sections:
            sec_id = _gen_id("sec")
            sec_links = sec.get("links", [])
            # Final content cleanup before storage
            clean_content = _clean_section_text(sec.get("content", ""))
            section_docs.append({
                "section_id": sec_id,
                "session_id": session_id,
                "card_id": card_id,
                "card_name": card_name,
                "bank_key": card.get("bank_key", ""),
                "bank_name": card.get("bank_name", ""),
                "source_url": card_url,
                "depth": 1,
                "section_name": sec["section_name"],
                "section_type": sec.get("section_type", "general"),
                "content": clean_content,
                "heading_text": sec.get("heading_text", ""),
                "is_approved": True,
                "is_expandable": sec.get("is_expandable", False),
                "parent_section": sec.get("parent_section", ""),
                "links": sec_links,
                "link_count": len(sec_links),
                "created_at": now,
            })
        if section_docs:
            await db[CARD_SECTIONS].insert_many(section_docs)
        total_sections += len(section_docs)

        # Build section_id lookup by section_name
        section_name_to_id = {}
        for sd in section_docs:
            section_name_to_id[sd["section_name"]] = {
                "section_id": sd["section_id"],
                "section_name": sd["section_name"],
            }
            # Also map by URLs found in this section's links
            for lnk in sd.get("links", []):
                lnk_url = lnk.get("url", "").rstrip('/').lower()
                if lnk_url:
                    section_name_to_id[lnk_url] = {
                        "section_id": sd["section_id"],
                        "section_name": sd["section_name"],
                    }

        # Store discovered URLs for depth 2 (with section mapping)
        url_docs = []
        for link in discovered_urls:
            link_hash = _hash_url(link["url"])
            # Try to find source section from: 1) link's source_section tag, 2) URL lookup
            src_section_name = link.get("source_section", "")
            source_section = section_name_to_id.get(src_section_name, {})
            if not source_section:
                link_url_normalized = link["url"].rstrip('/').lower()
                source_section = section_name_to_id.get(link_url_normalized, {})

            url_docs.append({
                "url_id": _gen_id("url"),
                "session_id": session_id,
                "source_card_id": card_id,
                "source_card_name": card_name,
                "source_section_id": source_section.get("section_id", ""),
                "source_section_name": source_section.get("section_name", link.get("source_section", "")),
                "url": link["url"],
                "url_hash": link_hash,
                "title": link.get("title", ""),
                "url_type": link.get("url_type", "web"),
                "depth": 2,
                "is_relevant": link.get("is_relevant", False),
                "status": "pending",
                "card_ids": [card_id],
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
    """Get parsed sections for a specific card with their mapped URLs."""
    db = await get_database()
    sections = await db[CARD_SECTIONS].find(
        {"session_id": session_id, "card_id": card_id}, {"_id": 0}
    ).to_list(length=100)

    # For each section, count and attach mapped depth-2 URLs
    for sec in sections:
        sec_id = sec.get("section_id", "")
        sec_name = sec.get("section_name", "")
        # Match by section_id OR section_name (sub-sections use name-based mapping)
        mapped_urls = await db[DISCOVERED_URLS].find(
            {"session_id": session_id, "$or": [
                {"source_section_id": sec_id},
                {"source_section_name": sec_name},
            ]},
            {"_id": 0, "url_id": 1, "url": 1, "title": 1, "status": 1, "url_type": 1},
        ).to_list(length=50)
        # Also check section's own stored links if no mapped URLs found
        if not mapped_urls and sec.get("links"):
            mapped_urls = [{"url": l["url"], "title": l.get("title", ""), "status": "pending"} for l in sec["links"]]
        sec["mapped_urls"] = mapped_urls
        sec["mapped_url_count"] = len(mapped_urls)

    # Also find unmapped URLs (not linked to any section)
    unmapped_urls = await db[DISCOVERED_URLS].find(
        {"session_id": session_id, "source_section_id": {"$in": ["", None]}},
        {"_id": 0, "url_id": 1, "url": 1, "title": 1, "status": 1, "url_type": 1},
    ).to_list(length=100)

    return {
        "card_id": card_id,
        "sections": sections,
        "total": len(sections),
        "unmapped_urls": unmapped_urls,
        "unmapped_url_count": len(unmapped_urls),
    }


@router.delete("/sessions/{session_id}/sections/{section_id}")
async def delete_section(session_id: str, section_id: str):
    """
    Delete a section and skip all its mapped depth-2 URLs.
    URLs won't be scraped during depth 2-3 processing.
    """
    db = await get_database()

    # Get section to confirm it exists
    section = await db[CARD_SECTIONS].find_one({
        "session_id": session_id, "section_id": section_id,
    })
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Mark all mapped URLs as skipped
    skip_result = await db[DISCOVERED_URLS].update_many(
        {"session_id": session_id, "source_section_id": section_id},
        {"$set": {"status": "skipped"}},
    )

    # Delete the section
    await db[CARD_SECTIONS].delete_one({"session_id": session_id, "section_id": section_id})

    logger.info(f"[V5] Deleted section {section_id} ({section.get('section_name', '')}), skipped {skip_result.modified_count} URLs")

    return {
        "success": True,
        "section_name": section.get("section_name", ""),
        "urls_skipped": skip_result.modified_count,
    }


@router.post("/sessions/{session_id}/sections/{section_id}/toggle-approval")
async def toggle_section_approval(session_id: str, section_id: str):
    """Toggle approval status of a section. Unapproved sections' URLs are skipped."""
    db = await get_database()
    section = await db[CARD_SECTIONS].find_one({
        "session_id": session_id, "section_id": section_id,
    })
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    new_status = not section.get("is_approved", True)
    url_status = "pending" if new_status else "skipped"

    await db[CARD_SECTIONS].update_one(
        {"session_id": session_id, "section_id": section_id},
        {"$set": {"is_approved": new_status}},
    )
    url_result = await db[DISCOVERED_URLS].update_many(
        {"session_id": session_id, "source_section_id": section_id},
        {"$set": {"status": url_status}},
    )

    return {
        "success": True,
        "is_approved": new_status,
        "urls_updated": url_result.modified_count,
    }


@router.get("/sessions/{session_id}/depth2-urls")
async def get_depth2_urls(session_id: str):
    """Get discovered depth 2 URLs with card associations."""
    db = await get_database()
    urls = await db[DISCOVERED_URLS].find(
        {"session_id": session_id, "depth": 2}, {"_id": 0}
    ).to_list(length=500)
    return {"urls": urls, "total": len(urls)}


# ============= STEP 4: PROCESS DEPTH 2-3 (SCRAPE & SECTION FOR REVIEW) =============

DEPTH2_SECTIONS = "v5_depth2_sections"  # Pending review, like depth 1 card_sections

@router.post("/sessions/{session_id}/process-depth2")
async def process_depth2(session_id: str, max_urls: int = 50):
    """
    Depth 2-3: Scrape discovered URLs and section them using HTML structure.
    NO LLM — same approach as depth 1.
    Results stored in v5_depth2_sections for user review before final storage.
    Preserves full context chain: bank > card > d1 section > d2 url > d2 sections.
    """
    db = await get_database()
    session = await db[SESSIONS].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    bank_name = session.get("bank_name", "")
    bank_key = session.get("bank_key", "")
    use_playwright = session.get("use_playwright", True)
    session_max_depth = session.get("max_depth", 3)

    from app.services.playwright_scraper import scrape_with_playwright
    from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
    from app.services.structured_scraper import _clean_section_text, _classify_section, _normalize_section_name, _is_relevant_link

    now = datetime.utcnow()
    total_sections = 0
    total_depth3_urls = 0
    processed_count = 0
    skipped_count = 0
    results = []

    # Process depth 2 and depth 3
    for current_depth in [2, 3]:
        if current_depth > session_max_depth:
            break

        # Only process APPROVED (pending) URLs — skipped ones are excluded
        urls_to_process = await db[DISCOVERED_URLS].find({
            "session_id": session_id,
            "depth": current_depth,
            "status": "pending",
        }).to_list(length=max_urls)

        logger.info(f"[V5] Depth {current_depth}: {len(urls_to_process)} URLs to process")

        for url_doc in urls_to_process:
            url = url_doc["url"]
            url_hash = _hash_url(url)
            source_card_names = url_doc.get("card_names", [])
            source_section_name = url_doc.get("source_section_name", "")

            # Check if already sectioned in THIS session
            existing = await db[DEPTH2_SECTIONS].find(
                {"session_id": session_id, "source_url": url}
            ).to_list(length=100)

            if existing:
                logger.info(f"[V5] Depth {current_depth}: Already sectioned {url[:60]}")
                await db[DISCOVERED_URLS].update_one(
                    {"_id": url_doc["_id"]},
                    {"$set": {"status": "completed", "sections_found": len(existing)}},
                )
                skipped_count += 1
                total_sections += len(existing)
                continue

            # Scrape the page
            html = None
            interactive_sections = None

            # Try interactive scraper first (clicks expandables) — same as depth 1
            if use_playwright:
                try:
                    from app.services.interactive_scraper import scrape_card_page_interactive
                    interactive_result = await scrape_card_page_interactive(url)
                    if interactive_result.get("sections"):
                        interactive_sections = interactive_result["sections"]
                        expandable_count = sum(1 for s in interactive_sections if s.get("is_expandable"))
                        sub_count = sum(len(s.get("sub_sections", [])) for s in interactive_sections)
                        logger.info(f"[V5] Depth {current_depth}: Interactive → {len(interactive_sections)} sections "
                                    f"({expandable_count} expandable, {sub_count} sub-sections) from {url[:60]}")
                    else:
                        html = interactive_result.get("full_html", "")
                        logger.info(f"[V5] Depth {current_depth}: Interactive returned no sections, got {len(html or '')} chars HTML from {url[:60]}")
                except Exception as e:
                    logger.warning(f"[V5] Depth {current_depth}: Interactive scrape failed for {url[:60]}: {e}")

            # Fallback: plain playwright
            if not interactive_sections and not html:
                try:
                    html = await scrape_with_playwright(url)
                    logger.info(f"[V5] Depth {current_depth}: Playwright scraped {len(html or '')} chars from {url[:60]}")
                except Exception as e:
                    logger.warning(f"[V5] Playwright failed for {url[:60]}: {e}")

            # Fallback: direct HTTP
            if not interactive_sections and not html:
                try:
                    html = await enhanced_web_scraper_service.scrape_url(url)
                except Exception as e:
                    logger.error(f"[V5] All scraping failed for {url[:60]}: {e}")
                    await db[DISCOVERED_URLS].update_one(
                        {"_id": url_doc["_id"]},
                        {"$set": {"status": "failed", "error": str(e)}},
                    )
                    continue

            if not interactive_sections and (not html or len(html) < 100):
                await db[DISCOVERED_URLS].update_one(
                    {"_id": url_doc["_id"]},
                    {"$set": {"status": "failed", "error": "Empty HTML"}},
                )
                continue

            # ---- SECTION THE CONTENT (HTML-only, no LLM) ----
            page_sections = []

            if interactive_sections:
                # Convert interactive scraper sections
                for isec in interactive_sections:
                    heading = isec.get("heading", "")
                    content = _clean_section_text(isec.get("content", ""))
                    sec_links = isec.get("links", [])
                    relevant_links = [l for l in sec_links if _is_relevant_link(l.get("url", ""), l.get("title", ""))]

                    if content and len(content) > 20:
                        page_sections.append({
                            "section_name": _normalize_section_name(heading),
                            "section_type": _classify_section(heading, content),
                            "content": content,
                            "heading_text": heading,
                            "links": relevant_links,
                            "is_expandable": isec.get("is_expandable", False),
                        })

                    # Sub-sections from expandable items
                    for sub in isec.get("sub_sections", []):
                        sub_content = _clean_section_text(sub.get("content", ""))
                        sub_links = sub.get("links", [])
                        relevant_sub_links = [l for l in sub_links if _is_relevant_link(l.get("url", ""), l.get("title", ""))]
                        sub_name = _normalize_section_name(f"{heading} - {sub.get('title', '')}")

                        if sub_content and len(sub_content) > 20:
                            page_sections.append({
                                "section_name": sub_name,
                                "section_type": _classify_section(sub_name, sub_content),
                                "content": sub_content,
                                "heading_text": f"{heading} → {sub.get('title', '')}",
                                "links": relevant_sub_links,
                                "parent_section": _normalize_section_name(heading),
                            })
            else:
                # HTML-only sectioning (same as depth 1 fallback)
                try:
                    from app.services.structured_scraper import parse_card_detail_page
                    html_sections, html_links = await parse_card_detail_page(html, url, "", None)
                    for sec in html_sections:
                        content = _clean_section_text(sec.get("content", ""))
                        if content and len(content) > 20:
                            page_sections.append(sec)
                except Exception as e:
                    logger.error(f"[V5] HTML sectioning failed for {url[:60]}: {e}")

            if not page_sections:
                # Last resort: store entire page text as one section
                if html:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'svg', 'iframe']):
                        tag.decompose()
                    text = _clean_section_text(soup.get_text(separator='\n', strip=True)[:8000])
                    if text:
                        page_sections.append({
                            "section_name": "page_content",
                            "section_type": "general",
                            "content": text,
                            "heading_text": url_doc.get("title", url),
                            "links": [],
                        })

            # Store sections for review (NOT final benefit storage)
            section_docs = []
            url_sections_links = []
            for sec in page_sections:
                sec_id = _gen_id("d2s")
                sec_links = sec.get("links", [])
                section_docs.append({
                    "section_id": sec_id,
                    "session_id": session_id,
                    "source_url": url,
                    "source_url_id": url_doc.get("url_id", ""),
                    "source_depth": current_depth,
                    # Full context chain
                    "bank_key": bank_key,
                    "bank_name": bank_name,
                    "source_card_names": source_card_names,
                    "source_d1_section": source_section_name,
                    # Section data
                    "section_name": sec["section_name"],
                    "section_type": sec.get("section_type", "general"),
                    "content": sec["content"],
                    "heading_text": sec.get("heading_text", ""),
                    "is_expandable": sec.get("is_expandable", False),
                    "parent_section": sec.get("parent_section", ""),
                    "links": sec_links,
                    "link_count": len(sec_links),
                    # Review state
                    "is_approved": True,
                    "is_stored": False,  # Not yet committed to final storage
                    "created_at": now,
                })
                url_sections_links.extend(sec_links)

            if section_docs:
                await db[DEPTH2_SECTIONS].insert_many(section_docs)
            total_sections += len(section_docs)

            # Discover depth 3+ URLs from section links
            next_depth = current_depth + 1
            if next_depth <= session_max_depth:
                seen_link_hashes = set()
                for link in url_sections_links:
                    link_hash = _hash_url(link["url"])
                    if link_hash in seen_link_hashes:
                        continue
                    seen_link_hashes.add(link_hash)
                    existing_link = await db[DISCOVERED_URLS].find_one({
                        "session_id": session_id, "url_hash": link_hash,
                    })
                    if not existing_link:
                        await db[DISCOVERED_URLS].insert_one({
                            "url_id": _gen_id("url"),
                            "session_id": session_id,
                            "source_card_name": ', '.join(source_card_names[:3]),
                            "source_section_name": url_doc.get("title", ""),
                            "url": link["url"],
                            "url_hash": link_hash,
                            "title": link.get("title", ""),
                            "depth": next_depth,
                            "status": "pending" if next_depth <= 3 else "needs_approval",
                            "card_ids": url_doc.get("card_ids", []),
                            "card_names": source_card_names,
                            "parent_url": url,
                            "created_at": now,
                        })
                        total_depth3_urls += 1

            # Mark URL as processed
            await db[DISCOVERED_URLS].update_one(
                {"_id": url_doc["_id"]},
                {"$set": {"status": "completed", "sections_found": len(section_docs)}},
            )

            processed_count += 1
            results.append({
                "url": url,
                "title": url_doc.get("title", ""),
                "depth": current_depth,
                "sections": len(section_docs),
                "links_found": len(url_sections_links),
                "source_cards": source_card_names[:3],
            })

    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "current_step": 4, "status": "depth2_sectioned",
            "stats.d2_sections": total_sections,
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
        "total_sections": total_sections,
        "depth3_urls_discovered": total_depth3_urls,
        "results": results,
    }


# ============= STEP 4b: REVIEW DEPTH 2-3 SECTIONS =============

@router.get("/sessions/{session_id}/depth2-sections")
async def get_depth2_sections(session_id: str, source_url: str = None):
    """Get depth 2-3 sections for review, optionally filtered by source URL."""
    db = await get_database()
    query = {"session_id": session_id}
    if source_url:
        query["source_url"] = source_url
    sections = await db[DEPTH2_SECTIONS].find(query, {"_id": 0}).to_list(length=500)

    # Group by source URL
    by_url = {}
    for sec in sections:
        url = sec["source_url"]
        if url not in by_url:
            by_url[url] = {
                "source_url": url,
                "source_depth": sec.get("source_depth", 2),
                "source_card_names": sec.get("source_card_names", []),
                "source_d1_section": sec.get("source_d1_section", ""),
                "sections": [],
            }
        by_url[url]["sections"].append(sec)

    return {
        "urls": list(by_url.values()),
        "total_urls": len(by_url),
        "total_sections": len(sections),
    }


@router.delete("/sessions/{session_id}/depth2-sections/{section_id}")
async def delete_depth2_section(session_id: str, section_id: str):
    """Delete a depth 2-3 section (reject it from final storage)."""
    db = await get_database()
    section = await db[DEPTH2_SECTIONS].find_one({
        "session_id": session_id, "section_id": section_id,
    })
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    await db[DEPTH2_SECTIONS].delete_one({"session_id": session_id, "section_id": section_id})
    logger.info(f"[V5] Deleted depth2 section {section_id}: {section.get('section_name', '')}")
    return {"success": True, "section_name": section.get("section_name", "")}


@router.post("/sessions/{session_id}/depth2-sections/{section_id}/toggle")
async def toggle_depth2_section(session_id: str, section_id: str):
    """Toggle approval of a depth 2-3 section."""
    db = await get_database()
    section = await db[DEPTH2_SECTIONS].find_one({
        "session_id": session_id, "section_id": section_id,
    })
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    new_status = not section.get("is_approved", True)
    await db[DEPTH2_SECTIONS].update_one(
        {"session_id": session_id, "section_id": section_id},
        {"$set": {"is_approved": new_status}},
    )
    return {"success": True, "is_approved": new_status}


@router.post("/sessions/{session_id}/store-approved")
async def store_approved_sections(session_id: str):
    """
    Final storage: Store ALL approved data from this V5 session.
    
    1. Approved depth 1 sections (card page content) → v5_benefit_sections
    2. Approved depth 2-3 sections → v5_benefit_sections
    3. Everything → approved_raw_data (for DataStore & Vectorization tab)
    
    Each source in approved_raw_data includes hierarchical context prefix:
      Bank > Card > Depth 1 Section > URL > Depth 2 Section
    This context is embedded WITH the content for vectorization.
    """
    import uuid
    db = await get_database()
    session = await db[SESSIONS].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    bank_name = session.get("bank_name", "")
    bank_key = session.get("bank_key", "")
    now = datetime.utcnow()
    stored_count = 0
    
    # ---- 1. Store approved depth 2-3 sections to v5_benefit_sections ----
    approved_d2 = await db[DEPTH2_SECTIONS].find({
        "session_id": session_id,
        "is_approved": True,
        "is_stored": {"$ne": True},
    }).to_list(length=1000)

    for sec in approved_d2:
        benefit_doc = {
            "benefit_id": _gen_id("ben"),
            "session_id": session_id,
            "bank_key": sec.get("bank_key", bank_key),
            "bank_name": sec.get("bank_name", bank_name),
            "source_card_names": sec.get("source_card_names", []),
            "source_d1_section": sec.get("source_d1_section", ""),
            "source_url": sec.get("source_url", ""),
            "source_depth": sec.get("source_depth", 2),
            "section_name": sec.get("section_name", ""),
            "section_type": sec.get("section_type", "general"),
            "content": sec.get("content", ""),
            "heading_text": sec.get("heading_text", ""),
            "parent_section": sec.get("parent_section", ""),
            "links": sec.get("links", []),
            "link_count": sec.get("link_count", 0),
            "stored_at": now,
        }
        await db[BENEFIT_SECTIONS].insert_one(benefit_doc)
        stored_count += 1
        await db[DEPTH2_SECTIONS].update_one(
            {"_id": sec["_id"]},
            {"$set": {"is_stored": True, "stored_at": now}},
        )

    # ---- 2. Gather ALL approved data for approved_raw_data ----
    # Get all cards in session
    all_cards = await db[CARDS].find({"session_id": session_id}).to_list(length=100)
    logger.info(f"[V5] Building approved_raw_data for {len(all_cards)} cards, {stored_count} d2 sections stored")

    # For each card, build a record with hierarchical sources
    records_created = []

    for card in all_cards:
        card_id = card.get("card_id", "")
        card_name = card.get("card_name", "Unknown Card")
        card_url = card.get("card_url", "")
        card_network = card.get("card_network", "")
        card_tier = card.get("card_tier", "")

        # Get depth 1 sections for this card (approved only)
        d1_sections = await db[CARD_SECTIONS].find({
            "session_id": session_id,
            "card_id": card_id,
            "is_approved": {"$ne": False},
        }, {"_id": 0}).to_list(length=100)

        # Get depth 2-3 benefit sections linked to this card
        d2_benefits = await db[BENEFIT_SECTIONS].find({
            "session_id": session_id,
            "$or": [
                {"source_card_names": card_name},
                {"source_card_names": {"$size": 0}},
                {"source_card_names": {"$exists": False}},
            ],
        }, {"_id": 0}).to_list(length=500)

        # Also get depth 2-3 sections from DEPTH2_SECTIONS (approved + stored)
        d2_sections = await db[DEPTH2_SECTIONS].find({
            "session_id": session_id,
            "is_approved": True,
            "is_stored": True,
            "$or": [
                {"source_card_names": card_name},
                {"source_card_names": {"$size": 0}},
                {"source_card_names": {"$exists": False}},
            ],
        }, {"_id": 0}).to_list(length=500)

        logger.info(f"[V5] Card '{card_name}': {len(d1_sections)} d1 sections, "
                     f"{len(d2_benefits)} d2 benefits, {len(d2_sections)} d2 sections")

        if not d1_sections and not d2_benefits and not d2_sections:
            continue

        # Build sources list with hierarchical context
        sources = []
        total_chars = 0

        # Depth 1 sources
        for sec in d1_sections:
            context_prefix = _build_context_prefix(
                bank_name=bank_name,
                card_name=card_name,
                depth=1,
                section_name=sec.get("section_name", ""),
                section_type=sec.get("section_type", "general"),
                parent_section=sec.get("parent_section", ""),
                source_url=card_url,
            )
            content = sec.get("content", "")
            contextual_content = f"{context_prefix}\n\n{content}"

            sources.append({
                "url": card_url,
                "title": sec.get("heading_text", sec.get("section_name", "")),
                "source_type": "web",
                "depth": 1,
                "section_name": sec.get("section_name", ""),
                "section_type": sec.get("section_type", "general"),
                "parent_section": sec.get("parent_section", ""),
                "is_expandable": sec.get("is_expandable", False),
                "raw_content": content,
                "cleaned_content": contextual_content,
                "cleaned_content_length": len(contextual_content),
                "context_prefix": context_prefix,
            })
            total_chars += len(contextual_content)

        # Depth 2-3 sources (use d2_sections which have full context)
        seen_d2_urls = set()
        for sec in (d2_sections or d2_benefits):
            src_url = sec.get("source_url", "")
            sec_name = sec.get("section_name", "")
            dedup_key = f"{src_url}|{sec_name}"
            if dedup_key in seen_d2_urls:
                continue
            seen_d2_urls.add(dedup_key)

            context_prefix = _build_context_prefix(
                bank_name=bank_name,
                card_name=card_name,
                depth=sec.get("source_depth", 2),
                section_name=sec_name,
                section_type=sec.get("section_type", "general"),
                parent_section=sec.get("parent_section", ""),
                d1_section=sec.get("source_d1_section", ""),
                source_url=src_url,
            )
            content = sec.get("content", sec.get("benefit_text", ""))
            contextual_content = f"{context_prefix}\n\n{content}"

            sources.append({
                "url": src_url,
                "title": sec.get("heading_text", sec_name),
                "source_type": "web",
                "depth": sec.get("source_depth", 2),
                "section_name": sec_name,
                "section_type": sec.get("section_type", "general"),
                "parent_section": sec.get("parent_section", ""),
                "d1_section": sec.get("source_d1_section", ""),
                "raw_content": content,
                "cleaned_content": contextual_content,
                "cleaned_content_length": len(contextual_content),
                "context_prefix": context_prefix,
            })
            total_chars += len(contextual_content)

        if not sources:
            continue

        # Create approved_raw_data record
        saved_id = str(uuid.uuid4())
        raw_record = {
            "saved_id": saved_id,
            "session_id": session_id,
            "extraction_version": "v5",
            "primary_url": card_url,
            "primary_title": card_name,
            "detected_card_name": card_name,
            "detected_bank": bank_name,
            "bank_key": bank_key,
            "card_network": card_network,
            "card_tier": card_tier,
            "sources": sources,
            "total_sources": len(sources),
            "total_content_length": total_chars,
            "stored_at": now,
            "status": "pending_processing",
            "vector_indexed": False,
        }

        await db.approved_raw_data.insert_one(raw_record)
        records_created.append({
            "saved_id": saved_id,
            "card_name": card_name,
            "sources": len(sources),
            "chars": total_chars,
        })

    # Update session
    await db[SESSIONS].update_one(
        {"session_id": session_id},
        {"$set": {
            "status": "stored",
            "stats.benefits_stored": stored_count,
            "stats.raw_records_created": len(records_created),
            "updated_at": now,
        }},
    )

    logger.info(f"[V5] Stored {stored_count} benefit sections + {len(records_created)} raw records for session {session_id}")

    return {
        "success": True,
        "stored": stored_count,
        "raw_records": records_created,
        "total_raw_records": len(records_created),
    }


def _build_context_prefix(
    bank_name: str = "",
    card_name: str = "",
    depth: int = 1,
    section_name: str = "",
    section_type: str = "",
    parent_section: str = "",
    d1_section: str = "",
    source_url: str = "",
) -> str:
    """
    Build a hierarchical context prefix for vectorization.
    This prefix is prepended to content so the vector embedding captures
    the full context chain.
    
    Example output:
      [Bank: Emirates NBD]
      [Card: Mastercard Platinum Credit Card]
      [Depth 1 Section: More advantages exclusively for you]
      [Depth 2 URL: https://www.emiratesnbd.com/en/offers/golf]
      [Section: Golf Privileges > Participating Courses]
      [Type: golf]
    """
    parts = []
    if bank_name:
        parts.append(f"[Bank: {bank_name}]")
    if card_name:
        parts.append(f"[Card: {card_name}]")
    if d1_section:
        parts.append(f"[Depth 1 Section: {d1_section}]")
    if depth >= 2 and source_url:
        parts.append(f"[Depth {depth} URL: {source_url}]")
    if parent_section:
        parts.append(f"[Section: {parent_section} > {section_name}]")
    elif section_name:
        parts.append(f"[Section: {section_name}]")
    if section_type and section_type != "general":
        parts.append(f"[Type: {section_type}]")
    return '\n'.join(parts)


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


# ============= SYSTEM CLEANUP =============

@router.post("/system/cleanup")
async def system_cleanup(
    clean_v5: bool = True,
    clean_v4: bool = True,
    clean_v2: bool = True,
    clean_approved_raw: bool = True,
    clean_vectors: bool = True,
    clean_pipelines: bool = True,
    clean_redis: bool = True,
):
    """
    Full system cleanup. Drops all data collections, resets ChromaDB, flushes Redis.
    Returns a report of what was deleted.
    """
    db = await get_database()
    report = {}

    # --- V5 collections ---
    if clean_v5:
        v5_collections = [
            "v5_sessions", "v5_cards", "v5_card_sections",
            "v5_benefit_sections", "v5_scraped_urls",
            "v5_discovered_urls", "v5_depth2_sections",
        ]
        for coll in v5_collections:
            count = await db[coll].count_documents({})
            if count > 0:
                await db[coll].delete_many({})
            report[coll] = count

    # --- V4 collections ---
    if clean_v4:
        v4_collections = [
            "v4_sessions", "session_cards", "v4_sources",
            "v4_discovered_urls",
        ]
        for coll in v4_collections:
            try:
                count = await db[coll].count_documents({})
                if count > 0:
                    await db[coll].delete_many({})
                report[coll] = count
            except Exception:
                report[coll] = 0

    # --- V2 collections ---
    if clean_v2:
        v2_collections = [
            "extraction_sessions", "raw_extractions", "extractions",
        ]
        for coll in v2_collections:
            try:
                count = await db[coll].count_documents({})
                if count > 0:
                    await db[coll].delete_many({})
                report[coll] = count
            except Exception:
                report[coll] = 0

    # --- Approved raw data (shared between V4/V5 and DataStore) ---
    if clean_approved_raw:
        count = await db.approved_raw_data.count_documents({})
        if count > 0:
            await db.approved_raw_data.delete_many({})
        report["approved_raw_data"] = count

    # --- Pipeline results ---
    if clean_pipelines:
        pipeline_collections = [
            "pipeline_results", "aggregated_pipeline_results",
            "approved_benefits", "approved_intelligence",
        ]
        for coll in pipeline_collections:
            try:
                count = await db[coll].count_documents({})
                if count > 0:
                    await db[coll].delete_many({})
                report[coll] = count
            except Exception:
                report[coll] = 0

    # --- ChromaDB vectors ---
    if clean_vectors:
        from app.services.vector_store import vector_store
        if vector_store.available:
            vec_count = vector_store._collection.count()
            vector_store.reset()
            report["chromadb_vectors"] = vec_count
        else:
            report["chromadb_vectors"] = "unavailable"

    # --- Redis cache ---
    if clean_redis:
        try:
            from app.core.redis_client import redis_client
            if redis_client and redis_client._pool:
                flushed = await redis_client.flush_all()
                report["redis"] = "flushed" if flushed else "failed"
            else:
                report["redis"] = "not connected"
        except Exception as e:
            report["redis"] = f"error: {str(e)}"

    total_docs = sum(v for v in report.values() if isinstance(v, int))
    logger.info(f"[V5] System cleanup: {total_docs} documents deleted, report: {report}")

    return {
        "success": True,
        "total_documents_deleted": total_docs,
        "report": report,
    }


@router.get("/system/stats")
async def system_stats():
    """Get counts for all collections — used by cleanup UI to show what exists."""
    db = await get_database()
    stats = {}

    all_collections = [
        "v5_sessions", "v5_cards", "v5_card_sections", "v5_benefit_sections",
        "v5_scraped_urls", "v5_discovered_urls", "v5_depth2_sections",
        "v4_sessions", "session_cards",
        "extraction_sessions", "raw_extractions",
        "approved_raw_data",
        "pipeline_results", "aggregated_pipeline_results",
        "approved_benefits", "approved_intelligence",
    ]

    for coll in all_collections:
        try:
            stats[coll] = await db[coll].count_documents({})
        except Exception:
            stats[coll] = 0

    # ChromaDB
    from app.services.vector_store import vector_store
    if vector_store.available:
        stats["chromadb_vectors"] = vector_store._collection.count()
    else:
        stats["chromadb_vectors"] = 0

    # Redis
    try:
        from app.core.redis_client import redis_client
        if redis_client and redis_client._pool:
            info = await redis_client.info()
            stats["redis_keys"] = info.get("db0", {}).get("keys", 0) if isinstance(info.get("db0"), dict) else 0
        else:
            stats["redis_keys"] = 0
    except Exception:
        stats["redis_keys"] = 0

    total = sum(v for v in stats.values() if isinstance(v, int))
    return {"stats": stats, "total_documents": total}
