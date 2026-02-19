"""
Dining Benefits Pipeline - LLM-first with regex fallback.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions, sanitize_merchants


class DiningPipeline(BasePipeline):
    name = "dining"
    benefit_type = "dining"
    description = "Extracts dining discounts, BOGO offers, and restaurant programs"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'dining', 'restaurant', 'food', 'entertainer', 'zomato',
        'bogo', 'fine-dining', 'meal', 'culinary'
    ]
    
    keywords = [
        'dining', 'restaurant', 'food', 'meal',
        'entertainer', 'zomato', 'talabat',
        'buy one get one', 'bogo', '2 for 1',
        'fine dining', 'discount', 'complimentary',
    ]
    
    patterns = {
        'dining_discount': r'(?P<value>\d+)\s*%\s*(?:off|discount)\s*(?:on|at)?\s*(?:dining|restaurant|food)',
        'bogo': r'(?:buy\s*(?:one|1)\s*get\s*(?:one|1)|bogo|2\s*for\s*1)',
        'entertainer': r'(?:the\s*)?entertainer\s*(?:membership|app)?',
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        ctx = self.format_card_context(card_context)
        return f"""Analyze credit card content to extract dining-related benefits.

{ctx}Source: {title}

Content:
{content}

Extract ALL dining benefits (discounts, BOGO, memberships). For each:
- benefit_name: Name of benefit
- discount_type: "percentage", "bogo", "membership", "complimentary"
- value: Discount value or description
- restaurants: Specific restaurants if mentioned
- conditions: Any conditions

Respond ONLY with valid JSON:
{{"dining_benefits": [{{"benefit_name": "25% Off Dining", "discount_type": "percentage", "value": "25%", "restaurants": [], "conditions": []}}]}}

If none found: {{"dining_benefits": []}}

JSON:"""
    
    def parse_llm_response(self, response: str, url: str, title: str, index: int) -> List[ExtractedBenefit]:
        benefits = []
        parsed = self._parse_llm_json(response)
        if not parsed:
            return benefits
        
        for item in (parsed.get('dining_benefits') or parsed.get('items', [])):
            if not isinstance(item, dict):
                continue
            name = item.get('benefit_name', 'Dining Benefit')
            value = item.get('value', '')
            restaurants = sanitize_merchants(item.get('restaurants', []))
            
            content_hash = hashlib.md5(f"{name}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"dining_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(name) or 'Dining Benefit',
                description=f"{name}: {value}" if value else (to_string(name) or ''),
                value=to_string(value),
                merchants=restaurants,
                conditions=sanitize_conditions(item.get('conditions', [])),
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method="llm",
                confidence=0.75,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        return benefits
    
    def _create_benefit_from_match(self, match: re.Match, pattern_name: str, content: str, url: str, title: str, index: int) -> Optional[ExtractedBenefit]:
        groups = match.groupdict()
        start = max(0, match.start() - 150)
        end = min(len(content), match.end() + 150)
        context = content[start:end].strip()
        value = groups.get('value', '')
        content_hash = hashlib.md5(match.group().encode()).hexdigest()[:8]
        
        if pattern_name == 'bogo':
            title_str = "Buy One Get One Free - Dining"
        elif pattern_name == 'entertainer':
            title_str = "The Entertainer Membership"
        else:
            title_str = f"{value}% Off Dining" if value else "Dining Discount"
        
        return ExtractedBenefit(
            benefit_id=f"dining_{content_hash}",
            benefit_type=self.benefit_type,
            title=title_str,
            description=match.group().strip(),
            value=f"{value}%" if value else None,
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.6,
            pipeline_version=self.version,
        )


pipeline_registry.register(DiningPipeline)
