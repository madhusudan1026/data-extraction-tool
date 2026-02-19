"""
Raw Extraction Storage Service

Handles storing all extracted content to MongoDB before LLM processing.
This preserves the complete extraction data for analysis and debugging.
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class RawExtractionStorageService:
    """Service for storing raw extraction data to MongoDB."""
    
    # Pattern definitions for detecting credit card information
    DETECTION_PATTERNS = {
        "annual_fee": [
            r'annual\s*fee[:\s]*(?:aed|usd|eur)?\s*[\d,]+(?:\.\d{2})?',
            r'(?:aed|usd)\s*[\d,]+(?:\.\d{2})?\s*(?:per\s*year|annually|annual)',
            r'yearly\s*fee[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'annual\s*fee\s*(?:waived|free|nil|zero)',
        ],
        "joining_fee": [
            r'joining\s*fee[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'one[- ]time\s*fee[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'joining\s*fee\s*(?:waived|free|nil)',
        ],
        "minimum_salary": [
            r'minimum\s*(?:monthly\s*)?salary[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'salary\s*(?:requirement|criteria)[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'(?:aed|usd)\s*[\d,]+\s*(?:minimum\s*)?salary',
            r'income\s*(?:requirement)?[:\s]*(?:aed|usd)?\s*[\d,]+',
        ],
        "cashback": [
            r'(\d+(?:\.\d+)?)\s*%\s*cash\s*back',
            r'cash\s*back[:\s]*(\d+(?:\.\d+)?)\s*%',
            r'(\d+(?:\.\d+)?)\s*%\s*(?:on|for)\s*(?:all|every|grocery|fuel|dining)',
            r'earn\s*(\d+(?:\.\d+)?)\s*%\s*(?:back|cashback)',
        ],
        "reward_points": [
            r'(\d+)\s*(?:reward\s*)?points?\s*(?:per|for\s*every)\s*(?:aed|usd)?\s*[\d,]*',
            r'earn\s*(\d+)\s*points?\s*(?:per|on)',
            r'(\d+)x?\s*points?\s*(?:on|for)',
            r'plus\s*points',
        ],
        "lounge_access": [
            r'(?:unlimited|free|complimentary)\s*(?:airport\s*)?lounge\s*access',
            r'lounge\s*(?:access|visits?)[:\s]*(?:unlimited|\d+)',
            r'(\d+)\s*(?:free\s*)?lounge\s*visits?',
            r'airport\s*lounge\s*(?:access|entry)',
            r'priority\s*pass',
            r'lounge\s*key',
        ],
        "golf_access": [
            r'(?:complimentary|free)\s*golf',
            r'golf\s*(?:access|privileges?)',
            r'(\d+)\s*(?:free\s*)?(?:rounds?\s*of\s*)?golf',
        ],
        "valet_parking": [
            r'(?:free|complimentary)\s*valet\s*parking',
            r'valet\s*parking\s*(?:service)?',
            r'(\d+)\s*(?:free\s*)?valet',
        ],
        "cinema_offers": [
            r'(?:buy\s*\d+\s*get\s*\d+|bogo)\s*(?:free\s*)?(?:movie|cinema|ticket)',
            r'(?:free|complimentary)\s*(?:movie\s*)?tickets?',
            r'cinema\s*(?:discount|offer)',
            r'(\d+)\s*(?:free\s*)?movie\s*tickets?',
        ],
        "travel_insurance": [
            r'travel\s*insurance\s*(?:up\s*to|coverage)?[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'(?:aed|usd)\s*[\d,]+\s*travel\s*insurance',
            r'complimentary\s*travel\s*insurance',
        ],
        "purchase_protection": [
            r'purchase\s*protection\s*(?:up\s*to)?[:\s]*(?:aed|usd)?\s*[\d,]+',
            r'buyer\s*protection',
        ],
        "interest_rate": [
            r'(?:interest|apr)\s*(?:rate)?[:\s]*(\d+(?:\.\d+)?)\s*%',
            r'(\d+(?:\.\d+)?)\s*%\s*(?:per\s*(?:month|annum)|p\.?[am]\.?|interest)',
        ],
        "credit_limit": [
            r'credit\s*limit[:\s]*(?:up\s*to\s*)?(?:aed|usd)?\s*[\d,]+',
            r'(?:maximum|max)\s*(?:credit\s*)?limit[:\s]*(?:aed|usd)?\s*[\d,]+',
        ],
        "supplementary_card": [
            r'supplementary\s*card[:\s]*(?:free|aed|usd)?\s*[\d,]*',
            r'(\d+)\s*(?:free\s*)?supplementary\s*cards?',
            r'add[- ]on\s*card',
        ],
        "dining_offers": [
            r'(?:up\s*to\s*)?(\d+)\s*%\s*(?:off|discount)\s*(?:on\s*)?dining',
            r'dining\s*(?:discount|offer|benefit)',
            r'restaurant\s*(?:discount|offer)',
        ],
        "fuel_surcharge": [
            r'fuel\s*surcharge\s*waiver',
            r'(\d+(?:\.\d+)?)\s*%\s*fuel\s*surcharge\s*waiver',
            r'no\s*fuel\s*surcharge',
        ],
        "airport_transfer": [
            r'(?:free|complimentary)\s*airport\s*transfer',
            r'airport\s*(?:pickup|drop|transfer)',
            r'limousine\s*(?:service|transfer)',
        ],
        "concierge": [
            r'(?:24\/?7\s*)?concierge\s*(?:service)?',
            r'lifestyle\s*concierge',
            r'personal\s*(?:assistant|concierge)',
        ],
    }
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.raw_extractions
    
    async def create_extraction(
        self,
        primary_url: str,
        keywords: List[str],
        keyword_source: str = "default",
        card_name_hint: Optional[str] = None,
        bank_hint: Optional[str] = None
    ) -> str:
        """Create a new raw extraction record."""
        import uuid
        
        extraction_id = str(uuid.uuid4())
        
        doc = {
            "extraction_id": extraction_id,
            "primary_url": primary_url,
            "primary_title": None,
            "detected_card_name": card_name_hint,
            "detected_bank": bank_hint,
            "sources": [],
            "total_sources": 0,
            "successful_sources": 0,
            "failed_sources": 0,
            "sections": [],
            "total_sections": 0,
            "selected_sections": 0,
            "keywords_used": keywords,
            "keyword_source": keyword_source,
            "total_raw_content_length": 0,
            "total_cleaned_content_length": 0,
            "total_selected_content_length": 0,
            "detected_patterns": {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "status": "pending",
            "processing_stage": "created",
            "errors": [],
            "llm_extraction_id": None,
            "llm_processed": False,
            "llm_processed_at": None
        }
        
        await self.collection.insert_one(doc)
        logger.info(f"Created raw extraction: {extraction_id}")
        
        return extraction_id
    
    async def add_source(
        self,
        extraction_id: str,
        url: str,
        source_type: str,
        parent_url: Optional[str],
        depth: int,
        raw_content: str,
        cleaned_content: str,
        title: Optional[str] = None,
        http_status: Optional[int] = None,
        content_type: Optional[str] = None,
        fetch_error: Optional[str] = None
    ) -> str:
        """Add a source document to the extraction."""
        import uuid
        
        source_id = str(uuid.uuid4())[:8]
        
        source_doc = {
            "source_id": source_id,
            "url": url,
            "source_type": source_type,
            "parent_url": parent_url,
            "depth": depth,
            "title": title,
            "raw_content": raw_content,
            "raw_content_length": len(raw_content),
            "cleaned_content": cleaned_content,
            "cleaned_content_length": len(cleaned_content),
            "fetch_timestamp": datetime.utcnow(),
            "http_status": http_status,
            "content_type": content_type,
            "fetch_error": fetch_error,
            "sections_extracted": 0,
            "relevant_sections": 0
        }
        
        # Update the extraction document
        update_ops = {
            "$push": {"sources": source_doc},
            "$inc": {
                "total_sources": 1,
                "total_raw_content_length": len(raw_content),
                "total_cleaned_content_length": len(cleaned_content)
            },
            "$set": {"updated_at": datetime.utcnow()}
        }
        
        if fetch_error:
            update_ops["$inc"]["failed_sources"] = 1
        else:
            update_ops["$inc"]["successful_sources"] = 1
        
        await self.collection.update_one(
            {"extraction_id": extraction_id},
            update_ops
        )
        
        logger.info(f"Added source {source_id} ({source_type}) to extraction {extraction_id}")
        
        return source_id
    
    async def add_sections(
        self,
        extraction_id: str,
        sections: List[Dict[str, Any]],
        source_url: str
    ):
        """Add multiple extracted sections."""
        import uuid
        
        section_docs = []
        for section_data in sections:
            section_doc = {
                "section_id": str(uuid.uuid4())[:8],
                "source_url": source_url,
                "content": section_data.get("content", ""),
                "content_length": len(section_data.get("content", "")),
                "relevance_score": section_data.get("score", 0),
                "keyword_matches": section_data.get("keyword_matches", []),
                "total_keyword_count": section_data.get("keyword_count", 0),
                "has_currency": section_data.get("has_currency", False),
                "has_percentage": section_data.get("has_percentage", False),
                "has_numbers": section_data.get("has_numbers", False),
                "detected_benefits": section_data.get("detected_benefits", []),
                "start_position": section_data.get("start_position", 0),
                "end_position": section_data.get("end_position", 0),
                "is_selected": section_data.get("is_selected", False)
            }
            section_docs.append(section_doc)
        
        # Count selected sections
        selected_count = sum(1 for s in section_docs if s.get("is_selected", False))
        selected_length = sum(s["content_length"] for s in section_docs if s.get("is_selected", False))
        
        await self.collection.update_one(
            {"extraction_id": extraction_id},
            {
                "$push": {"sections": {"$each": section_docs}},
                "$inc": {
                    "total_sections": len(section_docs),
                    "selected_sections": selected_count,
                    "total_selected_content_length": selected_length
                },
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        logger.info(f"Added {len(section_docs)} sections ({selected_count} selected) to extraction {extraction_id}")
    
    async def detect_and_store_patterns(
        self,
        extraction_id: str,
        content: str,
        source_url: str
    ) -> Dict[str, List[Dict]]:
        """Detect patterns in content and store them."""
        
        detected = {}
        content_lower = content.lower()
        
        for pattern_type, patterns in self.DETECTION_PATTERNS.items():
            matches = []
            for pattern in patterns:
                try:
                    for match in re.finditer(pattern, content_lower, re.IGNORECASE):
                        # Get context around the match
                        start = max(0, match.start() - 50)
                        end = min(len(content), match.end() + 50)
                        
                        match_info = {
                            "raw_text": match.group(0),
                            "full_match": content[match.start():match.end()],
                            "context": content[start:end],
                            "source_url": source_url,
                            "position": match.start(),
                            "groups": match.groups() if match.groups() else None
                        }
                        
                        # Try to extract numeric value
                        numeric_match = re.search(r'[\d,]+(?:\.\d+)?', match.group(0))
                        if numeric_match:
                            try:
                                match_info["numeric_value"] = float(numeric_match.group().replace(',', ''))
                            except:
                                pass
                        
                        # Detect currency
                        currency_match = re.search(r'(aed|usd|eur|gbp)', match.group(0), re.IGNORECASE)
                        if currency_match:
                            match_info["currency"] = currency_match.group(1).upper()
                        
                        matches.append(match_info)
                except Exception as e:
                    logger.warning(f"Pattern matching error for {pattern_type}: {e}")
            
            if matches:
                # Deduplicate matches
                unique_matches = []
                seen_texts = set()
                for m in matches:
                    if m["raw_text"] not in seen_texts:
                        seen_texts.add(m["raw_text"])
                        unique_matches.append(m)
                
                detected[pattern_type] = unique_matches
        
        # Store patterns in the database
        if detected:
            await self.collection.update_one(
                {"extraction_id": extraction_id},
                {
                    "$set": {
                        f"detected_patterns": detected,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Detected {sum(len(v) for v in detected.values())} patterns across {len(detected)} types")
        
        return detected
    
    async def update_status(
        self,
        extraction_id: str,
        status: str,
        processing_stage: str
    ):
        """Update extraction status."""
        await self.collection.update_one(
            {"extraction_id": extraction_id},
            {
                "$set": {
                    "status": status,
                    "processing_stage": processing_stage,
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    async def add_error(
        self,
        extraction_id: str,
        error_type: str,
        message: str,
        source_url: Optional[str] = None
    ):
        """Add an error to the extraction."""
        error_doc = {
            "type": error_type,
            "message": message,
            "source_url": source_url,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.collection.update_one(
            {"extraction_id": extraction_id},
            {
                "$push": {"errors": error_doc},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
    
    async def mark_llm_processed(
        self,
        extraction_id: str,
        llm_extraction_id: str
    ):
        """Mark extraction as processed by LLM."""
        await self.collection.update_one(
            {"extraction_id": extraction_id},
            {
                "$set": {
                    "llm_processed": True,
                    "llm_extraction_id": llm_extraction_id,
                    "llm_processed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    async def get_extraction(self, extraction_id: str) -> Optional[Dict]:
        """Get a raw extraction by ID."""
        return await self.collection.find_one({"extraction_id": extraction_id})
    
    async def get_extraction_summary(self, extraction_id: str) -> Optional[Dict]:
        """Get a summary of the extraction (without full content)."""
        doc = await self.collection.find_one(
            {"extraction_id": extraction_id},
            {
                "sources.raw_content": 0,
                "sources.cleaned_content": 0,
                "sections.content": 0
            }
        )
        return doc
    
    async def get_selected_content(self, extraction_id: str) -> str:
        """Get all selected section content concatenated."""
        doc = await self.collection.find_one({"extraction_id": extraction_id})
        if not doc:
            return ""
        
        selected_sections = [
            s["content"] for s in doc.get("sections", [])
            if s.get("is_selected", False)
        ]
        
        return "\n\n".join(selected_sections)
    
    async def list_extractions(
        self,
        limit: int = 20,
        skip: int = 0,
        status: Optional[str] = None,
        bank: Optional[str] = None
    ) -> List[Dict]:
        """List extractions with optional filters."""
        query = {}
        if status:
            query["status"] = status
        if bank:
            query["detected_bank"] = {"$regex": bank, "$options": "i"}
        
        cursor = self.collection.find(
            query,
            {
                "sources.raw_content": 0,
                "sources.cleaned_content": 0,
                "sections.content": 0
            }
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        return await cursor.to_list(length=limit)


# Create singleton instance
raw_extraction_storage_service = None

def get_raw_extraction_storage_service(db: AsyncIOMotorDatabase) -> RawExtractionStorageService:
    global raw_extraction_storage_service
    if raw_extraction_storage_service is None:
        raw_extraction_storage_service = RawExtractionStorageService(db)
    return raw_extraction_storage_service
