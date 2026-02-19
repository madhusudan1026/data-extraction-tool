"""
Pipeline Data Models

Shared dataclasses used by all extraction pipelines:
- ExtractedBenefit: A single extracted benefit
- SourceProcessingResult: Result from processing one source
- PipelineResult: Aggregate result from a pipeline run
- ConfidenceLevel: Enum for confidence tiers

Extracted from base_pipeline.py to allow reuse without circular imports.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class ConfidenceLevel(Enum):
    HIGH = "high"       # >0.8 - Direct match, explicit mention
    MEDIUM = "medium"   # 0.5-0.8 - Inferred or partial match
    LOW = "low"         # <0.5 - Weak signal, needs verification


@dataclass
class ExtractedBenefit:
    """A single extracted benefit from the pipeline."""
    benefit_id: str
    benefit_type: str           # e.g., 'cashback', 'lounge_access'
    title: str
    description: str
    value: Optional[str] = None  # e.g., '5%', 'AED 500', '4 visits'
    value_numeric: Optional[float] = None
    value_unit: Optional[str] = None

    # Conditions and limitations
    conditions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    eligible_categories: List[str] = field(default_factory=list)

    # Merchant/partner info
    merchants: List[str] = field(default_factory=list)
    partners: List[str] = field(default_factory=list)

    # Temporal info
    validity_period: Optional[str] = None
    frequency: Optional[str] = None  # e.g., 'per month', 'per year'

    # Caps and thresholds
    minimum_spend: Optional[str] = None
    maximum_benefit: Optional[str] = None
    cap_period: Optional[str] = None

    # Source tracking
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    source_text: Optional[str] = None
    source_index: Optional[int] = None
    extraction_method: str = "llm"  # 'llm', 'pattern', 'hybrid'

    # Quality metrics
    confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW

    # Metadata
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    pipeline_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "benefit_id": self.benefit_id,
            "benefit_type": self.benefit_type,
            "title": self.title,
            "description": self.description,
            "value": self.value,
            "value_numeric": self.value_numeric,
            "value_unit": self.value_unit,
            "conditions": self.conditions,
            "limitations": self.limitations,
            "eligible_categories": self.eligible_categories,
            "merchants": self.merchants,
            "partners": self.partners,
            "validity_period": self.validity_period,
            "frequency": self.frequency,
            "minimum_spend": self.minimum_spend,
            "maximum_benefit": self.maximum_benefit,
            "cap_period": self.cap_period,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_text": self.source_text,
            "source_index": self.source_index,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "extracted_at": self.extracted_at.isoformat(),
            "pipeline_version": self.pipeline_version,
        }


@dataclass
class SourceProcessingResult:
    """Result from processing a single source."""
    source_url: str
    source_title: str
    source_index: int
    content_length: int
    is_relevant: bool
    relevance_score: float
    keyword_matches: int

    # Extraction results
    llm_benefits: List[ExtractedBenefit] = field(default_factory=list)
    pattern_benefits: List[ExtractedBenefit] = field(default_factory=list)
    merged_benefits: List[ExtractedBenefit] = field(default_factory=list)

    # Timing
    llm_duration_ms: float = 0.0
    pattern_duration_ms: float = 0.0

    # Errors
    llm_error: Optional[str] = None
    pattern_error: Optional[str] = None


@dataclass
class PipelineResult:
    """Result from running a pipeline."""
    pipeline_name: str
    benefit_type: str
    success: bool
    benefits: List[ExtractedBenefit] = field(default_factory=list)

    # Per-source results
    source_results: List[SourceProcessingResult] = field(default_factory=list)

    # Statistics
    total_found: int = 0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0

    # Processing info
    sources_total: int = 0
    sources_relevant: int = 0
    sources_processed: int = 0
    content_processed_chars: int = 0
    llm_extractions: int = 0
    pattern_extractions: int = 0

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API response."""
        return {
            "pipeline_name": self.pipeline_name,
            "benefit_type": self.benefit_type,
            "success": self.success,
            "benefits": [b.to_dict() for b in self.benefits],
            "source_results": [
                {
                    "source_url": sr.source_url,
                    "source_title": sr.source_title,
                    "source_index": sr.source_index,
                    "is_relevant": sr.is_relevant,
                    "relevance_score": sr.relevance_score,
                    "llm_benefits_count": len(sr.llm_benefits),
                    "pattern_benefits_count": len(sr.pattern_benefits),
                    "merged_benefits_count": len(sr.merged_benefits),
                    "llm_duration_ms": sr.llm_duration_ms,
                    "llm_error": sr.llm_error,
                }
                for sr in self.source_results
            ],
            "statistics": {
                "total_found": self.total_found,
                "high_confidence": self.high_confidence_count,
                "medium_confidence": self.medium_confidence_count,
                "low_confidence": self.low_confidence_count,
                "sources_total": self.sources_total,
                "sources_relevant": self.sources_relevant,
                "sources_processed": self.sources_processed,
                "llm_extractions": self.llm_extractions,
                "pattern_extractions": self.pattern_extractions,
            },
            "timing": {
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "duration_seconds": self.duration_seconds,
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }
