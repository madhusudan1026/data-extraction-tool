"""
Rate limiting middleware using Redis.
Implements token bucket algorithm for rate limiting.
"""
from fastapi import Request, HTTPException, status
from typing import Optional
import time

from app.core.config import settings
from app.core.redis_client import redis_client
from app.utils.logger import logger


class RateLimiter:
    """Rate limiter using Redis."""

    def __init__(self):
        self.enabled = settings.RATE_LIMIT_ENABLED
        self.requests_limit = settings.RATE_LIMIT_REQUESTS
        self.window_seconds = settings.RATE_LIMIT_WINDOW

    async def check_rate_limit(self, client_id: str) -> tuple[bool, Optional[dict]]:
        """
        Check if client has exceeded rate limit.

        Args:
            client_id: Unique client identifier (e.g., IP address).

        Returns:
            Tuple of (is_allowed, limit_info).
        """
        if not self.enabled:
            return True, None

        try:
            key = f"rate_limit:{client_id}"
            current_time = int(time.time())

            # Get current count
            count = await redis_client.get(key)
            count = int(count) if count else 0

            # Check if limit exceeded
            if count >= self.requests_limit:
                ttl = await redis_client.get_client().ttl(key)
                limit_info = {
                    "limit": self.requests_limit,
                    "remaining": 0,
                    "reset": current_time + ttl,
                }
                return False, limit_info

            # Increment counter
            new_count = await redis_client.increment(key)

            # Set expiry on first request
            if new_count == 1:
                await redis_client.expire(key, self.window_seconds)

            limit_info = {
                "limit": self.requests_limit,
                "remaining": max(0, self.requests_limit - new_count),
                "reset": current_time + self.window_seconds,
            }

            return True, limit_info

        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            # Allow request if rate limiting fails
            return True, None


rate_limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    """Middleware to enforce rate limiting."""
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)

    # Get client identifier (IP address)
    client_id = request.client.host if request.client else "unknown"

    # Check rate limit
    is_allowed, limit_info = await rate_limiter.check_rate_limit(client_id)

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={
                "X-RateLimit-Limit": str(limit_info["limit"]),
                "X-RateLimit-Remaining": str(limit_info["remaining"]),
                "X-RateLimit-Reset": str(limit_info["reset"]),
            },
        )

    # Process request
    response = await call_next(request)

    # Add rate limit headers to response
    if limit_info:
        response.headers["X-RateLimit-Limit"] = str(limit_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(limit_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(limit_info["reset"])

    return response
