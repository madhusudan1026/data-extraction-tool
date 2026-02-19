"""
Custom exception classes for the application.
Provides structured error handling with appropriate HTTP status codes.
"""
from typing import Optional, Dict, Any


class BaseAPIException(Exception):
    """Base exception class for API errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(BaseAPIException):
    """Raised when data validation fails."""

    def __init__(self, message: str = "Validation error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=422, details=details)


class ExtractionError(BaseAPIException):
    """Raised when data extraction fails."""

    def __init__(self, message: str = "Extraction failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class LLMError(BaseAPIException):
    """Raised when LLM operation fails."""

    def __init__(self, message: str = "LLM operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class PDFProcessingError(BaseAPIException):
    """Raised when PDF processing fails."""

    def __init__(self, message: str = "PDF processing failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, details=details)


class WebScraperError(BaseAPIException):
    """Raised when web scraping fails."""

    def __init__(self, message: str = "Web scraping failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, details=details)


class DatabaseError(BaseAPIException):
    """Raised when database operation fails."""

    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class CacheError(BaseAPIException):
    """Raised when cache operation fails."""

    def __init__(self, message: str = "Cache operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class NotFoundError(BaseAPIException):
    """Raised when requested resource is not found."""

    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=404, details=details)


class BadRequestError(BaseAPIException):
    """Raised when request is malformed or invalid."""

    def __init__(self, message: str = "Bad request", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, details=details)


class UnauthorizedError(BaseAPIException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Unauthorized", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=401, details=details)


class ForbiddenError(BaseAPIException):
    """Raised when access is forbidden."""

    def __init__(self, message: str = "Forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=403, details=details)


class RateLimitError(BaseAPIException):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=429, details=details)


class TimeoutError(BaseAPIException):
    """Raised when operation times out."""

    def __init__(self, message: str = "Operation timed out", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=504, details=details)


class BatchProcessingError(BaseAPIException):
    """Raised when batch processing fails."""

    def __init__(self, message: str = "Batch processing failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class ComparisonError(BaseAPIException):
    """Raised when comparison operation fails."""

    def __init__(self, message: str = "Comparison failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class ConfigurationError(BaseAPIException):
    """Raised when configuration is invalid."""

    def __init__(self, message: str = "Configuration error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)
