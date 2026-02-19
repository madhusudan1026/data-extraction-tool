"""
Vector Store Service

Provides semantic search over extracted credit card content using ChromaDB.

Architecture:
  1. INGEST: After raw data approval (Step 7), chunk content into benefit-aware
     segments and embed them via Ollama's nomic-embed-text model.
  2. QUERY (RAG): Accept a natural language question, embed it, retrieve top-K
     relevant chunks, and build an LLM prompt with the retrieved context.
  3. FEED PIPELINES: Instead of sending raw 8K-char pages to pipelines, retrieve
     the most relevant chunks for each benefit type.

Collections:
  - card_benefits: One collection per deployment. Each document is a chunk with
    metadata (bank, card_name, source_url, page_type, benefit_category).
"""

import re
import hashlib
import logging
from typing import List, Dict, Any, Optional

import httpx

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from app.core.config import settings
from app.core.banks import detect_bank_from_url, get_bank_name

logger = logging.getLogger(__name__)


# ======================================================================
# Content Chunker
# ======================================================================

# Benefit category indicators for tagging chunks
CATEGORY_KEYWORDS = {
    "cashback": ["cashback", "cash back", "cash-back", "% back"],
    "lounge": ["lounge", "airport lounge", "priority pass", "lounge key", "diners club lounge"],
    "golf": ["golf", "green fee", "golf course", "tee time"],
    "dining": ["dining", "restaurant", "bogo", "dine", "food"],
    "travel": ["travel", "airline", "flight", "hotel", "booking", "miles"],
    "insurance": ["insurance", "coverage", "protection", "travel insurance", "purchase protection"],
    "rewards": ["rewards", "points", "miles", "earn rate", "redemption"],
    "movie": ["movie", "cinema", "vox", "reel", "novo"],
    "fee": ["annual fee", "joining fee", "interest rate", "late payment", "fee waiver"],
    "eligibility": ["eligibility", "minimum salary", "income requirement", "criteria"],
    "lifestyle": ["valet", "concierge", "lifestyle", "spa", "fitness"],
}


def detect_benefit_category(text: str) -> str:
    """Detect the primary benefit category from text content."""
    text_lower = text.lower()
    scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in kws if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def detect_page_type(url: str, title: str = "") -> str:
    """Classify a source page type from its URL and title."""
    combined = (url + " " + title).lower()
    if any(t in combined for t in ["terms", "condition", "key-fact", "tariff"]):
        return "terms"
    if any(t in combined for t in ["fee", "charge", "schedule"]):
        return "fees"
    if any(t in combined for t in ["benefit", "feature", "offer", "reward"]):
        return "benefits"
    if any(t in combined for t in [".pdf"]):
        return "pdf"
    return "general"


def chunk_content(
    content: str,
    source_url: str = "",
    source_title: str = "",
    card_name: str = "",
    bank_key: str = "",
    min_chunk_size: int = 80,
    max_chunk_size: int = 800,
    overlap: int = 50,
) -> List[Dict[str, Any]]:
    """
    Split content into benefit-aware chunks with metadata.

    Strategy:
    1. Split on double-newlines (paragraph boundaries)
    2. Merge short paragraphs; split long ones
    3. Tag each chunk with detected benefit category
    4. Attach metadata for filtered retrieval

    Returns list of {text, metadata} dicts.
    """
    if not content or len(content.strip()) < min_chunk_size:
        return []

    # Split into paragraphs
    paragraphs = re.split(r'\n{2,}', content)
    paragraphs = [p.strip() for p in paragraphs if len(p.strip()) >= 30]

    chunks: List[Dict[str, Any]] = []
    buffer = ""
    page_type = detect_page_type(source_url, source_title)
    bank_name = get_bank_name(bank_key) if bank_key else ""

    for para in paragraphs:
        if len(buffer) + len(para) + 2 <= max_chunk_size:
            buffer = (buffer + "\n\n" + para).strip() if buffer else para
        else:
            # Flush buffer as a chunk
            if len(buffer) >= min_chunk_size:
                chunk_id = hashlib.md5((source_url + str(len(chunks)) + buffer[:100]).encode()).hexdigest()[:16]
                chunks.append({
                    "id": chunk_id,
                    "text": buffer,
                    "metadata": {
                        "source_url": source_url,
                        "source_title": source_title,
                        "card_name": card_name,
                        "bank_key": bank_key,
                        "bank_name": bank_name,
                        "page_type": page_type,
                        "benefit_category": detect_benefit_category(buffer),
                        "char_count": len(buffer),
                    },
                })
            # Start new buffer
            if len(para) > max_chunk_size:
                # Split long paragraph with overlap
                for i in range(0, len(para), max_chunk_size - overlap):
                    segment = para[i : i + max_chunk_size]
                    if len(segment) >= min_chunk_size:
                        cid = hashlib.md5((source_url + str(len(chunks)) + segment[:100]).encode()).hexdigest()[:16]
                        chunks.append({
                            "id": cid,
                            "text": segment,
                            "metadata": {
                                "source_url": source_url,
                                "source_title": source_title,
                                "card_name": card_name,
                                "bank_key": bank_key,
                                "bank_name": bank_name,
                                "page_type": page_type,
                                "benefit_category": detect_benefit_category(segment),
                                "char_count": len(segment),
                            },
                        })
                buffer = ""
            else:
                buffer = para

    # Flush remaining buffer
    if len(buffer) >= min_chunk_size:
        chunk_id = hashlib.md5((source_url + str(len(chunks)) + buffer[:100]).encode()).hexdigest()[:16]
        chunks.append({
            "id": chunk_id,
            "text": buffer,
            "metadata": {
                "source_url": source_url,
                "source_title": source_title,
                "card_name": card_name,
                "bank_key": bank_key,
                "bank_name": bank_name,
                "page_type": page_type,
                "benefit_category": detect_benefit_category(buffer),
                "char_count": len(buffer),
            },
        })

    logger.info(f"Chunked {len(content)} chars into {len(chunks)} chunks (card={card_name})")
    return chunks


