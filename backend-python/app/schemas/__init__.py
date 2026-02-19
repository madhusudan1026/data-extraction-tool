"""Pydantic schemas for request/response validation."""
from app.schemas.extraction import (
    URLExtractionRequest,
    TextExtractionRequest,
    ExtractionConfig,
    ExtractionResponse,
    ExtractedDataResponse,
    ExtractedDataListResponse,
)
from app.schemas.batch import (
    BatchJobRequest,
    BatchJobResponse,
    BatchJobListResponse,
    BatchItemRequest,
)
from app.schemas.comparison import (
    ComparisonCreateRequest,
    ComparisonResponse,
    ComparisonListResponse,
    ComparisonAnalysisResponse,
)

__all__ = [
    "URLExtractionRequest",
    "TextExtractionRequest",
    "ExtractionConfig",
    "ExtractionResponse",
    "ExtractedDataResponse",
    "ExtractedDataListResponse",
    "BatchJobRequest",
    "BatchJobResponse",
    "BatchJobListResponse",
    "BatchItemRequest",
    "ComparisonCreateRequest",
    "ComparisonResponse",
    "ComparisonListResponse",
    "ComparisonAnalysisResponse",
]
