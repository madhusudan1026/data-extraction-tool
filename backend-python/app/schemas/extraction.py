"""
Pydantic schemas for extraction endpoints.
Handles request validation and response serialization.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, HttpUrl


class ExtractionConfig(BaseModel):
    """Configuration for extraction process."""
    model: Optional[str] = Field(None, description="LLM model to use")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="LLM temperature")
    bypass_cache: bool = Field(default=False, description="Bypass cache for this request")
    enable_fallback: bool = Field(default=True, description="Enable fallback extraction")
    timeout: Optional[int] = Field(None, gt=0, description="Timeout in seconds")
    custom_prompt: Optional[str] = Field(None, description="Custom extraction prompt")


class URLExtractionRequest(BaseModel):
    """Request schema for URL extraction."""
    url: HttpUrl = Field(..., description="URL to extract data from")
    config: Optional[ExtractionConfig] = Field(default_factory=ExtractionConfig)

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v):
        """Ensure URL uses http or https scheme."""
        if v.scheme not in ["http", "https"]:
            raise ValueError("URL must use http or https scheme")
        return v


class TextExtractionRequest(BaseModel):
    """Request schema for text extraction."""
    text: str = Field(..., min_length=100, description="Text content to extract from")
    config: Optional[ExtractionConfig] = Field(default_factory=ExtractionConfig)

    @field_validator("text")
    @classmethod
    def validate_text_length(cls, v):
        """Ensure text is not too long."""
        if len(v) > 100000:  # 100KB limit
            raise ValueError("Text content too large (maximum 100KB)")
        return v


class BenefitResponse(BaseModel):
    """Response schema for benefit data."""
    benefit_id: str
    benefit_name: str
    benefit_type: str
    benefit_value: Optional[str] = None
    description: str
    conditions: List[str] = Field(default_factory=list)
    eligible_categories: List[str] = Field(default_factory=list)
    frequency: Optional[str] = None
    cap_amount: Optional[str] = None
    additional_details: Optional[Dict[str, Any]] = None


class EntitlementResponse(BaseModel):
    """Response schema for entitlement data."""
    entitlement_id: str
    entitlement_name: str
    entitlement_type: Optional[str] = None
    description: str
    conditions: List[str] = Field(default_factory=list)
    redemption_locations: List[str] = Field(default_factory=list)
    additional_details: Optional[Dict[str, Any]] = None


class MerchantResponse(BaseModel):
    """Response schema for merchant data."""
    merchant_name: str
    merchant_type: str
    offers: List[str] = Field(default_factory=list)
    redemption_method: Optional[str] = None
    location_details: Optional[Dict[str, Any]] = None
    additional_details: Optional[Dict[str, Any]] = None


class FeesResponse(BaseModel):
    """Response schema for fees data."""
    annual_fee: Optional[str] = None
    interest_rate: Optional[str] = None
    foreign_transaction_fee: Optional[str] = None
    late_payment_fee: Optional[str] = None
    cash_advance_fee: Optional[str] = None
    balance_transfer_fee: Optional[str] = None
    additional_fees: Optional[Dict[str, Any]] = None


class EligibilityResponse(BaseModel):
    """Response schema for eligibility data."""
    minimum_salary: Optional[str] = None
    minimum_spend: Optional[str] = None
    minimum_age: Optional[str] = None
    employment_type: List[str] = Field(default_factory=list)
    nationality_requirements: List[str] = Field(default_factory=list)
    additional_requirements: Optional[Dict[str, Any]] = None


class MetadataResponse(BaseModel):
    """Response schema for metadata."""
    extraction_timestamp: Optional[datetime] = None
    content_length: Optional[int] = None
    processing_time_ms: Optional[int] = None
    llm_model_used: Optional[str] = None
    llm_temperature: Optional[float] = None
    source_hash: Optional[str] = None
    version: int = 1
    custom_fields: Optional[Dict[str, Any]] = None


class ExtractedDataResponse(BaseModel):
    """Response schema for extracted credit card data."""
    id: str = Field(..., description="Document ID")
    source_url: Optional[str] = None
    source_type: str
    card_name: str
    card_issuer: Optional[str] = None
    card_network: Optional[str] = None
    card_category: Optional[str] = None
    benefits: List[BenefitResponse] = Field(default_factory=list)
    entitlements: List[EntitlementResponse] = Field(default_factory=list)
    merchants_vendors: List[MerchantResponse] = Field(default_factory=list)
    fees: FeesResponse = Field(default_factory=FeesResponse)
    eligibility: EligibilityResponse = Field(default_factory=EligibilityResponse)
    extraction_method: str
    confidence_score: Optional[float] = None
    validation_status: str
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    metadata: MetadataResponse = Field(default_factory=MetadataResponse)
    tags: List[str] = Field(default_factory=list)
    schema_version: str = "1.0"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExtractionResponse(BaseModel):
    """Generic extraction response wrapper."""
    success: bool = True
    data: ExtractedDataResponse
    message: Optional[str] = None


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")


class ExtractedDataListResponse(BaseModel):
    """Response schema for list of extracted data."""
    success: bool = True
    data: List[ExtractedDataResponse]
    pagination: PaginationMeta
    message: Optional[str] = None


class DeleteResponse(BaseModel):
    """Response schema for delete operations."""
    success: bool = True
    message: str = "Extraction deleted successfully"


class HealthCheckResponse(BaseModel):
    """Response schema for health check."""
    status: str = "healthy"
    database: bool
    redis: bool
    llm: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)
