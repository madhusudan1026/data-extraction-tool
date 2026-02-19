"""
Intelligence Extraction Service.

Uses LLM to extract flexible intelligence items rather than fitting into rigid schemas.
The goal is to preserve all valuable information with proper context and relationships.
"""

import json
import uuid
import re
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.models.extracted_intelligence import (
    IntelligenceItem, IntelligenceCategory,
    CardInfo, CardVariant, FeeStructure, EligibilityCriteria,
    ValueSpec, Condition, Entity, SourceReference, ValueType, ConditionType
)
from app.core.config import settings
from app.services.ollama_client import ollama_client, parse_llm_json
from app.utils.logger import logger


class IntelligenceExtractionService:
    """Service to extract flexible intelligence from credit card content."""
    
    def __init__(self):
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.default_model = settings.DEFAULT_MODEL
        self.timeout = 300.0  # Increased to 5 minutes for complex extractions
    
    # Default keywords for relevance scoring
    DEFAULT_KEYWORDS = [
        'benefit', 'reward', 'cashback', 'discount', 'lounge', 'airport',
        'travel', 'insurance', 'annual fee', 'interest rate', 'eligibility',
        'minimum salary', 'points', 'miles', 'complimentary', 'free',
        'cinema', 'golf', 'concierge', 'valet', 'dining', 'shopping',
        'partner', 'merchant', 'offer', 'promotion', 'feature',
        'aed', 'usd', '%', 'per month', 'per year', 'waived',
        'mastercard', 'visa', 'diners', 'platinum', 'signature', 'world',
        'credit limit', 'supplementary', 'apply', 'requirement'
    ]
    
    def _preprocess_content(self, content: str, max_length: int = 12000, keywords: List[str] = None) -> str:
        """
        Preprocess and clean content to extract the most relevant parts.
        Focus on credit card specific information.
        
        Args:
            content: Raw content to preprocess
            max_length: Maximum length of output
            keywords: Custom keywords for relevance scoring (uses defaults if None)
        """
        # Use custom keywords if provided, otherwise use defaults
        relevant_keywords = keywords if keywords else self.DEFAULT_KEYWORDS
        
        logger.info(f"Using {len(relevant_keywords)} keywords for relevance scoring")
        logger.info(f"Original content length: {len(content)}")
        
        # Debug: Log a sample of the content to see its structure
        logger.info(f"Content sample (first 500 chars): {content[:500]}")
        logger.info(f"Content has 'Content from' marker: {'--- Content from' in content}")
        logger.info(f"Newline count in content: {content.count(chr(10))}")
        
        # Benefit indicator patterns - used to split long paragraphs into benefit-focused sections
        benefit_indicators = [
            # Bullets and list markers
            r'(?:^|\n)\s*[•●○■□▪▸►]\s*',
            r'(?:^|\n)\s*[-–—]\s+(?=[A-Z])',
            r'(?:^|\n)\s*\d+[.)]\s+',
            r'(?:^|\n)\s*[a-z][.)]\s+',
            # Benefit keywords at start of sentence
            r'(?:^|\n)(?:Enjoy|Get|Earn|Receive|Benefit|Access|Save|Free|Complimentary|Exclusive)\s+',
            r'(?:^|\n)(?:Up to|Upto|Minimum|Maximum|Starting from)\s+\d+',
            # Percentage/amount patterns
            r'(?:^|\n)[^.]*?\d+%\s+(?:cashback|discount|off|reward|back)',
            r'(?:^|\n)[^.]*?(?:AED|USD|EUR)\s*\d+',
        ]
        
        # Split by content source markers first (most reliable)
        source_sections = []
        if '--- Content from' in content:
            # Debug: Show where markers are
            marker_positions = [m.start() for m in re.finditer(r'--- Content from', content)]
            logger.info(f"Found {len(marker_positions)} '--- Content from' markers at positions: {marker_positions[:5]}...")
            
            # Sample the marker format
            first_marker_pos = content.find('--- Content from')
            marker_sample = content[first_marker_pos:first_marker_pos+200]
            logger.info(f"First marker sample: {marker_sample[:150]}")
            
            # More flexible regex - match everything until end of line or triple dash
            parts = re.split(r'(--- Content from .+? ---|\n--- Content from [^\n]+\n)', content)
            logger.info(f"Split into {len(parts)} parts")
            
            current_source = "main"
            current_content = ""
            
            for i, part in enumerate(parts):
                if '--- Content from' in part:
                    if current_content.strip():
                        source_sections.append((current_source, current_content.strip()))
                    current_source = part.strip()
                    current_content = ""
                else:
                    current_content += part
            
            if current_content.strip():
                source_sections.append((current_source, current_content.strip()))
            
            logger.info(f"Split into {len(source_sections)} source sections")
            
            # If still 0, try alternative approach - split by just the marker text
            if len(source_sections) == 0:
                logger.info("Trying alternative split approach...")
                # Split by newline + marker
                alt_parts = content.split('\n--- Content from ')
                logger.info(f"Alternative split gave {len(alt_parts)} parts")
                
                for i, part in enumerate(alt_parts):
                    if i == 0:
                        # First part is content before any marker
                        if part.strip():
                            source_sections.append(("main", part.strip()))
                    else:
                        # Find where the marker ends (look for ---\n or just take first line as source)
                        newline_pos = part.find('\n')
                        if newline_pos > 0:
                            source_name = '--- Content from ' + part[:newline_pos].strip()
                            section_content = part[newline_pos:].strip()
                            if section_content:
                                source_sections.append((source_name, section_content))
                
                logger.info(f"Alternative split gave {len(source_sections)} source sections")
        else:
            source_sections = [("main", content)]
            logger.info(f"No source markers found, treating as single section")
        
        # Now split each source section into paragraphs
        all_sections = []
        for source, source_content in source_sections:
            # Clean whitespace but preserve structure
            source_content = re.sub(r'[ \t]+', ' ', source_content)
            source_content = re.sub(r'\n{3,}', '\n\n', source_content)
            
            # Log what we're working with
            newline_count = source_content.count('\n')
            logger.info(f"Source section has {len(source_content)} chars, {newline_count} newlines")
            
            # Try different splitting strategies
            paragraphs = []
            
            # Strategy 1: Try double newlines first
            paragraphs = [p.strip() for p in re.split(r'\n\n+', source_content) if p.strip()]
            logger.info(f"Double newline split: {len(paragraphs)} paragraphs")
            
            # Strategy 2: If we got very few paragraphs, try single newlines
            if len(paragraphs) < 5:
                single_split = [p.strip() for p in source_content.split('\n') if p.strip() and len(p.strip()) > 30]
                if len(single_split) > len(paragraphs):
                    paragraphs = single_split
                    logger.info(f"Single newline split: {len(paragraphs)} paragraphs")
            
            # Strategy 3: If still too few, try sentence splitting (period + space + capital)
            if len(paragraphs) < 5 and len(source_content) > 500:
                sentence_split = [p.strip() for p in re.split(r'(?<=[.!?])\s+(?=[A-Z])', source_content) if p.strip() and len(p.strip()) > 30]
                if len(sentence_split) > len(paragraphs):
                    paragraphs = sentence_split
                    logger.info(f"Sentence split: {len(paragraphs)} paragraphs")
            
            # Strategy 4: If STILL too few (content is one big blob), use aggressive splitting
            if len(paragraphs) < 5 and len(source_content) > 500:
                # Split by any period followed by space
                aggressive_split = [p.strip() for p in re.split(r'\.\s+', source_content) if p.strip() and len(p.strip()) > 20]
                if len(aggressive_split) > len(paragraphs):
                    paragraphs = aggressive_split
                    logger.info(f"Aggressive period split: {len(paragraphs)} paragraphs")
            
            # Strategy 5: If content has common separators, split on those
            if len(paragraphs) < 10 and len(source_content) > 1000:
                # Try splitting on common benefit separators
                separator_patterns = [
                    r'\s*[|•●○]\s*',  # Pipe or bullet
                    r'\s*;\s*',        # Semicolon
                    r'\s+(?=\d+%)',    # Before percentages
                    r'\s+(?=AED\s*\d)', # Before AED amounts
                    r'\s+(?=Enjoy|Get|Earn|Free|Complimentary)\s+',  # Before benefit words
                ]
                
                for sep_pattern in separator_patterns:
                    sep_split = [p.strip() for p in re.split(sep_pattern, source_content) if p.strip() and len(p.strip()) > 20]
                    if len(sep_split) > len(paragraphs):
                        paragraphs = sep_split
                        logger.info(f"Separator pattern split ({sep_pattern[:20]}...): {len(paragraphs)} paragraphs")
                        break
            
            # Strategy 6: Last resort - chunk by character count
            if len(paragraphs) < 5 and len(source_content) > 1000:
                chunk_size = 500
                chunks = []
                for i in range(0, len(source_content), chunk_size):
                    chunk = source_content[i:i+chunk_size].strip()
                    if len(chunk) > 50:
                        chunks.append(chunk)
                if len(chunks) > len(paragraphs):
                    paragraphs = chunks
                    logger.info(f"Chunk split ({chunk_size} chars): {len(paragraphs)} chunks")
            
            for para in paragraphs:
                if len(para) >= 30:  # Minimum length
                    all_sections.append((source, para))
        
        logger.info(f"Split content into {len(all_sections)} total paragraphs/sections")
        
        # ADDITIONAL: Split long sections further using benefit indicators
        # This helps extract individual benefits from dense paragraphs
        refined_sections = []
        for source, section in all_sections:
            # If section is short enough, keep as is
            if len(section) < 300:
                refined_sections.append((source, section))
                continue
            
            # Try to split by benefit indicators
            sub_sections = [section]  # Start with the full section
            
            for pattern in benefit_indicators:
                new_sub_sections = []
                for sub in sub_sections:
                    if len(sub) < 200:
                        new_sub_sections.append(sub)
                        continue
                    
                    # Split by this pattern
                    parts = re.split(pattern, sub)
                    for part in parts:
                        part = part.strip()
                        if len(part) >= 30:
                            new_sub_sections.append(part)
                
                sub_sections = new_sub_sections
            
            # Add all sub-sections
            for sub in sub_sections:
                if len(sub) >= 30:
                    refined_sections.append((source, sub))
        
        logger.info(f"After keyword-based splitting: {len(refined_sections)} refined sections")
        
        # Score each section by relevance
        scored_sections = []
        for source, section in refined_sections:
            # Count keyword matches
            score = sum(1 for kw in relevant_keywords if kw.lower() in section.lower())
            
            # Boost sections with numbers/percentages (likely contain specific values)
            if re.search(r'\d+%|\d+\s*aed|aed\s*\d+', section.lower()):
                score += 5
            
            # Boost sections with currency amounts
            if re.search(r'aed|usd|gbp|eur|\$|£|€', section.lower()):
                score += 2
            
            # Boost sections mentioning specific benefits
            benefit_terms = ['lounge', 'cashback', 'reward', 'points', 'miles', 'insurance', 'discount']
            for term in benefit_terms:
                if term in section.lower():
                    score += 2
            
            if score > 0:  # Only include sections with at least one keyword match
                scored_sections.append((score, section))
        
        logger.info(f"After keyword filtering: {len(scored_sections)} relevant sections")
        
        # Sort by score (descending) and take top sections
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        
        # Log top scoring sections
        if scored_sections:
            logger.info(f"Top 3 section scores: {[s[0] for s in scored_sections[:3]]}")
        
        # Build final content from most relevant sections and track selection
        final_content = []
        current_length = 0
        sections_with_selection = []  # (score, content, is_selected)
        
        for score, section in scored_sections:
            is_selected = False
            if current_length + len(section) <= max_length:
                final_content.append(section)
                current_length += len(section)
                is_selected = True
            elif not final_content:
                # If we have nothing yet, take a truncated version
                final_content.append(section[:max_length])
                current_length = max_length
                is_selected = True
            
            sections_with_selection.append((score, section, is_selected))
        
        result = '\n\n'.join(final_content)
        
        logger.info(f"Preprocessed content: {len(content)} -> {len(result)} chars, {len(final_content)} sections selected")
        
        # Fallback: if still no content, just truncate original
        if not result:
            logger.warning("No sections found, using truncated original content")
            result = content[:max_length]
            sections_with_selection = [(0, content[:max_length], True)]
        
        return result, sections_with_selection  # Return sections with selection info
    
    async def extract_intelligence(
        self,
        content: str,
        source_url: str = None,
        card_name_hint: str = None,
        bank_hint: str = None,
        custom_keywords: List[str] = None,
        raw_extraction_id: str = None,
        raw_storage = None
    ):  # Returns IntelligenceResult (simple class)
        """
        Extract intelligence from content using LLM.
        
        Args:
            content: The text content to extract from
            source_url: URL of the source
            card_name_hint: Hint about card name if known
            bank_hint: Hint about bank if known
            custom_keywords: Custom keywords for relevance scoring (overrides defaults)
            raw_extraction_id: ID of the raw extraction record (for storing sections)
            raw_storage: RawExtractionStorageService instance
        """
        logger.info(f"Starting intelligence extraction, content length: {len(content)}")
        
        if custom_keywords:
            logger.info(f"Using {len(custom_keywords)} custom keywords")
        
        # Preprocess and extract most relevant content using custom or default keywords
        # Increased to 20000 chars to capture more benefits
        processed_content, scored_sections = self._preprocess_content(content, max_length=20000, keywords=custom_keywords)
        
        # Store sections if raw_storage is provided
        if raw_storage and raw_extraction_id and scored_sections:
            try:
                # Prepare section data for storage
                sections_data = []
                for score, section_content, is_selected in scored_sections:
                    # Analyze section for storage
                    keywords_to_use = custom_keywords if custom_keywords else self.DEFAULT_KEYWORDS
                    keyword_matches = []
                    for kw in keywords_to_use:
                        if kw.lower() in section_content.lower():
                            count = section_content.lower().count(kw.lower())
                            keyword_matches.append({"keyword": kw, "count": count})
                    
                    sections_data.append({
                        "content": section_content,
                        "score": score,
                        "keyword_matches": keyword_matches,
                        "keyword_count": len(keyword_matches),
                        "has_currency": bool(re.search(r'aed|usd|gbp|eur|\$|£|€', section_content, re.IGNORECASE)),
                        "has_percentage": bool(re.search(r'\d+%', section_content)),
                        "has_numbers": bool(re.search(r'\d+', section_content)),
                        "is_selected": is_selected
                    })
                
                await raw_storage.add_sections(raw_extraction_id, sections_data, source_url)
                logger.info(f"Stored {len(sections_data)} sections to raw extraction {raw_extraction_id}")
            except Exception as e:
                logger.warning(f"Failed to store sections: {e}")
        
        # Build the extraction prompt
        prompt = self._build_extraction_prompt(processed_content, card_name_hint, bank_hint)
        
        logger.info(f"Prompt length: {len(prompt)} chars")
        
        # Call LLM with retry
        response = await self._call_llm_with_retry(prompt)
        
        # Parse response
        extracted = self._parse_llm_response(response, source_url)
        
        return extracted
    
    async def _call_llm_with_retry(self, prompt: str, max_retries: int = 2) -> str:
        """Call LLM with retry logic via shared client."""
        result = await ollama_client.generate(
            prompt,
            num_predict=8000,
            timeout=self.timeout,
            max_retries=max_retries,
            caller="intelligence_extraction",
        )
        if result is None:
            raise Exception("LLM call failed after all retries")
        return result
    
    def _build_extraction_prompt(
        self, 
        content: str, 
        card_name_hint: str = None,
        bank_hint: str = None
    ) -> str:
        """Build the LLM prompt for intelligence extraction."""
        
        card_name = card_name_hint or 'Credit Card'
        bank = bank_hint or 'Bank'
        
        # Very simple prompt - just ask for a list
        prompt = f"""Read this credit card information and list all the benefits.

Card: {card_name}
Bank: {bank}

TEXT:
{content}

List every benefit you find in JSON format. Include title, description, and category.

Categories to use: reward, discount, access, insurance, service, fee, eligibility, partner, feature

Example output:
{{"card":{{"name":"{card_name}","bank":"{bank}"}},"intelligence":[{{"title":"Golf Access","description":"Free access to golf courses","category":"access"}}],"fees":{{"annual_fee":{{"raw":"AED 500"}}}},"eligibility":{{"minimum_salary":{{"raw":"AED 10000"}}}}}}

Now list ALL benefits from the text above. Return JSON only:"""
        
        return prompt
    
    def _parse_llm_response(
        self, 
        response: str, 
        source_url: str = None
    ):  # Returns IntelligenceResult
        """Parse LLM response into intelligence result."""
        
        logger.info(f"LLM raw response (first 500 chars): {response[:500]}")
        
        data = parse_llm_json(response)
        if data is None:
            logger.warning("Failed to parse JSON from LLM response, using empty structure")
            data = {}
        
        # Build IntelligenceResult from parsed data
        return self._build_intelligence_document(data, source_url)
    
    def _build_intelligence_document(
        self, 
        data: Dict, 
        source_url: str = None
    ):  # Returns IntelligenceResult
        """Build intelligence result from parsed data."""
        
        # Build card info
        card_data = data.get("card", {})
        
        # Handle networks - could be strings or dicts
        networks_raw = card_data.get("networks", [])
        networks = []
        for n in networks_raw:
            if isinstance(n, str):
                networks.append(n)
            elif isinstance(n, dict):
                networks.append(n.get("name", str(n)))
            else:
                networks.append(str(n))
        
        # Handle tiers - could be strings or dicts
        tiers_raw = card_data.get("tiers", [])
        tiers = []
        for t in tiers_raw:
            if isinstance(t, str):
                tiers.append(t)
            elif isinstance(t, dict):
                tiers.append(t.get("name", str(t)))
            else:
                tiers.append(str(t))
        
        # Handle variants
        variants_raw = card_data.get("variants", [])
        variants = []
        for v in variants_raw:
            if isinstance(v, dict):
                variants.append(CardVariant(
                    name=v.get("name", ""),
                    network=v.get("network"),
                    tier=v.get("tier")
                ))
            elif isinstance(v, str):
                variants.append(CardVariant(name=v))
        
        card = CardInfo(
            name=card_data.get("name", "Unknown Card"),
            bank=card_data.get("bank", "Unknown Bank"),
            card_type=card_data.get("type"),
            networks=networks,
            tiers=tiers,
            variants=variants,
            product_url=source_url
        )
        
        # Build intelligence items
        intelligence_items = []
        for item_data in data.get("intelligence", []):
            item = self._build_intelligence_item(item_data, source_url)
            if item:
                intelligence_items.append(item)
        
        # Build fees
        fees_data = data.get("fees", {})
        fees = FeeStructure(
            annual_fee=self._build_value_spec(fees_data.get("annual_fee")),
            joining_fee=self._build_value_spec(fees_data.get("joining_fee")),
            supplementary_card_fee=self._build_value_spec(fees_data.get("supplementary_card_fee")),
        )
        
        # Build eligibility
        elig_data = data.get("eligibility", {})
        eligibility = EligibilityCriteria(
            minimum_salary=self._build_value_spec(elig_data.get("minimum_salary")),
            minimum_age=self._build_value_spec(elig_data.get("minimum_age")),
            maximum_age=self._build_value_spec(elig_data.get("maximum_age")),
            employment_types=elig_data.get("employment_types", []),
            required_documents=elig_data.get("documents", []),
        )
        
        # Build intelligence index by category
        intelligence_by_category = {}
        for item in intelligence_items:
            cat = item.category
            if cat not in intelligence_by_category:
                intelligence_by_category[cat] = []
            intelligence_by_category[cat].append(item.item_id)
        
        # Collect all tags
        all_tags = list(set(tag for item in intelligence_items for tag in item.tags))
        
        # Collect all entities
        seen_entities = {}
        for item in intelligence_items:
            for entity in item.entities:
                key = f"{entity.type}:{entity.name}"
                if key not in seen_entities:
                    seen_entities[key] = entity
        all_entities = list(seen_entities.values())
        
        # Create a simple response object (not a Beanie document)
        # Using a dict-like structure that can be easily converted
        class IntelligenceResult:
            """Simple result container - not a MongoDB document."""
            def __init__(self):
                self.card = card
                self.intelligence = intelligence_items
                self.fees = fees
                self.eligibility = eligibility
                self.intelligence_by_category = intelligence_by_category
                self.all_tags = all_tags
                self.all_entities = all_entities
                self.sources_processed = [SourceReference(url=source_url)] if source_url else []
                self.extraction_metadata = {
                    "model": self.default_model if hasattr(self, 'default_model') else "phi",
                    "extracted_at": datetime.utcnow().isoformat()
                }
                self.total_items = len(intelligence_items)
                self.confidence_score = 0.0
                self.completeness_score = 0.0
        
        result = IntelligenceResult()
        result.extraction_metadata = {
            "model": self.default_model,
            "extracted_at": datetime.utcnow().isoformat()
        }
        
        # Calculate confidence
        result.confidence_score = self._calculate_confidence_simple(result)
        result.completeness_score = self._calculate_completeness_simple(result)
        
        return result
    
    def _calculate_confidence_simple(self, result) -> float:
        """Calculate confidence score based on extraction quality."""
        score = 0.0
        
        # Has card info
        if result.card.name and result.card.name != "Unknown Card":
            score += 0.2
        if result.card.bank and result.card.bank != "Unknown Bank":
            score += 0.1
        
        # Has intelligence items
        item_count = len(result.intelligence)
        if item_count > 0:
            score += min(0.3, item_count * 0.03)
        
        # Has headline items
        headline_count = len([i for i in result.intelligence if i.is_headline])
        if headline_count > 0:
            score += min(0.1, headline_count * 0.02)
        
        # Has fees
        if result.fees.annual_fee:
            score += 0.1
        
        # Has eligibility
        if result.eligibility.minimum_salary:
            score += 0.1
        
        # Has entities
        if result.all_entities:
            score += 0.1
        
        return min(1.0, score)
    
    def _calculate_completeness_simple(self, result) -> float:
        """Calculate completeness score."""
        checks = [
            result.card.name != "Unknown Card",
            result.card.bank != "Unknown Bank",
            len(result.intelligence) >= 5,
            len(result.intelligence) >= 10,
            len(result.intelligence) >= 20,
            any(i.is_headline for i in result.intelligence),
            result.fees.annual_fee is not None,
            result.eligibility.minimum_salary is not None,
            len(result.all_entities) > 0,
            len(result.all_tags) >= 5,
        ]
        
        return sum(checks) / len(checks)
    
    def _build_intelligence_item(
        self, 
        item_data: Dict, 
        source_url: str = None
    ) -> Optional[IntelligenceItem]:
        """Build a single intelligence item from data."""
        
        if not item_data.get("title") and not item_data.get("description"):
            return None
        
        # Map category string to enum
        category_str = item_data.get("category", "other").lower()
        try:
            category = IntelligenceCategory(category_str)
        except ValueError:
            category = IntelligenceCategory.OTHER
        
        # Build conditions
        conditions = []
        for cond_data in item_data.get("conditions", []):
            cond_type_str = cond_data.get("type", "other").lower()
            try:
                cond_type = ConditionType(cond_type_str)
            except ValueError:
                cond_type = ConditionType.OTHER
            
            conditions.append(Condition(
                type=cond_type,
                description=cond_data.get("description", ""),
                value=cond_data.get("value")
            ))
        
        # Build entities
        entities = []
        for entity_data in item_data.get("entities", []):
            entities.append(Entity(
                name=entity_data.get("name", ""),
                type=entity_data.get("type", "other"),
                category=entity_data.get("category")
            ))
        
        # Build value spec
        value = None
        if item_data.get("value"):
            value = self._build_value_spec(item_data["value"])
        
        return IntelligenceItem(
            item_id=str(uuid.uuid4())[:8],
            title=item_data.get("title", ""),
            description=item_data.get("description", item_data.get("title", "")),
            category=category,
            tags=item_data.get("tags", []),
            value=value,
            conditions=conditions,
            entities=entities,
            is_headline=item_data.get("is_headline", False),
            requires_enrollment=item_data.get("requires_enrollment", False),
            is_conditional=len(conditions) > 0,
            source=SourceReference(
                url=source_url,
                extracted_text=item_data.get("description")
            )
        )
    
    def _build_value_spec(self, value_data: Any) -> Optional[ValueSpec]:
        """Build a ValueSpec from data."""
        
        if value_data is None:
            return None
        
        if isinstance(value_data, str):
            return ValueSpec(raw_value=value_data)
        
        if isinstance(value_data, dict):
            raw = value_data.get("raw", str(value_data.get("numeric", "")))
            
            # Determine value type
            type_str = value_data.get("type", "text").lower()
            try:
                value_type = ValueType(type_str)
            except ValueError:
                value_type = ValueType.TEXT
            
            return ValueSpec(
                raw_value=raw,
                numeric_value=value_data.get("numeric"),
                value_type=value_type,
                currency=value_data.get("currency"),
                unit=value_data.get("unit")
            )
        
        return ValueSpec(raw_value=str(value_data))


# Global instance
intelligence_extraction_service = IntelligenceExtractionService()
