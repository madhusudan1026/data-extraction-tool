"""
Base Pipeline Class

Abstract base class that all benefit extraction pipelines inherit from.
Provides common functionality for:
- Loading raw data from MongoDB
- Processing each source individually
- LLM-first extraction with regex fallback
- Result validation and scoring
- Storing extracted benefits back to MongoDB

Architecture:
- For each source in approved_raw_data:
  1. Filter by relevance keywords
  2. Extract using LLM (primary method)
  3. Extract using regex patterns (fallback/enhancement)
  4. Merge results for completeness
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import re
import json
import asyncio
import hashlib
import os
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..services.ollama_client import ollama_client, parse_llm_json
from ..utils.sanitize import to_string, sanitize_conditions, sanitize_merchants, sanitize_categories
from ..utils.deduplication import (
    deduplicate_within_source,
    deduplicate_across_sources,
    are_benefits_similar,
    merge_benefits,
    DeduplicationStats
)
from ..utils.content_processor import (
    extract_relevant_content,
    calculate_relevance,
)
from ..utils.benefit_merger import (
    dict_to_benefit,
    merge_source_benefits,
    deduplicate_benefits as _deduplicate_benefits_fn,
    score_benefits as _score_benefits_fn,
    enhance_benefit as _enhance_benefit_fn,
    calculate_confidence as _calculate_confidence_fn,
)

# Re-export models so child pipelines importing from base_pipeline still work
from .models import ConfidenceLevel, ExtractedBenefit, SourceProcessingResult, PipelineResult

logger = logging.getLogger(__name__)



class BasePipeline(ABC):
    """
    Abstract base class for benefit extraction pipelines.
    
    Each pipeline is responsible for extracting a specific type of benefit
    (cashback, lounge access, rewards, etc.) from raw extracted data.
    
    Processing Flow (per source):
    1. Check relevance using keywords
    2. Extract using LLM (primary - better context understanding)
    3. Extract using regex patterns (fallback - catches specific patterns)
    4. Merge results for completeness
    
    Subclasses must implement:
    - name: Pipeline identifier
    - benefit_type: Type of benefit this pipeline extracts
    - keywords: Keywords to filter relevant content
    - patterns: Regex patterns for extraction
    - get_llm_prompt(): Generate LLM prompt for extraction
    - parse_llm_response(): Parse LLM response into benefits
    """
    
    # Subclasses must define these
    name: str = "base"
    benefit_type: str = "generic"
    description: str = "Base pipeline"
    version: str = "1.0"
    
    # Keywords for content filtering
    keywords: List[str] = []
    negative_keywords: List[str] = []  # Keywords that indicate irrelevant content
    
    # Minimum relevance score to process a source
    min_relevance_score: float = 0.1
    
    # Regex patterns for extraction
    patterns: Dict[str, str] = {}
    
    # URL/Title patterns to identify sources this pipeline should process
    # If a source URL or title matches any of these, this pipeline is relevant
    url_patterns: List[str] = []  # e.g., ['movie', 'cinema', 'film'] for movie pipeline
    
    # LLM configuration - model can be set via environment variable
    # Recommended models: llama3.2, mistral, phi3 (phi has very limited context)
    llm_enabled: bool = True
    llm_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")  # Default to llama3.2 for better quality
    llm_timeout: float = 180.0  # Increased for larger models
    llm_endpoint: str = "http://localhost:11434/api/generate"
    
    # Model-specific settings
    MODEL_CONFIGS = {
        "phi": {"max_content": 2000, "num_predict": 1000, "num_ctx": 2048},
        "phi3": {"max_content": 6000, "num_predict": 2000, "num_ctx": 8192},
        "llama3.2": {"max_content": 8000, "num_predict": 2000, "num_ctx": 8192},
        "llama2": {"max_content": 6000, "num_predict": 2000, "num_ctx": 4096},
        "mistral": {"max_content": 8000, "num_predict": 2000, "num_ctx": 8192},
        "default": {"max_content": 6000, "num_predict": 2000, "num_ctx": 4096},
    }
    
    # Processing limits
    max_content_per_source: int = 8000   # Will be adjusted based on model
    max_sources_to_process: int = 15     # Max sources to process per pipeline
    min_relevance_score: float = 0.3     # Minimum relevance to process
    
    # Concurrency control - class-level semaphore shared across all pipeline instances
    _llm_semaphore: asyncio.Semaphore = None
    _max_concurrent_llm_calls: int = 2   # Only 2 LLM calls at a time across all pipelines
    
    def get_model_config(self) -> Dict[str, int]:
        """Get configuration for the current LLM model."""
        return self.MODEL_CONFIGS.get(self.llm_model, self.MODEL_CONFIGS["default"])
    
    def is_relevant_for_source(self, url: str, title: str) -> bool:
        """
        Check if this pipeline is relevant for a given source based on URL/title matching.
        
        Args:
            url: The source URL
            title: The source title
            
        Returns:
            True if this pipeline should process this source, False otherwise
        """
        # If no URL patterns defined, pipeline is relevant for all sources
        if not self.url_patterns:
            return True
        
        # Combine URL and title for matching
        combined = f"{url} {title}".lower()
        
        # Check if any URL pattern matches
        for pattern in self.url_patterns:
            if pattern.lower() in combined:
                return True
        
        return False
    
    @classmethod
    def get_llm_semaphore(cls) -> asyncio.Semaphore:
        """Get or create the global LLM semaphore."""
        if cls._llm_semaphore is None:
            cls._llm_semaphore = asyncio.Semaphore(cls._max_concurrent_llm_calls)
        return cls._llm_semaphore
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize pipeline with database connection."""
        self.db = db
        self.compiled_patterns: Dict[str, re.Pattern] = {}
        self._card_context: Dict[str, Any] = {}  # Card context from raw data
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency."""
        for name, pattern in self.patterns.items():
            try:
                self.compiled_patterns[name] = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{name}': {e}")
    
    async def run(self, raw_data_id: str, source_indices: Optional[List[int]] = None) -> PipelineResult:
        """
        Run the pipeline on approved raw data.
        
        Args:
            raw_data_id: The saved_id of the approved raw data record
            source_indices: Optional list of source indices to process (None = all)
            
        Returns:
            PipelineResult with extracted benefits
        """
        
        logger.info(f"[{self.name}] ========== STARTING PIPELINE ==========")
        logger.info(f"[{self.name}] Raw data ID: {raw_data_id}")
        logger.info(f"[{self.name}] Source indices filter: {source_indices}")
        
        result = PipelineResult(
            pipeline_name=self.name,
            benefit_type=self.benefit_type,
            success=False,
        )
        
        try:
            # Load raw data
            raw_data = await self._load_raw_data(raw_data_id)
            if not raw_data:
                result.errors.append(f"Raw data not found: {raw_data_id}")
                logger.error(f"[{self.name}] Raw data not found!")
                return result
            
            # Log what we loaded from the database
            logger.info(f"[{self.name}] ========== LOADED RAW DATA ==========")
            logger.info(f"[{self.name}] raw_data_id: {raw_data_id}")
            logger.info(f"[{self.name}] primary_url: {raw_data.get('primary_url')}")
            logger.info(f"[{self.name}] total_sources in DB: {raw_data.get('total_sources')}")
            logger.info(f"[{self.name}] actual sources array length: {len(raw_data.get('sources', []))}")
            
            # Extract card context from raw data for use in prompts
            self._card_context = {
                'card_name': raw_data.get('card_name') or raw_data.get('detected_card_name'),
                'bank_name': raw_data.get('bank_name') or raw_data.get('detected_bank'),
                'card_type': raw_data.get('card_type'),
                'card_network': raw_data.get('card_network'),
                'card_tier': raw_data.get('card_tier'),
                'primary_url': raw_data.get('primary_url'),
            }
            
            # CRITICAL: Extract card structure from depth 0 (parent page) source
            # This tells us about combo cards like "Duo = MasterCard + Diners Club"
            sources = raw_data.get('sources', [])
            parent_source = None
            for src in sources:
                if src.get('depth', 0) == 0:
                    parent_source = src
                    break
            
            if parent_source:
                parent_content = parent_source.get('cleaned_content') or parent_source.get('raw_content') or ''
                card_structure = self._extract_card_structure(parent_content, self._card_context.get('card_name', ''))
                self._card_context['card_structure'] = card_structure
                self._card_context['parent_content_summary'] = parent_content[:2000]  # First 2000 chars for context
                logger.info(f"[{self.name}] Card structure from parent page: {card_structure}")
                
                # DEBUG: Print parent page content to see what card info is available
                logger.debug(f"\n{'='*60}")
                logger.debug(f"[{self.name}] PARENT PAGE (depth 0) CONTENT (first 3000 chars):")
                logger.debug(f"{'='*60}")
                logger.debug(parent_content[:3000])
                logger.debug(f"{'='*60}")
                logger.debug(f"[{self.name}] Card structure detected: {card_structure}")
                logger.debug(f"{'='*60}\n")
            
            logger.info(f"[{self.name}] Card context: {self._card_context.get('card_name')} from {self._card_context.get('bank_name')}")
            
            sources = raw_data.get('sources', [])
            result.sources_total = len(sources)
            
            # Log each source URL for debugging
            logger.info(f"[{self.name}] Sources in this raw_data record:")
            for i, src in enumerate(sources[:10]):  # Log first 10
                logger.info(f"[{self.name}]   {i+1}. {src.get('url', 'no-url')[:80]}")
            if len(sources) > 10:
                logger.info(f"[{self.name}]   ... and {len(sources) - 10} more")
            
            logger.info(f"[{self.name}] Found {len(sources)} total sources in DB record")
            
            if not sources:
                result.warnings.append("No sources found in raw data")
                result.success = True
                return result
            
            # FILTER BY SOURCE_INDICES FIRST if provided
            # When user explicitly selects sources, SKIP relevance filtering - they know what they want
            user_selected_sources = source_indices is not None and len(source_indices) > 0
            
            if user_selected_sources:
                logger.info(f"[{self.name}] USER SELECTED specific sources: {source_indices}")
                logger.info(f"[{self.name}] Skipping relevance filtering - processing ALL selected sources")
                relevant_sources = []
                for idx in source_indices:
                    if 0 <= idx < len(sources):
                        source = sources[idx]
                        content = source.get('cleaned_content') or source.get('raw_content') or ''
                        # Still calculate relevance for logging, but don't filter
                        relevance_score, keyword_matches = self._calculate_relevance(content, source.get('url', ''))
                        relevant_sources.append((idx, source, relevance_score, keyword_matches))
                        title = source.get('title') or 'Unknown'
                        logger.info(f"[{self.name}]   Source {idx}: {title[:50]}... (relevance={relevance_score:.2f})")
                    else:
                        logger.warning(f"[{self.name}] Source index {idx} out of range (0-{len(sources)-1})")
                logger.info(f"[{self.name}] Will process {len(relevant_sources)} user-selected sources (NO relevance filter)")
            else:
                # No specific sources selected - apply relevance filtering
                sources_to_process = [(idx, src) for idx, src in enumerate(sources)]
                
                # Pre-filter sources based on relevance to avoid unnecessary processing
                relevant_sources = []
                for idx, source in sources_to_process:
                    content = source.get('cleaned_content') or source.get('raw_content') or ''
                    if len(content) < 50:
                        continue
                    relevance_score, keyword_matches = self._calculate_relevance(content, source.get('url', ''))
                    if relevance_score >= self.min_relevance_score:
                        relevant_sources.append((idx, source, relevance_score, keyword_matches))
                
                # Sort by relevance score (highest first) and limit
                relevant_sources.sort(key=lambda x: x[2], reverse=True)
                relevant_sources = relevant_sources[:self.max_sources_to_process]
                
                logger.info(f"[{self.name}] Pre-filtered to {len(relevant_sources)} relevant sources (out of {len(sources)} total)")
            
            if not relevant_sources:
                logger.info(f"[{self.name}] No sources to process")
                result.warnings.append(f"No sources to process for {self.name}")
                result.success = True
                return result
            
            # Process sources - pass flag to skip relevance check in _process_single_source
            all_benefits = []
            
            for i, (original_idx, source, relevance, keywords) in enumerate(relevant_sources):
                title = source.get('title') or 'Unknown'
                logger.info(f"[{self.name}] ---- Processing source {i+1}/{len(relevant_sources)}: {title[:50]}... (relevance={relevance:.2f}, keywords={keywords}) ----")
                # Pass skip_relevance_check=True when user selected sources
                source_result = await self._process_single_source(source, original_idx, skip_relevance_check=user_selected_sources)
                result.source_results.append(source_result)
                
                if source_result.is_relevant:
                    result.sources_relevant += 1
                    
                    if source_result.merged_benefits:
                        result.sources_processed += 1
                        all_benefits.extend(source_result.merged_benefits)
                        result.llm_extractions += len(source_result.llm_benefits)
                        result.pattern_extractions += len(source_result.pattern_benefits)
                
                result.content_processed_chars += source_result.content_length
            
            logger.info(f"[{self.name}] Total benefits before dedup: {len(all_benefits)}")
            
            # Deduplicate benefits across sources
            deduplicated = self._deduplicate_benefits(all_benefits)
            
            logger.info(f"[{self.name}] Total benefits after dedup: {len(deduplicated)}")
            
            # Score and rank
            scored_benefits = self._score_benefits(deduplicated)
            
            # Update result
            result.benefits = scored_benefits
            result.total_found = len(scored_benefits)
            result.high_confidence_count = sum(1 for b in scored_benefits if b.confidence_level == ConfidenceLevel.HIGH)
            result.medium_confidence_count = sum(1 for b in scored_benefits if b.confidence_level == ConfidenceLevel.MEDIUM)
            result.low_confidence_count = sum(1 for b in scored_benefits if b.confidence_level == ConfidenceLevel.LOW)
            
            result.success = True
            
            logger.info(f"[{self.name}] ========== PIPELINE COMPLETE ==========")
            logger.info(f"[{self.name}] Total benefits: {result.total_found}")
            logger.info(f"[{self.name}] High confidence: {result.high_confidence_count}")
            logger.info(f"[{self.name}] Medium confidence: {result.medium_confidence_count}")
            logger.info(f"[{self.name}] Low confidence: {result.low_confidence_count}")
            
        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"[{self.name}] Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            result.completed_at = datetime.utcnow()
            result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        return result
    
    async def _process_single_source(self, source: Dict[str, Any], index: int, skip_relevance_check: bool = False) -> SourceProcessingResult:
        """
        Process a single source with LLM + Pattern extraction (both always run).
        
        Args:
            source: Source document from approved_raw_data
            index: Index of this source in the sources array
            skip_relevance_check: If True, always process regardless of relevance score
            
        Returns:
            SourceProcessingResult with extracted benefits
        """
        
        content = source.get('cleaned_content') or source.get('raw_content') or ''
        url = source.get('url') or ''
        title = source.get('title') or 'Unknown'
        
        logger.info(f"[{self.name}] Processing source {index}: {title[:50]}... ({len(content)} chars)")
        
        result = SourceProcessingResult(
            source_url=url,
            source_title=title,
            source_index=index,
            content_length=len(content),
            is_relevant=False,
            relevance_score=0.0,
            keyword_matches=0,
        )
        
        if not content or len(content) < 50:
            logger.warning(f"[{self.name}] Source {index}: Content too short ({len(content)} chars)")
            return result
        
        # Check relevance
        relevance_score, keyword_matches = self._calculate_relevance(content, url)
        result.relevance_score = relevance_score
        result.keyword_matches = keyword_matches
        
        logger.info(f"[{self.name}] Source {index}: Relevance={relevance_score:.2f}, Keywords={keyword_matches}")
        
        # Skip relevance check if user explicitly selected this source
        if not skip_relevance_check and relevance_score < self.min_relevance_score:
            logger.info(f"[{self.name}] Source {index}: Skipping - below relevance threshold")
            return result
        
        if skip_relevance_check:
            logger.info(f"[{self.name}] Source {index}: User-selected source - FORCING processing regardless of relevance")
        
        result.is_relevant = True
        
        # Step 1: Extract using LLM (primary method)
        llm_benefits = []
        pattern_benefits = []
        
        if self.llm_enabled:
            import time
            start_time = time.time()
            try:
                logger.info(f"[{self.name}] Source {index}: Starting LLM extraction...")
                llm_benefits = await self._extract_from_source_with_llm(content, url, title, index)
                result.llm_benefits = llm_benefits
                logger.info(f"[{self.name}] Source {index}: LLM extracted {len(llm_benefits)} benefits")
                for i, b in enumerate(llm_benefits):
                    logger.info(f"[{self.name}]   LLM Benefit {i+1}: {b.title}")
            except Exception as e:
                result.llm_error = str(e)
                logger.error(f"[{self.name}] Source {index}: LLM error: {e}")
                import traceback
                traceback.print_exc()
            result.llm_duration_ms = (time.time() - start_time) * 1000
        
        # Step 2: Extract using regex patterns (ALWAYS runs, not just fallback)
        import time
        start_time = time.time()
        try:
            logger.info(f"[{self.name}] Source {index}: Starting pattern extraction...")
            pattern_benefits = self._extract_from_source_with_patterns(content, url, title, index)
            result.pattern_benefits = pattern_benefits
            logger.info(f"[{self.name}] Source {index}: Pattern extracted {len(pattern_benefits)} benefits")
            for i, b in enumerate(pattern_benefits):
                logger.info(f"[{self.name}]   Pattern Benefit {i+1}: {b.title}")
        except Exception as e:
            result.pattern_error = str(e)
            logger.error(f"[{self.name}] Source {index}: Pattern error: {e}")
            import traceback
            traceback.print_exc()
        result.pattern_duration_ms = (time.time() - start_time) * 1000
        
        # Step 3: Combine LLM and pattern results (add all, don't merge aggressively)
        result.merged_benefits = self._merge_source_benefits(
            llm_benefits, 
            pattern_benefits,
            url,
            title,
            index
        )
        
        logger.info(f"[{self.name}] Source {index}: Final merged benefits: {len(result.merged_benefits)}")
        
        return result
    
    def _calculate_relevance(self, content: str, url: str = "") -> Tuple[float, int]:
        """Calculate relevance score (delegates to content_processor)."""
        return calculate_relevance(
            content, self.keywords, self.negative_keywords,
            url=url, pipeline_name=self.name,
        )

    def _extract_card_structure(self, content: str, card_name: str) -> Dict[str, Any]:
        """
        Extract card structure information from parent page content.
        
        This identifies combo/duo cards and their components.
        E.g., "Duo Credit Card" = "Duo MasterCard" + "Diners Club Card"
        
        Args:
            content: The parent page content (depth 0)
            card_name: The detected card name
            
        Returns:
            Dict with card structure info
        """
        structure = {
            'is_combo_card': False,
            'component_cards': [],
            'card_benefits_mapping': {},
            'detected_cards': []
        }
        
        content_lower = content.lower()
        
        # Detect combo/duo card patterns
        combo_patterns = [
            r'duo\s*(?:credit\s*)?card',
            r'two\s*cards?\s*in\s*one',
            r'combo\s*card',
            r'dual\s*card',
            r'pair\s*of\s*cards',
        ]
        
        for pattern in combo_patterns:
            if re.search(pattern, content_lower):
                structure['is_combo_card'] = True
                break
        
        # Extract specific card names mentioned
        card_name_patterns = [
            # MasterCard variants
            (r'(?:duo\s*)?mastercard(?:\s*(?:platinum|world|elite))?', 'MasterCard'),
            (r'platinum\s*(?:master\s*)?card', 'Platinum MasterCard'),
            (r'world\s*(?:master\s*)?card', 'World MasterCard'),
            # Diners Club
            (r'diners?\s*club(?:\s*card)?', 'Diners Club Card'),
            # Visa variants
            (r'visa\s*(?:infinite|signature|platinum)', 'Visa'),
            (r'visa\s*infinite', 'Visa Infinite'),
            (r'visa\s*signature', 'Visa Signature'),
            # AMEX
            (r'amex|american\s*express', 'American Express'),
        ]
        
        for pattern, card_type in card_name_patterns:
            if re.search(pattern, content_lower):
                if card_type not in structure['detected_cards']:
                    structure['detected_cards'].append(card_type)
        
        # Try to extract benefit-to-card mapping
        # Look for patterns like "Golf benefit is available on Diners Club card"
        benefit_mapping_patterns = [
            (r'golf[^.]*(?:diners|mastercard|visa)[^.]*', 'golf'),
            (r'lounge[^.]*(?:diners|mastercard|visa)[^.]*', 'lounge'),
            (r'movie[^.]*(?:diners|mastercard|visa)[^.]*', 'movie'),
            (r'cinema[^.]*(?:diners|mastercard|visa)[^.]*', 'movie'),
        ]
        
        for pattern, benefit_type in benefit_mapping_patterns:
            match = re.search(pattern, content_lower)
            if match:
                matched_text = match.group(0)
                # Determine which card
                if 'diners' in matched_text:
                    structure['card_benefits_mapping'][benefit_type] = 'Diners Club Card'
                elif 'mastercard' in matched_text:
                    structure['card_benefits_mapping'][benefit_type] = 'MasterCard'
                elif 'visa' in matched_text:
                    structure['card_benefits_mapping'][benefit_type] = 'Visa'
        
        # If it's a duo card and we found specific cards, mark them as components
        if structure['is_combo_card'] and structure['detected_cards']:
            structure['component_cards'] = structure['detected_cards']
        
        return structure
    
    def _extract_relevant_content(self, content: str, max_chars: int) -> str:
        """Extract most relevant content (delegates to content_processor)."""
        return extract_relevant_content(content, self.keywords, max_chars)

    async def _load_raw_data(self, raw_data_id: str) -> Optional[Dict[str, Any]]:
        """Load approved raw data from MongoDB."""
        collection = self.db.approved_raw_data
        return await collection.find_one({"saved_id": raw_data_id})
    
    async def _extract_from_source_with_llm(
        self, 
        content: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """
        Extract benefits from a single source using LLM.
        
        Args:
            content: The source content
            url: Source URL
            title: Source title
            index: Source index
            
        Returns:
            List of extracted benefits
        """
        
        # Get model-specific content limit
        model_config = self.get_model_config()
        max_content = model_config.get("max_content", 6000)
        
        # Log original content length
        original_length = len(content)
        
        # Smart content extraction: find the most relevant section
        content = self._extract_relevant_content(content, max_content)
        
        # DEBUG: Log content being sent to LLM (first 1500 chars)
        logger.info(f"[{self.name}] Source {index} content preview (first 1500 chars):")
        logger.info(f"[{self.name}] {content[:1500]}")
        logger.info(f"[{self.name}] ... (total {len(content)} chars, original {original_length} chars)")
        
        # Also print to console for immediate visibility
        logger.debug(f"\n{'='*60}")
        logger.debug(f"[{self.name}] SOURCE {index} CONTENT BEING SENT TO LLM:")
        logger.debug(f"{'='*60}")
        logger.debug(content[:2000])
        logger.debug(f"{'='*60}")
        logger.debug(f"[{self.name}] Total: {len(content)} chars (from original {original_length})")
        logger.debug(f"{'='*60}\n")
        
        # Generate prompt with card context
        prompt = self.get_llm_prompt(content, url, title, self._card_context)
        
        logger.debug(f"[{self.name}] Source {index}: {len(content)} chars content, {len(prompt)} chars prompt -> {self.llm_model}")
        
        # Call LLM
        response = await self._call_llm(prompt)
        
        if not response:
            return []
        
        logger.debug(f"[{self.name}] Source {index}: Got {len(response)} char response")
        
        # DEBUG: Log LLM response
        logger.debug(f"\n{'='*60}")
        logger.debug(f"[{self.name}] LLM RESPONSE:")
        logger.debug(f"{'='*60}")
        logger.debug(response[:2000])
        logger.debug(f"{'='*60}\n")
        
        # Parse response
        benefits = self.parse_llm_response(response, url, title, index)
        
        return benefits
    
    @staticmethod
    def format_card_context(card_context: Dict[str, Any] = None) -> str:
        """
        Build a card context header for LLM prompts.
        
        Returns a string like:
        CARD CONTEXT:
        - Card: Emirates NBD Visa Infinite
        - Bank: Emirates NBD
        - Network: Visa
        - Category: Infinite
        """
        if not card_context:
            return ""
        parts = ["CARD CONTEXT:"]
        if card_context.get("card_name"):
            parts.append(f"- Card: {card_context['card_name']}")
        if card_context.get("bank_name") or card_context.get("bank"):
            parts.append(f"- Bank: {card_context.get('bank_name') or card_context.get('bank')}")
        if card_context.get("card_network") or card_context.get("network"):
            parts.append(f"- Network: {card_context.get('card_network') or card_context.get('network')}")
        if card_context.get("card_tier"):
            parts.append(f"- Tier: {card_context['card_tier']}")
        if card_context.get("card_category") or card_context.get("category"):
            parts.append(f"- Category: {card_context.get('card_category') or card_context.get('category')}")
        if card_context.get("card_type"):
            parts.append(f"- Type: {card_context['card_type']}")
        if card_context.get("is_combo_card"):
            parts.append(f"- Combo card: Yes")
        if len(parts) <= 1:
            return ""
        return "\n".join(parts) + "\n"

    @abstractmethod
    def get_llm_prompt(self, content: str, url: str, title: str, card_context: Dict[str, Any] = None) -> str:
        """
        Generate the LLM prompt for extracting benefits from content.
        
        Subclasses must implement this with benefit-specific prompts.
        
        Args:
            content: The source content to analyze
            url: Source URL for context
            title: Source title for context
            card_context: Card information dict with keys: card_name, bank_name, card_type, card_network
            
        Returns:
            The prompt string to send to LLM
        """
        pass
    
    @abstractmethod
    def parse_llm_response(
        self, 
        response: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """
        Parse LLM response into ExtractedBenefit objects.
        
        Subclasses must implement this to parse their specific response format.
        
        Args:
            response: Raw LLM response
            url: Source URL
            title: Source title
            index: Source index
            
        Returns:
            List of extracted benefits
        """
        pass
    
    def _extract_from_source_with_patterns(
        self, 
        content: str, 
        url: str, 
        title: str, 
        index: int
    ) -> List[ExtractedBenefit]:
        """
        Extract benefits from a single source using regex patterns.
        
        Args:
            content: The source content
            url: Source URL
            title: Source title
            index: Source index
            
        Returns:
            List of extracted benefits
        """
        benefits = []
        
        for pattern_name, pattern in self.compiled_patterns.items():
            matches = pattern.finditer(content)
            
            for match in matches:
                benefit = self._create_benefit_from_match(
                    match=match,
                    pattern_name=pattern_name,
                    content=content,
                    url=url,
                    title=title,
                    index=index,
                )
                if benefit:
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
        """
        Create an ExtractedBenefit from a regex match.
        
        Subclasses can override this for custom match handling.
        """
        # Get context around the match
        start = max(0, match.start() - 100)
        end = min(len(content), match.end() + 100)
        context = content[start:end].strip()
        
        # Extract groups if available
        groups = match.groupdict() if match.lastindex else {}
        
        # Generate unique ID based on content
        content_hash = hashlib.md5(match.group().encode()).hexdigest()[:8]
        
        return ExtractedBenefit(
            benefit_id=f"{self.benefit_type}_{content_hash}",
            benefit_type=self.benefit_type,
            title=groups.get('title') or f"{self.benefit_type.replace('_', ' ').title()} Benefit",
            description=match.group().strip(),
            value=groups.get('value'),
            source_url=url,
            source_title=title,
            source_text=context,
            source_index=index,
            extraction_method="pattern",
            confidence=0.6,  # Base confidence for pattern matches
            confidence_level=ConfidenceLevel.MEDIUM,
            pipeline_version=self.version,
        )
    
    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Call the LLM endpoint via the shared Ollama client."""
        model_config = self.get_model_config()
        return await ollama_client.generate(
            prompt,
            model=self.llm_model,
            num_predict=model_config.get("num_predict", 2000),
            num_ctx=model_config.get("num_ctx", 4096),
            timeout=self.llm_timeout,
            caller=self.name,
        )
    
    def _parse_llm_json(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response using shared parser.
        
        If the LLM returns a bare JSON array instead of an object,
        wraps it as {"items": [...]}.
        """
        parsed = parse_llm_json(response)
        if isinstance(parsed, list):
            return {"items": parsed}
        return parsed
    
    def _merge_source_benefits(self, llm_benefits, pattern_benefits, url, title, index):
        """Merge LLM + pattern benefits (delegates to benefit_merger)."""
        return merge_source_benefits(
            llm_benefits, pattern_benefits, url, title, index,
            pipeline_name=self.name, benefit_type=self.benefit_type, version=self.version,
        )

    def _dict_to_benefit(self, d: dict):
        """Convert dict to ExtractedBenefit (delegates to benefit_merger)."""
        return dict_to_benefit(d, self.benefit_type, self.version)

    def _find_similar_benefit(self, benefit: ExtractedBenefit, existing_benefits: List[ExtractedBenefit]) -> Optional[str]:
        """Find if a similar benefit already exists (fuzzy matching)."""
        benefit_title_lower = benefit.title.lower().strip()
        benefit_title_words = set(benefit_title_lower.split())
        
        for existing in existing_benefits:
            existing_title_lower = existing.title.lower().strip()
            existing_title_words = set(existing_title_lower.split())
            
            # Check for significant word overlap (>60% of words match)
            common_words = benefit_title_words & existing_title_words
            if len(common_words) >= min(len(benefit_title_words), len(existing_title_words)) * 0.6:
                # Also check if values are similar
                if benefit.value and existing.value:
                    if benefit.value.lower() == existing.value.lower():
                        return existing.benefit_id
                else:
                    return existing.benefit_id
        
        return None
    
    def _get_benefit_key(self, benefit: ExtractedBenefit) -> str:
        """Generate a key for deduplication."""
        # Use normalized title + value for key
        title_norm = re.sub(r'\s+', ' ', benefit.title.lower().strip())
        value_norm = (benefit.value or '').lower().strip()
        return f"{title_norm}|{value_norm}"
    
    def _enhance_benefit(self, primary, secondary):
        """Enhance primary with secondary details (delegates to benefit_merger)."""
        return _enhance_benefit_fn(primary, secondary)

    def _deduplicate_benefits(self, benefits):
        """Cross-source dedup (delegates to benefit_merger)."""
        return _deduplicate_benefits_fn(benefits, self.name, self.benefit_type, self.version)

    def _score_benefits(self, benefits):
        """Score benefits (delegates to benefit_merger)."""
        return _score_benefits_fn(benefits)

    def _calculate_confidence(self, benefit):
        """Calculate confidence (delegates to benefit_merger)."""
        return _calculate_confidence_fn(benefit)

    async def save_results(self, raw_data_id: str, result: PipelineResult) -> str:
        """Save pipeline results to MongoDB."""
        collection = self.db.pipeline_results
        
        doc = {
            "raw_data_id": raw_data_id,
            "pipeline_name": self.name,
            "benefit_type": self.benefit_type,
            "pipeline_version": self.version,
            "result": result.to_dict(),
            "created_at": datetime.utcnow(),
        }
        
        # Upsert - update if same pipeline already run
        await collection.update_one(
            {
                "raw_data_id": raw_data_id,
                "pipeline_name": self.name,
            },
            {"$set": doc},
            upsert=True
        )
        
        return f"{raw_data_id}_{self.name}"
