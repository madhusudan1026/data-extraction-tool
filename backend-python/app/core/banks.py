"""
Centralized UAE Bank Configuration

Single source of truth for all bank-related metadata. Replaces the duplicate
definitions that existed in:
  - enhanced_extraction_service.BANK_PATTERNS
  - extraction_unified.BANK_CONFIGS
  - enhanced_web_scraper_service.BANK_PATTERNS (scraping-specific parts stay there)
"""

from typing import Optional, Dict, List


# ======================================================================
# Bank Registry
# ======================================================================

BANKS: Dict[str, Dict] = {
    "emirates_nbd": {
        "key": "emirates_nbd",
        "name": "Emirates NBD",
        "short_names": ["Emirates NBD", "ENBD"],
        "domains": ["emiratesnbd.com"],
        "country": "UAE",
        "base_url": "https://www.emiratesnbd.com",
        "cards_page": "https://www.emiratesnbd.com/en/cards/credit-cards",
        "requires_javascript": True,
        "card_url_patterns": [
            r"/en/cards/credit-cards/[\w-]+-card$",
            r"/en/cards/credit-cards/[\w-]+-credit-card$",
        ],
        "exclude_patterns": [
            "installment", "balance", "loan", "compare", "apply",
            "business", "corporate", "sme", "debit", "prepaid",
        ],
    },
    "fab": {
        "key": "fab",
        "name": "First Abu Dhabi Bank",
        "short_names": ["First Abu Dhabi Bank", "FAB", "Bank FAB"],
        "domains": ["bankfab.com", "fab.com"],
        "country": "UAE",
        "base_url": "https://www.bankfab.com",
        "cards_page": "https://www.bankfab.com/en-ae/personal/cards/credit-cards",
        "requires_javascript": False,
        "card_url_patterns": [r"/credit-cards/[\w-]+$"],
        "exclude_patterns": ["business", "corporate"],
    },
    "adcb": {
        "key": "adcb",
        "name": "Abu Dhabi Commercial Bank",
        "short_names": ["Abu Dhabi Commercial Bank", "ADCB"],
        "domains": ["adcb.com"],
        "country": "UAE",
        "base_url": "https://www.adcb.com",
        "cards_page": "https://www.adcb.com/en/personal/cards/credit-cards",
        "requires_javascript": False,
        "card_url_patterns": [r"/credit-cards/[\w-]+$"],
        "exclude_patterns": ["business", "corporate"],
    },
    "mashreq": {
        "key": "mashreq",
        "name": "Mashreq Bank",
        "short_names": ["Mashreq", "Mashreq Bank"],
        "domains": ["mashreq.com", "mashreqbank.com"],
        "country": "UAE",
        "base_url": "https://www.mashreq.com",
        "cards_page": "https://www.mashreq.com/en/uae/personal/cards/credit-cards",
        "requires_javascript": False,
        "card_url_patterns": [r"/credit-cards/[\w-]+$"],
        "exclude_patterns": ["business", "corporate"],
    },
    "dib": {
        "key": "dib",
        "name": "Dubai Islamic Bank",
        "short_names": ["Dubai Islamic Bank", "DIB"],
        "domains": ["dib.ae"],
        "country": "UAE",
        "base_url": "https://www.dib.ae",
        "cards_page": None,
        "requires_javascript": False,
        "card_url_patterns": [],
        "exclude_patterns": ["business", "corporate"],
    },
    "cbd": {
        "key": "cbd",
        "name": "Commercial Bank of Dubai",
        "short_names": ["Commercial Bank of Dubai", "CBD"],
        "domains": ["cbd.ae"],
        "country": "UAE",
        "base_url": "https://www.cbd.ae",
        "cards_page": None,
        "requires_javascript": False,
        "card_url_patterns": [],
        "exclude_patterns": ["business", "corporate"],
    },
    "rakbank": {
        "key": "rakbank",
        "name": "RAKBANK",
        "short_names": ["RAKBANK", "RAK Bank"],
        "domains": ["rakbank.ae"],
        "country": "UAE",
        "base_url": "https://www.rakbank.ae",
        "cards_page": None,
        "requires_javascript": False,
        "card_url_patterns": [],
        "exclude_patterns": ["business", "corporate"],
    },
    "citi": {
        "key": "citi",
        "name": "Citibank",
        "short_names": ["Citibank", "Citi"],
        "domains": ["citibank.ae", "citi.com"],
        "country": "UAE",
        "base_url": "https://www.citibank.ae",
        "cards_page": None,
        "requires_javascript": False,
        "card_url_patterns": [],
        "exclude_patterns": [],
    },
    "hsbc": {
        "key": "hsbc",
        "name": "HSBC",
        "short_names": ["HSBC"],
        "domains": ["hsbc.ae", "hsbc.com"],
        "country": "UAE",
        "base_url": "https://www.hsbc.ae",
        "cards_page": None,
        "requires_javascript": False,
        "card_url_patterns": [],
        "exclude_patterns": [],
    },
    "sc": {
        "key": "sc",
        "name": "Standard Chartered",
        "short_names": ["Standard Chartered"],
        "domains": ["sc.com"],
        "country": "UAE",
        "base_url": "https://www.sc.com",
        "cards_page": None,
        "requires_javascript": False,
        "card_url_patterns": [],
        "exclude_patterns": [],
    },
}


