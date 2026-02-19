"""
Vector Store API Routes

Provides endpoints for:
- Indexing approved raw data into the vector store
- Semantic search / RAG queries over indexed content
- Admin operations (stats, reset, delete)
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel, Field

from app.core.database import get_database
from app.core.config import settings
from app.services.vector_store import vector_store
from app.services.ollama_client import ollama_client
from app.utils.logger import logger

router = APIRouter(prefix="/api/v4/vector", tags=["Vector Store"])


# ============= Request/Response Models =============

class IndexRequest(BaseModel):
    saved_id: str = Field(..., description="The saved_id from approved_raw_data")


class QueryRequest(BaseModel):
    question: str = Field(..., description="Natural language question")
    n_results: int = Field(10, ge=1, le=50, description="Number of chunks to retrieve")
    bank_key: Optional[str] = Field(None, description="Filter by bank")
    card_name: Optional[str] = Field(None, description="Filter by card")
    benefit_category: Optional[str] = Field(None, description="Filter by category")


class RAGRequest(BaseModel):
    question: str = Field(..., description="Natural language question about card benefits")
    bank_key: Optional[str] = Field(None, description="Filter by bank")
    card_name: Optional[str] = Field(None, description="Filter by card")
    n_chunks: int = Field(10, ge=1, le=30, description="Number of context chunks")


# ============= Index Endpoints =============

@router.post("/index")
async def index_approved_data(request: IndexRequest):
    """
    Index an approved_raw_data record into the vector store.
    
    Chunks the content, embeds via Ollama's nomic-embed-text model,
    and stores in ChromaDB for semantic retrieval.
    """
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available (ChromaDB not installed)")
    
    db = await get_database()
    raw_data = await db.approved_raw_data.find_one({"saved_id": request.saved_id})
    
    if not raw_data:
        raise HTTPException(status_code=404, detail=f"Approved raw data not found: {request.saved_id}")
    
    try:
        result = await vector_store.index_approved_data(raw_data)
        
        # Update the raw data record to mark as indexed
        await db.approved_raw_data.update_one(
            {"saved_id": request.saved_id},
            {"$set": {"vector_indexed": True, "vector_chunks": result.get("chunks", 0)}}
        )
        
        return {
            "success": True,
            "saved_id": request.saved_id,
            **result,
        }
    except Exception as e:
        logger.error(f"Indexing failed for {request.saved_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/index-session/{session_id}")
async def index_session(session_id: str):
    """
    Index the approved raw data for a session.
    Convenience wrapper around /index using the session's saved_id.
    """
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    db = await get_database()
    session = await db.extraction_sessions.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    saved_id = session.get("approved_raw_id")
    if not saved_id:
        raise HTTPException(status_code=400, detail="Session has no approved raw data yet")
    
    raw_data = await db.approved_raw_data.find_one({"saved_id": saved_id})
    if not raw_data:
        raise HTTPException(status_code=404, detail=f"Approved raw data not found: {saved_id}")
    
    result = await vector_store.index_approved_data(raw_data)
    
    await db.approved_raw_data.update_one(
        {"saved_id": saved_id},
        {"$set": {"vector_indexed": True, "vector_chunks": result.get("chunks", 0)}}
    )
    
    return {"success": True, "saved_id": saved_id, **result}


# ============= Query Endpoints =============

@router.post("/search")
async def search_chunks(request: QueryRequest):
    """
    Semantic search over indexed content.
    
    Returns the most relevant chunks matching the question,
    optionally filtered by bank, card, or benefit category.
    """
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    hits = await vector_store.query(
        question=request.question,
        n_results=request.n_results,
        bank_key=request.bank_key,
        card_name=request.card_name,
        benefit_category=request.benefit_category,
    )
    
    return {
        "question": request.question,
        "results": hits,
        "count": len(hits),
    }


@router.post("/ask")
async def rag_query(request: RAGRequest):
    """
    RAG (Retrieval Augmented Generation) endpoint.
    
    1. Retrieves relevant chunks from the vector store
    2. Builds a context-aware prompt
    3. Sends to LLM for a synthesized answer
    
    This enables natural language querying like:
    - "Compare golf benefits across Emirates NBD cards"
    - "What cashback does the Visa Infinite offer on groceries?"
    - "Which cards have free airport lounge access?"
    """
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    # Step 1: Retrieve relevant chunks
    hits = await vector_store.query(
        question=request.question,
        n_results=request.n_chunks,
        bank_key=request.bank_key,
        card_name=request.card_name,
    )
    
    if not hits:
        return {
            "question": request.question,
            "answer": "No relevant information found in the indexed data. Please index some card data first.",
            "sources": [],
            "chunks_used": 0,
        }
    
    # Step 2: Build context from retrieved chunks
    context_parts = []
    sources_seen = set()
    for h in hits:
        context_parts.append(h["text"])
        src_url = h.get("metadata", {}).get("source_url", "")
        if src_url:
            sources_seen.add(src_url)
    
    context = "\n\n---\n\n".join(context_parts)
    
    # Step 3: Build RAG prompt
    prompt = f"""You are a UAE credit card benefits expert. Answer the question using ONLY the context provided below.
