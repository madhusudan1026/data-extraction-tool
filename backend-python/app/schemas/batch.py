"""
Pydantic schemas for batch processing endpoints.
Handles batch job requests and responses.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class BatchItemRequest(BaseModel):
    """Request schema for a single batch item."""
    source_type: str = Field(..., pattern="^(url|pdf|text)$", description="Type of source")
    source: str = Field(..., description="Source content or reference")
    item_id: Optional[str] = Field(None, description="Optional custom item ID")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v, info):
        """Validate source based on source_type."""
        source_type = info.data.get("source_type")

        if source_type == "text" and len(v) < 100:
            raise ValueError("Text source must be at least 100 characters")

        if source_type == "text" and len(v) > 100000:
            raise ValueError("Text source too large (maximum 100KB)")

        return v


class BatchConfigRequest(BaseModel):
    """Configuration for batch job execution."""
    concurrency: int = Field(default=5, ge=1, le=50, description="Number of concurrent extractions")
    timeout_per_item: int = Field(default=300, ge=30, le=600, description="Timeout per item in seconds")
    retry_failed: bool = Field(default=True, description="Whether to retry failed items")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum number of retries")
    stop_on_error: bool = Field(default=False, description="Stop job on first error")
    extraction_config: Dict[str, Any] = Field(default_factory=dict, description="Extraction configuration")


class BatchJobRequest(BaseModel):
    """Request schema for creating a batch job."""
    job_name: Optional[str] = Field(None, description="Human-readable job name")
    job_description: Optional[str] = Field(None, description="Job description")
    items: List[BatchItemRequest] = Field(..., min_length=1, max_length=100, description="Items to process")
    config: Optional[BatchConfigRequest] = Field(default_factory=BatchConfigRequest)
    tags: List[str] = Field(default_factory=list, description="Job tags")

    @field_validator("items")
    @classmethod
    def validate_items(cls, v):
        """Ensure items list is not empty and within limits."""
        if not v:
            raise ValueError("At least one item is required")
        if len(v) > 100:
            raise ValueError("Maximum 100 items allowed per batch")
        return v


class JobItemResponse(BaseModel):
    """Response schema for a batch job item."""
    item_id: str
    source_type: str
    source: str
    status: str
    result_id: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0


class JobStatisticsResponse(BaseModel):
    """Response schema for job statistics."""
    total_items: int
    pending_items: int
    processing_items: int
    completed_items: int
    failed_items: int
    skipped_items: int
    success_rate: float
    average_processing_time_ms: Optional[float] = None


class JobConfigResponse(BaseModel):
    """Response schema for job configuration."""
    concurrency: int
    timeout_per_item: int
    retry_failed: bool
    max_retries: int
    stop_on_error: bool
    extraction_config: Dict[str, Any]


class BatchJobResponse(BaseModel):
    """Response schema for batch job."""
    id: str = Field(..., description="Job ID")
    job_name: Optional[str] = None
    job_description: Optional[str] = None
    status: str
    items: List[JobItemResponse]
    config: JobConfigResponse
    statistics: JobStatisticsResponse
    progress_percentage: float
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_processing_time_ms: Optional[int] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    created_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BatchJobCreateResponse(BaseModel):
    """Response schema for batch job creation."""
    success: bool = True
    data: BatchJobResponse
    message: str = "Batch job created successfully"


class BatchJobListResponse(BaseModel):
    """Response schema for list of batch jobs."""
    success: bool = True
    data: List[BatchJobResponse]
    pagination: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class BatchJobStartResponse(BaseModel):
    """Response schema for starting a batch job."""
    success: bool = True
    job_id: str
    message: str = "Batch job started successfully"


class BatchJobCancelResponse(BaseModel):
    """Response schema for canceling a batch job."""
    success: bool = True
    job_id: str
    message: str = "Batch job cancelled successfully"


class BatchJobRetryResponse(BaseModel):
    """Response schema for retrying failed items."""
    success: bool = True
    job_id: str
    retried_items: int
    message: str = "Failed items queued for retry"
