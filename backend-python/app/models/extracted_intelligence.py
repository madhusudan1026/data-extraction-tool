"""
Flexible Intelligence Schema for Credit Card Data Extraction.

This schema prioritizes preserving intelligence over rigid categorization.
Instead of forcing data into benefits/entitlements/merchants, we store:
1. Raw intelligence items with their context
2. Relationships between items
3. Conditions and constraints
4. Source tracking for each piece of information

Key principles:
- Store the original text/value as extracted
- Allow flexible tagging instead of rigid categories
- Preserve relationships (e.g., "this discount applies at this merchant with this condition")
- Track the source of each piece of information
- Support hierarchical and linked data
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from beanie import Document, Indexed, before_event, Replace, Insert
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT


# ============= FLEXIBLE ENUMERATIONS =============

class IntelligenceCategory(str, Enum):
    """High-level categories for intelligence items - but not restrictive."""
    REWARD = "reward"                    # Points, miles, cashback
    ACCESS = "access"                    # Lounge, golf, spa, etc.
    DISCOUNT = "discount"                # Percentage off, buy-one-get-one
    COMPLIMENTARY = "complimentary"      # Free items/services
    INSURANCE = "insurance"              # Coverage, protection
    SERVICE = "service"                  # Concierge, support, etc.
    FEE = "fee"                          # Annual fee, charges, etc.
    LIMIT = "limit"                      # Credit limit, transaction limits
    ELIGIBILITY = "eligibility"          # Requirements to get the card
    PARTNER = "partner"                  # Merchant/brand partnerships
    PROMOTION = "promotion"              # Time-limited offers
    FEATURE = "feature"                  # Card features (contactless, etc.)
    PROGRAM = "program"                  # Loyalty programs, memberships
    OTHER = "other"


class ConditionType(str, Enum):
    """Types of conditions that can apply to intelligence items."""
    MINIMUM_SPEND = "minimum_spend"
    MAXIMUM_CAP = "maximum_cap"
    TIME_PERIOD = "time_period"
    LOCATION = "location"
    MERCHANT_CATEGORY = "merchant_category"
    SPECIFIC_MERCHANT = "specific_merchant"
    CARD_VARIANT = "card_variant"
    MEMBERSHIP_TIER = "membership_tier"
    BOOKING_CHANNEL = "booking_channel"
    DAY_OF_WEEK = "day_of_week"
    TRANSACTION_TYPE = "transaction_type"
    CUMULATIVE = "cumulative"
    FIRST_TIME = "first_time"
    OTHER = "other"


class ValueType(str, Enum):
    """Type of value in an intelligence item."""
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    POINTS = "points"
    MULTIPLIER = "multiplier"
    COUNT = "count"
    BOOLEAN = "boolean"
    TEXT = "text"
    RANGE = "range"


# ============= CORE BUILDING BLOCKS =============

class SourceReference(BaseModel):
    """Tracks where a piece of information came from."""
    url: Optional[str] = Field(None, description="Source URL")
    page_title: Optional[str] = Field(None, description="Title of source page")
    section: Optional[str] = Field(None, description="Section/heading where found")
    extracted_text: Optional[str] = Field(None, description="Original text as extracted")
    confidence: float = Field(default=0.5, ge=0, le=1, description="Confidence in extraction")
    extraction_method: str = Field(default="llm", description="How this was extracted")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class Condition(BaseModel):
    """A condition or constraint that applies to an intelligence item."""
    type: ConditionType = Field(default=ConditionType.OTHER)
    description: str = Field(..., description="Human-readable condition description")
    value: Optional[Union[str, float, int, bool, Dict[str, Any]]] = Field(None, description="Condition value")
    operator: Optional[str] = Field(None, description="e.g., 'minimum', 'maximum', 'equals', 'between'")
    
    # For complex conditions
    currency: Optional[str] = Field(None, description="Currency if applicable")
    time_unit: Optional[str] = Field(None, description="e.g., 'monthly', 'yearly', 'per transaction'")
    
    class Config:
        use_enum_values = True


class ValueSpec(BaseModel):
    """Specification of a value - flexible enough to handle various formats."""
    raw_value: str = Field(..., description="Original value as extracted (e.g., '5%', 'AED 500', '2X points')")
    numeric_value: Optional[float] = Field(None, description="Parsed numeric value if applicable")
    value_type: ValueType = Field(default=ValueType.TEXT)
    currency: Optional[str] = Field(None, description="Currency if applicable")
    unit: Optional[str] = Field(None, description="Unit (e.g., 'points', 'miles', 'visits')")
    
    # For ranges
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    
    class Config:
        use_enum_values = True


class Entity(BaseModel):
    """An entity referenced in intelligence (merchant, program, location, etc.)."""
    name: str = Field(..., description="Entity name")
    type: str = Field(..., description="Entity type (merchant, program, location, network, etc.)")
    category: Optional[str] = Field(None, description="Category/subcategory")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional entity details")
    
    # For merchants/partners
    locations: List[str] = Field(default_factory=list, description="Specific locations if applicable")
    website: Optional[str] = None
    
    class Config:
        use_enum_values = True


# ============= MAIN INTELLIGENCE ITEM =============

class IntelligenceItem(BaseModel):
    """
    A single piece of extracted intelligence.
    
    This is the core unit - it captures ONE piece of information with all its context.
    Examples:
    - "5% cashback on dining" 
    - "Free airport lounge access - 4 visits per year"
    - "Buy 1 Get 1 free at Cine Royal Cinemas"
    - "Minimum salary AED 12,000"
    """
    # Unique identifier within this extraction
    item_id: str = Field(..., description="Unique ID for this item")
    
    # Core content
    title: str = Field(..., description="Short title/summary of this intelligence")
    description: str = Field(..., description="Full description as extracted")
    category: IntelligenceCategory = Field(default=IntelligenceCategory.OTHER)
    tags: List[str] = Field(default_factory=list, description="Flexible tags for searchability")
    
    # Value specification (if this item has a quantifiable value)
    value: Optional[ValueSpec] = Field(None, description="The value/amount if applicable")
    
    # Conditions and constraints
    conditions: List[Condition] = Field(default_factory=list, description="Conditions that apply")
    
    # Related entities (merchants, programs, etc.)
    entities: List[Entity] = Field(default_factory=list, description="Related entities")
    
    # Relationships to other intelligence items
    related_items: List[str] = Field(default_factory=list, description="IDs of related items")
    parent_item: Optional[str] = Field(None, description="Parent item ID if this is a sub-item")
    
    # Temporal aspects
    validity_start: Optional[datetime] = None
    validity_end: Optional[datetime] = None
    is_promotional: bool = Field(default=False, description="Is this a time-limited promotion?")
    
    # Source tracking
    source: SourceReference = Field(default_factory=SourceReference)
    
    # Flags
    is_headline: bool = Field(default=False, description="Is this a key/headline benefit?")
    requires_enrollment: bool = Field(default=False, description="Does this require separate enrollment?")
    is_conditional: bool = Field(default=False, description="Does this have significant conditions?")
    
    class Config:
        use_enum_values = True


# ============= CARD INFORMATION =============

class CardVariant(BaseModel):
    """Information about a specific card variant (e.g., Mastercard vs Diners Club)."""
    name: str = Field(..., description="Variant name")
    network: Optional[str] = Field(None, description="Card network (Visa, Mastercard, etc.)")
    tier: Optional[str] = Field(None, description="Card tier (Platinum, Signature, etc.)")
    specific_intelligence: List[str] = Field(default_factory=list, description="IDs of variant-specific items")


class CardInfo(BaseModel):
    """Basic card information."""
    name: str = Field(..., description="Card name")
    bank: str = Field(..., description="Issuing bank")
    card_type: Optional[str] = Field(None, description="Type of card")
    
    # Multiple variants (e.g., Duo card has Mastercard + Diners Club)
    variants: List[CardVariant] = Field(default_factory=list)
    
    # Networks and tiers
    networks: List[str] = Field(default_factory=list, description="Card networks")
    tiers: List[str] = Field(default_factory=list, description="Card tiers")
    
    # URLs
    product_url: Optional[str] = None
    application_url: Optional[str] = None
    
    # Images
    card_image_url: Optional[str] = None


class FeeStructure(BaseModel):
    """Fee information - kept separate as it's important structured data."""
    annual_fee: Optional[ValueSpec] = None
    joining_fee: Optional[ValueSpec] = None
    supplementary_card_fee: Optional[ValueSpec] = None
    
    # Interest rates
    interest_rate_retail: Optional[ValueSpec] = None
    interest_rate_cash: Optional[ValueSpec] = None
    
    # Other fees as flexible dict
    other_fees: Dict[str, ValueSpec] = Field(default_factory=dict)
    
    # Fee waivers (stored as intelligence items but referenced here)
    waiver_conditions: List[str] = Field(default_factory=list, description="IDs of fee waiver items")