If the answer is not in the context, say "I don't have enough information to answer that."

CONTEXT:
{context}

QUESTION: {request.question}

Provide a clear, structured answer. Include specific values (percentages, amounts, limits) when available.
If comparing cards, use a clear comparison format.

ANSWER:"""
    
    # Step 4: Call LLM
    answer = await ollama_client.generate(
        prompt,
        temperature=0.1,
        num_predict=2000,
        timeout=120,
        caller="rag_query",
    )
    
    if not answer:
        answer = "Failed to generate an answer. Please try again."
    
    return {
        "question": request.question,
        "answer": answer,
        "sources": list(sources_seen),
        "chunks_used": len(hits),
    }


# ============= Admin Endpoints =============

# ---- Data Store & Vectorization Endpoints ----

@router.post("/preview-chunks")
async def preview_chunks(request: IndexRequest):
    """
    Preview how approved raw data will be chunked before indexing.
    Returns chunks with full metadata for user review.
    """
    from app.services.vector_store import chunk_content
    from app.core.banks import detect_bank_from_url
    
    db = await get_database()
    raw_data = await db.approved_raw_data.find_one({"saved_id": request.saved_id})
    if not raw_data:
        raise HTTPException(status_code=404, detail=f"Approved raw data not found: {request.saved_id}")
    
    card_name = raw_data.get("detected_card_name") or raw_data.get("card_name") or "Unknown"
    card_network = raw_data.get("card_network")
    card_tier = raw_data.get("card_tier")
    bank_key = raw_data.get("bank_key") or detect_bank_from_url(raw_data.get("primary_url", "")) or ""
    bank_name = raw_data.get("detected_bank", "")
    
    primary_url = raw_data.get("primary_url", "")
    
    all_chunks = []
    source_summaries = []
    
    for src_idx, source in enumerate(raw_data.get("sources", [])):
        content = source.get("cleaned_content") or source.get("raw_content") or ""
        if len(content) < 80:
            continue
        
        chunks = chunk_content(
            content,
            source_url=source.get("url", ""),
            source_title=source.get("title", ""),
            card_name=card_name,
            bank_key=bank_key,
        )
        
        for chunk in chunks:
            chunk["source_index"] = src_idx
            chunk["source_type"] = source.get("source_type", "web")
            chunk["source_depth"] = source.get("depth", 0)
            chunk["metadata"]["primary_url"] = primary_url
            if card_network:
                chunk["metadata"]["card_network"] = card_network
            if card_tier:
                chunk["metadata"]["card_tier"] = card_tier
        
        all_chunks.extend(chunks)
        source_summaries.append({
            "source_index": src_idx,
            "url": source.get("url", ""),
            "title": source.get("title", ""),
            "source_type": source.get("source_type", "web"),
            "depth": source.get("depth", 0),
            "content_length": len(content),
            "chunks_generated": len(chunks),
        })
    
    category_counts = {}
    for chunk in all_chunks:
        cat = chunk["metadata"].get("benefit_category", "general")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    return {
        "success": True,
        "saved_id": request.saved_id,
        "card_name": card_name,
        "card_network": card_network,
        "card_tier": card_tier,
        "bank_name": bank_name,
        "total_chunks": len(all_chunks),
        "total_sources": len(source_summaries),
        "category_breakdown": category_counts,
        "sources": source_summaries,
        "chunks": [
            {
                "chunk_index": i,
                "id": c["id"],
                "text": c["text"],
                "text_length": len(c["text"]),
                "source_index": c.get("source_index"),
                "source_type": c.get("source_type"),
                "source_depth": c.get("source_depth"),
                "metadata": c["metadata"],
            }
            for i, c in enumerate(all_chunks)
        ],
        "vector_store_available": vector_store.available,
    }


@router.post("/index-record")
async def index_record(request: IndexRequest):
    """
    Index an approved_raw_data record into the vector store.
    Same as /index but with clearer naming for the Data Store flow.
    """
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available. Install chromadb and run 'ollama pull nomic-embed-text'.")
    
    db = await get_database()
    raw_data = await db.approved_raw_data.find_one({"saved_id": request.saved_id})
    if not raw_data:
        raise HTTPException(status_code=404, detail=f"Approved raw data not found: {request.saved_id}")
    
    try:
        from datetime import datetime
        result = await vector_store.index_approved_data(raw_data)
        vector_chunks = result.get("chunks", 0)
        
        await db.approved_raw_data.update_one(
            {"saved_id": request.saved_id},
            {"$set": {
                "vector_indexed": True,
                "vector_chunks": vector_chunks,
                "vector_indexed_at": datetime.utcnow()
            }}
        )
        
        return {
            "success": True,
            "saved_id": request.saved_id,
            "vector_chunks": vector_chunks,
            "card_name": raw_data.get("detected_card_name", "Unknown"),
        }
    except Exception as e:
        logger.error(f"Indexing failed for {request.saved_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/record-data/{saved_id}")
async def get_record_vector_data(saved_id: str, limit: int = 200):
    """
    View indexed vector data for a specific approved_raw_data record.
    Returns chunks grouped by source with full metadata.
    """
    db = await get_database()
    raw_data = await db.approved_raw_data.find_one({"saved_id": saved_id})
    if not raw_data:
        raise HTTPException(status_code=404, detail="Approved raw data not found")
    
    if not vector_store.available:
        return {"success": False, "error": "Vector store not available"}
    
    card_name = raw_data.get("detected_card_name") or raw_data.get("card_name") or ""
    
    try:
        collection = vector_store._collection
        where_filter = {"card_name": card_name} if card_name else None
        results = collection.get(
            where=where_filter,
            limit=limit,
            include=["documents", "metadatas"],
        )
    except Exception as e:
        logger.error(f"Error querying vector store: {e}")
        return {"success": False, "error": str(e)}
    
    chunks_by_source = {}
    all_chunks = []
    
    for doc_id, text, meta in zip(
        results.get("ids", []),
        results.get("documents", []),
        results.get("metadatas", []),
    ):
        chunk_data = {
            "chunk_id": doc_id,
            "text": text,
            "text_length": len(text) if text else 0,
            "source_url": meta.get("source_url", ""),
            "source_title": meta.get("source_title", ""),
            "primary_url": meta.get("primary_url", ""),
            "card_name": meta.get("card_name", ""),
            "card_network": meta.get("card_network", ""),
            "card_tier": meta.get("card_tier", ""),
            "bank_name": meta.get("bank_name", ""),
            "bank_key": meta.get("bank_key", ""),
            "page_type": meta.get("page_type", ""),
            "benefit_category": meta.get("benefit_category", "general"),
            "char_count": meta.get("char_count", 0),
        }
        all_chunks.append(chunk_data)
        
        src_url = meta.get("source_url", "unknown")
        if src_url not in chunks_by_source:
            chunks_by_source[src_url] = {
                "source_url": src_url,
                "source_title": meta.get("source_title", ""),
                "page_type": meta.get("page_type", ""),
                "chunks": [],
            }
        chunks_by_source[src_url]["chunks"].append(chunk_data)
    
    category_counts = {}
    for chunk in all_chunks:
        cat = chunk["benefit_category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    return {
        "success": True,
        "saved_id": saved_id,
        "card_name": card_name,
        "card_network": raw_data.get("card_network"),
        "card_tier": raw_data.get("card_tier"),
        "bank_name": raw_data.get("detected_bank", ""),
        "total_chunks": len(all_chunks),
        "total_sources": len(chunks_by_source),
        "category_breakdown": category_counts,
        "sources": list(chunks_by_source.values()),
    }


@router.get("/stats")
async def vector_stats():
    """Get vector store statistics."""
    return vector_store.stats()


# ============= PIPELINE EXECUTION ENDPOINTS =============

@router.get("/banks")
async def list_banks_with_cards():
    """
    List all banks and their discovered cards from session_cards collection.
    Groups cards by bank (from session metadata).
    """
    db = await get_database()
    
    # Get all sessions with bank info
    sessions = await db.v4_sessions.find(
        {"bank_name": {"$ne": None, "$ne": ""}},
        {"session_id": 1, "bank_key": 1, "bank_name": 1}
    ).to_list(length=500)
    
    session_bank_map = {}
    for s in sessions:
        session_bank_map[s["session_id"]] = {
            "bank_key": s.get("bank_key", ""),
            "bank_name": s.get("bank_name", ""),
        }
    
    # Get all cards from session_cards
    all_cards = await db.session_cards.find({}).to_list(length=2000)
    
    # Group by bank
    banks = {}
    for card in all_cards:
        sid = card.get("session_id", "")
        bank_info = session_bank_map.get(sid, {})
        bank_name = bank_info.get("bank_name", "Unknown Bank")
        bank_key = bank_info.get("bank_key", "")
        
        if not bank_name or bank_name == "Unknown Bank":
            # Try to detect from card URL
            from app.core.banks import detect_bank_from_url, get_bank_name
            bk = detect_bank_from_url(card.get("card_url", ""))
            if bk:
                bank_key = bk
                bank_name = get_bank_name(bk) or bank_name
        
        if bank_name not in banks:
            banks[bank_name] = {
                "bank_name": bank_name,
                "bank_key": bank_key,
                "cards": [],
            }
        
        # Check if this card name already exists (dedup across sessions)
        existing_names = [c["card_name"] for c in banks[bank_name]["cards"]]
        if card["card_name"] not in existing_names:
            banks[bank_name]["cards"].append({
                "card_id": card["card_id"],
                "card_name": card["card_name"],
                "card_url": card.get("card_url", ""),
                "card_network": card.get("card_network", ""),
                "card_tier": card.get("card_tier", ""),
                "card_image": card.get("card_image"),
                "session_id": sid,
            })
    
    return {
        "success": True,
        "banks": sorted(banks.values(), key=lambda b: b["bank_name"]),
        "total_banks": len(banks),
        "total_cards": sum(len(b["cards"]) for b in banks.values()),
    }


@router.get("/card-chunks/{card_name}")
async def get_card_chunks(
    card_name: str,
    bank_key: Optional[str] = None,
    card_url: Optional[str] = None,
    limit: int = 500,
):
    """
    Find ALL vector chunks related to a specific card.
    
    Uses multiple strategies since card_name in session_cards may differ
    from card_name in chunk metadata (which comes from approved_raw_data):
    
    1. Exact card_name match in metadata
    2. Partial card_name match (substring search in card_name metadata)
    3. All bank chunks (by bank_key) — bank-wide crawls store under one card name
    4. URL-based match (primary_url or source_url contains the card URL)
    5. Text-based match (chunk text mentions card name keywords)
    """
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    db = await get_database()
    collection = vector_store._collection
    total_in_store = collection.count()
    
    all_chunks = []
    seen_ids = set()
    match_sources = {}  # Track how each chunk was found
    
    def _add_chunks(results, source_label):
        added = 0
        for doc_id, text, meta in zip(
            results.get("ids", []),
            results.get("documents", []),
            results.get("metadatas", []),
        ):
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                chunk = _build_chunk_data(doc_id, text, meta)
                chunk["match_source"] = source_label
                all_chunks.append(chunk)
                added += 1
        return added
    
    # 1. Exact card_name match in metadata
    try:
        results = collection.get(where={"card_name": card_name}, limit=limit, include=["documents", "metadatas"])
        n = _add_chunks(results, "exact_card_name")
        logger.info(f"[Pipeline] Strategy 1 - Exact card_name '{card_name}': {n} chunks")
    except Exception as e:
        logger.warning(f"[Pipeline] Strategy 1 failed: {e}")
    
    # 2. Check all_card_names field (multi-card sources store pipe-delimited names)
    #    ChromaDB doesn't support $contains on strings, so get bank chunks and filter
    if bank_key:
        try:
            results = collection.get(where={"bank_key": bank_key}, limit=limit, include=["documents", "metadatas"])
            card_name_lower = card_name.lower()
            added = 0
            for doc_id, text, meta in zip(
                results.get("ids", []),
                results.get("documents", []),
                results.get("metadatas", []),
            ):
                if doc_id in seen_ids:
                    continue
                # Check all_card_names field
                all_names = (meta.get("all_card_names", "") or "").lower()
                meta_card = (meta.get("card_name", "") or "").lower()
                if card_name_lower in all_names or card_name_lower == meta_card:
                    seen_ids.add(doc_id)
                    chunk = _build_chunk_data(doc_id, text, meta)
                    chunk["match_source"] = "bank_card_names"
                    all_chunks.append(chunk)
                    added += 1
            logger.info(f"[Pipeline] Strategy 2 - Bank '{bank_key}' card_names match: {added} from {len(results.get('ids', []))} bank chunks")
        except Exception as e:
            logger.warning(f"[Pipeline] Strategy 2 failed: {e}")
    
    # 3. URL-based: match chunks by card_url in source_url or primary_url
    if card_url:
        try:
            where_filter = {"bank_key": bank_key} if bank_key else None
            get_limit = limit if bank_key else total_in_store
            results = collection.get(where=where_filter, limit=get_limit, include=["documents", "metadatas"])
            card_url_clean = card_url.rstrip('/').lower()
            added = 0
            for doc_id, text, meta in zip(
                results.get("ids", []),
                results.get("documents", []),
                results.get("metadatas", []),
            ):
                if doc_id in seen_ids:
                    continue
                src_url = (meta.get("source_url", "") or "").rstrip('/').lower()
                pri_url = (meta.get("primary_url", "") or "").rstrip('/').lower()
                if card_url_clean in src_url or card_url_clean in pri_url or src_url in card_url_clean:
                    seen_ids.add(doc_id)
                    chunk = _build_chunk_data(doc_id, text, meta)
                    chunk["match_source"] = "url_match"
                    all_chunks.append(chunk)
                    added += 1
            logger.info(f"[Pipeline] Strategy 3 - URL match '{card_url[:60]}': {added} chunks")
        except Exception as e:
            logger.warning(f"[Pipeline] Strategy 3 failed: {e}")
    
    # 4. Text-based: search chunk text for card name keywords
    if len(all_chunks) == 0:
        try:
            # Get all chunks and filter by URL
            results = collection.get(limit=total_in_store, include=["documents", "metadatas"])
            card_url_clean = card_url.rstrip('/').lower()
            added = 0
            for doc_id, text, meta in zip(
                results.get("ids", []),
                results.get("documents", []),
                results.get("metadatas", []),
            ):
                if doc_id in seen_ids:
                    continue
                src_url = (meta.get("source_url", "") or "").rstrip('/').lower()
                pri_url = (meta.get("primary_url", "") or "").rstrip('/').lower()
                if card_url_clean in src_url or card_url_clean in pri_url or src_url in card_url_clean:
                    seen_ids.add(doc_id)
                    chunk = _build_chunk_data(doc_id, text, meta)
                    chunk["match_source"] = "url_match"
                    all_chunks.append(chunk)
                    added += 1
            logger.info(f"[Pipeline] Strategy 3 - URL match '{card_url[:50]}': {added} chunks")
        except Exception as e:
            logger.warning(f"[Pipeline] Strategy 3 failed: {e}")
    
    # 4. If still nothing, try text-based: search all chunks for card name keywords
    if len(all_chunks) == 0:
        try:
            results = collection.get(limit=total_in_store, include=["documents", "metadatas"])
            # Build search terms from card name
            card_name_lower = card_name.lower()
            # Also try individual significant words (skip common words)
            stop_words = {'credit', 'card', 'cards', 'the', 'a', 'and', 'or', 'for', 'of', 'in', 'on', 'to'}
            name_words = [w.lower() for w in card_name.split() if w.lower() not in stop_words and len(w) > 2]
            
            added = 0
            for doc_id, text, meta in zip(
                results.get("ids", []),
                results.get("documents", []),
                results.get("metadatas", []),
            ):
                if doc_id in seen_ids:
                    continue
                text_lower = (text or "").lower()
                meta_card = (meta.get("card_name", "") or "").lower()
                
                # Match if: full card name in text, OR card name in metadata, OR 2+ significant words match
                if (card_name_lower in text_lower or
                    card_name_lower in meta_card or
                    (len(name_words) >= 2 and sum(1 for w in name_words if w in text_lower) >= 2) or
                    (len(name_words) >= 2 and sum(1 for w in name_words if w in meta_card) >= 2)):
                    seen_ids.add(doc_id)
                    chunk = _build_chunk_data(doc_id, text, meta)
                    chunk["match_source"] = "text_match"
                    all_chunks.append(chunk)
                    added += 1
            logger.info(f"[Pipeline] Strategy 4 - Text match for '{card_name}': {added} chunks")
        except Exception as e:
            logger.warning(f"[Pipeline] Strategy 4 failed: {e}")
    
    logger.info(f"[Pipeline] TOTAL chunks for '{card_name}': {len(all_chunks)}")
    
    # Build category breakdown
    category_counts = {}
    chunks_by_category = {}
    for chunk in all_chunks:
        cat = chunk["benefit_category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if cat not in chunks_by_category:
            chunks_by_category[cat] = []
        chunks_by_category[cat].append(chunk)
    
    # Group by source
    chunks_by_source = {}
    for chunk in all_chunks:
        src = chunk["source_url"] or "unknown"
        if src not in chunks_by_source:
            chunks_by_source[src] = {
                "source_url": src,
                "source_title": chunk.get("source_title", ""),
                "page_type": chunk.get("page_type", ""),
                "chunk_count": 0,
            }
        chunks_by_source[src]["chunk_count"] += 1
    
    # Match source stats
    match_stats = {}
    for chunk in all_chunks:
        ms = chunk.get("match_source", "unknown")
        match_stats[ms] = match_stats.get(ms, 0) + 1
    
    return {
        "success": True,
        "card_name": card_name,
        "bank_key": bank_key or "",
        "card_url": card_url or "",
        "total_chunks": len(all_chunks),
        "total_sources": len(chunks_by_source),
        "category_breakdown": category_counts,
        "match_stats": match_stats,
        "categories": {
            cat: chunks for cat, chunks in sorted(chunks_by_category.items(), key=lambda x: -len(x[1]))
        },
        "sources": list(chunks_by_source.values()),
        "chunks": all_chunks,
    }


@router.get("/debug/all-metadata")
async def debug_all_metadata(limit: int = 50):
    """
    DEBUG: Show all unique card_names, bank_keys, and sample metadata in ChromaDB.
    Use this to diagnose card_name mismatches.
    """
    if not vector_store.available:
        return {"error": "Vector store not available"}
    
    collection = vector_store._collection
    total = collection.count()
    
    results = collection.get(limit=min(total, limit), include=["metadatas"])
    
    card_names = {}
    bank_keys = {}
    primary_urls = {}
    
    for meta in results.get("metadatas", []):
        cn = meta.get("card_name", "")
        bk = meta.get("bank_key", "")
        pu = meta.get("primary_url", "")
        
        card_names[cn] = card_names.get(cn, 0) + 1
        if bk:
            bank_keys[bk] = bank_keys.get(bk, 0) + 1
        if pu:
            primary_urls[pu] = primary_urls.get(pu, 0) + 1
    
    return {
        "total_chunks": total,
        "sampled": len(results.get("ids", [])),
        "unique_card_names": dict(sorted(card_names.items(), key=lambda x: -x[1])),
        "unique_bank_keys": dict(sorted(bank_keys.items(), key=lambda x: -x[1])),
        "unique_primary_urls": dict(sorted(primary_urls.items(), key=lambda x: -x[1])),
        "sample_metadata": results.get("metadatas", [])[:5],
    }


def _build_chunk_data(doc_id: str, text: str, meta: dict) -> dict:
    """Build standardized chunk data dict from ChromaDB results."""
    return {
        "chunk_id": doc_id,
        "text": text,
        "text_length": len(text) if text else 0,
        "source_url": meta.get("source_url", ""),
        "source_title": meta.get("source_title", ""),
        "primary_url": meta.get("primary_url", ""),
        "card_name": meta.get("card_name", ""),
        "card_network": meta.get("card_network", ""),
        "card_tier": meta.get("card_tier", ""),
        "bank_name": meta.get("bank_name", ""),
        "bank_key": meta.get("bank_key", ""),
        "page_type": meta.get("page_type", ""),
        "benefit_category": meta.get("benefit_category", "general"),
        "char_count": meta.get("char_count", 0),
    }


@router.post("/reset")
async def reset_vector_store():
    """Reset (delete and recreate) the vector store collection."""
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    vector_store.reset()
    return {"success": True, "message": "Vector store reset successfully"}


@router.delete("/card/{card_name}")
async def delete_card_vectors(card_name: str):
    """Delete all indexed chunks for a specific card."""
    if not vector_store.available:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    vector_store.delete_card(card_name)
    return {"success": True, "card_name": card_name, "message": f"Deleted vectors for {card_name}"}


@router.get("/health")
async def vector_health():
    """Check vector store health and embedding model availability."""
    health = {
        "chromadb_available": vector_store.available,
        "total_documents": vector_store.count(),
    }
    
    # Test embedding model
    try:
        from app.services.vector_store import embed_texts
        test_embed = await embed_texts(["test"])
        health["embed_model"] = settings.EMBED_MODEL
        health["embed_dimensions"] = len(test_embed[0]) if test_embed else 0
        health["embed_available"] = True
    except Exception as e:
        health["embed_available"] = False
        health["embed_error"] = str(e)
    
    return health
