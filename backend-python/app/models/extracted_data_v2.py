"""
Enhanced ExtractedData model with comprehensive schema for credit card information.
Supports detailed benefits, entitlements, merchants, conditions, and redemption rules.
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from beanie import Document, Indexed, before_event, Replace, Insert
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT


# ============= ENUMERATIONS =============

class BenefitType(str, Enum):
    """Enumeration of benefit types."""
    CASHBACK = "cashback"
    DISCOUNT = "discount"
    LOUNGE_ACCESS = "lounge_access"
    TRAVEL = "travel"
    DINING = "dining"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    LIFESTYLE = "lifestyle"
    INSURANCE = "insurance"
    CONCIERGE = "concierge"
    REWARDS_POINTS = "rewards_points"
    COMPLIMENTARY = "complimentary"
    OTHER = "other"


class EntitlementType(str, Enum):
    """Enumeration of entitlement types."""
    LOUNGE_ACCESS = "lounge_access"
    AIRPORT_TRANSFER = "airport_transfer"
    VALET_PARKING = "valet_parking"
    CONCIERGE = "concierge"
    GOLF_ACCESS = "golf_access"
    SPA_ACCESS = "spa_access"
    MOVIE_TICKETS = "movie_tickets"
    ROADSIDE_ASSISTANCE = "roadside_assistance"
    TRAVEL_INSURANCE = "travel_insurance"
    PURCHASE_PROTECTION = "purchase_protection"
    EXTENDED_WARRANTY = "extended_warranty"
    OTHER = "other"


class MerchantCategory(str, Enum):
    """Enumeration of merchant categories."""
    SUPERMARKET = "supermarket"
    GROCERY = "grocery"
    RESTAURANT = "restaurant"
    FAST_FOOD = "fast_food"
    CAFE = "cafe"
    FASHION = "fashion"
    ELECTRONICS = "electronics"
    TRAVEL = "travel"
    HOTEL = "hotel"
    AIRLINE = "airline"
    FUEL = "fuel"
    ENTERTAINMENT = "entertainment"
    CINEMA = "cinema"
    ONLINE = "online"
    DEPARTMENT_STORE = "department_store"
    PHARMACY = "pharmacy"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    UTILITIES = "utilities"
    OTHER = "other"


class Frequency(str, Enum):
    """Enumeration of frequency types."""
    PER_TRANSACTION = "per_transaction"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    UNLIMITED = "unlimited"
    ONE_TIME = "one_time"
    OTHER = "other"


class SourceType(str, Enum):
    """Enumeration of source types."""
    URL = "url"
    PDF = "pdf"
    TEXT = "text"
    API = "api"


class CardNetwork(str, Enum):
    """Enumeration of card networks."""
    VISA = "Visa"
    MASTERCARD = "Mastercard"
    AMERICAN_EXPRESS = "American Express"
    DINERS_CLUB = "Diners Club"
    DISCOVER = "Discover"
    UNIONPAY = "UnionPay"
    OTHER = "Other"


class CardCategory(str, Enum):
    """Enumeration of card categories."""
    STANDARD = "Standard"
    CLASSIC = "Classic"
    GOLD = "Gold"
    PLATINUM = "Platinum"
    TITANIUM = "Titanium"
    SIGNATURE = "Signature"
    INFINITE = "Infinite"
    WORLD = "World"
    WORLD_ELITE = "World Elite"
    BLACK = "Black"
    CENTURION = "Centurion"
    OTHER = "Other"


class CardType(str, Enum):
    """Type of credit card."""
    CASHBACK = "cashback"
    REWARDS = "rewards"
    TRAVEL = "travel"
    LIFESTYLE = "lifestyle"
    SHOPPING = "shopping"
    BUSINESS = "business"
    PREMIUM = "premium"
    ENTRY_LEVEL = "entry_level"
    CO_BRANDED = "co_branded"
    OTHER = "other"


class ExtractionMethod(str, Enum):
    """Enumeration of extraction methods."""
    LLM = "llm"
    ENHANCED_LLM = "enhanced_llm"
    FALLBACK = "fallback"
    HYBRID = "hybrid"
    MANUAL = "manual"


class ValidationStatus(str, Enum):
    """Enumeration of validation statuses."""
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    REQUIRES_REVIEW = "requires_review"
    PARTIAL = "partial"


class Currency(str, Enum):
    """Common currencies in UAE region."""
    AED = "AED"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    SAR = "SAR"
    OTHER = "OTHER"


# ============= CONDITION MODELS =============

class SpendCondition(BaseModel):
    """Spend-based condition for benefits/entitlements."""
    minimum_spend: Optional[float] = Field(None, description="Minimum spend amount")
    currency: Currency = Field(default=Currency.AED, description="Currency of spend")
    period: Frequency = Field(default=Frequency.MONTHLY, description="Time period for spend")
    spend_categories: List[str] = Field(default_factory=list, description="Categories that count toward spend")
    excluded_categories: List[str] = Field(default_factory=list, description="Categories excluded from spend")
    description: Optional[str] = Field(None, description="Human-readable description")


class EligibilityCondition(BaseModel):
    """Eligibility condition for a benefit or entitlement."""
    condition_type: str = Field(..., description="Type of condition")
    condition_value: str = Field(..., description="Value/threshold for condition")
    description: Optional[str] = Field(None, description="Human-readable description")
    is_mandatory: bool = Field(default=True, description="Whether this is mandatory")


class RedemptionRule(BaseModel):
    """Rules for redeeming a benefit or entitlement."""
    method: str = Field(..., description="How to redeem (e.g., 'card_payment', 'app', 'website')")
    instructions: Optional[str] = Field(None, description="Step-by-step instructions")
    booking_required: bool = Field(default=False, description="Whether advance booking is required")
    booking_channel: Optional[str] = Field(None, description="Where to book (e.g., 'app', 'phone', 'website')")
    promo_code: Optional[str] = Field(None, description="Promo code if applicable")
    terms_url: Optional[str] = Field(None, description="URL to detailed terms")


class CapLimit(BaseModel):
    """Cap/limit on a benefit."""
    cap_type: str = Field(..., description="Type of cap (e.g., 'amount', 'count', 'percentage')")
    cap_value: float = Field(..., description="Value of the cap")
    currency: Optional[Currency] = Field(None, description="Currency if monetary cap")
    period: Frequency = Field(default=Frequency.MONTHLY, description="Period for the cap")
    description: Optional[str] = Field(None, description="Human-readable description")


# ============= MAIN SUBDOCUMENT MODELS =============

class Benefit(BaseModel):
    """Comprehensive benefit subdocument schema."""
    benefit_id: str = Field(..., description="Unique identifier for the benefit")
    benefit_name: str = Field(..., description="Name of the benefit")
    benefit_type: BenefitType = Field(..., description="Type of benefit")
    
    # Value information
    benefit_value: Optional[str] = Field(None, description="Value of the benefit (e.g., '5%', 'AED 100')")
    benefit_value_numeric: Optional[float] = Field(None, description="Numeric value for calculations")
    value_type: Optional[str] = Field(None, description="Type of value (percentage, fixed, variable)")
    
    # Description
    description: str = Field(..., description="Full description of the benefit")
    short_description: Optional[str] = Field(None, description="Brief summary")
    
    # Conditions and eligibility
    conditions: List[str] = Field(default_factory=list, description="General conditions and limitations")
    spend_conditions: List[SpendCondition] = Field(default_factory=list, description="Spend-based conditions")
    eligibility_conditions: List[EligibilityCondition] = Field(default_factory=list, description="Eligibility requirements")
    
    # Categories and applicability
    eligible_categories: List[str] = Field(default_factory=list, description="Categories where benefit applies")
    excluded_categories: List[str] = Field(default_factory=list, description="Categories excluded from benefit")
    eligible_merchants: List[str] = Field(default_factory=list, description="Specific merchants where applicable")
    
    # Caps and limits
    caps: List[CapLimit] = Field(default_factory=list, description="Caps and limits on the benefit")
    frequency: Optional[Frequency] = Field(None, description="How often benefit can be used")
    max_usage: Optional[int] = Field(None, description="Maximum usage count")
    
    # Redemption
    redemption_rules: List[RedemptionRule] = Field(default_factory=list, description="How to redeem")
    auto_applied: bool = Field(default=False, description="Whether benefit is automatically applied")
    
    # Validity
    valid_from: Optional[datetime] = Field(None, description="Start date of validity")
    valid_until: Optional[datetime] = Field(None, description="End date of validity")
    is_promotional: bool = Field(default=False, description="Whether this is a promotional benefit")
    
    # Additional info
    terms_url: Optional[str] = Field(None, description="URL to full terms")
    additional_details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class Entitlement(BaseModel):
    """Comprehensive entitlement subdocument schema."""
    entitlement_id: str = Field(..., description="Unique identifier for the entitlement")
    entitlement_name: str = Field(..., description="Name of the entitlement")
    entitlement_type: EntitlementType = Field(..., description="Type of entitlement")
    
    # Description
    description: str = Field(..., description="Full description of the entitlement")
    short_description: Optional[str] = Field(None, description="Brief summary")
    
    # Value (for quantifiable entitlements)
    quantity: Optional[int] = Field(None, description="Number of uses/items included")
    quantity_per_period: Optional[str] = Field(None, description="E.g., '4 per month'")
    monetary_value: Optional[float] = Field(None, description="Monetary equivalent if applicable")
    currency: Optional[Currency] = Field(None, description="Currency for monetary value")
    
    # Conditions
    conditions: List[str] = Field(default_factory=list, description="Conditions for entitlement")
    spend_conditions: List[SpendCondition] = Field(default_factory=list, description="Spend requirements")
    eligibility_conditions: List[EligibilityCondition] = Field(default_factory=list, description="Eligibility requirements")
    
    # Usage details
    frequency: Optional[Frequency] = Field(None, description="Frequency of entitlement")
    caps: List[CapLimit] = Field(default_factory=list, description="Usage caps")
    
    # Where to use
    redemption_locations: List[str] = Field(default_factory=list, description="Where it can be redeemed")
    partner_networks: List[str] = Field(default_factory=list, description="Partner networks (e.g., 'LoungeKey', 'Priority Pass')")
    geographic_coverage: Optional[str] = Field(None, description="Geographic scope (e.g., 'UAE', 'Worldwide')")
    
    # Redemption
    redemption_rules: List[RedemptionRule] = Field(default_factory=list, description="How to redeem")
    
    # Validity
    valid_from: Optional[datetime] = Field(None, description="Start date")
    valid_until: Optional[datetime] = Field(None, description="End date")
    
    # Supplementary card holder access
    supplementary_access: bool = Field(default=False, description="Whether supplementary cardholders can use")
    supplementary_conditions: Optional[str] = Field(None, description="Conditions for supplementary access")
    
    # Fees if conditions not met
    fallback_fee: Optional[float] = Field(None, description="Fee charged if conditions not met")
    fallback_fee_currency: Optional[Currency] = Field(None, description="Currency for fallback fee")
    
    # Additional info
    terms_url: Optional[str] = Field(None, description="URL to full terms")
    additional_details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class MerchantOffer(BaseModel):
    """Specific offer at a merchant."""
    offer_id: Optional[str] = Field(None, description="Unique offer identifier")
    offer_type: str = Field(..., description="Type of offer (discount, cashback, bogo, etc.)")
    offer_value: str = Field(..., description="Value of offer (e.g., '20% off', 'AED 40 off')")
    offer_value_numeric: Optional[float] = Field(None, description="Numeric value")
    description: Optional[str] = Field(None, description="Offer description")
    conditions: List[str] = Field(default_factory=list, description="Offer conditions")
    minimum_spend: Optional[float] = Field(None, description="Minimum spend for offer")
    caps: List[CapLimit] = Field(default_factory=list, description="Caps on offer")
    valid_from: Optional[datetime] = Field(None, description="Start date")
    valid_until: Optional[datetime] = Field(None, description="End date")
    promo_code: Optional[str] = Field(None, description="Promo code if needed")


class Merchant(BaseModel):
    """Comprehensive merchant/vendor subdocument schema."""
    merchant_id: Optional[str] = Field(None, description="Unique merchant identifier")
    merchant_name: str = Field(..., description="Name of the merchant")
    merchant_category: MerchantCategory = Field(default=MerchantCategory.OTHER, description="Category of merchant")
    merchant_subcategory: Optional[str] = Field(None, description="Subcategory")
    
    # Brand information
    brand_name: Optional[str] = Field(None, description="Brand name if different from merchant name")
    parent_company: Optional[str] = Field(None, description="Parent company if applicable")
    
    # Offers
    offers: List[MerchantOffer] = Field(default_factory=list, description="Available offers")
    general_benefit: Optional[str] = Field(None, description="General benefit at this merchant")
    
    # Redemption
    redemption_method: Optional[str] = Field(None, description="How to redeem (e.g., 'card_payment', 'app')")
    redemption_instructions: Optional[str] = Field(None, description="Instructions for redemption")
    booking_required: bool = Field(default=False, description="Whether booking is required")
    booking_url: Optional[str] = Field(None, description="URL for booking")
    
    # Location details
    locations: List[str] = Field(default_factory=list, description="Specific locations")
    geographic_coverage: Optional[str] = Field(None, description="Geographic scope")
    is_online: bool = Field(default=False, description="Whether available online")
    website_url: Optional[str] = Field(None, description="Merchant website")
    app_name: Optional[str] = Field(None, description="App name if applicable")
    
    # Additional info
    additional_details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class Fee(BaseModel):
    """Individual fee item."""
    fee_name: str = Field(..., description="Name of the fee")
    fee_amount: Optional[float] = Field(None, description="Fee amount")
    fee_percentage: Optional[float] = Field(None, description="Fee as percentage")
    currency: Currency = Field(default=Currency.AED, description="Fee currency")
    frequency: Frequency = Field(default=Frequency.YEARLY, description="Fee frequency")
    description: Optional[str] = Field(None, description="Fee description")
    waiver_conditions: List[str] = Field(default_factory=list, description="Conditions for fee waiver")
    is_waivable: bool = Field(default=False, description="Whether fee can be waived")


class Fees(BaseModel):
    """Comprehensive fees structure."""
    # Main fees
    annual_fee: Optional[Fee] = Field(None, description="Annual fee details")
    joining_fee: Optional[Fee] = Field(None, description="Joining/activation fee")
    
    # Interest rates
    interest_rate_monthly: Optional[float] = Field(None, description="Monthly interest rate %")
    interest_rate_annual: Optional[float] = Field(None, description="Annual interest rate (APR) %")
    
    # Transaction fees
    foreign_transaction_fee: Optional[Fee] = Field(None, description="Foreign transaction fee")
    cash_advance_fee: Optional[Fee] = Field(None, description="Cash advance fee")
    balance_transfer_fee: Optional[Fee] = Field(None, description="Balance transfer fee")
    
    # Penalty fees
    late_payment_fee: Optional[Fee] = Field(None, description="Late payment fee")
    over_limit_fee: Optional[Fee] = Field(None, description="Over limit fee")
    returned_payment_fee: Optional[Fee] = Field(None, description="Returned payment fee")
    
    # Other fees
    supplementary_card_fee: Optional[Fee] = Field(None, description="Supplementary card fee")
    replacement_card_fee: Optional[Fee] = Field(None, description="Card replacement fee")
    statement_fee: Optional[Fee] = Field(None, description="Paper statement fee")
    
    # All fees list
    all_fees: List[Fee] = Field(default_factory=list, description="All fees in a list")
    
    # Additional
    fee_schedule_url: Optional[str] = Field(None, description="URL to full fee schedule")
    additional_fees: Optional[Dict[str, Any]] = Field(None, description="Other fees")


class Eligibility(BaseModel):
    """Comprehensive eligibility criteria."""
    # Income requirements - store both raw string and parsed value
    minimum_salary: Optional[Union[float, str]] = Field(None, description="Minimum salary requirement")
    minimum_salary_currency: Currency = Field(default=Currency.AED, description="Salary currency")
    minimum_salary_transfer: Optional[bool] = Field(None, description="Whether salary transfer is required")
    
    # For self-employed
    minimum_bank_balance: Optional[Union[float, str]] = Field(None, description="Minimum bank balance for self-employed")
    bank_balance_period: Optional[str] = Field(None, description="Period for bank balance (e.g., 'last 3 months')")
    
    # Age requirements
    minimum_age: Optional[Union[int, str]] = Field(None, description="Minimum age")
    maximum_age: Optional[Union[int, str]] = Field(None, description="Maximum age")
    
    # Employment
    employment_types: List[str] = Field(default_factory=list, description="Eligible employment types")
    employment_tenure: Optional[str] = Field(None, description="Minimum employment tenure")
    
    # Residency
    nationality_requirements: List[str] = Field(default_factory=list, description="Eligible nationalities")
    residency_requirements: List[str] = Field(default_factory=list, description="Residency requirements")
    uae_national_benefits: Optional[str] = Field(None, description="Special benefits for UAE nationals")
    
    # Credit
    credit_score_requirement: Optional[str] = Field(None, description="Credit score requirement")
    existing_relationship: Optional[bool] = Field(None, description="Whether existing bank relationship required")
    
    # Documents
    required_documents: List[str] = Field(default_factory=list, description="Required documents")
    
    def get_minimum_salary_numeric(self) -> Optional[float]:
        """Extract numeric value from minimum_salary, handling strings like 'AED 12000'."""
        if self.minimum_salary is None:
            return None
        if isinstance(self.minimum_salary, (int, float)):
            return float(self.minimum_salary)
        if isinstance(self.minimum_salary, str):
            import re
            # Remove currency codes and commas, extract number
            cleaned = re.sub(r'[A-Za-z,\s]+', '', self.minimum_salary)
            if cleaned:
                try:
                    return float(cleaned)
                except ValueError:
                    return None
        return None
    
    def get_minimum_bank_balance_numeric(self) -> Optional[float]:
        """Extract numeric value from minimum_bank_balance."""
        if self.minimum_bank_balance is None:
            return None
        if isinstance(self.minimum_bank_balance, (int, float)):
            return float(self.minimum_bank_balance)
        if isinstance(self.minimum_bank_balance, str):
            import re
            cleaned = re.sub(r'[A-Za-z,\s]+', '', self.minimum_bank_balance)
            if cleaned:
                try:
                    return float(cleaned)
                except ValueError:
                    return None
        return None
    
    def get_minimum_age_numeric(self) -> Optional[int]:
        """Extract numeric value from minimum_age."""
        if self.minimum_age is None:
            return None
        if isinstance(self.minimum_age, int):
            return self.minimum_age
        if isinstance(self.minimum_age, str):
            import re
            match = re.search(r'\d+', self.minimum_age)
            if match:
                return int(match.group())
        return None
    
    def get_maximum_age_numeric(self) -> Optional[int]:
        """Extract numeric value from maximum_age."""
        if self.maximum_age is None:
            return None
        if isinstance(self.maximum_age, int):
            return self.maximum_age
        if isinstance(self.maximum_age, str):
            import re
            match = re.search(r'\d+', self.maximum_age)
            if match:
                return int(match.group())
        return None
    
    # Additional
    additional_requirements: Optional[Dict[str, Any]] = Field(None, description="Other requirements")


class InsuranceCoverage(BaseModel):
    """Insurance coverage details."""
    coverage_name: str = Field(..., description="Name of coverage")
    coverage_type: str = Field(..., description="Type of coverage")
    coverage_amount: Optional[float] = Field(None, description="Coverage amount")
    currency: Currency = Field(default=Currency.AED, description="Currency")
    description: Optional[str] = Field(None, description="Coverage description")
    conditions: List[str] = Field(default_factory=list, description="Conditions")
    exclusions: List[str] = Field(default_factory=list, description="Exclusions")


class CardIssuerInfo(BaseModel):
    """Information about the card issuer."""
    bank_name: str = Field(..., description="Name of the issuing bank")
    bank_code: Optional[str] = Field(None, description="Bank code/identifier")
    country: str = Field(default="UAE", description="Country of issuer")
    website: Optional[str] = Field(None, description="Bank website")
    customer_service_phone: Optional[str] = Field(None, description="Customer service number")
    customer_service_email: Optional[str] = Field(None, description="Customer service email")


class HistoryEntry(BaseModel):
    """History entry for tracking changes."""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = Field(default="system")
    changes: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(default="2.0")


class SourceDocument(BaseModel):
    """Represents a source document (PDF, webpage, etc.) that was processed."""
    document_id: str = Field(..., description="Unique identifier for this document")
    document_type: str = Field(..., description="Type: 'webpage', 'pdf', 'key_facts', 'terms_conditions'")
    url: str = Field(..., description="URL or path to the document")
    title: Optional[str] = Field(None, description="Document title")
    
    # Content summary
    content_length: int = Field(default=0, description="Length of extracted content")
    content_preview: Optional[str] = Field(None, description="First 500 chars of content")
    
    # What was extracted from this document
    extracted_benefits: List[str] = Field(default_factory=list, description="Benefits found in this doc")
    extracted_fees: List[str] = Field(default_factory=list, description="Fees found in this doc")
    extracted_terms: List[str] = Field(default_factory=list, description="Terms found in this doc")
    extracted_eligibility: List[str] = Field(default_factory=list, description="Eligibility info found")
    
    # Processing status
    fetch_status: str = Field(default="success", description="success, failed, skipped")
    fetch_error: Optional[str] = Field(None, description="Error message if failed")
    processing_time_ms: Optional[int] = Field(None, description="Time to process this doc")
    
    # Metadata
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    content_hash: Optional[str] = Field(None, description="Hash of content for deduplication")


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process."""
    extraction_timestamp: Optional[datetime] = None
    content_length: Optional[int] = None
    processing_time_ms: Optional[int] = None
    llm_model_used: Optional[str] = None
    llm_temperature: Optional[float] = None
    source_hash: Optional[str] = None
    pages_scraped: int = Field(default=1)
    links_followed: int = Field(default=0)
    pdfs_processed: int = Field(default=0)
    tables_extracted: int = Field(default=0)
    version: int = Field(default=1)
    extraction_notes: List[str] = Field(default_factory=list)
    custom_fields: Optional[Dict[str, Any]] = None


