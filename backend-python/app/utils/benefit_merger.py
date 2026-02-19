"""
Benefit Merger & Scorer

Handles post-extraction benefit processing:
- Merging LLM + pattern results from a single source (Level 1 dedup)
- Cross-source deduplication (Level 2 dedup)
- Confidence scoring
- dict ↔ ExtractedBenefit conversion

Extracted from base_pipeline to keep the core class slim.
"""

import logging
from typing import List, Optional, Dict, Any

from ..pipelines.models import ExtractedBenefit, ConfidenceLevel
from ..utils.sanitize import sanitize_conditions, sanitize_merchants, sanitize_categories
from ..utils.deduplication import (
    deduplicate_within_source,
    deduplicate_across_sources,
)

logger = logging.getLogger(__name__)


# ======================================================================
# dict ↔ ExtractedBenefit conversion
# ======================================================================

def dict_to_benefit(d: Dict[str, Any], fallback_type: str = "generic", fallback_version: str = "1.0") -> Optional[ExtractedBenefit]:
    """Convert a dictionary back to an ExtractedBenefit object."""
    try:
        conf_level = d.get('confidence_level', 'medium')
        if isinstance(conf_level, str):
            conf_level = ConfidenceLevel(conf_level)
        return ExtractedBenefit(
            benefit_id=d.get('benefit_id', ''),
            benefit_type=d.get('benefit_type', fallback_type),
            title=d.get('title', ''),
            description=d.get('description', ''),
            value=d.get('value'),
            value_numeric=d.get('value_numeric'),
            value_unit=d.get('value_unit'),
            conditions=d.get('conditions', []),
            limitations=d.get('limitations', []),
            merchants=d.get('merchants', []),
            partners=d.get('partners', []),
            eligible_categories=d.get('eligible_categories', []),
            minimum_spend=d.get('minimum_spend'),
            maximum_benefit=d.get('maximum_benefit'),
            frequency=d.get('frequency'),
            validity_period=d.get('validity_period'),
            source_url=d.get('source_url', ''),
            source_title=d.get('source_title', ''),
            source_index=d.get('source_index', 0),
            extraction_method=d.get('extraction_method', 'unknown'),
            confidence=d.get('confidence', 0.5),
            confidence_level=conf_level,
            pipeline_version=d.get('pipeline_version', fallback_version),
        )
    except Exception as exc:
        logger.error(f"dict_to_benefit failed: {exc}")
        return None


# ======================================================================
# Merge LLM + pattern results for one source  (Level 1)
# ======================================================================

def merge_source_benefits(
    llm_benefits: List[ExtractedBenefit],
    pattern_benefits: List[ExtractedBenefit],
    url: str,
    title: str,
    index: int,
    pipeline_name: str = "",
    benefit_type: str = "generic",
    version: str = "1.0",
) -> List[ExtractedBenefit]:
    """
    Merge LLM and pattern benefits from a single source with Level 1 dedup.
    """
    all_benefits: List[ExtractedBenefit] = []
    for b in llm_benefits:
        b.source_url = url
        b.source_title = title
        b.source_index = index
        all_benefits.append(b)
    for b in pattern_benefits:
        b.source_url = url
        b.source_title = title
        b.source_index = index
        all_benefits.append(b)

    prefix = f"[{pipeline_name}] " if pipeline_name else ""
    logger.info(f"{prefix}Source {index}: Combined {len(llm_benefits)} LLM + {len(pattern_benefits)} pattern = {len(all_benefits)}")

    if not all_benefits:
        return []

    dicts = [b.to_dict() for b in all_benefits]
    deduped, stats = deduplicate_within_source(dicts, source_url=url)
    logger.info(
        f"{prefix}Source {index}: L1 dedup {stats.input_count} -> {stats.output_count} "
        f"(-{stats.duplicates_removed} dup, {stats.merged_count} merged)"
    )

    return [b for d in deduped if (b := dict_to_benefit(d, benefit_type, version)) is not None]


# ======================================================================
# Cross-source deduplication  (Level 2)
# ======================================================================

def deduplicate_benefits(
    benefits: List[ExtractedBenefit],
    pipeline_name: str = "",
    benefit_type: str = "generic",
    version: str = "1.0",
) -> List[ExtractedBenefit]:
    """Deduplicate benefits across all sources (Level 2)."""
    if not benefits:
        return []

    dicts = [b.to_dict() for b in benefits]
    deduped, stats = deduplicate_across_sources(dicts, pipeline_name=pipeline_name)
    prefix = f"[{pipeline_name}] " if pipeline_name else ""
    logger.info(
        f"{prefix}L2 dedup {stats.input_count} -> {stats.output_count} "
        f"(-{stats.duplicates_removed} dup, {stats.merged_count} merged)"
    )
    return [b for d in deduped if (b := dict_to_benefit(d, benefit_type, version)) is not None]


# ======================================================================
# Confidence scoring
# ======================================================================

def calculate_confidence(benefit: ExtractedBenefit) -> float:
    """
    Calculate evidence-based confidence score.

    Factors: extraction method, presence of value/conditions/merchants, description quality.
    """
    score = benefit.confidence

    if benefit.extraction_method == 'hybrid':
        score = max(score, 0.75)
    elif benefit.extraction_method == 'llm':
        score = max(score, 0.7)

    if benefit.value:
        score += 0.05
        if benefit.value_numeric is not None:
            score += 0.05
    if benefit.conditions:
        score += 0.05
    if benefit.merchants or benefit.partners:
        score += 0.05
    if len(benefit.description) > 50:
        score += 0.05

    return min(score, 1.0)


def score_benefits(benefits: List[ExtractedBenefit]) -> List[ExtractedBenefit]:
    """Score and assign confidence levels, returning sorted list."""
    for b in benefits:
        b.confidence = calculate_confidence(b)
        if b.confidence >= 0.8:
            b.confidence_level = ConfidenceLevel.HIGH
        elif b.confidence >= 0.5:
            b.confidence_level = ConfidenceLevel.MEDIUM
        else:
            b.confidence_level = ConfidenceLevel.LOW
    benefits.sort(key=lambda b: b.confidence, reverse=True)
    return benefits


# ======================================================================
# Benefit enhancement (merge secondary into primary)
# ======================================================================

def enhance_benefit(primary: ExtractedBenefit, secondary: ExtractedBenefit) -> ExtractedBenefit:
    """Enhance *primary* benefit with details from *secondary*."""
    primary.conditions = list(set(sanitize_conditions(primary.conditions) + sanitize_conditions(secondary.conditions)))
    primary.limitations = list(set(sanitize_conditions(primary.limitations) + sanitize_conditions(secondary.limitations)))
    primary.merchants = list(set(sanitize_merchants(primary.merchants) + sanitize_merchants(secondary.merchants)))
    primary.partners = list(set(sanitize_conditions(primary.partners) + sanitize_conditions(secondary.partners)))
    primary.eligible_categories = list(set(sanitize_categories(primary.eligible_categories) + sanitize_categories(secondary.eligible_categories)))

    if not primary.value and secondary.value:
        primary.value = secondary.value
        primary.value_numeric = secondary.value_numeric
        primary.value_unit = secondary.value_unit
    if not primary.frequency and secondary.frequency:
        primary.frequency = secondary.frequency
    if not primary.minimum_spend and secondary.minimum_spend:
        primary.minimum_spend = secondary.minimum_spend
    if not primary.maximum_benefit and secondary.maximum_benefit:
        primary.maximum_benefit = secondary.maximum_benefit

    primary.confidence = min(primary.confidence + 0.1, 1.0)
    return primary
