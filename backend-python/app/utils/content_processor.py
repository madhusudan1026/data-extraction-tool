"""
Content Processor

Handles content preparation for LLM extraction:
- Noise removal (navigation, footers, language selectors)
- Section scoring by keyword density
- Smart content extraction that prioritises benefit-rich sections
- URL-aware relevance bonuses for T&C/fee pages

Extracted from base_pipeline._extract_relevant_content and _calculate_relevance.
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Noise patterns common to UAE bank pages
# --------------------------------------------------------------------------
NOISE_PATTERNS = [
    r'(?i)choose your language.*?(?=\n\n|\Z)',
    r'(?i)united arab emirates.*?(?=\n\n|\Z)',
    r'(?i)our websites.*?(?=\n\n|\Z)',
    r'(?i)asset management.*?(?=\n\n|\Z)',
    r'(?i)copyright.*?(?=\n|\Z)',
    r'(?i)privacy policy.*?(?=\n|\Z)',
    r'(?i)terms and conditions\s*$',
    r'\n\s*\|\s*\n',        # menu separators
    r'\n\s*عربي\s*\n',      # Arabic language links
    r'\n\s*english\s*\n',   # English language links
]

# Benefit indicator terms for section scoring
BENEFIT_INDICATORS = [
    'free', 'complimentary', 'discount', '%', 'aed',
    'offer', 'eligible', 'valid', 'terms', 'conditions', 'benefit',
]

# URL patterns that indicate high-value pages (T&C, fee schedules, key facts)
HIGH_VALUE_URL_PATTERNS = [
    'terms', 'conditions', 'key-facts', 'keyfacts', 'fee-schedule',
    'fee_schedule', 'tariff', 'charges', 'schedule-of-charges',
]


def remove_noise(content: str) -> str:
    """Strip navigation, footer, language-selector noise from content."""
    cleaned = content
    for pattern in NOISE_PATTERNS:
        cleaned = re.sub(pattern, '\n', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    return cleaned.strip()


def extract_relevant_content(
    content: str,
    keywords: List[str],
    max_chars: int,
) -> str:
    """
    Extract the most relevant portion of *content* for LLM processing.

    1. Remove navigation/header/footer noise
    2. Score sections by keyword density + benefit indicators
    3. Return the highest-scoring sections up to *max_chars*
    """
    if len(content) <= max_chars:
        return content

    cleaned = remove_noise(content)
    if len(cleaned) <= max_chars:
        return cleaned

    # Split into sections and score
    sections = cleaned.split('\n\n')
    scored: List[Tuple[float, str]] = []

    for section in sections:
        if len(section.strip()) < 20:
            continue
        section_lower = section.lower()
        score = 0.0

        for kw in keywords:
            if kw.lower() in section_lower:
                score += 1

        for indicator in BENEFIT_INDICATORS:
            if indicator in section_lower:
                score += 0.5

        scored.append((score, section))

    scored.sort(key=lambda x: x[0], reverse=True)

    parts: List[str] = []
    length = 0
    for score, section in scored:
        if length + len(section) + 2 <= max_chars:
            parts.append(section)
            length += len(section) + 2
        elif not parts:
            parts.append(section[:max_chars])
            break

    return '\n\n'.join(parts).strip()


def calculate_relevance(
    content: str,
    keywords: List[str],
    negative_keywords: List[str],
    url: str = "",
    pipeline_name: str = "",
) -> Tuple[float, int]:
    """
    Calculate relevance score for *content*.

    Returns (relevance_score, keyword_matches).
    """
    content_lower = content.lower()
    url_lower = url.lower() if url else ""

    # URL-pattern bonus for T&C / fee / key-facts pages
    url_bonus = 0.0
    for pattern in HIGH_VALUE_URL_PATTERNS:
        if pattern in url_lower:
            url_bonus = 0.3
            logger.info(f"[{pipeline_name}] URL bonus +0.3 for T&C/fee page: {url[:80]}")
            break

    # Negative keyword rejection
    if any(neg in content_lower for neg in negative_keywords):
        return 0.0, 0

    # Count keyword matches
    keyword_matches = 0
    exact_phrase_matches = 0
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in content_lower:
            keyword_matches += 1
            if re.search(r'\b' + re.escape(kw_lower) + r'\b', content_lower):
                exact_phrase_matches += 1

    if not keywords:
        return 0.5 + url_bonus, 0

    if keyword_matches == 0:
        return url_bonus, 0
    elif keyword_matches == 1:
        return 0.2 + url_bonus, keyword_matches
    elif keyword_matches >= 5 or exact_phrase_matches >= 3:
        relevance_score = 1.0
    elif keyword_matches >= 3 or exact_phrase_matches >= 2:
        relevance_score = 0.8
    elif keyword_matches >= 2:
        relevance_score = 0.5
    else:
        relevance_score = 0.3

    return min(1.0, relevance_score + url_bonus), keyword_matches
