"""
Multi-Level Deduplication for Extracted Benefits

This module provides a comprehensive deduplication strategy at three levels:
1. Within a single source (LLM + Pattern + Hybrid results)
2. Across all sources within a single pipeline
3. Across all pipelines (final aggregation)

The key insight is that duplicates can occur due to:
- Same benefit extracted by LLM and regex patterns
- Same benefit appearing on multiple pages/sources
- Same benefit type extracted by multiple pipelines (e.g., "dining" could extract 
  something "lifestyle" also extracts)
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationStats:
    """Statistics about deduplication process."""
    input_count: int = 0
    output_count: int = 0
    duplicates_removed: int = 0
    merged_count: int = 0
    
    @property
    def reduction_percentage(self) -> float:
        if self.input_count == 0:
            return 0.0
        return ((self.input_count - self.output_count) / self.input_count) * 100


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    # Lowercase, remove extra whitespace, remove special chars
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s%$]', '', text)
    return text


def normalize_value(value: str) -> str:
    """Normalize benefit values for comparison."""
    if not value:
        return ""
    value = value.lower().strip()
    # Normalize AED formats
    value = re.sub(r'aed\s*', 'aed ', value)
    # Normalize percentages
    value = re.sub(r'(\d+)\s*%', r'\1%', value)
    # Remove commas in numbers
    value = re.sub(r'(\d),(\d)', r'\1\2', value)
    return value


def text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two texts."""
    if not text1 or not text2:
        return 0.0
    
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if norm1 == norm2:
        return 1.0
    
    # Check if one contains the other
    if norm1 in norm2 or norm2 in norm1:
        return 0.9
    
    return SequenceMatcher(None, norm1, norm2).ratio()


def are_benefits_similar(benefit1: Dict[str, Any], benefit2: Dict[str, Any], 
                          threshold: float = 0.75) -> Tuple[bool, float]:
    """
    Determine if two benefits are similar enough to be considered duplicates.
    
    Returns:
        Tuple of (is_similar, similarity_score)
    """
    # Extract key fields
    title1 = benefit1.get('title', '')
    title2 = benefit2.get('title', '')
    value1 = benefit1.get('value', '')
    value2 = benefit2.get('value', '')
    desc1 = benefit1.get('description', '')
    desc2 = benefit2.get('description', '')
    type1 = benefit1.get('benefit_type', '')
    type2 = benefit2.get('benefit_type', '')
    
    # Quick check: exact title match
    if normalize_text(title1) == normalize_text(title2):
        return True, 1.0
    
    # Quick check: same type and same normalized value
    if type1 == type2 and value1 and value2:
        if normalize_value(value1) == normalize_value(value2):
            title_sim = text_similarity(title1, title2)
            if title_sim > 0.5:
                return True, title_sim
    
    # Calculate weighted similarity
    title_sim = text_similarity(title1, title2)
    value_sim = 1.0 if normalize_value(value1) == normalize_value(value2) else 0.0
    desc_sim = text_similarity(desc1, desc2)
    
    # Weighted score (title is most important)
    weighted_score = (title_sim * 0.5) + (value_sim * 0.3) + (desc_sim * 0.2)
    
    # Boost if same benefit type
    if type1 == type2:
        weighted_score = min(weighted_score * 1.1, 1.0)
    
    return weighted_score >= threshold, weighted_score


