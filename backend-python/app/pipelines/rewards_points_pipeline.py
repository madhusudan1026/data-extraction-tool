"""
Rewards Points Pipeline

Extracts rewards/points earning benefits including:
- Points earning rates
- Bonus points promotions
- Points redemption options
- Miles earning (airline partnerships)
- Points expiry policies

Processing: LLM-first extraction with regex pattern fallback for each source.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions


class RewardsPointsPipeline(BasePipeline):
    """Pipeline for extracting rewards points benefits."""
    
    name = "rewards_points"
    benefit_type = "rewards_points"
    description = "Extracts points earning rates, bonus points, and redemption options"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'rewards', 'points', 'miles', 'skywards', 'bonus-points',
        'earning-rate', 'redemption', 'loyalty'
    ]
    
    keywords = [
        'points', 'reward points', 'rewards',
        'earn points', 'earning rate',
        'bonus points', 'extra points',
        'miles', 'air miles', 'skywards',
        'etihad guest', 'emirates skywards',
        'marriott bonvoy', 'hilton honors',
        'multiply points', 'double points', 'triple points',
        'points per', 'miles per',
        'redemption', 'redeem points',
    ]
    
    negative_keywords = []
    
    patterns = {
        'points_per_spend': r'(?P<points>\d+)\s*(?:reward)?\s*points?\s*(?:per|for every)\s*(?:aed|usd|\$)?\s*(?P<spend>\d+)',
        'earn_points': r'earn\s*(?:up to)?\s*(?P<points>\d+(?:,\d{3})*)\s*(?:bonus|reward)?\s*points?',
        'miles_per_spend': r'(?P<miles>\d+)\s*(?:air)?\s*miles?\s*(?:per|for every)\s*(?:aed|usd|\$)?\s*(?P<spend>\d+)',
        'multiplier': r'(?P<multiplier>double|triple|2x|3x|4x|5x|10x)\s*(?:the)?\s*(?:reward)?\s*points?',
        'skywards': r'(?:emirates)?\s*skywards?\s*(?:miles?)?\s*(?:earn)?\s*(?P<value>\d+)?',
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        """Generate LLM prompt for extracting rewards benefits."""
        ctx = self.format_card_context(card_context)
        return f"""Analyze credit card content to extract rewards points and miles benefits.

{ctx}Source: {title}
URL: {url}

Content:
{content}

Extract ALL rewards/points/miles benefits. For each, provide:
- type: "points" or "miles"
- earning_rate: Points/miles per spend (e.g., "1 point per AED 1")
- bonus_points: Any bonus offers (e.g., "5000 welcome bonus")
- category: Spending category if specific
- loyalty_program: Program name if any (Skywards, Etihad Guest, Marriott Bonvoy)
- multiplier: Accelerated earning if mentioned (2x, 3x)
- conditions: Any conditions

Respond ONLY with valid JSON:
{{"rewards_benefits": [
  {{"type": "points", "earning_rate": "1 per AED 1", "bonus_points": null, "category": "general", "loyalty_program": null, "multiplier": null, "conditions": []}}
]}}

If none found: {{"rewards_benefits": []}}

JSON:"""
    
    def parse_llm_response(self, response: str, url: str, title: str, index: int) -> List[ExtractedBenefit]:
        """Parse LLM response into rewards benefits."""
        benefits = []
        parsed = self._parse_llm_json(response)
        
        if not parsed:
            return benefits
        
        for item in (parsed.get('rewards_benefits') or parsed.get('items', [])):
            if not isinstance(item, dict):
                continue
            
            reward_type = item.get('type', 'points')
            earning_rate = item.get('earning_rate', '')
            bonus = item.get('bonus_points', '')
            program = item.get('loyalty_program', '')
            multiplier = item.get('multiplier', '')
            
            # Build value and title
            if earning_rate:
                value_str = earning_rate
                benefit_title = f"Earn {earning_rate}"
            elif bonus:
                value_str = bonus
                benefit_title = str(bonus)
            elif multiplier:
                value_str = f"{multiplier} {reward_type}"
                benefit_title = f"{multiplier} {reward_type.title()} Earning"
            else:
                continue
            
            if program:
                benefit_title += f" ({program})"
            
            content_hash = hashlib.md5(f"{value_str}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"rewards_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(benefit_title) or 'Rewards Benefit',
                description=f"Rewards: {value_str}",
                value=to_string(value_str),
                value_unit=to_string(reward_type),
                partners=[program.lower().replace(' ', '_')] if program else [],
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
        """Create rewards benefit from regex match."""
        groups = match.groupdict()
        start = max(0, match.start() - 150)
        end = min(len(content), match.end() + 150)
        context = content[start:end].strip()
        
        value_str = groups.get('points') or groups.get('miles') or groups.get('value') or groups.get('multiplier') or ''
        content_hash = hashlib.md5(match.group().encode()).hexdigest()[:8]
        
        return ExtractedBenefit(
            benefit_id=f"rewards_{content_hash}",
            benefit_type=self.benefit_type,
            title=f"Earn {value_str} Points" if value_str else "Reward Points",
            description=match.group().strip(),
            value=value_str,
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.6,
            pipeline_version=self.version,
        )


pipeline_registry.register(RewardsPointsPipeline)
