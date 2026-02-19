"""
Logging configuration using Loguru.
Provides structured logging with rotation and retention.
"""
import sys
from pathlib import Path
from loguru import logger as _logger

from app.core.config import settings


def setup_logger():
    """
    Configure loguru logger with file and console handlers.

    Returns:
        Configured logger instance.
    """
    # Remove default handler
    _logger.remove()

    # Add console handler with custom format
    _logger.add(
        sys.stderr,
        format=settings.LOG_FORMAT,
        level=settings.LOG_LEVEL,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Create logs directory if it doesn't exist
    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Add file handler for all logs
    _logger.add(
        settings.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        backtrace=True,
        diagnose=True,
    )

    # Add separate error file handler
    error_log_dir = Path(settings.LOG_ERROR_FILE).parent
    error_log_dir.mkdir(parents=True, exist_ok=True)

    _logger.add(
        settings.LOG_ERROR_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        backtrace=True,
        diagnose=True,
    )

    return _logger


# Initialize logger
logger = setup_logger()


# Context manager for logging context
class LogContext:
    """Context manager for adding context to logs."""

    def __init__(self, **kwargs):
        self.context = kwargs

    def __enter__(self):
        logger.bind(**self.context)
        return logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# Helper functions
def log_function_call(func):
    """Decorator to log function calls."""
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed with error: {str(e)}")
            raise
    return wrapper


async def log_async_function_call(func):
    """Decorator to log async function calls."""
    async def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__} (async) with args={args}, kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"{func.__name__} (async) completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} (async) failed with error: {str(e)}")
            raise
    return wrapper
