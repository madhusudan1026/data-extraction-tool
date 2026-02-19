"""
Lifestyle Benefits Pipeline - LLM-first with regex fallback.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions


class LifestylePipeline(BasePipeline):
    name = "lifestyle"
    benefit_type = "lifestyle"
    description = "Extracts golf, spa, fitness, entertainment, and lifestyle benefits"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    # Note: Lifestyle is a catch-all, so fewer specific patterns
    url_patterns = [
        'spa', 'fitness', 'gym', 'wellness', 'health-club',
        'concert', 'event', 'lifestyle', 'valet'
    ]
    
    keywords = [
        'golf', 'spa', 'fitness', 'gym',
        'movie', 'cinema', 'entertainment',
        'concert', 'event', 'tickets',
        'wellness', 'health club',
        'shopping', 'retail', 'discount',
        'lifestyle', 'exclusive',
    ]
    
    patterns = {
        'golf': r'(?:complimentary|free)?\s*golf\s*(?:access|rounds?|green fees?)',
        'spa': r'(?:complimentary|free)?\s*spa\s*(?:access|treatment|session)',
        'gym': r'(?:complimentary|free)?\s*(?:gym|fitness)\s*(?:membership|access)',
        'movie': r'(?:complimentary|free)?\s*(?:movie|cinema)\s*tickets?\s*(?P<value>\d+)?',
        'discount': r'(?P<value>\d+)\s*%\s*(?:off|discount)\s*(?:on|at)?\s*(?P<category>[a-zA-Z\s]+)',
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        ctx = self.format_card_context(card_context)
        return f"""Analyze credit card content to extract lifestyle and entertainment benefits.

{ctx}Source: {title}

Content:
{content}

Extract ALL lifestyle benefits (golf, spa, gym, movies, entertainment, shopping). For each:
- benefit_name: Name of benefit
- category: Category (golf, spa, fitness, cinema, entertainment, shopping)
- value: Discount or number of complimentary items
- partners: Specific partners/venues if mentioned
- conditions: Any conditions

Respond ONLY with valid JSON:
{{"lifestyle_benefits": [{{"benefit_name": "Complimentary Golf", "category": "golf", "value": "4 rounds", "partners": ["Emirates Golf Club"], "conditions": []}}]}}

If none found: {{"lifestyle_benefits": []}}

JSON:"""
    
    def parse_llm_response(self, response: str, url: str, title: str, index: int) -> List[ExtractedBenefit]:
        benefits = []
        parsed = self._parse_llm_json(response)
        if not parsed:
            return benefits
        
        for item in (parsed.get('lifestyle_benefits') or parsed.get('items', [])):
            if not isinstance(item, dict):
                continue
            name = item.get('benefit_name', 'Lifestyle Benefit')
            value = item.get('value', '')
            partners = sanitize_conditions(item.get('partners', []))  # Partners can use same sanitizer
            
            content_hash = hashlib.md5(f"{name}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"lifestyle_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(name) or 'Lifestyle Benefit',
                description=f"{name}: {value}" if value else (to_string(name) or ''),
                value=to_string(value),
                partners=partners,
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
            'golf': 'Golf Access',
            'spa': 'Spa Access',
            'gym': 'Fitness Membership',
            'movie': 'Movie Tickets',
            'discount': 'Lifestyle Discount',
        }
        
        return ExtractedBenefit(
            benefit_id=f"lifestyle_{content_hash}",
            benefit_type=self.benefit_type,
            title=titles.get(pattern_name, 'Lifestyle Benefit'),
            description=match.group().strip(),
            value=value if value else None,
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.6,
            pipeline_version=self.version,
        )


pipeline_registry.register(LifestylePipeline)
