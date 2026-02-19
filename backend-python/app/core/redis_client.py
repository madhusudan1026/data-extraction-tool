"""
Redis client setup and connection management.
Provides async Redis operations for caching.
"""
from typing import Optional, Union, Any
import json
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError

from app.core.config import settings
from app.utils.logger import logger


class RedisClient:
    """Redis client manager with connection pooling."""

    _pool: Optional[ConnectionPool] = None
    _client: Optional[Redis] = None

    @classmethod
    async def connect(cls):
        """
        Establish connection to Redis with connection pooling.
        """
        try:
            logger.info(f"Connecting to Redis at {settings.REDIS_URL}")

            cls._pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                db=settings.REDIS_DB,
                decode_responses=settings.REDIS_DECODE_RESPONSES,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            )

            cls._client = Redis(connection_pool=cls._pool)

            # Verify connection
            await cls._client.ping()
            logger.info("Redis connection established successfully")

        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise

    @classmethod
    async def disconnect(cls):
        """Close Redis connection."""
        if cls._client:
            logger.info("Closing Redis connection")
            await cls._client.close()
            cls._client = None

        if cls._pool:
            await cls._pool.disconnect()
            cls._pool = None
            logger.info("Redis connection closed")

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping Redis to check connection health.

        Returns:
            bool: True if connection is healthy, False otherwise.
        """
        try:
            if cls._client:
                await cls._client.ping()
                return True
            return False
        except RedisError as e:
            logger.error(f"Redis ping failed: {str(e)}")
            return False

    @classmethod
    def get_client(cls) -> Redis:
        """
        Get the Redis client instance.

        Returns:
            Redis: Redis client.

        Raises:
            RuntimeError: If client is not connected.
        """
        if cls._client is None:
            raise RuntimeError("Redis client is not connected. Call connect() first.")
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Optional[str]:
        """
        Get value from Redis.

        Args:
            key: Redis key.

        Returns:
            Value if exists, None otherwise.
        """
        try:
            client = cls.get_client()
            value = await client.get(key)
            return value
        except RedisError as e:
            logger.error(f"Redis GET error for key {key}: {str(e)}")
            return None

    @classmethod
    async def set(
        cls,
        key: str,
        value: Union[str, dict, list],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in Redis with optional TTL.

        Args:
            key: Redis key.
            value: Value to store (will be JSON encoded if dict/list).
            ttl: Time to live in seconds.

        Returns:
            True if successful, False otherwise.
        """
        try:
            client = cls.get_client()

            # Convert dict/list to JSON string
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            if ttl:
                await client.setex(key, ttl, value)
            else:
                await client.set(key, value)

            return True
        except RedisError as e:
            logger.error(f"Redis SET error for key {key}: {str(e)}")
            return False

    @classmethod
    async def delete(cls, key: str) -> bool:
        """
        Delete key from Redis.

        Args:
            key: Redis key to delete.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            client = cls.get_client()
            await client.delete(key)
            return True
        except RedisError as e:
            logger.error(f"Redis DELETE error for key {key}: {str(e)}")
            return False

    @classmethod
    async def exists(cls, key: str) -> bool:
        """
        Check if key exists in Redis.

        Args:
            key: Redis key.

        Returns:
            True if exists, False otherwise.
        """
        try:
            client = cls.get_client()
            result = await client.exists(key)
            return bool(result)
        except RedisError as e:
            logger.error(f"Redis EXISTS error for key {key}: {str(e)}")
            return False

    @classmethod
    async def get_json(cls, key: str) -> Optional[Union[dict, list]]:
        """
        Get JSON value from Redis and decode it.

        Args:
            key: Redis key.

        Returns:
            Decoded JSON object if exists, None otherwise.
        """
        value = await cls.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error for key {key}: {str(e)}")
        return None

    @classmethod
    async def set_json(
        cls,
        key: str,
        value: Union[dict, list],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set JSON value in Redis.

        Args:
            key: Redis key.
            value: Dict or list to store.
            ttl: Time to live in seconds.

        Returns:
            True if successful, False otherwise.
        """
        return await cls.set(key, value, ttl)

    @classmethod
    async def increment(cls, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter in Redis.

        Args:
            key: Redis key.
            amount: Amount to increment by.

        Returns:
            New value after increment, None on error.
        """
        try:
            client = cls.get_client()
            return await client.incrby(key, amount)
        except RedisError as e:
            logger.error(f"Redis INCRBY error for key {key}: {str(e)}")
            return None

    @classmethod
    async def expire(cls, key: str, ttl: int) -> bool:
        """
        Set TTL on an existing key.

        Args:
            key: Redis key.
            ttl: Time to live in seconds.

        Returns:
            True if successful, False otherwise.
        """
        try:
            client = cls.get_client()
            await client.expire(key, ttl)
            return True
        except RedisError as e:
            logger.error(f"Redis EXPIRE error for key {key}: {str(e)}")
            return False

    @classmethod
    async def keys(cls, pattern: str = "*") -> list[str]:
        """
        Get keys matching pattern.

        Args:
            pattern: Redis key pattern.

        Returns:
            List of matching keys.
        """
        try:
            client = cls.get_client()
            return await client.keys(pattern)
        except RedisError as e:
            logger.error(f"Redis KEYS error for pattern {pattern}: {str(e)}")
            return []

    @classmethod
    async def flush_db(cls) -> bool:
        """
        Flush all keys in current database (USE WITH CAUTION).

        Returns:
            True if successful, False otherwise.
        """
        try:
            client = cls.get_client()
            await client.flushdb()
            logger.warning("Redis database flushed")
            return True
        except RedisError as e:
            logger.error(f"Redis FLUSHDB error: {str(e)}")
            return False


# Global Redis client instance
redis_client = RedisClient()
