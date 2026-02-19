"""
Golf Benefits Pipeline

Extracts golf-related benefits including:
- Complimentary golf sessions
- Eligible golf courses per card tier
- Access frequency (per month/year)
- Booking requirements and procedures
- Fees and charges (processing, no-show, cart)
- Minimum spend requirements
- Eligible cards

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


class GolfPipeline(BasePipeline):
    """Pipeline for extracting golf benefits."""
    
    name = "golf"
    benefit_type = "golf"
    description = "Extracts golf privileges, courses, fees, and booking details"
    version = "2.0"
    
    # URL patterns to identify sources this pipeline should process
    url_patterns = [
        'golf', 'golfing', 'tee-time', 'green-fee', 'driving-range',
        'golf-course', 'golf-club', 'golf-privilege'
    ]
    
    keywords = [
        'golf', 'golfing', 'golf course', 'golf courses',
        'golf club', 'golf clubs', 'golf session', 'golf sessions',
        'complimentary golf', 'free golf', 'golf privileges',
        'golf access', 'golf benefit', 'golf benefits',
        'tee time', 'tee times', 'golf booking',
        'golf discount', 'golf offer', 'golf offers',
        'golf cart', 'golf equipment',
        'driving range', 'practice range',
        'green fee', 'greens fee',
    ]
    
    negative_keywords = [
        'no golf',
        'golf not included',
        'golf excluded',
    ]
    
    patterns = {
        # Golf course names (UAE specific) - More flexible patterns
        'course_jebel_ali': r'jebel\s*ali\s*(?:golf\s*)?(?:club|course|resort)?',
        'course_arabian_ranches': r'arabian\s*ranches\s*(?:golf\s*)?(?:club|course)?',
        'course_meydan': r'(?:the\s+)?track[,\s]*meydan|meydan\s*golf',
        'course_abu_dhabi_city': r'abu\s*dhabi\s*city\s*golf\s*(?:club|course)?',
        'course_abu_dhabi': r'abu\s*dhabi\s*golf\s*(?:club|course)?',
        'course_sharjah': r'sharjah\s*golf\s*(?:&|and)?\s*(?:shooting\s*)?(?:club|course)?',
        'course_emirates': r'emirates\s*golf\s*(?:club|course)?',
        'course_dubai_creek': r'dubai\s*creek\s*golf\s*(?:&|and)?\s*(?:yacht\s*)?(?:club|course)?',
        'course_jumeirah': r'jumeirah\s*golf\s*(?:estates|club|course)?',
        'course_al_hamra': r'al\s*hamra\s*golf\s*(?:club|course)?',
        'course_yas_links': r'yas\s*links\s*(?:abu\s*dhabi)?',
        'course_saadiyat': r'saadiyat\s*(?:beach\s*)?golf\s*(?:club|course)?',
        'course_els': r'els\s*club',
        'course_montgomerie': r'montgomerie\s*golf\s*(?:club|course)?',
        
        # Access frequency - More flexible
        'access_twice_month': r'(?:twice|two\s*times?|2\s*(?:times?|x)?)\s*(?:per|a|each|every)?\s*month',
        'access_once_month': r'(?:once|one\s*time?|1\s*(?:time?|x)?)\s*(?:per|a|each|every)?\s*month',
        'access_per_month': r'(\d+)\s*(?:times?|sessions?|rounds?|visits?)\s*(?:per|a|each|every)\s*month',
        'access_per_year': r'(\d+)\s*(?:times?|sessions?|rounds?|visits?)\s*(?:per|a|each|every)\s*year',
        
        # Complimentary access
        'complimentary_golf': r'(?:complimentary|free|no\s+charge)\s+(?:golf\s+)?(?:access|session|round|tee\s+time|green\s*fee)',
        'free_golf_sessions': r'(\d+)\s+(?:complimentary|free)\s+(?:golf\s+)?(?:sessions?|rounds?|visits?)',
        
        # Fees and charges - More flexible AED patterns
        'processing_fee': r'(?:processing|booking)\s*fee[:\s]*(?:of\s*)?(?:aed\s*)?(\d+(?:\.\d{2})?)',
        'no_show_fee': r'no[- ]?show\s*(?:fee|charge|penalty)[:\s]*(?:of\s*)?(?:aed\s*)?(\d+(?:\.\d{2})?)',
        'booking_fee': r'booking\s*(?:fee|charge)[:\s]*(?:of\s*)?(?:aed\s*)?(\d+(?:\.\d{2})?)',
        'golf_cart_fee': r'(?:golf\s*)?cart\s*(?:charges?|fees?|rental)[:\s]*(?:aed\s*)?(\d+(?:\.\d{2})?)',
        'aed_amount': r'aed\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        
        # Minimum spend requirement
        'minimum_spend': r'(?:minimum|min\.?)\s*(?:monthly\s*)?spend[:\s]*(?:of\s*)?(?:aed\s*)?([\d,]+(?:\.\d{2})?)',
        'monthly_spend': r'(?:monthly|per\s*month)\s*(?:minimum\s*)?spend[:\s]*(?:of\s*)?(?:aed\s*)?([\d,]+(?:\.\d{2})?)',
        
        # Booking requirements - Enhanced
        'book_sms': r'(?:sms|text)\s*(?:to\s*)?(\d+)',
        'book_phone': r'(?:call|phone|contact)[:\s]*(\d[\d\s-]+)',
        'book_advance': r'(\d+)\s*(?:days?|hours?|hrs?)\s*(?:in\s+)?advance',
        'book_prior': r'(?:prior|advance)\s*(?:booking|reservation)\s*(?:of\s*)?(\d+)\s*(?:days?|hours?)',
        'book_required': r'(?:advance\s*)?(?:booking|reservation)\s*(?:is\s*)?(?:required|mandatory|necessary)',
        'registration_required': r'(?:card\s*)?registration\s*(?:is\s*)?(?:required|mandatory|necessary)',
        
        # Card type patterns - Enhanced for Emirates NBD
        'visa_infinite': r'visa\s*infinite',
        'visa_signature': r'visa\s*signature',
        'world_elite': r'(?:world\s*)?elite\s*(?:mastercard)?',
        'mastercard_world': r'mastercard\s*world',
        'platinum_card': r'platinum\s*(?:credit|debit)?\s*card',
        'signature_card': r'signature\s*(?:credit|debit)?\s*card',
        'infinite_card': r'infinite\s*(?:credit|debit)?\s*card',
        'beyond_card': r'beyond\s*(?:credit|debit)?\s*card',
        
        # Discount patterns
        'golf_discount': r'(\d+)\s*%\s*(?:discount|off)\s*(?:on\s+)?(?:golf|green\s*fee)',
        'discounted_rate': r'discounted?\s*(?:rate|price|fee)[:\s]*(?:aed\s*)?(\d+)',
        
        # Eligibility keywords
        'eligible_cards_section': r'(?:eligible|qualifying)\s*cards?[:\s]',
        'cardholder_access': r'cardholder(?:s)?\s*(?:can|may|get|receive|enjoy)\s*(?:access|golf)',
    }
    
    # Known UAE golf courses
    UAE_GOLF_COURSES = [
        "Jebel Ali Golf Club",
        "Arabian Ranches Golf Club", 
        "The Track, Meydan Golf",
        "Abu Dhabi City Golf Club",
        "Abu Dhabi Golf Club",
        "Sharjah Golf & Shooting Club",
        "Emirates Golf Club",
        "Dubai Creek Golf & Yacht Club",
        "Jumeirah Golf Estates",
        "Al Hamra Golf Club",
        "Yas Links Abu Dhabi",
        "Saadiyat Beach Golf Club",
        "The Els Club",
        "Montgomerie Golf Club",
    ]
    
    # Card tier definitions for mapping
    CARD_TIERS = {
        'premium': ['visa infinite', 'world elite', 'beyond', 'signature'],
        'standard': ['visa signature', 'platinum', 'mastercard world'],
    }
    
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        """Generate LLM prompt for extracting golf benefits."""
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
IMPORTANT - "{card_name}" is a COMBO CARD containing:
- {', '.join(component_cards)}

If you see "Diners Club Credit Card" in the golf eligibility list, this means the Duo Credit Card 
gets golf access through its Diners Club component!
"""
        
        # Check if this is the Duo card specifically
        if 'duo' in card_name.lower():
            card_structure_info += """
CRITICAL FOR DUO CREDIT CARD:
- Duo Credit Card = Duo MasterCard + Diners Club Card
- If "Diners Club Credit Card" is listed for golf → Duo Card gets golf (via Diners Club)
- The golf benefit frequency for Diners Club applies to Duo Card
"""
        
        return f"""Extract golf benefits from this bank webpage.

CARD BEING ANALYZED: {card_name} from {bank_name}
{card_structure_info}
CONTENT:
{content}

TASK: Find golf benefits. Look for:
1. Lists of cards with "once a month" or "twice a month" access
2. If "Diners Club Credit Card" is listed, note its frequency - this applies to Duo Card too!

Extract into JSON array:
{{
  "title": "Golf benefit name",
  "description": "ONE sentence only",
  "value": "1 complimentary session",
  "frequency": "once per month OR twice per month - CRITICAL!",
  "eligible_cards": ["The specific card(s) - if Diners Club listed, include both 'Diners Club Credit Card' AND note it applies to 'Duo Credit Card'"],
  "merchants": ["Golf course names"],
  "minimum_spend": "AED amount if mentioned",
  "conditions": ["Booking requirements", "Terms"],
  "fees": {{"processing_fee": "AED 30", "no_show_fee": "AED 249", "cart_fee": "As applicable"}}
}}

CRITICAL RULES:
1. FIND THE FREQUENCY - look for "once a month" or "twice a month" lists
2. If "Diners Club Credit Card" appears in "once a month" list → Duo Card gets golf ONCE per month
3. Include ALL fees mentioned (processing fee, no-show fee, cart charges)
4. Include minimum spend requirements

Example for Duo Card when "Diners Club Credit Card" is in "once a month" list:
{{
  "title": "Complimentary Golf Access",
  "description": "Free green fee at participating golf courses via Diners Club card",
  "value": "1 complimentary session",
  "frequency": "once per month",
  "eligible_cards": ["Diners Club Credit Card", "Duo Credit Card (via Diners Club)"],
  "merchants": ["Jebel Ali Golf Club", "Arabian Ranches Golf Club", "Sharjah Golf & Shooting Club"],
  "minimum_spend": "AED 5,000 per month",
  "conditions": ["Book in advance", "AED 249 fee if spend below AED 5,000"],
  "fees": {{"processing_fee": "AED 30", "no_show_fee": "AED 249", "cart_fee": "As applicable"}}
}}

Return ONLY valid JSON array:"""

    def _extract_card_specific_golf_benefits(self, content: str, card_name: str) -> Dict[str, Any]:
        """
        Extract golf benefits specifically for the given card using regex.
        
        Parses eligibility lists like:
        "These cards give you golf access twice a month:"
        - Card A
        - Card B
        
        "These cards give you golf access once a month:"
        - Diners Club Credit Card  <-- This means Duo Card gets golf!
        
        Returns dict with card-specific eligibility.
        """
        result = {
            'card_found': False,
            'frequency': None,
            'via_card': None,  # For combo cards like Duo
            'golf_courses': [],
            'fees': {},
            'minimum_spend': None
        }
        
        if not card_name:
            return result
        
        card_name_lower = card_name.lower()
        content_lower = content.lower()
        
        # For Duo card, check for Diners Club
        is_duo_card = 'duo' in card_name_lower
        
        # Cards to look for
        cards_to_find = [card_name_lower]
        if is_duo_card:
            cards_to_find.extend(['diners club', 'diners club credit card'])
        
        # Parse frequency sections
        # Look for "twice a month" and "once a month" sections
        twice_section = ""
        once_section = ""
        
        # Split by frequency markers
        twice_match = re.search(r'(twice\s+a\s+month|two\s+times?\s+(?:a|per)\s+month)[:\s]*(.*?)(?=once\s+a\s+month|one\s+time?\s+(?:a|per)\s+month|book\s+a\s+golf|fees\s+and\s+charges|$)', 
                                content_lower, re.DOTALL | re.IGNORECASE)
        once_match = re.search(r'(once\s+a\s+month|one\s+time?\s+(?:a|per)\s+month)[:\s]*(.*?)(?=twice\s+a\s+month|book\s+a\s+golf|fees\s+and\s+charges|$)', 
                               content_lower, re.DOTALL | re.IGNORECASE)
        
        if twice_match:
            twice_section = twice_match.group(2)
        if once_match:
            once_section = once_match.group(2)
        
        # Check which section contains our card
        for card_pattern in cards_to_find:
            if card_pattern in twice_section:
                result['card_found'] = True
                result['frequency'] = 'twice per month'
                if card_pattern != card_name_lower:
                    result['via_card'] = card_pattern.title()
                break
            elif card_pattern in once_section:
                result['card_found'] = True
                result['frequency'] = 'once per month'
                if card_pattern != card_name_lower:
                    result['via_card'] = card_pattern.title()
                break
        
        # Extract golf courses
        course_patterns = [
            r'jebel\s*ali\s*(?:golf\s*)?(?:club|resort)?',
            r'arabian\s*ranches\s*(?:golf\s*)?(?:club)?',
            r'(?:the\s+)?track[,\s]*meydan(?:\s*golf)?',
            r'abu\s*dhabi\s*(?:city\s*)?golf\s*(?:club)?',
            r'sharjah\s*golf\s*(?:&|and)?\s*(?:shooting\s*)?(?:club)?',
            r'emirates\s*golf\s*(?:club)?',
        ]
        
        for pattern in course_patterns:
            if re.search(pattern, content_lower):
                # Clean up the course name
                match = re.search(pattern, content_lower)
                if match:
                    course_name = match.group(0).title()
                    course_name = re.sub(r'\s+', ' ', course_name)
                    if course_name not in result['golf_courses']:
                        result['golf_courses'].append(course_name)
        
        # Extract fees
        processing_fee = re.search(r'processing\s*fee[:\s]*(?:aed\s*)?([\d,]+)', content_lower)
        if processing_fee:
            result['fees']['processing_fee'] = f"AED {processing_fee.group(1)}"
        
        no_show_fee = re.search(r'no[\s-]*show\s*fee[:\s]*(?:aed\s*)?([\d,]+)', content_lower)
        if no_show_fee:
            result['fees']['no_show_fee'] = f"AED {no_show_fee.group(1)}"
        
        cart_fee = re.search(r'(?:golf\s*)?cart\s*(?:charges?|fee)[:\s]*((?:aed\s*)?[\d,]+|as\s*applicable)', content_lower)
        if cart_fee:
            result['fees']['cart_fee'] = cart_fee.group(1).title()
        
        # Extract minimum spend
        min_spend = re.search(r'minimum\s*(?:monthly\s*)?spend\s*(?:of\s*)?(?:aed\s*)?([\d,]+)', content_lower)
        if min_spend:
            result['minimum_spend'] = f"AED {min_spend.group(1)}"
        
        return result
    
    def parse_llm_response(
        self, 
        response: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """Parse LLM response into ExtractedBenefit objects."""
        import logging
        logger = logging.getLogger(__name__)
        
        benefits = []
        
        # Try to parse JSON from response
        parsed = self._parse_llm_json(response)
        
        if not parsed:
            return benefits
        
        # Handle both array and object responses
        items = parsed if isinstance(parsed, list) else parsed.get('items', [parsed])
        
        logger.info(f"[{self.name}] Parsing {len(items)} items from LLM response")
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            # Log the raw item for debugging
            logger.info(f"[{self.name}] Raw LLM item: frequency={item.get('frequency')}, eligible_cards={item.get('eligible_cards')}, value={item.get('value')}")
            
            # Generate unique ID
            benefit_id = hashlib.md5(
                f"{item.get('title') or ''}{url}".encode()
            ).hexdigest()[:16]
            
            # Extract fees from nested structure if present
            fees_data = item.get('fees', {})
            
            # Use sanitize utility for conditions
            conditions = sanitize_conditions(item.get('conditions', []))
            
            # Add fee information to conditions if present (handle both key variations)
            if isinstance(fees_data, dict):
                proc_fee = to_string(fees_data.get('processing_fee'))
                if proc_fee:
                    conditions.append(f"Processing fee: {proc_fee}")
                no_show = to_string(fees_data.get('no_show_fee'))
                if no_show:
                    conditions.append(f"No-show fee: {no_show}")
                # Handle both cart_charges and cart_fee
                cart_fee = to_string(fees_data.get('cart_fee') or fees_data.get('cart_charges'))
                if cart_fee:
                    conditions.append(f"Golf cart charges: {cart_fee}")
            
            # Extract booking details
            booking_data = item.get('booking_details', {})
            if isinstance(booking_data, dict):
                method = to_string(booking_data.get('method'))
                if method:
                    conditions.append(f"Booking: {method}")
                adv = to_string(booking_data.get('advance_booking'))
                if adv:
                    conditions.append(f"Advance booking: {adv}")
                reg = to_string(booking_data.get('registration'))
                if reg:
                    conditions.append(f"Registration: {reg}")
            
            # Handle booking info at top level - use to_string helper
            booking_method = to_string(item.get('booking_method'))
            if booking_method:
                conditions.append(f"Booking method: {booking_method}")
            
            # Handle booking_methods list
            booking_methods = to_string_list(item.get('booking_methods'))
            if booking_methods:
                conditions.append(f"Booking methods: {', '.join(booking_methods)}")
            
            sms_num = to_string(item.get('sms_number'))
            if sms_num:
                conditions.append(f"SMS booking: {sms_num}")
            phone_num = to_string(item.get('phone_number'))
            if phone_num:
                conditions.append(f"Phone booking: {phone_num}")
            booking_contact = to_string(item.get('booking_contact'))
            if booking_contact:
                conditions.append(f"Booking contact: {booking_contact}")
            adv_booking = to_string(item.get('advance_booking'))
            if adv_booking:
                conditions.append(f"Advance booking: {adv_booking}")
            
            # Use sanitize utilities for lists
            eligible_cards = sanitize_categories(item.get('eligible_cards', []))
            eligible_categories = sanitize_categories(item.get('eligible_categories', []))
            
            # Merge eligible_cards into eligible_categories if not already there
            for card in eligible_cards:
                if card and card not in eligible_categories:
                    eligible_categories.append(card)
            
            # Also add eligible card info to conditions for visibility
            if eligible_cards:
                card_str = ", ".join(eligible_cards)
                if "Eligible card" not in str(conditions):
                    conditions.append(f"Eligible cards: {card_str}")
            
            # Use sanitize utility for merchants
            merchants = sanitize_merchants(item.get('merchants', []))
            
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title=to_string(item.get('title')) or 'Golf Benefit',
                description=to_string(item.get('description')) or '',
                value=to_string(item.get('value')),
                conditions=conditions,
                merchants=merchants,
                eligible_categories=eligible_categories,
                minimum_spend=to_string(item.get('minimum_spend')),
                frequency=to_string(item.get('frequency')),
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='llm',
                confidence=0.7,
                confidence_level=ConfidenceLevel.MEDIUM,
                pipeline_version=self.version,
            )
            
            benefits.append(benefit)
        
        return benefits
    
    def _extract_from_source_with_patterns(
        self, 
        content: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """Extract golf benefits using comprehensive regex patterns.
        
        IMPORTANT: Pattern extraction uses card-specific extraction to get
        accurate frequency and eligibility for the card being analyzed.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        benefits = []
        content_lower = content.lower()
        
        # Get card context for validation
        card_context = getattr(self, '_card_context', {})
        card_name = card_context.get('card_name') or ''
        card_name_lower = card_name.lower()
        
        # CRITICAL: Get card-specific golf eligibility first
        card_specific = self._extract_card_specific_golf_benefits(content, card_name)
        
        logger.info(f"[{self.name}] Card-specific golf extraction for '{card_name}': {card_specific}")
        logger.debug(f"[{self.name}] Card-specific golf extraction: {card_specific}")
        
        # ========== 1. EXTRACT ALL GOLF COURSES ==========
        courses_found = set()
        
        # Use card-specific courses if available
        if card_specific.get('golf_courses'):
            courses_found = set(card_specific['golf_courses'])
        else:
            # Use compiled patterns for known courses
            for pattern_name, pattern in self.compiled_patterns.items():
                if pattern_name.startswith('course_'):
                    if pattern.search(content_lower):
                        # Map to proper course name
                        course_key = pattern_name.replace('course_', '')
                        for known_course in self.UAE_GOLF_COURSES:
                            if course_key.replace('_', ' ') in known_course.lower():
                                courses_found.add(known_course)
                                break
            
            # Also do direct text search for course names
            for course in self.UAE_GOLF_COURSES:
                # Check variations
                course_lower = course.lower()
                course_simple = course_lower.replace(' & ', ' ').replace(',', '')
            if course_lower in content_lower or course_simple in content_lower:
                courses_found.add(course)
        
        # ========== CREATE CARD-SPECIFIC GOLF BENEFIT (PRIORITY) ==========
        # If we have card-specific data, create a high-confidence benefit
        if card_specific.get('card_found') and card_specific.get('frequency'):
            via_card = card_specific.get('via_card', '')
            eligible_cards = [card_name]
            if via_card:
                eligible_cards.append(f"{via_card} (component card)")
            
            conditions = []
            
            # Add frequency as primary condition
            conditions.append(f"Frequency: {card_specific['frequency']}")
            
            # Add via card info
            if via_card:
                conditions.append(f"Golf access via {via_card} component of {card_name}")
            
            # Add fees
            fees = card_specific.get('fees', {})
            if fees.get('processing_fee'):
                conditions.append(f"Processing fee: {fees['processing_fee']}")
            if fees.get('no_show_fee'):
                conditions.append(f"No-show fee: {fees['no_show_fee']}")
            if fees.get('cart_fee'):
                conditions.append(f"Golf cart: {fees['cart_fee']}")
            
            # Add minimum spend
            if card_specific.get('minimum_spend'):
                conditions.append(f"Minimum monthly spend: {card_specific['minimum_spend']}")
            
            # Use card-specific courses or found courses
            golf_courses = card_specific.get('golf_courses', []) or list(courses_found)
            
            benefit_id = hashlib.md5(f"golf_card_specific_{card_name}_{url}".encode()).hexdigest()[:16]
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title=f"Golf Access - {card_name}",
                description=f"Complimentary golf access {card_specific['frequency']}" + (f" via {via_card}" if via_card else ""),
                value=f"1 session {card_specific['frequency']}",
                frequency=card_specific['frequency'],
                merchants=golf_courses,
                eligible_categories=eligible_cards,
                minimum_spend=card_specific.get('minimum_spend'),
                conditions=conditions,
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='pattern+card_specific',
                confidence=0.95,
                confidence_level=ConfidenceLevel.HIGH,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
            logger.info(f"[{self.name}] Created card-specific golf benefit for {card_name}: {card_specific['frequency']}")
        
        # Only add generic course benefit if we don't have card-specific data
        elif courses_found:
            benefit_id = hashlib.md5(f"golf_courses_{url}".encode()).hexdigest()[:16]
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title="Eligible Golf Courses",
                description=f"Access to {len(courses_found)} premium golf courses in UAE",
                value=f"{len(courses_found)} courses",
                merchants=list(courses_found),
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='pattern',
                confidence=0.95,
                confidence_level=ConfidenceLevel.HIGH,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        # ========== 2. EXTRACT ACCESS FREQUENCY - CONSERVATIVE APPROACH ==========
        # Only extract frequency if we can identify the specific card type it applies to
        # Don't create generic "Premium Cards" benefits
        
        # Look for specific card type mentions along with frequency
        frequency_card_patterns = [
            # Diners Club patterns
            (r'diners\s*club.*?once\s*(?:a|per|each)?\s*month|once\s*(?:a|per|each)?\s*month.*?diners\s*club', 
             'Diners Club', 'once per month', '1 session per month'),
            (r'diners\s*club.*?twice\s*(?:a|per|each)?\s*month|twice\s*(?:a|per|each)?\s*month.*?diners\s*club', 
             'Diners Club', 'twice per month', '2 sessions per month'),
            # Visa Infinite patterns  
            (r'visa\s*infinite.*?twice\s*(?:a|per|each)?\s*month|twice\s*(?:a|per|each)?\s*month.*?visa\s*infinite', 
             'Visa Infinite', 'twice per month', '2 sessions per month'),
            (r'visa\s*infinite.*?once\s*(?:a|per|each)?\s*month|once\s*(?:a|per|each)?\s*month.*?visa\s*infinite', 
             'Visa Infinite', 'once per month', '1 session per month'),
            # World Elite patterns
            (r'world\s*elite.*?twice\s*(?:a|per|each)?\s*month|twice\s*(?:a|per|each)?\s*month.*?world\s*elite', 
             'World Elite', 'twice per month', '2 sessions per month'),
        ]
        
        for pattern, card_type, freq, value in frequency_card_patterns:
            if re.search(pattern, content_lower, re.DOTALL):
                # Only add if relevant to the card being analyzed or if card context is empty
                is_relevant = (
                    not card_name or 
                    card_type.lower() in card_name or
                    any(term in card_name for term in card_type.lower().split())
                )
                
                if is_relevant:
                    benefit_id = hashlib.md5(f"golf_{card_type}_{freq}_{url}".encode()).hexdigest()[:16]
                    benefit = ExtractedBenefit(
                        benefit_id=benefit_id,
                        benefit_type=self.benefit_type,
                        title=f"{card_type} Golf Access",
                        description=f"Complimentary green fee access {freq}",
                        value=value,
                        frequency=freq,
                        eligible_categories=[card_type],
                        source_url=url,
                        source_title=title,
                        source_index=index,
                        extraction_method='pattern',
                        confidence=0.85,
                        confidence_level=ConfidenceLevel.MEDIUM,
                        pipeline_version=self.version,
                    )
                    benefits.append(benefit)
        
        # ========== 3. EXTRACT ALL FEES ==========
        # Processing fee - multiple patterns
        processing_fee_patterns = [
            r'processing\s*fee[:\s]*(?:of\s*)?(?:aed\s*)?(\d+)',
            r'aed\s*(\d+)\s*(?:per\s*)?processing',
            r'(\d+)\s*aed\s*processing',
        ]
        for pattern in processing_fee_patterns:
            match = re.search(pattern, content_lower)
            if match:
                fee_value = match.group(1)
                benefit_id = hashlib.md5(f"golf_processing_fee_{url}".encode()).hexdigest()[:16]
                benefit = ExtractedBenefit(
                    benefit_id=benefit_id,
                    benefit_type=self.benefit_type,
                    title="Golf Processing Fee",
                    description="Processing fee charged per golf booking",
                    value=f"AED {fee_value}",
                    conditions=["Charged per booking", "Non-refundable"],
                    source_url=url,
                    source_title=title,
                    source_index=index,
                    extraction_method='pattern',
                    confidence=0.95,
                    confidence_level=ConfidenceLevel.HIGH,
                    pipeline_version=self.version,
                )
                benefits.append(benefit)
                break
        
        # No-show fee - multiple patterns
        no_show_patterns = [
            r'no[- ]?show\s*(?:fee|charge|penalty)[:\s]*(?:of\s*)?(?:aed\s*)?(\d+)',
            r'aed\s*(\d+)\s*(?:for\s*)?no[- ]?show',
            r'(\d+)\s*aed\s*no[- ]?show',
            r'no[- ]?show.*?aed\s*(\d+)',
        ]
        for pattern in no_show_patterns:
            match = re.search(pattern, content_lower)
            if match:
                fee_value = match.group(1)
                benefit_id = hashlib.md5(f"golf_noshow_fee_{url}".encode()).hexdigest()[:16]
                benefit = ExtractedBenefit(
                    benefit_id=benefit_id,
                    benefit_type=self.benefit_type,
                    title="Golf No-Show Fee",
                    description="Penalty fee for missing booked golf session without cancellation",
                    value=f"AED {fee_value}",
                    conditions=["Charged for no-show without prior cancellation", "Cancel 24 hours in advance to avoid"],
                    source_url=url,
                    source_title=title,
                    source_index=index,
                    extraction_method='pattern',
                    confidence=0.95,
                    confidence_level=ConfidenceLevel.HIGH,
                    pipeline_version=self.version,
                )
                benefits.append(benefit)
                break
        
        # Golf cart charges
        if 'golf cart' in content_lower or 'cart charge' in content_lower:
            cart_info = "Charges applicable"
            cart_match = re.search(r'(?:golf\s*)?cart[:\s]*(?:charges?\s*)?(?:aed\s*)?(\d+)', content_lower)
            if cart_match:
                cart_info = f"AED {cart_match.group(1)}"
            
            benefit_id = hashlib.md5(f"golf_cart_fee_{url}".encode()).hexdigest()[:16]
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title="Golf Cart Charges",
                description="Golf cart rental fees at participating courses",
                value=cart_info,
                conditions=["Payable at the course", "Optional"],
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='pattern',
                confidence=0.85,
                confidence_level=ConfidenceLevel.HIGH,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        # ========== 4. EXTRACT BOOKING INFORMATION ==========
        booking_info = []
        booking_contact = None
        
        # SMS booking - multiple patterns
        sms_patterns = [
            r'sms\s*(?:to\s*)?(\d{4,})',
            r'send\s*(?:an?\s*)?sms\s*(?:to\s*)?(\d{4,})',
            r'text\s*(?:to\s*)?(\d{4,})',
        ]
        for pattern in sms_patterns:
            sms_match = re.search(pattern, content_lower)
            if sms_match:
                booking_contact = f"SMS to {sms_match.group(1)}"
                booking_info.append(f"Book via SMS to {sms_match.group(1)}")
                break
        
        # Phone booking - improved patterns for UAE numbers
        phone_patterns = [
            r'(?:call|phone|dial|contact)[:\s]*(\+?971[\s-]?\d[\d\s-]{6,})',  # UAE international format
            r'(?:call|phone|dial|contact)[:\s]*(04[\s-]?\d[\d\s-]{6,})',       # Dubai landline
            r'(?:call|phone|dial|contact)[:\s]*(800[\s-]?\d[\d\s-]{3,})',      # Toll-free
            r'(?:call|phone|dial|contact)[:\s]*(\+?\d[\d\s-]{7,})',            # General format
            r'(?:hotline|helpline)[:\s]*(\+?\d[\d\s-]{7,})',                   # Hotline
            r'at\s*(\+?971[\s-]?\d[\d\s-]{6,})',                               # "at +971..."
            r'(?:phone|tel|telephone)\s*(?:number|no\.?)?[:\s]*(\+?\d[\d\s-]{7,})',  # Phone number: format
        ]
        for pattern in phone_patterns:
            phone_match = re.search(pattern, content_lower)
            if phone_match:
                phone = phone_match.group(1).strip()
                # Clean up the phone number
                phone_clean = re.sub(r'[\s-]+', ' ', phone).strip()
                booking_info.append(f"Call {phone_clean}")
                if not booking_contact:
                    booking_contact = f"Phone: {phone_clean}"
                break
        
        # Also look for phone numbers near "book" or "reservation" keywords
        if not any('Call' in info for info in booking_info):
            context_phone_match = re.search(
                r'(?:book|reserv|golf).*?(\+?971[\s-]?\d[\d\s-]{6,}|\d{3}[\s-]?\d{3,}[\s-]?\d{3,})',
                content_lower
            )
            if context_phone_match:
                phone = context_phone_match.group(1).strip()
                phone_clean = re.sub(r'[\s-]+', ' ', phone).strip()
                booking_info.append(f"Call {phone_clean}")
        
        # Advance booking requirement
        advance_match = re.search(r'(\d+)\s*(?:hours?|days?|hrs?)\s*(?:in\s*)?advance', content_lower)
        if advance_match:
            booking_info.append(f"Book {advance_match.group(1)} hours/days in advance")
        elif 'advance' in content_lower and 'book' in content_lower:
            booking_info.append("Advance booking required")
        
        # Registration requirement
        if 'registration' in content_lower or 'register' in content_lower:
            if 'card' in content_lower:
                booking_info.append("Card registration required before first use")
        
        if booking_info:
            benefit_id = hashlib.md5(f"golf_booking_info_{url}".encode()).hexdigest()[:16]
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title="Golf Booking Process",
                description="How to book complimentary golf sessions",
                value=booking_contact or "See conditions",
                conditions=booking_info,
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='pattern',
                confidence=0.9,
                confidence_level=ConfidenceLevel.HIGH,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        # ========== 5. EXTRACT ELIGIBLE CARD TYPES ==========
        card_types_found = set()
        card_patterns = [
            (r'visa\s*infinite', 'Visa Infinite'),
            (r'visa\s*signature', 'Visa Signature'),
            (r'world\s*elite', 'World Elite Mastercard'),
            (r'mastercard\s*world', 'Mastercard World'),
            (r'platinum', 'Platinum Card'),
            (r'beyond', 'Beyond Card'),
            (r'signature\s*(?:credit|debit)', 'Signature Card'),
            (r'infinite\s*(?:credit|debit)', 'Infinite Card'),
        ]
        
        for pattern, card_name in card_patterns:
            if re.search(pattern, content_lower):
                card_types_found.add(card_name)
        
        if card_types_found:
            benefit_id = hashlib.md5(f"golf_eligible_cards_{url}".encode()).hexdigest()[:16]
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title="Eligible Card Types for Golf",
                description=f"{len(card_types_found)} card types eligible for golf privileges",
                value=f"{len(card_types_found)} card types",
                eligible_categories=list(card_types_found),
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='pattern',
                confidence=0.9,
                confidence_level=ConfidenceLevel.HIGH,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        # ========== 6. EXTRACT MINIMUM SPEND ==========
        spend_match = re.search(
            r'(?:minimum|min\.?)\s*(?:monthly\s*)?spend[:\s]*(?:of\s*)?(?:aed\s*)?([\d,]+)',
            content_lower
        )
        if spend_match:
            spend_value = spend_match.group(1).replace(',', '')
            benefit_id = hashlib.md5(f"golf_min_spend_{url}".encode()).hexdigest()[:16]
            benefit = ExtractedBenefit(
                benefit_id=benefit_id,
                benefit_type=self.benefit_type,
                title="Minimum Spend Requirement",
                description=f"Monthly minimum spend required to maintain golf privileges",
                value=f"AED {spend_value}",
                minimum_spend=f"AED {spend_value}",
                conditions=[
                    f"Maintain monthly spend of AED {spend_value}",
                    "Fee may be charged if requirement not met"
                ],
                source_url=url,
                source_title=title,
                source_index=index,
                extraction_method='pattern',
                confidence=0.9,
                confidence_level=ConfidenceLevel.HIGH,
                pipeline_version=self.version,
            )
            benefits.append(benefit)
        
        return benefits


# Register pipeline
pipeline_registry.register(GolfPipeline)