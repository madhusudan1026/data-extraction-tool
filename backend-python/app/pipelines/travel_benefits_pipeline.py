"""
Travel Benefits Pipeline - LLM-first with regex fallback.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions


class TravelBenefitsPipeline(BasePipeline):
    name = "travel_benefits"
    benefit_type = "travel"
    description = "Extracts travel insurance, transfers, hotel benefits"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'travel', 'airport-transfer', 'limousine', 'chauffeur',
        'hotel', 'flight', 'baggage', 'trip', 'vacation'
    ]
    
    keywords = [
        'travel', 'trip', 'travel insurance',
        'flight delay', 'baggage', 'lost baggage',
        'airport transfer', 'limousine', 'chauffeur',
        'hotel', 'upgrade', 'complimentary night',
        'car rental', 'valet parking', 'fast track',
        'visa', 'concierge',
    ]
    
    patterns = {
        'travel_insurance': r'travel\s*insurance\s*(?:up to)?\s*(?:aed|usd|\$)?\s*(?P<value>\d+(?:,\d{3})*)?',
        'flight_delay': r'flight\s*delay\s*(?:cover|compensation)?\s*(?:aed|usd|\$)?\s*(?P<value>\d+(?:,\d{3})*)?',
        'airport_transfer': r'(?:complimentary|free)?\s*(?:airport)?\s*(?:transfer|limousine)',
        'valet_parking': r'(?:complimentary|free)?\s*valet\s*parking',
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        ctx = self.format_card_context(card_context)
        return f"""Analyze credit card content to extract travel-related benefits.

{ctx}Source: {title}

Content:
{content}

Extract ALL travel benefits (insurance, transfers, hotel, car rental, parking, etc.). For each:
- benefit_name: Name of benefit
- benefit_type: Category (insurance, transfer, hotel, car_rental, parking)
- value: Coverage amount or discount
- conditions: Any conditions

Respond ONLY with valid JSON:
{{"travel_benefits": [{{"benefit_name": "Travel Insurance", "benefit_type": "insurance", "value": "AED 500,000", "conditions": []}}]}}

If none found: {{"travel_benefits": []}}

JSON:"""
    
    def parse_llm_response(self, response: str, url: str, title: str, index: int) -> List[ExtractedBenefit]:
        benefits = []
        parsed = self._parse_llm_json(response)
        if not parsed:
            return benefits
        
        for item in (parsed.get('travel_benefits') or parsed.get('items', [])):
            if not isinstance(item, dict):
                continue
            name = item.get('benefit_name', 'Travel Benefit')
            value = item.get('value', '')
            content_hash = hashlib.md5(f"{name}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"travel_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(name) or 'Travel Benefit',
                description=f"{name}: {value}" if value else (to_string(name) or ''),
                value=to_string(value),
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
            'travel_insurance': 'Travel Insurance',
            'flight_delay': 'Flight Delay Compensation',
            'airport_transfer': 'Airport Transfer',
            'valet_parking': 'Valet Parking',
        }
        
        return ExtractedBenefit(
            benefit_id=f"travel_{content_hash}",
            benefit_type=self.benefit_type,
            title=titles.get(pattern_name, 'Travel Benefit'),
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


pipeline_registry.register(TravelBenefitsPipeline)
