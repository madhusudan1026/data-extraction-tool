"""
Fee Waiver Benefits Pipeline - LLM-first with regex fallback.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string


class FeeWaiverPipeline(BasePipeline):
    name = "fee_waiver"
    benefit_type = "fee_waiver"
    description = "Extracts annual fee waivers, forex fee waivers, and other fee benefits"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'fee-waiver', 'annual-fee', 'joining-fee', 'forex', 
        'free-for-life', 'zero-fee', 'fee-reversal'
    ]
    
    keywords = [
        'fee waiver', 'waived', 'no fee', 'zero fee',
        'annual fee', 'joining fee', 'membership fee',
        'forex', 'foreign exchange', 'currency conversion',
        'free for life', 'lifetime free',
        'first year free', 'complimentary',
    ]
    
    patterns = {
        'annual_fee_waiver': r'(?:annual|yearly)\s*fee\s*(?:waived?|free|zero|no)',
        'forex_waiver': r'(?:no|zero|0%?)\s*(?:forex|foreign exchange|currency conversion)\s*(?:fee|charge|markup)',
        'lifetime_free': r'(?:free for life|lifetime free|life long free)',
        'first_year_free': r'(?:first year free|year 1 free|joining fee waived)',
        'annual_fee_amount': r'annual\s*fee\s*(?:of|:)?\s*(?:aed|usd|\$)?\s*(?P<value>\d+(?:,\d{3})*)',
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        ctx = self.format_card_context(card_context)
        return f"""Analyze credit card content to extract fee-related benefits and waivers.

{ctx}Source: {title}

Content:
{content}

Extract ALL fee waivers and fee benefits. For each:
- benefit_name: Name (e.g., "Annual Fee Waiver", "Zero Forex Fee")
- fee_type: Type (annual_fee, joining_fee, forex_fee, late_payment_fee)
- waiver_condition: Condition for waiver if any (e.g., "spend AED 36,000/year")
- original_fee: Original fee amount if mentioned

Respond ONLY with valid JSON:
{{"fee_benefits": [{{"benefit_name": "Annual Fee Waiver", "fee_type": "annual_fee", "waiver_condition": "spend AED 36,000/year", "original_fee": "AED 500"}}]}}

If none found: {{"fee_benefits": []}}

JSON:"""
    
    def parse_llm_response(self, response: str, url: str, title: str, index: int) -> List[ExtractedBenefit]:
        benefits = []
        parsed = self._parse_llm_json(response)
        if not parsed:
            return benefits
        
        for item in (parsed.get('fee_benefits') or parsed.get('items', [])):
            if not isinstance(item, dict):
                continue
            name = item.get('benefit_name', 'Fee Benefit')
            condition = to_string(item.get('waiver_condition', ''))
            original_fee = to_string(item.get('original_fee', ''))
            content_hash = hashlib.md5(f"{name}_{url}".encode()).hexdigest()[:8]
            
            conditions = [condition] if condition else []
            
            benefit = ExtractedBenefit(
                benefit_id=f"fee_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(name) or 'Fee Benefit',
                description=f"{name}" + (f" (Original: {original_fee})" if original_fee else ""),
                value=original_fee if original_fee else None,
                conditions=conditions,
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
        
        titles = {
            'annual_fee_waiver': 'Annual Fee Waiver',
            'forex_waiver': 'Zero Forex Fee',
            'lifetime_free': 'Lifetime Free Card',
            'first_year_free': 'First Year Free',
            'annual_fee_amount': f'Annual Fee: AED {value}' if value else 'Annual Fee',
        }
        
        return ExtractedBenefit(
            benefit_id=f"fee_{content_hash}",
            benefit_type=self.benefit_type,
            title=titles.get(pattern_name, 'Fee Benefit'),
            description=match.group().strip(),
            value=f"AED {value}" if value else None,
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.6,
            pipeline_version=self.version,
        )


pipeline_registry.register(FeeWaiverPipeline)
