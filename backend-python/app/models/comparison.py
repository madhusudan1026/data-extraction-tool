"""
Comparison model for storing credit card comparisons.
Allows users to compare multiple cards side-by-side.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import Field, BaseModel
from beanie import Document, Indexed
from pymongo import IndexModel, DESCENDING


class ComparisonCard(BaseModel):
    """Card reference within a comparison."""
    card_id: str = Field(..., description="ID of the extracted data document")
    card_name: str = Field(..., description="Name of the card")
    card_issuer: Optional[str] = Field(None, description="Card issuer")
    display_order: int = Field(default=0, description="Display order in comparison")


class ComparisonCriteria(BaseModel):
    """Criteria used for comparison."""
    compare_benefits: bool = Field(default=True, description="Compare benefits")
    compare_fees: bool = Field(default=True, description="Compare fees")
    compare_merchants: bool = Field(default=True, description="Compare merchants")
    compare_eligibility: bool = Field(default=True, description="Compare eligibility")
    custom_criteria: Dict[str, Any] = Field(default_factory=dict, description="Custom comparison criteria")


class BenefitComparison(BaseModel):
    """Comparison of a specific benefit across cards."""
    benefit_type: str = Field(..., description="Type of benefit being compared")
    card_benefits: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Benefits by card ID"
    )
    winner: Optional[str] = Field(None, description="Card ID with best benefit")
    notes: Optional[str] = Field(None, description="Comparison notes")


class FeeComparison(BaseModel):
    """Comparison of fees across cards."""
    fee_type: str = Field(..., description="Type of fee being compared")
    card_fees: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Fees by card ID"
    )
    lowest_fee_card: Optional[str] = Field(None, description="Card ID with lowest fee")
    notes: Optional[str] = Field(None, description="Comparison notes")


class ComparisonResult(BaseModel):
    """Results of the comparison analysis."""
    benefit_comparisons: List[BenefitComparison] = Field(
        default_factory=list,
        description="Benefit comparisons"
    )
    fee_comparisons: List[FeeComparison] = Field(
        default_factory=list,
        description="Fee comparisons"
    )
    overall_winner: Optional[str] = Field(None, description="Overall best card ID")
    summary: Optional[str] = Field(None, description="Summary of comparison")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")


class Comparison(Document):
    """
    Document model for credit card comparisons.
    Stores comparison configurations and results.
    """
    # Comparison identification
    comparison_name: str = Field(..., description="Name of the comparison")
    description: Optional[str] = Field(None, description="Description of the comparison")

    # Cards being compared
    cards: List[ComparisonCard] = Field(..., min_length=2, description="Cards in comparison")

    # Comparison configuration
    criteria: ComparisonCriteria = Field(
        default_factory=ComparisonCriteria,
        description="Comparison criteria"
    )

    # Results
    results: Optional[ComparisonResult] = Field(None, description="Comparison results")

    # Analysis metadata
    analysis_completed: bool = Field(default=False, description="Whether analysis is complete")
    analysis_timestamp: Optional[datetime] = Field(None, description="When analysis was completed")

    # Sharing and visibility
    is_public: bool = Field(default=False, description="Whether comparison is publicly visible")
    share_token: Optional[str] = Field(None, description="Token for sharing")

    # User tracking
    created_by: Optional[str] = Field(None, description="User who created the comparison")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "comparisons"
        indexes = [
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("created_by", 1)]),
            IndexModel([("is_public", 1)]),
            IndexModel([("share_token", 1)]),
        ]

    def add_card(self, card_id: str, card_name: str, card_issuer: Optional[str] = None):
        """
        Add a card to the comparison.

        Args:
            card_id: ID of the card.
            card_name: Name of the card.
            card_issuer: Card issuer.
        """
        # Check if card already exists
        if any(card.card_id == card_id for card in self.cards):
            return

        display_order = len(self.cards)
        new_card = ComparisonCard(
            card_id=card_id,
            card_name=card_name,
            card_issuer=card_issuer,
            display_order=display_order
        )
        self.cards.append(new_card)
        self.updated_at = datetime.utcnow()

    def remove_card(self, card_id: str):
        """
        Remove a card from the comparison.

        Args:
            card_id: ID of the card to remove.
        """
        self.cards = [card for card in self.cards if card.card_id != card_id]
        # Reorder remaining cards
        for i, card in enumerate(self.cards):
            card.display_order = i
        self.updated_at = datetime.utcnow()

    def reorder_cards(self, card_order: List[str]):
        """
        Reorder cards based on provided list of card IDs.

        Args:
            card_order: List of card IDs in desired order.
        """
        card_dict = {card.card_id: card for card in self.cards}
        self.cards = []
        for i, card_id in enumerate(card_order):
            if card_id in card_dict:
                card = card_dict[card_id]
                card.display_order = i
                self.cards.append(card)
        self.updated_at = datetime.utcnow()

    async def complete_analysis(self, results: ComparisonResult):
        """
        Mark comparison analysis as complete and save results.

        Args:
            results: Comparison results.
        """
        self.results = results
        self.analysis_completed = True
        self.analysis_timestamp = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        await self.save()

    def get_card_ids(self) -> List[str]:
        """Get list of card IDs in the comparison."""
        return [card.card_id for card in self.cards]

    def get_card_count(self) -> int:
        """Get number of cards in the comparison."""
        return len(self.cards)

    @classmethod
    async def get_public_comparisons(cls, limit: int = 20):
        """Get public comparisons."""
        return await cls.find({"is_public": True}).sort("-created_at").limit(limit).to_list()

    @classmethod
    async def get_by_share_token(cls, share_token: str):
        """Get comparison by share token."""
        return await cls.find_one({"share_token": share_token})

    @classmethod
    async def get_user_comparisons(cls, user_id: str, limit: int = 20):
        """Get comparisons created by a specific user."""
        return await cls.find({"created_by": user_id}).sort("-created_at").limit(limit).to_list()
