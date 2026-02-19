"""
Lounge Access Pipeline

Extracts airport lounge access benefits including:
- Number of complimentary visits
- Lounge networks (Priority Pass, LoungeKey, DragonPass)
- Airport coverage
- Guest policies
- Access conditions

Processing: LLM-first extraction with regex pattern fallback for each source.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, sanitize_conditions


class LoungeAccessPipeline(BasePipeline):
    """Pipeline for extracting airport lounge access benefits."""
    
    name = "lounge_access"
    benefit_type = "lounge_access"
    description = "Extracts airport lounge access, visits, networks, and conditions"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'lounge', 'airport-lounge', 'priority-pass', 'lounge-key',
        'dragonpass', 'plaza-premium', 'marhaba', 'ahlan'
    ]
    
    keywords = [
        'lounge', 'lounges', 'lounge access',
        'airport lounge', 'airport lounges',
        'priority pass', 'prioritypass',
        'lounge key', 'loungekey',
        'dragon pass', 'dragonpass',
        'plaza premium', 'marhaba',
        'business lounge', 'first class lounge',
        'complimentary access', 'free access',
        'visits per year', 'annual visits',
        'guest access', 'accompanying guest',
    ]
    
    negative_keywords = [
        'no lounge access',
        'lounge not included',
    ]
    
    patterns = {
        # Match "X complimentary lounge visits"
        'complimentary_visits': r'(?P<value>\d+)\s*(?:complimentary|free|unlimited)?\s*(?:airport)?\s*lounge\s*(?:visits?|access(?:es)?)',
        
        # Match "lounge access X times per year"
        'visits_per_year': r'lounge\s*access\s*(?P<value>\d+)\s*(?:times?|visits?)\s*(?:per|a|each)\s*year',
        
        # Match "unlimited lounge access"
        'unlimited_access': r'unlimited\s*(?:airport)?\s*lounge\s*(?:access|visits?)',
        
        # Match Priority Pass mentions
        'priority_pass': r'priority\s*pass\s*(?P<tier>select|prestige|standard)?(?:\s*membership)?',
        
        # Match LoungeKey mentions
        'lounge_key': r'lounge\s*key\s*(?:access|membership)?',
        
        # Match guest policy
        'guest_policy': r'(?P<value>\d+)?\s*(?:complimentary|free)?\s*guest(?:s)?\s*(?:per visit|included|allowed)?',
        
        # Match per visit fee
        'visit_fee': r'(?:aed|usd|\$)\s*(?P<value>\d+(?:\.\d{2})?)\s*per\s*(?:visit|entry|access)',
    }
    
    # Known lounge networks
    LOUNGE_NETWORKS = {
        'priority_pass': ['priority pass', 'prioritypass'],
        'lounge_key': ['lounge key', 'loungekey'],
        'dragon_pass': ['dragon pass', 'dragonpass'],
        'plaza_premium': ['plaza premium'],
        'marhaba': ['marhaba'],
        'diners_club': ['diners club lounge'],
    }
    
    def _detect_lounge_network(self, text: str) -> List[str]:
        """Detect which lounge networks are mentioned."""
        networks = []
        text_lower = text.lower()
        
        for network, variants in self.LOUNGE_NETWORKS.items():
            if any(v in text_lower for v in variants):
                networks.append(network)
        
        return networks
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        """Generate LLM prompt for extracting lounge access benefits."""
        ctx = self.format_card_context(card_context)
        return f"""You are analyzing credit card content to extract airport lounge access benefits.

{ctx}Source: {title}
URL: {url}

Content to analyze:
{content}

Extract ALL lounge access benefits mentioned. For each benefit, provide:
- visits: Number of complimentary visits (e.g., "4", "unlimited")
- frequency: How often (e.g., "per year", "per month", "per quarter")
- network: Lounge network (Priority Pass, LoungeKey, DragonPass, Plaza Premium, Marhaba, etc.)
- tier: Membership tier if mentioned (Select, Prestige, Standard)
- guest_policy: Guest access details (e.g., "1 guest free", "guests at USD 32 each")
- conditions: List of conditions (e.g., ["international flights only", "minimum spend required"])

Respond ONLY with a valid JSON object:
{{"lounge_benefits": [
  {{"visits": "4", "frequency": "per year", "network": "Priority Pass", "tier": "Select", "guest_policy": "1 guest free", "conditions": []}}
]}}

If no lounge benefits found, respond with: {{"lounge_benefits": []}}