# ======================================================================
# Embedding via Ollama
# ======================================================================

EMBED_MODEL = "nomic-embed-text"


async def embed_texts(texts: List[str], model: str = EMBED_MODEL) -> List[List[float]]:
    """
    Get embeddings from Ollama's /api/embed endpoint.

    Args:
        texts: List of strings to embed.
        model: Embedding model name (default: nomic-embed-text).

    Returns:
        List of embedding vectors (each a list of floats).
    """
    base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    endpoint = f"{base_url}/api/embed"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(endpoint, json={"model": model, "input": texts})
        resp.raise_for_status()
        data = resp.json()

    embeddings = data.get("embeddings", [])
    if len(embeddings) != len(texts):
        logger.warning(f"Expected {len(texts)} embeddings, got {len(embeddings)}")
    return embeddings


# ======================================================================
# Vector Store Service
# ======================================================================

class VectorStoreService:
    """
    Manages the ChromaDB vector store for credit card benefit content.
    """

    COLLECTION_NAME = "card_benefits"

    def __init__(self):
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not installed — vector store disabled")
            self._client = None
            self._collection = None
            return

        persist_dir = getattr(settings, "CHROMA_PERSIST_DIR", "./chroma_data")
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"VectorStore ready: collection={self.COLLECTION_NAME}, "
            f"persist={persist_dir}, docs={self._collection.count()}"
        )

    @property
    def available(self) -> bool:
        return self._collection is not None

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    async def index_approved_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Chunk and embed all sources from an approved raw-data record,
        then upsert into the vector store.

        Uses per-source card_names when available (bank-wide crawls),
        falls back to the record-level card_name.

        Args:
            raw_data: The approved_raw_data MongoDB document.

        Returns:
            Summary dict with counts.
        """
        if not self.available:
            return {"error": "Vector store not available"}

        # Record-level defaults
        record_card_name = raw_data.get("card_name") or raw_data.get("detected_card_name") or ""
        record_card_network = raw_data.get("card_network") or ""
        record_card_tier = raw_data.get("card_tier") or ""
        primary_url = raw_data.get("primary_url") or ""
        bank_key = raw_data.get("bank_key") or ""
        if not bank_key:
            bank_key = detect_bank_from_url(primary_url) or ""

        all_chunks: List[Dict[str, Any]] = []

        for source in raw_data.get("sources", []):
            content = source.get("cleaned_content") or source.get("raw_content") or ""
            if len(content) < 80:
                continue
            
            # Per-source card context (from bank-wide crawl with card_ids)
            src_card_names = source.get("card_names", [])
            src_card_name = src_card_names[0] if src_card_names else record_card_name
            src_card_network = source.get("card_network") or record_card_network
            src_card_tier = source.get("card_tier") or record_card_tier
            src_card_url = source.get("card_url") or primary_url
            
            chunks = chunk_content(
                content,
                source_url=source.get("url", ""),
                source_title=source.get("title", ""),
                card_name=src_card_name,
                bank_key=bank_key,
            )
            # Attach card-level metadata to each chunk
            for chunk in chunks:
                chunk["metadata"]["primary_url"] = src_card_url
                chunk["metadata"]["card_name"] = src_card_name
                if src_card_network:
                    chunk["metadata"]["card_network"] = src_card_network
                if src_card_tier:
                    chunk["metadata"]["card_tier"] = src_card_tier
                # Store all card names for multi-card sources
                if len(src_card_names) > 1:
                    chunk["metadata"]["all_card_names"] = "|".join(src_card_names)
            all_chunks.extend(chunks)

        if not all_chunks:
            return {"chunks": 0, "card_name": record_card_name}

        # Deduplicate chunks by ID (safety net)
        seen_ids = set()
        unique_chunks = []
        for chunk in all_chunks:
            if chunk["id"] not in seen_ids:
                seen_ids.add(chunk["id"])
                unique_chunks.append(chunk)
        if len(unique_chunks) < len(all_chunks):
            logger.warning(f"Deduped {len(all_chunks) - len(unique_chunks)} duplicate chunk IDs")
        all_chunks = unique_chunks

        # Embed in batches of 64
        batch_size = 64
        total_embedded = 0

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]
            try:
                embeddings = await embed_texts(texts)
            except Exception as exc:
                logger.error(f"Embedding batch {i} failed: {exc}")
                continue

            self._collection.upsert(
                ids=[c["id"] for c in batch],
                documents=texts,
                embeddings=embeddings,
                metadatas=[c["metadata"] for c in batch],
            )
            total_embedded += len(batch)

        logger.info(f"Indexed {total_embedded} chunks for card={record_card_name}")
        return {
            "chunks": total_embedded,
            "card_name": record_card_name,
            "bank_key": bank_key,
            "total_docs": self._collection.count(),
        }

    # ------------------------------------------------------------------
    # Query (RAG retrieval)
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        *,
        n_results: int = 10,
        bank_key: Optional[str] = None,
        card_name: Optional[str] = None,
        benefit_category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most relevant chunks for a natural-language question.

        Args:
            question: The user's question.
            n_results: Number of chunks to return.
            bank_key: Optional filter by bank.
            card_name: Optional filter by card.
            benefit_category: Optional filter by category.

        Returns:
            List of {text, metadata, distance} dicts, sorted by relevance.
        """
        if not self.available:
            return []

        # Build where clause
        where_clauses = []
        if bank_key:
            where_clauses.append({"bank_key": bank_key})
        if card_name:
            where_clauses.append({"card_name": card_name})
        if benefit_category:
            where_clauses.append({"benefit_category": benefit_category})

        where = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        # Embed the question
        try:
            q_embeddings = await embed_texts([question])
        except Exception as exc:
            logger.error(f"Failed to embed query: {exc}")
            return []

        results = self._collection.query(
            query_embeddings=q_embeddings,
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # Flatten results
        hits: List[Dict[str, Any]] = []
        for doc, meta, dist in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0],
        ):
            hits.append({"text": doc, "metadata": meta, "distance": dist})

        return hits

    # ------------------------------------------------------------------
    # Feed pipelines: retrieve chunks for a specific benefit type
    # ------------------------------------------------------------------

    async def get_pipeline_context(
        self,
        benefit_type: str,
        card_name: str,
        bank_key: str = "",
        n_results: int = 15,
    ) -> str:
        """
        Retrieve and concatenate the most relevant chunks for a pipeline.

        Instead of sending 8K chars of raw page text, this provides
        pre-filtered, benefit-specific content for better LLM extraction.
        """
        hits = await self.query(
            question=f"{benefit_type} benefits conditions details",
            n_results=n_results,
            bank_key=bank_key or None,
            card_name=card_name or None,
            benefit_category=benefit_type if benefit_type != "generic" else None,
        )
        if not hits:
            return ""
        return "\n\n---\n\n".join(h["text"] for h in hits)

    # ------------------------------------------------------------------
    # Admin helpers
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Total documents in the collection."""
        return self._collection.count() if self.available else 0

    def delete_card(self, card_name: str) -> int:
        """Delete all chunks for a specific card."""
        if not self.available:
            return 0
        # ChromaDB delete by metadata filter
        self._collection.delete(where={"card_name": card_name})
        logger.info(f"Deleted chunks for card={card_name}")
        return 1

    def reset(self) -> None:
        """Delete and recreate the collection."""
        if not self.available:
            return
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector store reset")

    def stats(self) -> Dict[str, Any]:
        """Return collection statistics."""
        if not self.available:
            return {"available": False}
        return {
            "available": True,
            "collection": self.COLLECTION_NAME,
            "total_documents": self._collection.count(),
        }


# ======================================================================
# Global singleton
# ======================================================================
vector_store = VectorStoreService()
