"""
Movie/Cinema Benefits Pipeline

Extracts movie and cinema-related benefits including:
- Free movie tickets (quantity, frequency)
- Ticket types (2D, 3D, IMAX, VIP, 4DX, etc.)
- Eligible cinema chains and locations
- Card eligibility for different ticket tiers
- Booking process and requirements
- Terms and conditions
- Exclusions (premiere shows, special events, etc.)
- Companion tickets
- Discounts and offers

Processing: LLM-first extraction with comprehensive regex pattern fallback.
"""

import logging
logger = logging.getLogger(__name__)

import re
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base_pipeline import BasePipeline, ExtractedBenefit, ConfidenceLevel
from .pipeline_registry import pipeline_registry
from ..utils.sanitize import to_string, to_string_list, sanitize_conditions, sanitize_merchants, sanitize_categories


class MoviePipeline(BasePipeline):
    """Pipeline for extracting movie/cinema benefits."""
    
    name = "movie"
    benefit_type = "movie"
    description = "Extracts movie tickets, cinema benefits, and entertainment offers"
    version = "1.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'movie', 'cinema', 'film', 'cine-royal', 'cinestar', 
        'vox-cinema', 'reel-cinema', 'novo-cinema', 'imax', 
        'entertainment', 'ticket'
    ]
    
    keywords = [
        # Core movie/cinema keywords
        'movie', 'movies', 'cinema', 'cinemas', 'film', 'films',
        'movie ticket', 'movie tickets', 'cinema ticket', 'cinema tickets',
        'free movie', 'free movies', 'complimentary movie', 'complimentary ticket',
        'buy one get one', 'bogo', 'buy 1 get 1',
        
        # Ticket types
        '2d', '3d', 'imax', 'vip', '4dx', 'screenx', 'dolby',
        'standard ticket', 'premium ticket', 'vip ticket',
        'standard 2d', 'standard 3d', 'vip screening',
        
        # Cinema chains (UAE)
        'vox', 'vox cinemas', 'reel', 'reel cinemas', 
        'novo', 'novo cinemas', 'cine royal', 'cinestar',
        'oscar', 'star cinemas', 'cinemacity',
        
        # Benefits keywords
        'movie benefit', 'movie benefits', 'cinema benefit', 'cinema benefits',
        'movie offer', 'movie offers', 'cinema offer',
        'entertainment', 'entertainment benefit',
        
        # Companion/additional tickets
        'companion ticket', 'guest ticket', 'additional ticket',
        'bring a friend', 'plus one',
    ]
    
    negative_keywords = [
        'no movie',
        'movie not included',
        'cinema excluded',
        'movies excluded',
    ]
    
    patterns = {
        # Cinema chain names (UAE specific)
        'cinema_vox': r'vox\s*(?:cinemas?)?',
        'cinema_reel': r'reel\s*(?:cinemas?)?',
        'cinema_novo': r'novo\s*(?:cinemas?)?',
        'cinema_cine_royal': r'cine\s*royal(?:\s*cinemas?)?',
        'cinema_cinestar': r'cinestar(?:\s*cinemas?)?',
        'cinema_oscar': r'oscar\s*(?:cinemas?)?',
        'cinema_star': r'star\s*(?:cinemas?)?',
        
        # Ticket types
        'ticket_2d': r'(?:standard\s*)?2d(?:\s*ticket)?',
        'ticket_3d': r'(?:standard\s*)?3d(?:\s*ticket)?',
        'ticket_imax': r'imax(?:\s*ticket)?',
        'ticket_vip': r'vip(?:\s*(?:ticket|screening|experience))?',
        'ticket_4dx': r'4dx(?:\s*ticket)?',
        'ticket_screenx': r'screen\s*x(?:\s*ticket)?',
        'ticket_dolby': r'dolby(?:\s*(?:atmos|cinema|ticket))?',
        'ticket_gold': r'gold(?:\s*(?:class|ticket|experience))?',
        'ticket_max': r'max(?:\s*(?:ticket|screen))?',
        
        # Free tickets patterns
        'free_tickets': r'(\d+)\s*(?:free|complimentary)\s*(?:movie\s*)?tickets?',
        'tickets_per_month': r'(\d+)\s*(?:movie\s*)?tickets?\s*(?:per|a|each|every)\s*month',
        'tickets_per_week': r'(\d+)\s*(?:movie\s*)?tickets?\s*(?:per|a|each|every)\s*week',
        'buy_one_get_one': r'buy\s*(?:one|1)\s*get\s*(?:one|1)(?:\s*free)?',
        'bogo': r'bogo|b1g1',
        
        # Companion tickets
        'companion_ticket': r'(?:companion|guest|additional)\s*ticket',
        'plus_one': r'(?:bring\s*a\s*friend|\+\s*1|plus\s*one)',
        
        # Card eligibility
        'eligible_cards': r'(?:eligible|qualifying)\s*cards?[:\s]',
        'cardholders': r'(?:card\s*)?holders?\s*(?:can|may|get|receive|enjoy)',
        
        # Exclusions
        'premiere_excluded': r'(?:premiere|premier)\s*(?:shows?|screenings?)\s*(?:excluded|not\s*included)',
        'special_events_excluded': r'(?:special\s*events?|festivals?)\s*(?:excluded|not\s*included)',
        'weekends_excluded': r'(?:weekends?|saturday|sunday)\s*(?:excluded|not\s*(?:valid|included))',
        'public_holidays_excluded': r'(?:public\s*)?holidays?\s*(?:excluded|not\s*(?:valid|included))',
        
        # Booking
        'advance_booking': r'(?:advance|prior)\s*booking\s*(?:required|necessary)',
        'book_online': r'book(?:ing)?\s*(?:online|via\s*(?:app|website))',
        'book_counter': r'book(?:ing)?\s*(?:at\s*)?(?:counter|box\s*office)',
        
        # Validity
        'valid_days': r'valid\s*(?:on|only)?\s*((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekdays?|weekends?)(?:\s*(?:to|[-–]|and|,)\s*(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))*)',
        'valid_locations': r'valid\s*(?:at|in)\s*(?:all|select(?:ed)?)\s*(?:locations?|branches?|cinemas?)',
        
        # Terms patterns
        'terms_apply': r'(?:terms?\s*(?:and|&)?\s*conditions?\s*apply|t&c\s*apply)',
        'subject_to': r'subject\s*to\s*(?:availability|terms|conditions)',
        'non_transferable': r'non[- ]?transferable',
        'not_valid_with': r'(?:not|cannot\s*be)\s*(?:valid|combined|used)\s*with\s*(?:other\s*)?(?:offers?|promotions?|discounts?)',
        
        # Discount patterns  
        'percent_off': r'(\d+)\s*%\s*(?:off|discount)',
        'discount_on_tickets': r'(\d+)\s*%\s*(?:off|discount)\s*(?:on\s*)?(?:movie\s*)?tickets?',
        
        # Fees
        'booking_fee': r'booking\s*(?:fee|charge)[:\s]*(?:aed\s*)?(\d+(?:\.\d{2})?)',
        'processing_fee': r'processing\s*(?:fee|charge)[:\s]*(?:aed\s*)?(\d+(?:\.\d{2})?)',
    }
    
    # Known UAE cinema chains
    UAE_CINEMA_CHAINS = [
        "VOX Cinemas",
        "Reel Cinemas",
        "Novo Cinemas",
        "Cine Royal Cinemas",
        "CineStar Cinemas",
        "Oscar Cinemas",
        "Star Cinemas",
        "Cinema City",
    ]
    
    # Ticket type hierarchy (for mapping card tiers)
    TICKET_TYPES = {
        'premium': ['imax', 'vip', '4dx', 'screenx', 'dolby', 'gold class', 'max'],
        'standard': ['2d', '3d', 'standard'],
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        """Generate LLM prompt for extracting movie/cinema benefits."""
        card_context = card_context or {}
        card_name = card_context.get('card_name') or 'Unknown Card'
        bank_name = card_context.get('bank_name') or 'Unknown Bank'
        
        # Build card structure context for combo cards
        card_structure = card_context.get('card_structure', {})
        card_structure_info = ""
        
        if card_structure.get('is_combo_card'):
            component_cards = card_structure.get('component_cards', [])
            if component_cards:
                card_structure_info = f"""
IMPORTANT - This is a COMBO CARD with multiple cards:
- Parent Card: {card_name}
- Component Cards: {', '.join(component_cards)}
- Identify which specific card provides the movie benefit if mentioned!
"""
        
        return f"""Extract movie/cinema benefits from this bank webpage.

CARD: {card_name} from {bank_name}
{card_structure_info}
CONTENT:
{content}

CRITICAL: Look for ELIGIBILITY TABLES that show which cards get which ticket types!
Tables often use ✓/√ for YES and ✗/× for NO.

Example table format:
Card Type          | Standard 2D | Standard 2D VIP
Duo Credit Card    |     √       |       ×

This means Duo Credit Card ONLY gets Standard 2D, NOT VIP!

Extract into JSON array:
{{
  "title": "Movie benefit name",
  "description": "ONE sentence only",
  "value": "Buy 1 Get 1 Free",
  "ticket_type_included": ["Standard 2D"],
  "ticket_type_excluded": ["Standard 2D VIP", "IMAX", "4DX"],
  "frequency": "6 tickets (3 free) per month",
  "merchants": ["Cinema name"],
  "eligible_cards": ["Card names"],
  "conditions": ["Terms as separate items"],
  "card_ticket_mapping": {{
    "Duo Credit Card": {{"Standard 2D": true, "Standard 2D VIP": false}},
    "Etihad Limitless": {{"Standard 2D": true, "Standard 2D VIP": true}}
  }}
}}

IMPORTANT RULES:
1. EXTRACT THE ELIGIBILITY TABLE if present - show which cards get which ticket types
2. For "{card_name}", specifically note what IS and IS NOT included
3. Use "ticket_type_included" for formats the card CAN use
4. Use "ticket_type_excluded" for formats the card CANNOT use
5. Include "card_ticket_mapping" showing the full table

Return ONLY valid JSON array:"""

    def _extract_card_specific_movie_benefits(self, content: str, card_name: str) -> Dict[str, Any]:
        """
        Extract movie benefits specifically for the given card using regex.
        
        Parses eligibility tables like:
        Emirates NBD card type    Standard 2D    Standard 2D VIP
        Duo Credit Card               √              ×
        
        Returns dict with card-specific eligibility.
        """
        result = {
            'card_found': False,
            'ticket_types_included': [],
            'ticket_types_excluded': [],
            'raw_table_data': {}
        }
        
        if not card_name:
            return result
        
        card_name_lower = card_name.lower()
        content_lower = content.lower()
        
        # Check if this card is mentioned at all
        if card_name_lower not in content_lower and 'duo' not in card_name_lower:
            return result
        
        # For Duo card, also check for just "duo"
        card_patterns = [card_name_lower]
        if 'duo' in card_name_lower:
            card_patterns.extend(['duo credit card', 'duo card', 'duo'])
        
        # Try to find the eligibility table
        # Look for patterns like "Card Type | Standard 2D | Standard 2D VIP"
        # followed by card rows with checkmarks
        
        lines = content.split('\n')
        table_started = False
        header_line = None
        ticket_columns = []
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Detect table header
            if ('standard 2d' in line_lower or '2d standard' in line_lower) and ('vip' in line_lower or 'card type' in line_lower):
                table_started = True
                header_line = line
                # Parse columns - look for ticket type names
                if 'standard 2d vip' in line_lower or '2d vip' in line_lower:
                    ticket_columns = ['Standard 2D', 'Standard 2D VIP']
                elif 'standard 2d' in line_lower:
                    ticket_columns = ['Standard 2D']
                continue
            
            # If we're in the table, look for our card
            if table_started:
                for card_pattern in card_patterns:
                    if card_pattern in line_lower:
                        result['card_found'] = True
                        
                        # Parse checkmarks - look for √/✓ and ×/✗
                        # The line format is typically: "Card Name    √    ×"
                        checkmarks = []
                        for char in line:
                            if char in '√✓':
                                checkmarks.append(True)
                            elif char in '×✗':
                                checkmarks.append(False)
                        
                        # Map checkmarks to ticket types
                        for j, ticket_type in enumerate(ticket_columns):
                            if j < len(checkmarks):
                                if checkmarks[j]:
                                    result['ticket_types_included'].append(ticket_type)
                                else:
                                    result['ticket_types_excluded'].append(ticket_type)
                                result['raw_table_data'][ticket_type] = checkmarks[j]
                        
                        break
                
                # Stop if we've gone too far from header (tables are usually compact)
                if i > 20 and table_started:
                    break
        
        return result

    def parse_llm_response(self, response: str, url: str, title: str, source_index: int) -> List[ExtractedBenefit]:
        """Parse LLM response into ExtractedBenefit objects."""
        import logging
        logger = logging.getLogger(__name__)
        
        benefits = []
        
        try:
            data = self._parse_llm_json(response)
            if not data:
                logger.warning(f"[{self.name}] Failed to parse JSON from LLM response")
                return benefits
            
            # Handle different return types
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # Could be {"items": [...]} or a single item
                if "items" in data:
                    items = data["items"]
                else:
                    items = [data]
            else:
                logger.warning(f"[{self.name}] Unexpected data type from LLM: {type(data)}")
                return benefits
            
            logger.info(f"[{self.name}] Processing {len(items)} items from LLM response")
            
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    logger.warning(f"[{self.name}] Skipping non-dict item at index {idx}: {type(item)}")
                    continue
                
                # Extract and sanitize fields
                raw_title = item.get('title') or item.get('benefit') or item.get('name') or ''
                title_str = to_string(raw_title) or f'Movie Benefit {idx+1}'
                
                raw_description = item.get('description') or item.get('details') or ''
                description_str = to_string(raw_description)
                
                raw_value = item.get('value') or item.get('tickets') or item.get('amount') or ''
                value_str = to_string(raw_value)
                
                # Get ticket types - handle both old and new field names
                ticket_type_included = to_string_list(item.get('ticket_type_included', []))
                ticket_type_excluded = to_string_list(item.get('ticket_type_excluded', []))
                ticket_type = to_string(item.get('ticket_type') or item.get('format') or '')
                
                # If old format, try to parse
                if ticket_type and not ticket_type_included:
                    ticket_type_included = [t.strip() for t in ticket_type.split(',')]
                
                # Get card-ticket mapping if available
                card_ticket_mapping = item.get('card_ticket_mapping', {})
                
                # Get frequency
                frequency = to_string(item.get('frequency') or item.get('per_month') or '')
                
                # Sanitize list fields
                conditions = sanitize_conditions(item.get('conditions', []))
                exclusions = sanitize_conditions(item.get('exclusions', []))
                merchants = sanitize_merchants(item.get('merchants', []) or item.get('cinemas', []))
                eligible_cards = to_string_list(item.get('eligible_cards', []))
                
                # Merge eligible_cards into eligible_categories
                eligible_categories = []
                for card in eligible_cards:
                    if card and card not in eligible_categories:
                        eligible_categories.append(card)
                
                # Build conditions from ticket type info
                if ticket_type_included:
                    conditions.insert(0, f"Ticket types INCLUDED: {', '.join(ticket_type_included)}")
                if ticket_type_excluded:
                    conditions.insert(1, f"Ticket types EXCLUDED: {', '.join(ticket_type_excluded)}")
                
                # Add card-specific ticket mapping to conditions
                if card_ticket_mapping:
                    for card, mapping in card_ticket_mapping.items():
                        if isinstance(mapping, dict):
                            included = [k for k, v in mapping.items() if v]
                            excluded = [k for k, v in mapping.items() if not v]
                            if included or excluded:
                                card_info = f"{card}: "
                                if included:
                                    card_info += f"✓ {', '.join(included)}"
                                if excluded:
                                    card_info += f" | ✗ {', '.join(excluded)}"
                                conditions.append(card_info)
                
                # Generate benefit ID
                benefit_id = hashlib.md5(
                    f"{self.name}:{title_str}:{value_str}:{','.join(ticket_type_included)}:{source_index}".encode()
                ).hexdigest()[:12]
                
                # Determine confidence based on specificity
                confidence = 0.85
                if ticket_type and eligible_cards:
                    confidence = 0.95
                elif value_str and merchants:
                    confidence = 0.90
                
                # Build a clean description - DO NOT append all fields to it
                clean_description = description_str
                
                # Add ticket type info to description only if description is empty
                if not clean_description and ticket_type:
                    clean_description = f"Movie benefit for {ticket_type} tickets"
                elif not clean_description:
                    clean_description = f"Movie benefit at {', '.join(merchants) if merchants else 'cinema'}"
                
                # Add exclusions as separate conditions (prefixed for clarity)
                all_conditions = list(conditions)
                if exclusions:
                    for excl in exclusions:
                        if excl and not excl.lower().startswith('excluded') and not excl.lower().startswith('not '):
                            all_conditions.append(f"Excluded: {excl}")
                        else:
                            all_conditions.append(excl)
                
                # Add eligible cards to conditions for visibility
                if eligible_cards:
                    all_conditions.append(f"Eligible cards: {', '.join(eligible_cards)}")
                
                # Add ticket type to conditions if present
                if ticket_type:
                    all_conditions.insert(0, f"Valid for: {ticket_type}")
                
                benefit = ExtractedBenefit(
                    benefit_id=f"movie_{benefit_id}",
                    benefit_type=self.benefit_type,
                    title=title_str,
                    description=clean_description[:300] if clean_description else '',
                    value=value_str,
                    frequency=frequency,
                    conditions=all_conditions,
                    merchants=merchants,
                    eligible_categories=eligible_categories,
                    source_url=url,
                    source_title=title,
                    source_index=source_index,
                    extraction_method="llm",
                    confidence=confidence,
                    confidence_level=ConfidenceLevel.HIGH if confidence >= 0.85 else ConfidenceLevel.MEDIUM,
                    pipeline_version=self.version,
                )
                
                benefits.append(benefit)
                logger.info(f"[{self.name}] Parsed LLM benefit: {title_str} | {value_str} | Cards: {eligible_cards}")
                
        except Exception as e:
            logger.error(f"[{self.name}] Error parsing LLM response: {e}")
            import traceback
            traceback.print_exc()
        
        return benefits

    def _extract_from_source_with_patterns(self, content: str, url: str, title: str, source_index: int) -> List[ExtractedBenefit]:
        """Extract movie benefits using regex patterns WITH card-specific filtering."""
        import logging
        logger = logging.getLogger(__name__)
        
        benefits = []
        content_lower = content.lower()
        
        # CRITICAL: Get card-specific eligibility first
        card_name = self._card_context.get('card_name', '')
        card_specific = self._extract_card_specific_movie_benefits(content, card_name)
        
        logger.info(f"[{self.name}] Card-specific extraction for '{card_name}': {card_specific}")
        logger.debug(f"[{self.name}] Card-specific movie extraction: {card_specific}")
        
        # Track what we've found
        found_cinemas = []
        found_ticket_types = []
        found_tickets_count = None
        found_frequency = None
        found_exclusions = []
        found_conditions = []
        
        # Find cinema chains
        for cinema in self.UAE_CINEMA_CHAINS:
            if cinema.lower() in content_lower:
                found_cinemas.append(cinema)
        
        # Find ticket types
        ticket_type_patterns = {
            'Standard 2D': [r'standard\s*2d', r'2d\s*(?:ticket|movie)', r'\b2d\b'],
            'Standard 3D': [r'standard\s*3d', r'3d\s*(?:ticket|movie)', r'\b3d\b'],
            'IMAX': [r'imax'],
            'VIP': [r'vip\s*(?:ticket|screening|experience)?', r'gold\s*class'],
            '4DX': [r'4dx'],
            'Dolby': [r'dolby\s*(?:atmos|cinema)?'],
        }
        
        for ticket_type, patterns in ticket_type_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    if ticket_type not in found_ticket_types:
                        found_ticket_types.append(ticket_type)
                    break
        
        # Find number of tickets
        tickets_match = re.search(r'(\d+)\s*(?:free|complimentary)\s*(?:movie\s*)?tickets?', content_lower)
        if tickets_match:
            found_tickets_count = tickets_match.group(1)
        
        # Find frequency
        freq_match = re.search(r'(\d+)\s*(?:tickets?\s*)?(?:per|a|each|every)\s*(month|week)', content_lower)
        if freq_match:
            found_frequency = f"{freq_match.group(1)} per {freq_match.group(2)}"
        
        # Find exclusions
        exclusion_patterns = [
            (r'(?:premiere|premier)\s*(?:shows?|screenings?)\s*(?:excluded|not\s*included)', 'Premiere shows excluded'),
            (r'vip\s*(?:excluded|not\s*included)', 'VIP screenings excluded'),
            (r'imax\s*(?:excluded|not\s*included)', 'IMAX excluded'),
            (r'3d\s*(?:excluded|not\s*included)', '3D excluded'),
            (r'(?:weekends?|saturday|sunday)\s*(?:excluded|not\s*(?:valid|included))', 'Weekends excluded'),
            (r'(?:public\s*)?holidays?\s*(?:excluded|not\s*(?:valid|included))', 'Public holidays excluded'),
            (r'special\s*(?:events?|screenings?)\s*(?:excluded|not\s*included)', 'Special events excluded'),
        ]
        
        for pattern, exclusion_text in exclusion_patterns:
            if re.search(pattern, content_lower):
                found_exclusions.append(exclusion_text)
        
        # Find conditions
        condition_patterns = [
            (r'advance\s*booking\s*(?:required|necessary)', 'Advance booking required'),
            (r'subject\s*to\s*availability', 'Subject to availability'),
            (r'non[- ]?transferable', 'Non-transferable'),
            (r'(?:terms?\s*(?:and|&)?\s*conditions?\s*apply|t&c\s*apply)', 'Terms and conditions apply'),
            (r'valid\s*(?:on\s*)?weekdays?\s*only', 'Valid on weekdays only'),
            (r'(?:must|need\s*to)\s*(?:present|show)\s*card', 'Must present card'),
        ]
        
        for pattern, condition_text in condition_patterns:
            if re.search(pattern, content_lower):
                found_conditions.append(condition_text)
        
        # Create benefits from findings
        if found_cinemas or found_ticket_types or found_tickets_count:
            # CRITICAL: If we have card-specific data, use it to override generic findings
            if card_specific.get('card_found'):
                # Use card-specific ticket types
                card_included = card_specific.get('ticket_types_included', [])
                card_excluded = card_specific.get('ticket_types_excluded', [])
                
                if card_included:
                    found_ticket_types = card_included
                if card_excluded:
                    for excl in card_excluded:
                        excl_msg = f"{excl} NOT available for {card_name}"
                        if excl_msg not in found_exclusions:
                            found_exclusions.insert(0, excl_msg)
                
                # Add card-specific condition
                found_conditions.insert(0, f"Card-specific: {card_name} eligible for {', '.join(card_included) if card_included else 'limited tickets'}")
                if card_excluded:
                    found_conditions.insert(1, f"NOT eligible for: {', '.join(card_excluded)}")
                
                logger.info(f"[{self.name}] Applied card-specific filtering: included={card_included}, excluded={card_excluded}")
            
            # Main movie benefit
            title_parts = []
            if found_tickets_count:
                title_parts.append(f"{found_tickets_count} Free Movie Tickets")
            else:
                title_parts.append("Movie Ticket Benefit")
            
            if found_ticket_types:
                title_parts.append(f"({', '.join(found_ticket_types[:2])})")
            
            # Add card name to title for clarity
            if card_specific.get('card_found') and card_name:
                title_parts.append(f"- {card_name}")
            
            benefit_title = ' '.join(title_parts)
            
            value_parts = []
            if found_tickets_count:
                value_parts.append(f"{found_tickets_count} tickets")
            if found_frequency:
                value_parts.append(found_frequency)
            
            benefit_value = ' | '.join(value_parts) if value_parts else 'Complimentary tickets'
            
            description_parts = ['Movie ticket benefit']
            if found_cinemas:
                description_parts.append(f"at {', '.join(found_cinemas[:3])}")
            if found_ticket_types:
                description_parts.append(f"for {', '.join(found_ticket_types)}")
            
            benefit_id = hashlib.md5(
                f"{self.name}:pattern:{benefit_title}:{source_index}".encode()
            ).hexdigest()[:12]
            
            # Set higher confidence if we have card-specific data
            confidence = 0.85 if card_specific.get('card_found') else 0.65
            
            benefit = ExtractedBenefit(
                benefit_id=f"movie_{benefit_id}",
                benefit_type=self.benefit_type,
                title=benefit_title,
                description=' '.join(description_parts),
                value=benefit_value,
                frequency=found_frequency,
                conditions=found_conditions + found_exclusions,
                merchants=found_cinemas,
                eligible_categories=[card_name] if card_name else [],
                source_url=url,
                source_title=title,
                source_index=source_index,
                extraction_method="pattern+card_specific" if card_specific.get('card_found') else "pattern",
                confidence=confidence,
                confidence_level=ConfidenceLevel.HIGH if confidence >= 0.85 else ConfidenceLevel.MEDIUM,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
            logger.info(f"[{self.name}] Pattern extracted: {benefit_title}")
        
        # Create separate benefit for each exclusion found (to highlight what's NOT included)
        for exclusion in found_exclusions[:3]:  # Limit to top 3
            benefit_id = hashlib.md5(
                f"{self.name}:exclusion:{exclusion}:{source_index}".encode()
            ).hexdigest()[:12]
            
            benefit = ExtractedBenefit(
                benefit_id=f"movie_{benefit_id}",
                benefit_type=self.benefit_type,
                title=f"Movie Benefit Exclusion: {exclusion}",
                description=f"This benefit type is not included: {exclusion}",
                value="Not included",
                conditions=[exclusion],
                merchants=found_cinemas,
                eligible_categories=[],
                source_url=url,
                source_title=title,
                source_index=source_index,
                extraction_method="pattern",
                confidence=0.70,
                confidence_level=ConfidenceLevel.MEDIUM,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        return benefits


# Register the pipeline
pipeline_registry.register(MoviePipeline)
