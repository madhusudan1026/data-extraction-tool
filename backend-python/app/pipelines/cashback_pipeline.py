"""
Cashback Benefits Pipeline

Extracts cashback-related benefits including:
- Percentage cashback rates
- Category-specific cashback
- Merchant-specific cashback
- Cashback caps and limits
- Minimum spend requirements

Processing: LLM-first extraction with regex pattern fallback for each source.
"""

import re
import uuid
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions, sanitize_merchants


class CashbackPipeline(BasePipeline):
    """Pipeline for extracting cashback benefits."""
    
    name = "cashback"
    benefit_type = "cashback"
    description = "Extracts cashback rates, categories, caps, and conditions"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'cashback', 'cash-back', 'rebate', 'rewards-cashback',
        'earn-back', 'money-back'
    ]
    
    keywords = [
        'cashback', 'cash back', 'cash-back',
        'earn back', 'money back',
        'rebate', 'refund',
        'return', 'savings',
        '%', 'percent',
        'grocery', 'groceries', 'supermarket',
        'dining', 'restaurant', 'food',
        'fuel', 'petrol', 'gas station',
        'shopping', 'retail', 'online',
        'travel', 'airline', 'hotel',
        'utility', 'utilities', 'bills',
        'education', 'school', 'tuition',
        'healthcare', 'medical', 'pharmacy',
    ]
    
    negative_keywords = [
        'no cashback',
        'cashback not applicable',
        'excluded from cashback',
    ]
    
    patterns = {
        # Match "X% cashback on Y"
        'percentage_cashback': r'(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:cash\s*back|cashback|cb)\s*(?:on|for|at)?\s*(?P<category>[a-zA-Z\s]{3,30})?',
        
        # Match "cashback of X%"
        'cashback_of': r'(?:cash\s*back|cashback)\s*(?:of|up to|upto)?\s*(?P<value>\d+(?:\.\d+)?)\s*%',
        
        # Match "earn X% on Y"
        'earn_percentage': r'earn\s*(?:up to|upto)?\s*(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:cash\s*back|cashback|cb)?\s*(?:on|for|at)?\s*(?P<category>[a-zA-Z\s]{3,30})?',
        
        # Match "AED X cashback"
        'fixed_cashback': r'(?:aed|usd|eur|\$)\s*(?P<value>\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:cash\s*back|cashback)',
        
        # Match cashback caps "up to AED X"
        'cashback_cap': r'(?:up to|upto|maximum|max|capped at)\s*(?:aed|usd|\$)?\s*(?P<value>\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:cash\s*back|cashback|per month|monthly|per year|annually)?',
        
        # Match minimum spend "minimum spend of AED X"
        'minimum_spend': r'(?:minimum|min)\s*(?:spend|spending|purchase)\s*(?:of|:)?\s*(?:aed|usd|\$)?\s*(?P<value>\d+(?:,\d{3})*(?:\.\d{2})?)',
    }
    
    # Category mapping for normalization
    CATEGORY_MAP = {
        'grocery': ['grocery', 'groceries', 'supermarket', 'hypermarket', 'carrefour', 'lulu'],
        'dining': ['dining', 'restaurant', 'food', 'cafe', 'coffee', 'eat'],
        'fuel': ['fuel', 'petrol', 'gas', 'gas station', 'filling station', 'adnoc', 'enoc'],
        'travel': ['travel', 'airline', 'hotel', 'booking', 'flight', 'emirates', 'etihad'],
        'shopping': ['shopping', 'retail', 'online', 'e-commerce', 'ecommerce', 'amazon', 'noon'],
        'utilities': ['utility', 'utilities', 'bills', 'electricity', 'water', 'telecom', 'dewa', 'du', 'etisalat'],
        'education': ['education', 'school', 'tuition', 'university', 'college'],
        'healthcare': ['healthcare', 'medical', 'pharmacy', 'hospital', 'clinic'],
        'entertainment': ['entertainment', 'cinema', 'movies', 'streaming', 'netflix'],
        'international': ['international', 'overseas', 'foreign', 'abroad'],
    }
    
    def _normalize_category(self, category: str) -> str:
        """Normalize category names to standard values."""
        if not category:
            return 'general'
        
        category_lower = category.lower().strip()
        
        for standard, variants in self.CATEGORY_MAP.items():
            if any(v in category_lower for v in variants):
                return standard
        
        return category_lower if len(category_lower) > 2 else 'general'
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        """Generate LLM prompt for extracting cashback benefits."""
        ctx = self.format_card_context(card_context)
        return f"""You are analyzing credit card content to extract cashback benefits.

{ctx}Source: {title}
URL: {url}

Content to analyze:
{content}

Extract ALL cashback benefits mentioned. For each cashback benefit, provide:
- rate: The cashback percentage (e.g., "5%") or fixed amount (e.g., "AED 50")
- category: What type of purchases (grocery, dining, fuel, travel, shopping, utilities, education, healthcare, entertainment, international, general)
- conditions: List of conditions/requirements (minimum spend, card type, time period)
- cap: Maximum cashback limit if mentioned (e.g., "AED 500 per month")
- merchants: Specific merchants if mentioned (e.g., ["Carrefour", "Lulu"])

Respond ONLY with a valid JSON object:
{{"cashback_benefits": [
  {{"rate": "5%", "category": "dining", "conditions": ["minimum spend AED 100"], "cap": "AED 500/month", "merchants": []}},
  {{"rate": "2%", "category": "general", "conditions": [], "cap": null, "merchants": []}}
]}}

If no cashback benefits found, respond with: {{"cashback_benefits": []}}

JSON:"""
    
    def parse_llm_response(
        self, 
        response: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """Parse LLM response into cashback benefits."""
        benefits = []
        parsed = self._parse_llm_json(response)
        
        if not parsed:
            return benefits
        
        items = parsed.get('cashback_benefits') or parsed.get('items', [])
        if isinstance(items, dict):
            items = [items]
        
        for item in items:
            if not isinstance(item, dict):
                continue
                
            rate = str(item.get('rate', ''))
            if not rate:
                continue
            
            # Parse rate value
            value_numeric = None
            value_unit = 'percent' if '%' in rate else 'AED'
            rate_match = re.search(r'(\d+(?:\.\d+)?)', rate)
            if rate_match:
                value_numeric = float(rate_match.group(1))
            
            # Normalize category
            category = item.get('category', 'general')
            normalized_category = self._normalize_category(category)
            
            # Build conditions list - use sanitize utility
            conditions = sanitize_conditions(item.get('conditions', []))
            
            # Build limitations from cap
            limitations = []
            cap = to_string(item.get('cap'))
            if cap:
                limitations.append(f"Cap: {cap}")
            
            # Get merchants - use sanitize utility
            merchants = sanitize_merchants(item.get('merchants', []))
            
            # Create title
            if normalized_category and normalized_category != 'general':
                benefit_title = f"{rate} Cashback on {normalized_category.title()}"
            else:
                benefit_title = f"{rate} Cashback"
            
            # Generate unique ID
            content_hash = hashlib.md5(f"{rate}_{category}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"cashback_{content_hash}",
                benefit_type=self.benefit_type,
                title=benefit_title,
                description=f"Earn {rate} cashback on {normalized_category} purchases",
                value=rate,
                value_numeric=value_numeric,
                value_unit=value_unit,
                conditions=conditions,
                limitations=limitations,
                eligible_categories=[normalized_category] if normalized_category != 'general' else [],
                merchants=merchants,
                maximum_benefit=cap,
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method="llm",
                confidence=0.75,
                confidence_level=ConfidenceLevel.MEDIUM,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        return benefits
    
    def _create_benefit_from_match(
        self, 
        match: re.Match, 
        pattern_name: str, 
        content: str,
        url: str,
        title: str,
        index: int,
    ) -> Optional[ExtractedBenefit]:
        """Create cashback benefit from regex match."""
        groups = match.groupdict()
        
        # Extract value
        value_str = groups.get('value', '')
        value_numeric = None
        value_unit = None
        
        if value_str:
            value_clean = value_str.replace(',', '')
            try:
                value_numeric = float(value_clean)
            except ValueError:
                pass
            
            # Determine unit based on pattern
            if '%' in match.group() or pattern_name in ['percentage_cashback', 'cashback_of', 'earn_percentage']:
                value_unit = 'percent'
                value_str = f"{value_str}%"
            else:
                value_unit = 'AED'
                value_str = f"AED {value_str}"
        
        # Extract and normalize category
        category = groups.get('category', '')
        normalized_category = self._normalize_category(category)
        
        # Get context around match
        start = max(0, match.start() - 150)
        end = min(len(content), match.end() + 150)
        context = content[start:end].strip()
        
        # Create title
        if normalized_category and normalized_category != 'general':
            benefit_title = f"{value_str} Cashback on {normalized_category.title()}"
        else:
            benefit_title = f"{value_str} Cashback"
        
        # Look for conditions in context
        conditions = []
        min_match = re.search(r'minimum\s*(?:spend|purchase)?\s*(?:of|:)?\s*(?:aed|usd|\$)?\s*(\d+(?:,\d{3})*)', context, re.IGNORECASE)
        if min_match:
            conditions.append(f"Minimum spend: AED {min_match.group(1)}")
        
        # Look for caps in context
        limitations = []
        cap_match = re.search(r'(?:up to|max|capped at)\s*(?:aed|usd|\$)?\s*(\d+(?:,\d{3})*)\s*(?:per|monthly|annually)?', context, re.IGNORECASE)
        if cap_match:
            limitations.append(f"Capped at AED {cap_match.group(1)}")
        
        # Generate unique ID
        content_hash = hashlib.md5(match.group().encode()).hexdigest()[:8]
        
        return ExtractedBenefit(
            benefit_id=f"cashback_{content_hash}",
            benefit_type=self.benefit_type,
            title=benefit_title,
            description=match.group().strip(),
            value=value_str,
            value_numeric=value_numeric,
            value_unit=value_unit,
            conditions=conditions,
            limitations=limitations,
            eligible_categories=[normalized_category] if normalized_category != 'general' else [],
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.6,
            confidence_level=ConfidenceLevel.MEDIUM,
            pipeline_version=self.version,
        )


# Register the pipeline
pipeline_registry.register(CashbackPipeline)