class EligibilityCriteria(BaseModel):
    """Eligibility information - kept separate as it's commonly queried."""
    minimum_salary: Optional[ValueSpec] = None
    minimum_age: Optional[ValueSpec] = None
    maximum_age: Optional[ValueSpec] = None
    
    employment_types: List[str] = Field(default_factory=list)
    nationality_requirements: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    
    # Additional criteria as intelligence items
    additional_criteria: List[str] = Field(default_factory=list, description="IDs of additional criteria items")


# ============= MAIN DOCUMENT =============

class ExtractedIntelligence(Document):
    """
    Main document storing all extracted intelligence for a credit card.
    
    Design philosophy:
    1. Store raw intelligence items that preserve the original information
    2. Allow flexible categorization through tags
    3. Maintain relationships between items
    4. Track sources for everything
    5. Keep commonly-queried fields (fees, eligibility) in structured format
    6. Support multiple card variants
    """
    
    # Basic card info
    card: CardInfo = Field(..., description="Card information")
    
    # All intelligence items - the core of our extraction
    intelligence: List[IntelligenceItem] = Field(default_factory=list, description="All extracted intelligence")
    
    # Structured data for common queries
    fees: FeeStructure = Field(default_factory=FeeStructure)
    eligibility: EligibilityCriteria = Field(default_factory=EligibilityCriteria)
    
    # Quick access indexes (item IDs grouped by category)
    intelligence_by_category: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="Item IDs grouped by category for quick access"
    )
    
    # Tags index for search
    all_tags: List[str] = Field(default_factory=list, description="All unique tags across items")
    
    # Entities index
    all_entities: List[Entity] = Field(default_factory=list, description="All unique entities")
    
    # Source documents processed
    sources_processed: List[SourceReference] = Field(default_factory=list)
    
    # Extraction metadata
    extraction_metadata: Dict[str, Any] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    # Quality metrics
    total_items: int = Field(default=0)
    confidence_score: float = Field(default=0.0)
    completeness_score: float = Field(default=0.0)
    
    # Status
    is_deleted: bool = Field(default=False)
    
    class Settings:
        name = "extracted_intelligence"
        indexes = [
            IndexModel([("card.bank", ASCENDING)]),
            IndexModel([("card.name", ASCENDING)]),
            IndexModel([("all_tags", ASCENDING)]),
            IndexModel([("extracted_at", DESCENDING)]),
            IndexModel([("confidence_score", DESCENDING)]),
        ]
    
    @before_event([Replace, Insert])
    def update_indexes(self):
        """Update derived fields before saving."""
        self.last_updated = datetime.utcnow()
        self.total_items = len(self.intelligence)
        
        # Build category index
        self.intelligence_by_category = {}
        for item in self.intelligence:
            cat = item.category
            if cat not in self.intelligence_by_category:
                self.intelligence_by_category[cat] = []
            self.intelligence_by_category[cat].append(item.item_id)
        
        # Build tags index
        all_tags = set()
        for item in self.intelligence:
            all_tags.update(item.tags)
        self.all_tags = list(all_tags)
        
        # Build entities index
        seen_entities = {}
        for item in self.intelligence:
            for entity in item.entities:
                key = f"{entity.type}:{entity.name}"
                if key not in seen_entities:
                    seen_entities[key] = entity
        self.all_entities = list(seen_entities.values())
    
    def get_items_by_category(self, category: IntelligenceCategory) -> List[IntelligenceItem]:
        """Get all intelligence items in a category."""
        return [item for item in self.intelligence if item.category == category]
    
    def get_items_by_tag(self, tag: str) -> List[IntelligenceItem]:
        """Get all intelligence items with a specific tag."""
        return [item for item in self.intelligence if tag in item.tags]
    
    def get_items_by_entity(self, entity_name: str) -> List[IntelligenceItem]:
        """Get all intelligence items related to an entity."""
        return [
            item for item in self.intelligence 
            if any(e.name.lower() == entity_name.lower() for e in item.entities)
        ]
    
    def get_headline_items(self) -> List[IntelligenceItem]:
        """Get headline/key benefits."""
        return [item for item in self.intelligence if item.is_headline]
    
    def get_conditional_items(self) -> List[IntelligenceItem]:
        """Get items with significant conditions."""
        return [item for item in self.intelligence if item.is_conditional]
    
    def to_summary(self) -> Dict[str, Any]:
        """Generate a summary view of the intelligence."""
        return {
            "card_name": self.card.name,
            "bank": self.card.bank,
            "total_intelligence_items": self.total_items,
            "categories": {
                cat: len(items) 
                for cat, items in self.intelligence_by_category.items()
            },
            "headline_benefits": [
                {"title": item.title, "description": item.description}
                for item in self.get_headline_items()
            ],
            "key_entities": [
                {"name": e.name, "type": e.type}
                for e in self.all_entities[:10]
            ],
            "tags": self.all_tags[:20],
            "confidence": self.confidence_score,
            "sources_count": len(self.sources_processed)
        }


# ============= HELPER FUNCTIONS =============

def create_intelligence_item(
    title: str,
    description: str,
    category: IntelligenceCategory = IntelligenceCategory.OTHER,
    tags: List[str] = None,
    value_raw: str = None,
    conditions: List[Dict] = None,
    entities: List[Dict] = None,
    source_url: str = None,
    source_text: str = None,
    is_headline: bool = False,
) -> IntelligenceItem:
    """Helper to create an intelligence item with common defaults."""
    import uuid
    
    item = IntelligenceItem(
        item_id=str(uuid.uuid4())[:8],
        title=title,
        description=description,
        category=category,
        tags=tags or [],
        is_headline=is_headline,
        source=SourceReference(
            url=source_url,
            extracted_text=source_text
        )
    )
    
    if value_raw:
        item.value = ValueSpec(raw_value=value_raw)
    
    if conditions:
        item.conditions = [Condition(**c) for c in conditions]
        item.is_conditional = len(conditions) > 0
    
    if entities:
        item.entities = [Entity(**e) for e in entities]
    
    return item