JSON:"""
    
    def parse_llm_response(
        self, 
        response: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """Parse LLM response into lounge access benefits."""
        benefits = []
        parsed = self._parse_llm_json(response)
        
        if not parsed:
            return benefits
        
        items = parsed.get('lounge_benefits') or parsed.get('items', [])
        if isinstance(items, dict):
            items = [items]
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            visits = str(item.get('visits', ''))
            network = item.get('network', '')
            tier = item.get('tier', '')
            frequency = item.get('frequency', 'per year')
            guest_policy = item.get('guest_policy', '')
            
            # Parse visit count
            value_numeric = None
            if visits.lower() == 'unlimited':
                value_numeric = -1
            elif visits:
                try:
                    value_numeric = float(visits)
                except ValueError:
                    pass
            
            # Build title
            if network:
                benefit_title = f"{network}"
                if tier:
                    benefit_title += f" {tier}"
                if visits and visits.lower() != 'unlimited':
                    benefit_title += f" - {visits} Visits"
                elif visits.lower() == 'unlimited':
                    benefit_title += " - Unlimited Access"
            elif visits:
                if visits.lower() == 'unlimited':
                    benefit_title = "Unlimited Lounge Access"
                else:
                    benefit_title = f"{visits} Complimentary Lounge Visits"
            else:
                benefit_title = "Airport Lounge Access"
            
            # Build conditions - use sanitize utility
            conditions = sanitize_conditions(item.get('conditions', []))
            
            if guest_policy:
                conditions.append(f"Guest policy: {to_string(guest_policy)}")
            
            # Generate unique ID
            content_hash = hashlib.md5(f"{visits}_{network}_{url}".encode()).hexdigest()[:8]
            
            benefit = ExtractedBenefit(
                benefit_id=f"lounge_{content_hash}",
                benefit_type=self.benefit_type,
                title=to_string(benefit_title) or 'Lounge Access',
                description=f"Airport lounge access via {network}" if network else "Airport lounge access",
                value=to_string(visits),
                value_numeric=value_numeric,
                value_unit='visits',
                frequency=to_string(frequency),
                conditions=conditions,
                partners=[network.lower().replace(' ', '_')] if network else [],
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
        """Create lounge access benefit from regex match."""
        groups = match.groupdict()
        
        # Get context
        start = max(0, match.start() - 200)
        end = min(len(content), match.end() + 200)
        context = content[start:end].strip()
        
        # Detect lounge networks in context
        networks = self._detect_lounge_network(context)
        
        # Extract value
        value_str = groups.get('value', '')
        value_numeric = None
        
        if pattern_name == 'unlimited_access':
            value_str = 'Unlimited'
            value_numeric = -1
        elif value_str:
            try:
                value_numeric = float(value_str)
            except ValueError:
                pass
        
        # Determine frequency
        frequency = 'per year'
        if 'per month' in context.lower() or 'monthly' in context.lower():
            frequency = 'per month'
        elif 'per quarter' in context.lower():
            frequency = 'per quarter'
        
        # Create title based on pattern
        if pattern_name == 'priority_pass':
            tier = groups.get('tier', '').title() or ''
            benefit_title = f"Priority Pass {tier} Membership".strip()
        elif pattern_name == 'lounge_key':
            benefit_title = "LoungeKey Access"
        elif pattern_name == 'unlimited_access':
            benefit_title = "Unlimited Lounge Access"
        elif value_str:
            benefit_title = f"{value_str} Complimentary Lounge Visits"
        else:
            benefit_title = "Airport Lounge Access"
        
        # Look for guest policy in context
        conditions = []
        guest_match = re.search(r'(\d+)?\s*(?:complimentary|free)?\s*guest(?:s)?', context, re.IGNORECASE)
        if guest_match and guest_match.group(1):
            conditions.append(f"{guest_match.group(1)} guest(s) included")
        
        # Look for limitations
        limitations = []
        if 'international' in context.lower() and 'only' in context.lower():
            limitations.append("International flights only")
        
        # Generate unique ID
        content_hash = hashlib.md5(match.group().encode()).hexdigest()[:8]
        
        return ExtractedBenefit(
            benefit_id=f"lounge_{content_hash}",
            benefit_type=self.benefit_type,
            title=benefit_title,
            description=match.group().strip(),
            value=value_str if value_str else None,
            value_numeric=value_numeric,
            value_unit='visits' if value_numeric and value_numeric > 0 else None,
            frequency=frequency,
            conditions=conditions,
            limitations=limitations,
            partners=networks,
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.65,
            confidence_level=ConfidenceLevel.MEDIUM,
            pipeline_version=self.version,
        )


# Register the pipeline
pipeline_registry.register(LoungeAccessPipeline)