# ======================================================================
# Helper functions
# ======================================================================

def detect_bank_from_url(url: str) -> Optional[str]:
    """Return bank key (e.g. 'emirates_nbd') from a URL, or None."""
    url_lower = url.lower()
    for key, bank in BANKS.items():
        for domain in bank["domains"]:
            if domain in url_lower:
                return key
    return None


def get_bank_name(bank_key: Optional[str]) -> str:
    """Return full bank name from key, or 'Unknown Bank'."""
    if bank_key and bank_key in BANKS:
        return BANKS[bank_key]["name"]
    return "Unknown Bank"


def get_bank(bank_key: str) -> Optional[Dict]:
    """Return full bank config dict, or None."""
    return BANKS.get(bank_key)


def list_bank_keys() -> List[str]:
    """Return all registered bank keys."""
    return list(BANKS.keys())


def list_banks_summary() -> List[Dict]:
    """Return a list of {key, name} for UI display."""
    return [{"key": k, "name": v["name"]} for k, v in BANKS.items()]


# ======================================================================
# Card Metadata Detection (Network + Tier)
# ======================================================================

import re

# Network detection patterns — order matters (check specific first)
NETWORK_PATTERNS = [
    # Pattern, network name, aliases to check in URL/name
    ("visa_signature",  "Visa",        [r"\bvisa\s+signature\b"]),
    ("visa_infinite",   "Visa",        [r"\bvisa\s+infinite\b"]),
    ("visa_platinum",   "Visa",        [r"\bvisa\s+platinum\b"]),
    ("visa",            "Visa",        [r"\bvisa\b"]),
    ("world_elite",     "Mastercard",  [r"\bworld\s*elite\b"]),
    ("world_mc",        "Mastercard",  [r"\bworld\s+mastercard\b", r"\bmastercard\s+world\b"]),
    ("mastercard",      "Mastercard",  [r"\bmastercard\b", r"\bmaster\s*card\b"]),
    ("amex",            "American Express", [r"\bam(?:erican)?\s*ex(?:press)?\b", r"\bamex\b"]),
    ("diners",          "Diners Club", [r"\bdiners?\s*club\b"]),
    ("unionpay",        "UnionPay",    [r"\bunion\s*pay\b"]),
]

# Tier detection patterns — order: most specific first
TIER_PATTERNS = [
    ("World Elite",  [r"\bworld\s*elite\b"]),
    ("Infinite",     [r"\binfinite\b"]),
    ("Centurion",    [r"\bcenturion\b"]),
    ("Black",        [r"\bblack\b"]),
    ("Signature",    [r"\bsignature\b"]),
    ("World",        [r"\bworld\b(?!\s*elite)"]),  # "World" but not "World Elite"
    ("Platinum",     [r"\bplatinum\b"]),
    ("Titanium",     [r"\btitanium\b"]),
    ("Gold",         [r"\bgold\b"]),
    ("Classic",      [r"\bclassic\b"]),
    ("Standard",     [r"\bstandard\b"]),
]


def detect_card_metadata(
    card_name: str,
    url: str = "",
    content: str = "",
) -> Dict[str, Optional[str]]:
    """
    Detect card network and tier from card name, URL, and page content.

    Scans the card name first (highest signal), then URL path, then first
    2000 chars of content as fallback.

    Returns:
        {"card_network": "Visa"|"Mastercard"|...|None,
         "card_tier": "Infinite"|"Platinum"|...|None}
    """
    # Combine signals — card name is highest priority, then URL, then content snippet
    name_lower = card_name.lower() if card_name else ""
    url_lower = url.lower() if url else ""
    # Only use first 2000 chars of content to avoid noise from unrelated sections
    content_snippet = content[:2000].lower() if content else ""

    # Search in priority order: name → url → content
    search_texts = [name_lower, url_lower, content_snippet]

    # --- Detect network ---
    card_network = None
    for _, network_name, patterns in NETWORK_PATTERNS:
        for text in search_texts:
            if not text:
                continue
            for pat in patterns:
                if re.search(pat, text):
                    card_network = network_name
                    break
            if card_network:
                break
        if card_network:
            break

    # --- Detect tier ---
    card_tier = None
    for tier_name, patterns in TIER_PATTERNS:
        for text in search_texts:
            if not text:
                continue
            for pat in patterns:
                if re.search(pat, text):
                    card_tier = tier_name
                    break
            if card_tier:
                break
        if card_tier:
            break

    return {
        "card_network": card_network,
        "card_tier": card_tier,
    }
