"""
Raw Extraction Model - Stores all extracted content before LLM processing.

This model captures:
- Raw content from web pages and PDFs
- Source metadata (URL, type, parent URL)
- Extraction metadata (keywords matched, section scores)
- Timestamps and processing info
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from beanie import Document, Indexed
from pydantic import BaseModel, Field
import uuid


class KeywordMatch(BaseModel):
    """Tracks which keywords were found in a section."""
    keyword: str
    count: int = 1
    positions: List[int] = Field(default_factory=list)  # Character positions where found


class ExtractedSection(BaseModel):
    """A single section of extracted content with metadata."""
    section_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str
    content_length: int = 0
    
    # Scoring
    relevance_score: float = 0.0
    keyword_matches: List[KeywordMatch] = Field(default_factory=list)
    total_keyword_count: int = 0
    
    # Content characteristics
    has_currency: bool = False
    has_percentage: bool = False
    has_numbers: bool = False
    detected_benefits: List[str] = Field(default_factory=list)  # Benefits mentioned in this section
    
    # Position in original content
    start_position: int = 0
    end_position: int = 0
    
    def __init__(self, **data):
        super().__init__(**data)
        if self.content:
            self.content_length = len(self.content)


class SourceDocument(BaseModel):
    """Metadata about a source document (web page or PDF)."""
    source_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    url: str
    source_type: str = "web"  # web, pdf, api
    
    # Hierarchy
    parent_url: Optional[str] = None  # The main URL that led to this source
    depth: int = 0  # How many levels deep from the parent URL
    
    # Content metadata
    title: Optional[str] = None
    raw_content: str = ""
    raw_content_length: int = 0
    cleaned_content: str = ""
    cleaned_content_length: int = 0
    
    # Fetch metadata
    fetch_timestamp: datetime = Field(default_factory=datetime.utcnow)
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    encoding: Optional[str] = None
    
    # Processing metadata
    sections_extracted: int = 0
    relevant_sections: int = 0
    
    # Errors
    fetch_error: Optional[str] = None
    parse_error: Optional[str] = None


class RawExtraction(Document):
    """
    Main document storing all raw extracted data for a credit card extraction job.
    
    This is stored BEFORE LLM processing to preserve all original data.
    """
    
    # Identification
    extraction_id: Indexed(str) = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Primary source
    primary_url: Indexed(str)
    primary_title: Optional[str] = None
    
    # Card identification (if detected)
    detected_card_name: Optional[str] = None
    detected_bank: Optional[str] = None
    
    # All sources processed
    sources: List[SourceDocument] = Field(default_factory=list)
    total_sources: int = 0
    successful_sources: int = 0
    failed_sources: int = 0
    
    # Extracted sections (the valuable content)
    sections: List[ExtractedSection] = Field(default_factory=list)
    total_sections: int = 0
    selected_sections: int = 0  # Sections that passed relevance threshold
    
    # Keyword extraction metadata
    keywords_used: List[str] = Field(default_factory=list)
    keyword_source: str = "default"  # default, custom, combined
    
    # Content statistics
    total_raw_content_length: int = 0
    total_cleaned_content_length: int = 0
    total_selected_content_length: int = 0
    
    # Detected patterns (pre-LLM extraction)
    detected_patterns: Dict[str, Any] = Field(default_factory=dict)
    """
    Example structure:
    {
        "annual_fees": ["AED 500", "AED 750 waived first year"],
        "cashback_rates": ["5% on groceries", "2% on all purchases"],
        "lounge_access": ["Unlimited airport lounge access"],
        "minimum_salary": ["AED 10,000", "AED 15,000"],
        "insurance_coverage": ["Travel insurance up to AED 500,000"],
        "reward_points": ["1 point per AED spent"],
        ...
    }
    """
    
    # Processing timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Processing status
    status: str = "pending"  # pending, processing, completed, failed
    processing_stage: str = "created"  # created, fetching, parsing, scoring, completed
    
    # Error tracking
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Reference to LLM extraction (if completed)
    llm_extraction_id: Optional[str] = None
    llm_processed: bool = False
    llm_processed_at: Optional[datetime] = None
    
    class Settings:
        name = "raw_extractions"
        indexes = [
            "primary_url",
            "extraction_id",
            "detected_bank",
            "created_at",
            "status"
        ]
    
    def add_source(self, source: SourceDocument):
        """Add a source document."""
        self.sources.append(source)
        self.total_sources = len(self.sources)
        if source.fetch_error:
            self.failed_sources += 1
        else:
            self.successful_sources += 1
        self.total_raw_content_length += source.raw_content_length
        self.total_cleaned_content_length += source.cleaned_content_length
        self.updated_at = datetime.utcnow()
    
    def add_section(self, section: ExtractedSection):
        """Add an extracted section."""
        self.sections.append(section)
        self.total_sections = len(self.sections)
        self.updated_at = datetime.utcnow()
    
    def add_error(self, error_type: str, message: str, source_url: Optional[str] = None):
        """Log an error."""
        self.errors.append({
            "type": error_type,
            "message": message,
            "source_url": source_url,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.updated_at = datetime.utcnow()
    
    def mark_completed(self):
        """Mark extraction as completed."""
        self.status = "completed"
        self.processing_stage = "completed"
        self.updated_at = datetime.utcnow()
    
    def mark_failed(self, error: str):
        """Mark extraction as failed."""
        self.status = "failed"
        self.add_error("fatal", error)
        self.updated_at = datetime.utcnow()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of this extraction."""
        return {
            "extraction_id": self.extraction_id,
            "primary_url": self.primary_url,
            "detected_card": self.detected_card_name,
            "detected_bank": self.detected_bank,
            "sources": {
                "total": self.total_sources,
                "successful": self.successful_sources,
                "failed": self.failed_sources
            },
            "sections": {
                "total": self.total_sections,
                "selected": self.selected_sections
            },
            "content": {
                "raw_length": self.total_raw_content_length,
                "cleaned_length": self.total_cleaned_content_length,
                "selected_length": self.total_selected_content_length
            },
            "keywords_count": len(self.keywords_used),
            "patterns_detected": len(self.detected_patterns),
            "status": self.status,
            "llm_processed": self.llm_processed,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class DetectedPattern(BaseModel):
    """A pattern detected in the content (e.g., fee amount, benefit)."""
    pattern_type: str  # annual_fee, cashback, lounge_access, etc.
    raw_text: str  # The original text that matched
    normalized_value: Optional[str] = None  # Cleaned/normalized value
    numeric_value: Optional[float] = None  # If applicable
    currency: Optional[str] = None  # AED, USD, etc.
    unit: Optional[str] = None  # %, points, visits, etc.
    
    # Source tracking
    source_url: str
    section_id: Optional[str] = None
    
    # Context
    context_before: Optional[str] = None  # Text before the match
    context_after: Optional[str] = None  # Text after the match
    
    # Confidence
    confidence: float = 1.0  # 0-1, based on pattern match quality
    
    # Metadata
    detected_at: datetime = Field(default_factory=datetime.utcnow)
