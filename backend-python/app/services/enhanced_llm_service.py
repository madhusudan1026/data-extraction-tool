"""
Enhanced LLM Service for Credit Card Data Extraction.
Features:
- Credit card specific extraction prompts
- Multi-stage extraction pipeline
- Bank-specific parsing strategies
- Structured output validation
- Support for both Ollama and OpenAI-compatible APIs
"""
from typing import Optional, Dict, Any, List, Tuple
import json
import re
import asyncio
import hashlib

from app.core.config import settings
from app.core.exceptions import LLMError
from app.utils.logger import logger
from app.services.cache_service import cache_service
from app.services.ollama_client import ollama_client, parse_llm_json


class EnhancedLLMService:
    """Enhanced service for LLM-based credit card data extraction."""

    def __init__(self):
        # Base Ollama URL (without endpoint path)
        self.ollama_base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        # Legacy endpoint setting (for backward compatibility)
        legacy_endpoint = getattr(settings, 'OLLAMA_URL', None)
        if legacy_endpoint and '/api/' in legacy_endpoint:
            # Extract base URL from legacy setting
            self.ollama_base_url = legacy_endpoint.rsplit('/api/', 1)[0]
        
        self.model = getattr(settings, 'DEFAULT_MODEL', 'llama3')
        self.temperature = getattr(settings, 'DEFAULT_TEMPERATURE', 0.1)
        self.timeout = getattr(settings, 'LLM_TIMEOUT', 120)
        self.max_retries = getattr(settings, 'LLM_MAX_RETRIES', 3)
        self.num_predict = getattr(settings, 'LLM_NUM_PREDICT', 4096)
        
        # OpenAI-compatible endpoint (optional)
        self.openai_endpoint = getattr(settings, 'OPENAI_API_URL', None)
        self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        
        logger.info(f"EnhancedLLMService initialized: base_url={self.ollama_base_url}, model={self.model}")

    async def extract_credit_card_data(
        self,
        content: str,
        config: Optional[Dict[str, Any]] = None,
        bank_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract comprehensive credit card data from content.

        Args:
            content: Text content to extract from (formatted by enhanced scraper).
            config: Optional configuration override.
            bank_name: Optional bank name for specialized extraction.

        Returns:
            Comprehensive extracted data matching the V2 schema.
        """
        config = config or {}
        # Filter out None values so defaults are used
        model = config.get("model") or self.model
        temperature = config.get("temperature") if config.get("temperature") is not None else self.temperature
        bypass_cache = config.get("bypass_cache", False)
        
        logger.info(f"Starting extraction with model={model}, temperature={temperature}")

        # Generate content hash for caching
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]

        # Check cache
        if not bypass_cache:
            cached = await cache_service.get_llm_response(content_hash, model)
            if cached:
                logger.info("Returning cached LLM extraction result")
                return cached

        # Use simple single-stage extraction for better performance with local models
        try:
            result = await self._extract_simple(content, model, temperature)
            
            # Normalize and validate
            self._normalize_data(result)
            
            # Cache the result
            await cache_service.cache_llm_response(content_hash, model, result)
            
            logger.info(
                "LLM extraction successful",
                extra={
                    "benefits_count": len(result.get("benefits", [])),
                    "merchants_count": len(result.get("merchants_vendors", [])),
                }
            )
            
            return result

        except Exception as e:
            logger.error(f"Enhanced LLM extraction failed: {str(e)}")
            raise LLMError(f"Extraction failed: {str(e)}")

    # Model-specific content limits
    MODEL_CONTENT_LIMITS = {
        "phi": 2000,
        "phi3": 6000,
        "llama3.2": 8000,
        "llama2": 6000,
        "mistral": 8000,
        "gemma": 6000,
        "default": 6000,
    }

    def _get_max_content_length(self) -> int:
        """Get the max content length for the current model."""
        return self.MODEL_CONTENT_LIMITS.get(self.model, self.MODEL_CONTENT_LIMITS["default"])

    def _extract_relevant_sections(self, content: str, max_chars: int) -> str:
        """
        Smart content extraction: prioritize benefit-rich sections over blind truncation.
        
        Instead of content[:2000], this method:
        1. Removes navigation/footer noise
        2. Scores sections by keyword density
        3. Returns the most relevant content up to max_chars
        """
        if len(content) <= max_chars:
            return content
        
        # Remove common noise
        noise_patterns = [
            r'(?i)choose your language.*?(?=\n\n|\Z)',
            r'(?i)copyright.*?(?=\n|\Z)',
            r'(?i)privacy policy.*?(?=\n|\Z)',
            r'(?i)terms and conditions\s*$',
            r'(?i)cookie\s*(?:policy|consent).*?(?=\n\n|\Z)',
            r'\n\s*\|\s*\n',
            r'\n\s*عربي\s*\n',
        ]
        
        cleaned = content
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '\n', cleaned, flags=re.IGNORECASE)
        
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        
        if len(cleaned) <= max_chars:
            return cleaned.strip()
        
        # Score sections by benefit keyword density
        benefit_keywords = [
            'cashback', 'cash back', 'lounge', 'airport', 'golf', 'movie', 'cinema',
            'insurance', 'travel', 'dining', 'reward', 'points', 'miles',
            'complimentary', 'free', 'discount', '%', 'aed', 'annual fee',
            'minimum salary', 'eligibility', 'concierge', 'valet',
            'offer', 'benefit', 'feature', 'entitlement', 'privilege',
        ]
        
        sections = cleaned.split('\n\n')
        scored_sections = []
        
        for section in sections:
            if len(section.strip()) < 20:
                continue
            
            section_lower = section.lower()
            score = sum(1 for kw in benefit_keywords if kw in section_lower)
            
            # Boost sections with monetary values (strong signal of benefit details)
            if re.search(r'(?:aed|usd)\s*[\d,]+|\d+%', section_lower):
                score += 3
            
            scored_sections.append((score, section))
        
        # Sort by score (highest first) and reconstruct
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        
        result_parts = []
        current_length = 0
        
        for score, section in scored_sections:
            if current_length + len(section) + 2 <= max_chars:
                result_parts.append(section)
                current_length += len(section) + 2
            elif current_length == 0:
                result_parts.append(section[:max_chars])
                break
        
        return '\n\n'.join(result_parts).strip()

    async def _extract_simple(
        self,
        content: str,
        model: str,
        temperature: float
    ) -> Dict[str, Any]:
        """
        Single-stage extraction with smart content selection.
        
        Key improvements over original:
        - Uses model-appropriate content length (not hardcoded 2000)
        - Smart section extraction prioritizes benefit-rich content
        - More structured prompt with explicit schema guidance
        """
        
        # Use model-appropriate content limit instead of hardcoded 2000
        max_content = self.MODEL_CONTENT_LIMITS.get(model, self.MODEL_CONTENT_LIMITS["default"])
        
        # Smart extraction: prioritize benefit-rich sections
        relevant_content = self._extract_relevant_sections(content, max_content)
        
        logger.info(f"Content: {len(content)} chars original -> {len(relevant_content)} chars after smart extraction (limit: {max_content})")
        
        prompt = f"""You are a UAE credit card data extraction specialist. Extract ALL benefits, fees, and features from this credit card content.

CONTENT:
{relevant_content}

Extract and return ONLY a valid JSON object with this structure:
{{
  "card_name": "full card name",
  "card_issuer": {{"bank_name": "bank name", "country": "UAE"}},
  "card_network": "Visa/Mastercard/Amex",
  "card_category": "Standard/Gold/Platinum/Signature/Infinite/World",
  "card_type": "cashback/rewards/travel/lifestyle",
  "benefits": [
    {{
      "benefit_id": "benefit_1",
      "benefit_name": "name of benefit",
      "benefit_type": "cashback/discount/lounge_access/rewards_points/travel/dining/entertainment/insurance/complimentary/other",
      "benefit_value": "e.g. 5% or AED 100 or Free or 4 visits",
      "description": "detailed description",
      "conditions": ["list of conditions"],
      "eligible_categories": ["grocery", "dining", "fuel", "travel", "shopping", "general"]
    }}
  ],
  "entitlements": [
    {{
      "entitlement_id": "entitlement_1",
      "entitlement_name": "name",
      "entitlement_type": "lounge_access/valet_parking/concierge/golf_access/movie_tickets/airport_transfer/other",
      "description": "description",
      "quantity": null,
      "conditions": ["conditions"]
    }}
  ],
  "fees": {{
    "annual_fee": {{"fee_amount": 0, "currency": "AED", "waiver_conditions": []}},
    "interest_rate_annual": null,
    "foreign_transaction_fee": null,
    "late_payment_fee": null
  }},
  "eligibility": {{
    "minimum_salary": null,
    "minimum_salary_currency": "AED",
    "minimum_age": null,
    "employment_types": []
  }},
  "merchants_vendors": [
    {{
      "merchant_name": "name",
      "merchant_category": "supermarket/restaurant/travel/fuel/entertainment/other",
      "offers": [{{"offer_type": "discount/cashback", "offer_value": "value", "description": "desc"}}]
    }}
  ],
  "insurance_coverage": [
    {{
      "coverage_name": "name",
      "coverage_type": "travel/purchase/other",
      "coverage_amount": null,
      "currency": "AED"
    }}
  ]
}}

IMPORTANT: Extract EVERY benefit you can find. Look for cashback rates, lounge access, golf privileges, movie tickets, insurance coverage, reward points, dining offers, travel benefits, concierge services, valet parking, and any complimentary services. Return ONLY valid JSON.

JSON:"""

        logger.info(f"Extraction prompt length: {len(prompt)} chars, model: {model}")
        return await self._call_llm(prompt, model, temperature)

    async def _call_llm(
        self,
        prompt: str,
        model: str,
        temperature: float
    ) -> Dict[str, Any]:
        """Make LLM API call via shared Ollama client, then parse JSON."""
        
        raw = await ollama_client.generate(
            prompt,
            model=model,
            temperature=temperature,
            num_predict=self.num_predict,
            timeout=self.timeout,
            max_retries=self.max_retries,
            caller="enhanced_llm",
        )
        
        if raw is None:
            raise LLMError("LLM call returned no response after all retries")
        
        logger.debug(f"LLM raw response: {raw[:500]}...")
        
        parsed = parse_llm_json(raw)
        if parsed is None:
            raise LLMError("No valid JSON found in LLM response")
        return parsed

    def _merge_extraction_stages(
        self,
        basic_data: Dict[str, Any],
        detailed_data: Dict[str, Any],
        eligibility_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge data from all extraction stages."""
        merged = {}
        
        # Stage 1: Basic data
        for key in ['card_name', 'card_issuer', 'card_network', 'card_networks',
                    'card_category', 'card_type', 'is_combo_card', 'combo_cards',
                    'benefits', 'entitlements', 'rewards_program_name', 'rewards_earn_rate']:
            if key in basic_data and basic_data[key]:
                merged[key] = basic_data[key]
        
        # Stage 2: Details
        for key in ['merchants_vendors', 'partner_programs', 'fees', 'insurance_coverage']:
            if key in detailed_data and detailed_data[key]:
                merged[key] = detailed_data[key]
        
        # Stage 3: Eligibility
        for key in ['eligibility', 'credit_limit_min', 'credit_limit_max',
                    'application_url', 'application_process', 'general_terms',
                    'promotional_offers']:
            if key in eligibility_data and eligibility_data[key]:
                merged[key] = eligibility_data[key]
        
        return merged

    def _normalize_data(self, data: Dict[str, Any]) -> None:
        """Normalize extracted data to ensure schema compliance."""
        
        # Valid enum values
        valid_benefit_types = [
            "cashback", "discount", "lounge_access", "travel", "dining",
            "shopping", "entertainment", "lifestyle", "insurance", "concierge",
            "rewards_points", "complimentary", "other"
        ]
        
        valid_entitlement_types = [
            "lounge_access", "airport_transfer", "valet_parking", "concierge",
            "golf_access", "spa_access", "movie_tickets", "roadside_assistance",
            "travel_insurance", "purchase_protection", "extended_warranty", "other"
        ]
        
        valid_merchant_categories = [
            "supermarket", "grocery", "restaurant", "fast_food", "cafe",
            "fashion", "electronics", "travel", "hotel", "airline", "fuel",
            "entertainment", "cinema", "online", "department_store", "pharmacy",
            "education", "healthcare", "utilities", "other"
        ]
        
        valid_frequencies = [
            "per_transaction", "daily", "weekly", "monthly", "quarterly",
            "yearly", "unlimited", "one_time", "other"
        ]
        
        # Normalize benefits
        if isinstance(data.get("benefits"), list):
            for i, benefit in enumerate(data["benefits"]):
                # Add ID if missing
                if "benefit_id" not in benefit or not benefit["benefit_id"]:
                    benefit["benefit_id"] = f"benefit_{i + 1}"
                
                # Normalize benefit_type
                if "benefit_type" in benefit:
                    bt = str(benefit["benefit_type"]).lower().replace(" ", "_")
                    if bt not in valid_benefit_types:
                        # Try to map
                        if "cash" in bt:
                            bt = "cashback"
                        elif "discount" in bt or "off" in bt:
                            bt = "discount"
                        elif "lounge" in bt:
                            bt = "lounge_access"
                        elif "travel" in bt:
                            bt = "travel"
                        elif "dine" in bt or "restaurant" in bt or "food" in bt:
                            bt = "dining"
                        elif "shop" in bt or "retail" in bt:
                            bt = "shopping"
                        elif "movie" in bt or "cinema" in bt or "entertainment" in bt:
                            bt = "entertainment"
                        elif "point" in bt or "reward" in bt:
                            bt = "rewards_points"
                        elif "free" in bt or "complimentary" in bt:
                            bt = "complimentary"
                        else:
                            bt = "other"
                    benefit["benefit_type"] = bt
                else:
                    benefit["benefit_type"] = "other"
                
                # Ensure arrays exist
                for array_field in ["conditions", "eligible_categories", "excluded_categories", 
                                   "caps", "spend_conditions", "eligible_merchants"]:
                    if array_field not in benefit or not isinstance(benefit[array_field], list):
                        benefit[array_field] = []
                
                # Normalize frequency
                if "frequency" in benefit and benefit["frequency"]:
                    freq = str(benefit["frequency"]).lower().replace(" ", "_")
                    if freq not in valid_frequencies:
                        benefit["frequency"] = "other"
        
        # Normalize entitlements
        if isinstance(data.get("entitlements"), list):
            for i, entitlement in enumerate(data["entitlements"]):
                if "entitlement_id" not in entitlement or not entitlement["entitlement_id"]:
                    entitlement["entitlement_id"] = f"entitlement_{i + 1}"
                
                if "entitlement_type" in entitlement:
                    et = str(entitlement["entitlement_type"]).lower().replace(" ", "_")
                    if et not in valid_entitlement_types:
                        if "lounge" in et:
                            et = "lounge_access"
                        elif "transfer" in et or "airport" in et:
                            et = "airport_transfer"
                        elif "valet" in et or "parking" in et:
                            et = "valet_parking"
                        elif "concierge" in et:
                            et = "concierge"
                        elif "golf" in et:
                            et = "golf_access"
                        elif "movie" in et or "cinema" in et:
                            et = "movie_tickets"
                        elif "road" in et or "assist" in et:
                            et = "roadside_assistance"
                        elif "insurance" in et:
                            et = "travel_insurance"
                        else:
                            et = "other"
                    entitlement["entitlement_type"] = et
                else:
                    entitlement["entitlement_type"] = "other"
                
                for array_field in ["conditions", "spend_conditions", "redemption_locations", "partner_networks"]:
                    if array_field not in entitlement or not isinstance(entitlement[array_field], list):
                        entitlement[array_field] = []
        
        # Normalize merchants
        if isinstance(data.get("merchants_vendors"), list):
            for merchant in data["merchants_vendors"]:
                if "merchant_category" in merchant:
                    mc = str(merchant["merchant_category"]).lower().replace(" ", "_")
                    if mc not in valid_merchant_categories:
                        if "super" in mc or "grocer" in mc:
                            mc = "supermarket"
                        elif "restaurant" in mc or "dine" in mc:
                            mc = "restaurant"
                        elif "fashion" in mc or "cloth" in mc:
                            mc = "fashion"
                        elif "cinema" in mc or "movie" in mc:
                            mc = "cinema"
                        elif "travel" in mc or "airline" in mc or "hotel" in mc:
                            mc = "travel"
                        elif "online" in mc or "e-commerce" in mc:
                            mc = "online"
                        else:
                            mc = "other"
                    merchant["merchant_category"] = mc
                else:
                    merchant["merchant_category"] = "other"
                
                if "offers" not in merchant or not isinstance(merchant["offers"], list):
                    merchant["offers"] = []
        
        # Ensure top-level structures exist
        if "fees" not in data or not isinstance(data["fees"], dict):
            data["fees"] = {}
        
        if "eligibility" not in data or not isinstance(data["eligibility"], dict):
            data["eligibility"] = {}
        
        if "benefits" not in data:
            data["benefits"] = []
        
        if "entitlements" not in data:
            data["entitlements"] = []
        
        if "merchants_vendors" not in data:
            data["merchants_vendors"] = []
        
        if "insurance_coverage" not in data:
            data["insurance_coverage"] = []

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to LLM via shared client."""
        return await ollama_client.test_connection()


# Global instance
enhanced_llm_service = EnhancedLLMService()