"""
Pydantic schemas for comparison endpoints.
Handles comparison requests and responses.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class ComparisonCardRequest(BaseModel):
    """Request schema for adding a card to comparison."""
    card_id: str = Field(..., description="ID of the extracted data document")


class ComparisonCriteriaRequest(BaseModel):
    """Request schema for comparison criteria."""
    compare_benefits: bool = Field(default=True, description="Compare benefits")
    compare_fees: bool = Field(default=True, description="Compare fees")
    compare_merchants: bool = Field(default=True, description="Compare merchants")
    compare_eligibility: bool = Field(default=True, description="Compare eligibility")
    custom_criteria: Dict[str, Any] = Field(default_factory=dict, description="Custom comparison criteria")


class ComparisonCreateRequest(BaseModel):
    """Request schema for creating a comparison."""
    comparison_name: str = Field(..., min_length=1, max_length=200, description="Name of the comparison")
    description: Optional[str] = Field(None, description="Description of the comparison")
    card_ids: List[str] = Field(..., min_length=2, max_length=10, description="List of card IDs to compare")
    criteria: Optional[ComparisonCriteriaRequest] = Field(
        default_factory=ComparisonCriteriaRequest,
        description="Comparison criteria"
    )
    is_public: bool = Field(default=False, description="Whether comparison is publicly visible")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    @field_validator("card_ids")
    @classmethod
    def validate_card_ids(cls, v):
        """Ensure at least 2 cards and no more than 10."""
        if len(v) < 2:
            raise ValueError("At least 2 cards are required for comparison")
        if len(v) > 10:
            raise ValueError("Maximum 10 cards allowed in a comparison")
        # Check for duplicates
        if len(v) != len(set(v)):
            raise ValueError("Duplicate card IDs are not allowed")
        return v


class ComparisonUpdateRequest(BaseModel):
    """Request schema for updating a comparison."""
    comparison_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    criteria: Optional[ComparisonCriteriaRequest] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class ComparisonCardResponse(BaseModel):
    """Response schema for card in comparison."""
    card_id: str
    card_name: str
    card_issuer: Optional[str] = None
    display_order: int


class ComparisonCriteriaResponse(BaseModel):
    """Response schema for comparison criteria."""
    compare_benefits: bool
    compare_fees: bool
    compare_merchants: bool
    compare_eligibility: bool
    custom_criteria: Dict[str, Any]


class BenefitComparisonResponse(BaseModel):
    """Response schema for benefit comparison."""
    benefit_type: str
    card_benefits: Dict[str, List[str]]
    winner: Optional[str] = None
    notes: Optional[str] = None


class FeeComparisonResponse(BaseModel):
    """Response schema for fee comparison."""
    fee_type: str
    card_fees: Dict[str, Optional[str]]
    lowest_fee_card: Optional[str] = None
    notes: Optional[str] = None


class ComparisonResultResponse(BaseModel):
    """Response schema for comparison results."""
    benefit_comparisons: List[BenefitComparisonResponse]
    fee_comparisons: List[FeeComparisonResponse]
    overall_winner: Optional[str] = None
    summary: Optional[str] = None
    recommendations: List[str]


class ComparisonResponse(BaseModel):
    """Response schema for comparison."""
    id: str = Field(..., description="Comparison ID")
    comparison_name: str
    description: Optional[str] = None
    cards: List[ComparisonCardResponse]
    criteria: ComparisonCriteriaResponse
    results: Optional[ComparisonResultResponse] = None
    analysis_completed: bool
    analysis_timestamp: Optional[datetime] = None
    is_public: bool
    share_token: Optional[str] = None
    created_by: Optional[str] = None
    tags: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ComparisonListResponse(BaseModel):
    """Response schema for list of comparisons."""
    success: bool = True
    data: List[ComparisonResponse]
    pagination: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class ComparisonAnalysisResponse(BaseModel):
    """Response schema for comparison analysis."""
    success: bool = True
    comparison_id: str
    results: ComparisonResultResponse
    message: str = "Comparison analysis completed successfully"


class ComparisonDeleteResponse(BaseModel):
    """Response schema for comparison deletion."""
    success: bool = True
    message: str = "Comparison deleted successfully"


class ComparisonAddCardRequest(BaseModel):
    """Request schema for adding a card to existing comparison."""
    card_id: str = Field(..., description="ID of the card to add")


class ComparisonRemoveCardRequest(BaseModel):
    """Request schema for removing a card from comparison."""
    card_id: str = Field(..., description="ID of the card to remove")


class ComparisonReorderRequest(BaseModel):
    """Request schema for reordering cards in comparison."""
    card_order: List[str] = Field(..., min_length=2, description="Ordered list of card IDs")

    @field_validator("card_order")
    @classmethod
    def validate_card_order(cls, v):
        """Ensure no duplicates in card order."""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate card IDs in card_order")
        return v