def merge_benefits(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two similar benefits, keeping the best information from each.
    
    The primary benefit is preferred for main fields, but lists are merged
    and missing values are filled from secondary.
    """
    merged = primary.copy()
    
    # Merge list fields (conditions, merchants, etc.)
    # Note: excluded_categories is not in ExtractedBenefit dataclass
    list_fields = ['conditions', 'merchants', 'partners', 'limitations', 
                   'eligible_categories']
    
    for field in list_fields:
        primary_list = primary.get(field, []) or []
        secondary_list = secondary.get(field, []) or []
        
        # Ensure both are lists
        if isinstance(primary_list, str):
            primary_list = [primary_list]
        if isinstance(secondary_list, str):
            secondary_list = [secondary_list]
        
        # Merge and deduplicate
        combined = []
        seen_normalized = set()
        for item in primary_list + secondary_list:
            if item and isinstance(item, str):
                normalized = normalize_text(item)
                if normalized and normalized not in seen_normalized:
                    combined.append(item)
                    seen_normalized.add(normalized)
        
        merged[field] = combined
    
    # Fill missing scalar values from secondary
    scalar_fields = ['value', 'value_numeric', 'value_unit', 'frequency', 
                     'minimum_spend', 'maximum_benefit', 'description']
    
    for field in scalar_fields:
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    
    # Use higher confidence
    primary_conf = primary.get('confidence', 0)
    secondary_conf = secondary.get('confidence', 0)
    merged['confidence'] = max(primary_conf, secondary_conf)
    
    # Track that this was merged
    merged['_merged'] = True
    merged['_merged_from'] = [
        primary.get('benefit_id'),
        secondary.get('benefit_id')
    ]
    
    # Prefer LLM extraction method if available
    if primary.get('extraction_method') == 'llm' or secondary.get('extraction_method') == 'llm':
        merged['extraction_method'] = 'hybrid'
    
    return merged


def deduplicate_within_source(benefits: List[Dict[str, Any]], 
                               source_url: str = None) -> Tuple[List[Dict[str, Any]], DeduplicationStats]:
    """
    Level 1: Deduplicate benefits from different extraction methods for same source.
    
    This handles duplicates from LLM, pattern, and hybrid extraction on the same content.
    Most aggressive deduplication - same source means high chance of true duplicates.
    """
    stats = DeduplicationStats(input_count=len(benefits))
    
    if not benefits:
        return [], stats
    
    # Filter to only benefits from this source if specified
    if source_url:
        benefits = [b for b in benefits if b.get('source_url') == source_url]
    
    if len(benefits) <= 1:
        stats.output_count = len(benefits)
        return benefits, stats
    
    deduplicated = []
    used_indices = set()
    
    for i, benefit in enumerate(benefits):
        if i in used_indices:
            continue
        
        # Find all similar benefits
        similar_group = [benefit]
        for j, other in enumerate(benefits):
            if j <= i or j in used_indices:
                continue
            
            is_similar, score = are_benefits_similar(benefit, other, threshold=0.7)
            if is_similar:
                similar_group.append(other)
                used_indices.add(j)
        
        # Merge all similar benefits
        if len(similar_group) > 1:
            # Sort by confidence to pick best as primary
            similar_group.sort(key=lambda b: b.get('confidence', 0), reverse=True)
            merged = similar_group[0]
            for other in similar_group[1:]:
                merged = merge_benefits(merged, other)
                stats.merged_count += 1
            deduplicated.append(merged)
        else:
            deduplicated.append(benefit)
        
        used_indices.add(i)
    
    stats.output_count = len(deduplicated)
    stats.duplicates_removed = stats.input_count - stats.output_count
    
    logger.debug(f"Level 1 dedup: {stats.input_count} -> {stats.output_count} "
                 f"({stats.reduction_percentage:.1f}% reduction)")
    
    return deduplicated, stats


def deduplicate_across_sources(benefits: List[Dict[str, Any]], 
                                pipeline_name: str = None) -> Tuple[List[Dict[str, Any]], DeduplicationStats]:
    """
    Level 2: Deduplicate benefits across different sources within same pipeline.
    
    Same benefit info might appear on multiple pages. Less aggressive than Level 1
    since different sources might have legitimately different information.
    """
    stats = DeduplicationStats(input_count=len(benefits))
    
    if not benefits:
        return [], stats
    
    if len(benefits) <= 1:
        stats.output_count = len(benefits)
        return benefits, stats
    
    # Group by normalized title + value combination
    groups: Dict[str, List[Dict[str, Any]]] = {}
    
    for benefit in benefits:
        title = normalize_text(benefit.get('title', ''))
        value = normalize_value(benefit.get('value', ''))
        key = f"{title}|{value}"
        
        if key not in groups:
            groups[key] = []
        groups[key].append(benefit)
    
    deduplicated = []
    
    for key, group in groups.items():
        if len(group) == 1:
            deduplicated.append(group[0])
        else:
            # Multiple benefits with same title+value - merge them
            group.sort(key=lambda b: b.get('confidence', 0), reverse=True)
            merged = group[0]
            for other in group[1:]:
                merged = merge_benefits(merged, other)
                stats.merged_count += 1
            deduplicated.append(merged)
    
    # Second pass: check for similar but not exact matches
    final = []
    used_indices = set()
    
    for i, benefit in enumerate(deduplicated):
        if i in used_indices:
            continue
        
        similar_group = [benefit]
        for j, other in enumerate(deduplicated):
            if j <= i or j in used_indices:
                continue
            
            is_similar, score = are_benefits_similar(benefit, other, threshold=0.8)
            if is_similar:
                similar_group.append(other)
                used_indices.add(j)
        
        if len(similar_group) > 1:
            similar_group.sort(key=lambda b: b.get('confidence', 0), reverse=True)
            merged = similar_group[0]
            for other in similar_group[1:]:
                merged = merge_benefits(merged, other)
                stats.merged_count += 1
            final.append(merged)
        else:
            final.append(benefit)
        
        used_indices.add(i)
    
    stats.output_count = len(final)
    stats.duplicates_removed = stats.input_count - stats.output_count
    
    logger.debug(f"Level 2 dedup ({pipeline_name}): {stats.input_count} -> {stats.output_count} "
                 f"({stats.reduction_percentage:.1f}% reduction)")
    
    return final, stats


def deduplicate_across_pipelines(all_benefits: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], DeduplicationStats]:
    """
    Level 3: Deduplicate benefits across all pipelines.
    
    Different pipelines might extract the same benefit (e.g., dining and lifestyle
    both extract a restaurant discount). Least aggressive - different pipelines
    represent different categorizations.
    """
    stats = DeduplicationStats(input_count=len(all_benefits))
    
    if not all_benefits:
        return [], stats
    
    if len(all_benefits) <= 1:
        stats.output_count = len(all_benefits)
        return all_benefits, stats
    
    # Group by normalized title
    title_groups: Dict[str, List[Dict[str, Any]]] = {}
    
    for benefit in all_benefits:
        title = normalize_text(benefit.get('title', ''))
        if not title:
            title = '_untitled_'
        
        if title not in title_groups:
            title_groups[title] = []
        title_groups[title].append(benefit)
    
    deduplicated = []
    
    for title, group in title_groups.items():
        if len(group) == 1:
            deduplicated.append(group[0])
        else:
            # Check if they're truly the same (same value, similar description)
            # Group by value
            value_groups: Dict[str, List[Dict[str, Any]]] = {}
            for b in group:
                value = normalize_value(b.get('value', '')) or '_no_value_'
                if value not in value_groups:
                    value_groups[value] = []
                value_groups[value].append(b)
            
            for value, vgroup in value_groups.items():
                if len(vgroup) == 1:
                    deduplicated.append(vgroup[0])
                else:
                    # Same title, same value - definitely duplicates
                    # Prefer by pipeline priority and confidence
                    pipeline_priority = ['cashback', 'lounge_access', 'golf', 'dining', 
                                        'travel_benefits', 'insurance', 'fee_waiver', 
                                        'rewards_points', 'lifestyle']
                    
                    def sort_key(b):
                        pipeline = b.get('benefit_type', '')
                        try:
                            priority = pipeline_priority.index(pipeline)
                        except ValueError:
                            priority = 100
                        confidence = b.get('confidence', 0)
                        return (priority, -confidence)
                    
                    vgroup.sort(key=sort_key)
                    merged = vgroup[0]
                    for other in vgroup[1:]:
                        merged = merge_benefits(merged, other)
                        stats.merged_count += 1
                    deduplicated.append(merged)
    
    stats.output_count = len(deduplicated)
    stats.duplicates_removed = stats.input_count - stats.output_count
    
    logger.info(f"Level 3 dedup (cross-pipeline): {stats.input_count} -> {stats.output_count} "
                f"({stats.reduction_percentage:.1f}% reduction)")
    
    return deduplicated, stats


def full_deduplication_pipeline(
    benefits_by_source: Dict[str, List[Dict[str, Any]]],
    pipeline_name: str = None
) -> Tuple[List[Dict[str, Any]], Dict[str, DeduplicationStats]]:
    """
    Run full deduplication pipeline: Level 1 -> Level 2.
    
    Args:
        benefits_by_source: Dict mapping source_url to list of benefits from that source
        pipeline_name: Name of the pipeline (for logging)
        
    Returns:
        Tuple of (deduplicated benefits, stats by level)
    """
    all_stats = {}
    
    # Level 1: Deduplicate within each source
    level1_results = []
    total_l1_stats = DeduplicationStats()
    
    for source_url, benefits in benefits_by_source.items():
        deduped, stats = deduplicate_within_source(benefits, source_url)
        level1_results.extend(deduped)
        total_l1_stats.input_count += stats.input_count
        total_l1_stats.output_count += stats.output_count
        total_l1_stats.merged_count += stats.merged_count
    
    total_l1_stats.duplicates_removed = total_l1_stats.input_count - total_l1_stats.output_count
    all_stats['level1'] = total_l1_stats
    
    # Level 2: Deduplicate across sources
    final_results, l2_stats = deduplicate_across_sources(level1_results, pipeline_name)
    all_stats['level2'] = l2_stats
    
    logger.info(f"[{pipeline_name or 'unknown'}] Full dedup: "
                f"{total_l1_stats.input_count} -> {total_l1_stats.output_count} (L1) "
                f"-> {l2_stats.output_count} (L2)")
    
    return final_results, all_stats
