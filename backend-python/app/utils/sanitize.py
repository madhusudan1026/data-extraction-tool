"""
Data sanitization utilities for pipeline extraction.

Handles conversion of potentially nested or malformed LLM responses
into clean, flat data structures suitable for database storage.
"""

from typing import Any, List, Optional


def to_string(val: Any) -> Optional[str]:
    """
    Safely convert any value to a string.
    
    Handles:
    - None -> None
    - str -> str
    - dict -> extracts 'value' or 'amount' key, or stringifies
    - other -> str(val)
    
    Args:
        val: Any value from LLM response
        
    Returns:
        String representation or None
    """
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip() if val.strip() else None
    if isinstance(val, dict):
        # Try to get a meaningful value from dict
        extracted = val.get('value') or val.get('amount') or val.get('text')
        if extracted:
            return to_string(extracted)
        # Stringify dict if no known keys
        return str(val)
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bool):
        return str(val).lower()
    return str(val)


def to_string_list(val: Any) -> List[str]:
    """
    Convert any value to a list of strings.
    
    Handles:
    - None -> []
    - str -> [str]
    - list -> [to_string(item) for each item]
    - dict -> [str(dict)]
    - other -> [str(val)]
    
    Args:
        val: Any value from LLM response
        
    Returns:
        List of strings (empty list if val is None or empty)
    """
    if val is None:
        return []
    
    if isinstance(val, str):
        stripped = val.strip()
        return [stripped] if stripped else []
    
    if isinstance(val, list):
        result = []
        for item in val:
            if item is None:
                continue
            if isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    result.append(stripped)
            elif isinstance(item, dict):
                # Convert dict to readable string
                str_val = to_string(item)
                if str_val:
                    result.append(str_val)
            else:
                str_val = str(item).strip()
                if str_val:
                    result.append(str_val)
        return result
    
    if isinstance(val, dict):
        return [str(val)]
    
    str_val = str(val).strip()
    return [str_val] if str_val else []


def sanitize_conditions(conditions: Any) -> List[str]:
    """
    Sanitize conditions list from LLM response.
    
    Ensures all items are strings and handles nested structures.
    
    Args:
        conditions: Conditions value from LLM (could be list, str, dict, etc)
        
    Returns:
        List of condition strings
    """
    return to_string_list(conditions)


def sanitize_merchants(merchants: Any) -> List[str]:
    """
    Sanitize merchants list from LLM response.
    
    Args:
        merchants: Merchants value from LLM
        
    Returns:
        List of merchant name strings
    """
    return to_string_list(merchants)


def sanitize_categories(categories: Any) -> List[str]:
    """
    Sanitize categories/eligible_cards list from LLM response.
    
    Args:
        categories: Categories or eligible_cards value from LLM
        
    Returns:
        List of category/card strings
    """
    return to_string_list(categories)


def safe_join(items: List[str], separator: str = ", ") -> str:
    """
    Safely join a list of items into a string.
    
    Args:
        items: List of items (will be converted to strings)
        separator: Join separator
        
    Returns:
        Joined string or empty string
    """
    str_items = to_string_list(items)
    return separator.join(str_items)