# ============= MAIN DOCUMENT MODEL =============

class ExtractedDataV2(Document):
    """
    Enhanced document model for extracted credit card data.
    Version 2.0 with comprehensive schema for UAE credit cards.
    """
    # Source information
    source_url: Optional[str] = Field(None, description="Source URL if extracted from web")
    source_urls: List[str] = Field(default_factory=list, description="All URLs scraped")
    source_type: SourceType = Field(..., description="Type of source")
    source_documents: List[SourceDocument] = Field(default_factory=list, description="All source documents processed")
    
    # Card identification
    card_name: str = Field(..., description="Full name of the credit card")
    card_name_arabic: Optional[str] = Field(None, description="Arabic name if available")
    card_slug: Optional[str] = Field(None, description="URL-friendly identifier")
    
    # Issuer information
    card_issuer: CardIssuerInfo = Field(..., description="Card issuing bank information")
    
    # Card classification
    card_network: Optional[CardNetwork] = Field(None, description="Card network")
    card_networks: List[CardNetwork] = Field(default_factory=list, description="Multiple networks if combo card")
    card_category: Optional[CardCategory] = Field(None, description="Card category/tier")
    card_type: Optional[CardType] = Field(None, description="Type of card")
    is_combo_card: bool = Field(default=False, description="Whether this is a combo card (e.g., Duo)")
    combo_cards: List[str] = Field(default_factory=list, description="Names of cards in combo")
    
    # Benefits and features
    benefits: List[Benefit] = Field(default_factory=list, description="List of benefits")
    entitlements: List[Entitlement] = Field(default_factory=list, description="List of entitlements")
    
    # Merchants and partners
    merchants_vendors: List[Merchant] = Field(default_factory=list, description="Partner merchants")
    partner_programs: List[str] = Field(default_factory=list, description="Partner programs (e.g., 'LoungeKey')")
    
    # Fees and charges
    fees: Fees = Field(default_factory=Fees, description="Fee structure")
    
    # Eligibility
    eligibility: Eligibility = Field(default_factory=Eligibility, description="Eligibility criteria")
    
    # Insurance and protection
    insurance_coverage: List[InsuranceCoverage] = Field(default_factory=list, description="Insurance coverages")
    
    # Rewards program
    rewards_program_name: Optional[str] = Field(None, description="Name of rewards program")
    rewards_earn_rate: Optional[str] = Field(None, description="Base rewards earn rate")
    rewards_redemption_options: List[str] = Field(default_factory=list, description="How rewards can be redeemed")
    
    # Credit limit
    credit_limit_min: Optional[float] = Field(None, description="Minimum credit limit")
    credit_limit_max: Optional[float] = Field(None, description="Maximum credit limit")
    
    # Application
    application_url: Optional[str] = Field(None, description="URL to apply")
    application_process: Optional[str] = Field(None, description="Description of application process")
    
    # Extraction metadata
    extraction_method: ExtractionMethod = Field(
        default=ExtractionMethod.FALLBACK,
        description="Method used for extraction"
    )
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Confidence score")
    extraction_metadata: ExtractionMetadata = Field(
        default_factory=ExtractionMetadata,
        description="Extraction process metadata"
    )
    
    # Validation
    validation_status: ValidationStatus = Field(
        default=ValidationStatus.PENDING,
        description="Validation status"
    )
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors")
    validation_warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    completeness_score: Optional[float] = Field(None, ge=0, le=1, description="Data completeness score")
    
    # Tags and categorization
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    regions: List[str] = Field(default_factory=list, description="Applicable regions")
    
    # Raw data storage
    raw_extracted_text: Optional[str] = Field(None, description="Raw text that was extracted")
    raw_llm_response: Optional[Dict[str, Any]] = Field(None, description="Raw LLM response")
    
    # Version control
    schema_version: str = Field(default="2.0", description="Schema version")
    history: List[HistoryEntry] = Field(default_factory=list, description="Change history")
    
    # Soft delete
    is_deleted: bool = Field(default=False, description="Soft delete flag")
    deleted_at: Optional[datetime] = Field(None, description="Deletion timestamp")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_verified_at: Optional[datetime] = Field(None, description="Last manual verification")

    class Settings:
        name = "extracted_data_v2"
        indexes = [
            # Text search
            IndexModel([
                ("card_name", TEXT),
                ("benefits.description", TEXT),
                ("entitlements.description", TEXT),
                ("merchants_vendors.merchant_name", TEXT),
            ]),
            # Basic lookups
            IndexModel([("card_name", ASCENDING)]),
            IndexModel([("card_issuer.bank_name", ASCENDING)]),
            IndexModel([("card_network", ASCENDING)]),
            IndexModel([("card_category", ASCENDING)]),
            IndexModel([("card_type", ASCENDING)]),
            # Benefits
            IndexModel([("benefits.benefit_type", ASCENDING)]),
            IndexModel([("benefits.benefit_name", ASCENDING)]),
            # Entitlements
            IndexModel([("entitlements.entitlement_type", ASCENDING)]),
            # Merchants
            IndexModel([("merchants_vendors.merchant_name", ASCENDING)]),
            IndexModel([("merchants_vendors.merchant_category", ASCENDING)]),
            # Eligibility
            IndexModel([("eligibility.minimum_salary", ASCENDING)]),
            # Status and timestamps
            IndexModel([("validation_status", ASCENDING)]),
            IndexModel([("confidence_score", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("updated_at", DESCENDING)]),
            IndexModel([("is_deleted", ASCENDING)]),
            # Composite indexes
            IndexModel([("card_issuer.bank_name", ASCENDING), ("card_category", ASCENDING)]),
            IndexModel([("is_deleted", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("validation_status", ASCENDING), ("confidence_score", DESCENDING)]),
            IndexModel([("card_network", ASCENDING), ("card_type", ASCENDING)]),
        ]

    @before_event(Replace, Insert)
    async def update_timestamp(self):
        """Update the updated_at timestamp before saving."""
        self.updated_at = datetime.utcnow()
        
        # Generate slug if not present
        if not self.card_slug and self.card_name:
            self.card_slug = self.card_name.lower().replace(' ', '-').replace('/', '-')

    def add_to_history(self, changes: Dict[str, Any], updated_by: str = "system"):
        """Add an entry to the document history."""
        history_entry = HistoryEntry(
            updated_at=datetime.utcnow(),
            updated_by=updated_by,
            changes=changes,
            schema_version=self.schema_version
        )
        self.history.append(history_entry)

    async def soft_delete(self):
        """Soft delete the document."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        await self.save()

    async def restore(self):
        """Restore a soft-deleted document."""
        self.is_deleted = False
        self.deleted_at = None
        await self.save()

    def calculate_completeness_score(self) -> float:
        """Calculate how complete the extracted data is."""
        total_fields = 0
        filled_fields = 0
        
        # Core fields (weighted higher)
        core_checks = [
            (self.card_name and len(self.card_name) > 3, 2),
            (self.card_issuer is not None, 2),
            (len(self.benefits) > 0, 3),
            (len(self.entitlements) > 0, 2),
            (len(self.merchants_vendors) > 0, 2),
            (self.fees.annual_fee is not None, 1),
            (self.eligibility.minimum_salary is not None, 1),
            (self.card_network is not None, 1),
            (self.card_category is not None, 1),
        ]
        
        for check, weight in core_checks:
            total_fields += weight
            if check:
                filled_fields += weight
        
        # Benefit quality
        if self.benefits:
            benefit_quality = sum(
                1 for b in self.benefits 
                if b.description and len(b.description) > 20 and len(b.conditions) > 0
            ) / len(self.benefits)
            filled_fields += benefit_quality * 2
            total_fields += 2
        
        self.completeness_score = filled_fields / total_fields if total_fields > 0 else 0
        return self.completeness_score

    @classmethod
    async def find_active(cls, **kwargs):
        """Find active (non-deleted) documents."""
        return cls.find({"is_deleted": False, **kwargs})

    @classmethod
    async def search_cards(cls, search_text: str, limit: int = 20):
        """Search cards using text search."""
        return await cls.find(
            {"$text": {"$search": search_text}, "is_deleted": False}
        ).limit(limit).to_list()

    @classmethod
    async def find_by_benefit_type(cls, benefit_type: BenefitType, limit: int = 50):
        """Find cards by benefit type."""
        return await cls.find(
            {"benefits.benefit_type": benefit_type.value, "is_deleted": False}
        ).limit(limit).to_list()

    @classmethod
    async def find_by_merchant(cls, merchant_name: str, limit: int = 50):
        """Find cards by merchant name."""
        return await cls.find(
            {
                "merchants_vendors.merchant_name": {"$regex": merchant_name, "$options": "i"},
                "is_deleted": False
            }
        ).limit(limit).to_list()

    @classmethod
    async def find_by_bank(cls, bank_name: str, limit: int = 50):
        """Find cards by issuing bank."""
        return await cls.find(
            {
                "card_issuer.bank_name": {"$regex": bank_name, "$options": "i"},
                "is_deleted": False
            }
        ).limit(limit).to_list()

    @classmethod
    async def find_by_eligibility(cls, max_salary: float, currency: Currency = Currency.AED, limit: int = 50):
        """Find cards where minimum salary is at or below the given amount.
        
        Note: This query works best when minimum_salary is stored as a number.
        If stored as string (e.g., 'AED 12000'), the comparison may not work as expected.
        Consider using regex or aggregation pipeline for string values.
        """
        return await cls.find(
            {
                "$or": [
                    {"eligibility.minimum_salary": {"$lte": max_salary}},
                    {"eligibility.minimum_salary": None},
                    {"eligibility.minimum_salary": {"$exists": False}}
                ],
                "eligibility.minimum_salary_currency": currency.value,
                "is_deleted": False
            }
        ).limit(limit).to_list()
