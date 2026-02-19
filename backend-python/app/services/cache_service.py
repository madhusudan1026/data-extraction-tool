"""
Cache service using Redis for caching LLM responses and extraction results.
Provides high-level caching operations with TTL management.
"""
from typing import Optional, Union, Dict, Any
import json
import hashlib

from app.core.redis_client import redis_client
from app.core.config import settings
from app.utils.logger import logger


class CacheService:
    """Service for managing cache operations."""

    def __init__(self):
        self.enabled = settings.ENABLE_CACHING
        self.default_ttl = settings.CACHE_TTL_DEFAULT
        self.llm_ttl = settings.CACHE_TTL_LLM
        self.extraction_ttl = settings.CACHE_TTL_EXTRACTION

    async def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value if exists, None otherwise.
        """
        if not self.enabled:
            return None

        try:
            value = await redis_client.get(key)
            if value:
                logger.debug(f"Cache hit for key: {key}")
            else:
                logger.debug(f"Cache miss for key: {key}")
            return value
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {str(e)}")
            return None

    async def set(
        self,
        key: str,
        value: Union[str, dict, list],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time to live in seconds (uses default if not provided).

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            ttl = ttl or self.default_ttl
            success = await redis_client.set(key, value, ttl)
            if success:
                logger.debug(f"Cached value for key: {key} with TTL: {ttl}s")
            return success
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {str(e)}")
            return False

    async def get_json(self, key: str) -> Optional[Union[Dict, list]]:
        """
        Get JSON value from cache.

        Args:
            key: Cache key.

        Returns:
            Decoded JSON object if exists, None otherwise.
        """
        if not self.enabled:
            return None

        try:
            return await redis_client.get_json(key)
        except Exception as e:
            logger.error(f"Cache get_json error for key {key}: {str(e)}")
            return None

    async def set_json(
        self,
        key: str,
        value: Union[dict, list],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set JSON value in cache.

        Args:
            key: Cache key.
            value: JSON-serializable object.
            ttl: Time to live in seconds.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            ttl = ttl or self.default_ttl
            return await redis_client.set_json(key, value, ttl)
        except Exception as e:
            logger.error(f"Cache set_json error for key {key}: {str(e)}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key to delete.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            success = await redis_client.delete(key)
            if success:
                logger.debug(f"Deleted cache key: {key}")
            return success
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {str(e)}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key.

        Returns:
            True if exists, False otherwise.
        """
        if not self.enabled:
            return False

        try:
            return await redis_client.exists(key)
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {str(e)}")
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "llm:*").

        Returns:
            Number of keys deleted.
        """
        try:
            keys = await redis_client.keys(pattern)
            count = 0
            for key in keys:
                if await self.delete(key):
                    count += 1
            logger.info(f"Invalidated {count} cache keys matching pattern: {pattern}")
            return count
        except Exception as e:
            logger.error(f"Cache invalidate_pattern error for pattern {pattern}: {str(e)}")
            return 0

    def generate_cache_key(self, *args, **kwargs) -> str:
        """
        Generate a cache key from arguments.

        Args:
            *args: Positional arguments to include in key.
            **kwargs: Keyword arguments to include in key.

        Returns:
            Generated cache key.
        """
        # Combine all arguments into a single string
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        key_string = ":".join(key_parts)

        # Hash the key string for consistency
        key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]
        return key_hash

    async def cache_llm_response(
        self,
        content: str,
        model: str,
        response: Dict[str, Any]
    ) -> bool:
        """
        Cache LLM response with appropriate TTL.

        Args:
            content: Input content.
            model: LLM model used.
            response: LLM response to cache.

        Returns:
            True if successful, False otherwise.
        """
        key = self.get_llm_cache_key(content, model)
        return await self.set_json(key, response, self.llm_ttl)

    async def get_llm_response(
        self,
        content: str,
        model: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached LLM response.

        Args:
            content: Input content.
            model: LLM model used.

        Returns:
            Cached response if exists, None otherwise.
        """
        key = self.get_llm_cache_key(content, model)
        return await self.get_json(key)

    def get_llm_cache_key(self, content: str, model: str) -> str:
        """
        Generate cache key for LLM response.

        Args:
            content: Input content.
            model: LLM model.

        Returns:
            Cache key.
        """
        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        return f"llm:{model}:{content_hash}"

    async def cache_extraction_result(
        self,
        source: str,
        source_type: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        Cache extraction result.

        Args:
            source: Source content or URL.
            source_type: Type of source.
            result: Extraction result to cache.

        Returns:
            True if successful, False otherwise.
        """
        key = self.get_extraction_cache_key(source, source_type)
        return await self.set_json(key, result, self.extraction_ttl)

    async def get_extraction_result(
        self,
        source: str,
        source_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached extraction result.

        Args:
            source: Source content or URL.
            source_type: Type of source.

        Returns:
            Cached result if exists, None otherwise.
        """
        key = self.get_extraction_cache_key(source, source_type)
        return await self.get_json(key)

    def get_extraction_cache_key(self, source: str, source_type: str) -> str:
        """
        Generate cache key for extraction result.

        Args:
            source: Source content or URL.
            source_type: Type of source.

        Returns:
            Cache key.
        """
        source_hash = hashlib.md5(source.encode()).hexdigest()[:16]
        return f"extraction:{source_type}:{source_hash}"

    async def clear_all(self) -> bool:
        """
        Clear all cache (USE WITH CAUTION).

        Returns:
            True if successful, False otherwise.
        """
        try:
            success = await redis_client.flush_db()
            if success:
                logger.warning("Cleared all cache")
            return success
        except Exception as e:
            logger.error(f"Cache clear_all error: {str(e)}")
            return False


# Global cache service instance
cache_service = CacheService()
