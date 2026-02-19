"""Service layer for business logic."""
from app.services.cache_service import cache_service
from app.services.pdf_service import pdf_service
from app.services.validation_service import validation_service
from app.services.comparison_service import comparison_service

# Enhanced services
from app.services.enhanced_web_scraper_service import enhanced_web_scraper_service
from app.services.enhanced_llm_service import enhanced_llm_service
from app.services.enhanced_extraction_service import enhanced_extraction_service

# batch_service is V2-era and depends on removed ExtractionJob model;
# import lazily in routes that need it to avoid startup crash
# from app.services.batch_service import batch_service

__all__ = [
    "cache_service",
    "pdf_service",
    "validation_service",
    "comparison_service",
    "enhanced_web_scraper_service",
    "enhanced_llm_service",
    "enhanced_extraction_service",
]
