"""
Insurance Benefits Pipeline - LLM-first with regex fallback.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions


class InsurancePipeline(BasePipeline):
    name = "insurance"
    benefit_type = "insurance"
    description = "Extracts purchase protection, extended warranty, fraud protection"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'insurance', 'protection', 'warranty', 'coverage',
        'fraud-protection', 'purchase-protection', 'liability'
    ]
    
    keywords = [
        'insurance', 'protection', 'coverage',
        'purchase protection', 'buyer protection',
        'extended warranty', 'warranty extension',
        'fraud protection', 'zero liability',
        'personal accident', 'life insurance',
        'medical', 'health insurance',
    ]
    
    patterns = {
        'purchase_protection': r'purchase\s*protection\s*(?:up to|upto)?\s*(?:aed|usd|\$)?\s*(?P<value>\d+(?:,\d{3})*)?',
        'extended_warranty': r'extended\s*warranty\s*(?:of|up to|for)?\s*(?P<value>\d+)\s*(?:months?|years?)?',
        'fraud_protection': r'(?:zero|no)\s*liability\s*(?:on)?\s*(?:fraud|unauthorized)',
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        ctx = self.format_card_context(card_context)
        return f"""Analyze credit card content to extract insurance and protection benefits.

{ctx}Source: {title}

Content:
{content}

Extract ALL insurance/protection benefits. For each:
- benefit_name: Name of benefit
- coverage_type: Type (purchase_protection, warranty, fraud, accident, medical)
- coverage_amount: Amount if mentioned
- conditions: Any conditions

Respond ONLY with valid JSON:
{{"insurance_benefits": [{{"benefit_name": "Purchase Protection", "coverage_type": "purchase_protection", "coverage_amount": "AED 10,000", "conditions": []}}]}}

If none found: {{"insurance_benefits": []}}

JSON:"""
    
    def parse_llm_response(self, response: str, url: str, title: str, index: int) -> List[ExtractedBenefit]:
        benefits = []
        parsed = self._parse_llm_json(response)
        if not parsed:
            return benefits
        
        for item in (parsed.get('insurance_benefits') or parsed.get('items', [])):
            if not isinstance(item, dict):
                continue
            name = item.get('benefit_name', 'Insurance Benefit')
            amount = item.get('coverage_amount', '')
            content_hash = hashlib.md5(f"{name}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"insurance_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(name) or 'Insurance Benefit',
                description=f"{name}: {amount}" if amount else (to_string(name) or ''),
                value=to_string(amount),
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
        
        titles = {
            'purchase_protection': 'Purchase Protection',
            'extended_warranty': 'Extended Warranty',
            'fraud_protection': 'Zero Fraud Liability',
        }
        
        return ExtractedBenefit(
            benefit_id=f"insurance_{content_hash}",
            benefit_type=self.benefit_type,
            title=titles.get(pattern_name, 'Insurance Benefit'),
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


pipeline_registry.register(InsurancePipeline)
