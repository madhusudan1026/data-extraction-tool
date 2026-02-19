"""Utility modules."""
from app.utils.logger import logger
from app.utils.sanitize import (
    to_string,
    to_string_list,
    sanitize_conditions,
    sanitize_merchants,
    sanitize_categories,
    safe_join,
)
from app.utils.deduplication import (
    deduplicate_within_source,
    deduplicate_across_sources,
    deduplicate_across_pipelines,
    are_benefits_similar,
    merge_benefits,
    DeduplicationStats,
)

__all__ = [
    "logger",
    "to_string",
    "to_string_list",
    "sanitize_conditions",
    "sanitize_merchants",
    "sanitize_categories",
    "safe_join",
    "deduplicate_within_source",
    "deduplicate_across_sources",
    "deduplicate_across_pipelines",
    "are_benefits_similar",
    "merge_benefits",
    "DeduplicationStats",
]
