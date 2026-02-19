"""
MongoDB connection and initialization using Motor and Beanie ODM.
Provides async database operations with connection pooling.
"""
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from contextlib import asynccontextmanager

from app.core.config import settings
from app.utils.logger import logger


class Database:
    """Database connection manager."""

    client: Optional[AsyncIOMotorClient] = None
    database = None

    @classmethod
    async def connect(cls):
        """
        Establish connection to MongoDB and initialize Beanie.
        Sets up connection pooling and database instance.
        """
        try:
            logger.info(f"Connecting to MongoDB at {settings.mongodb_url_safe}")

            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=30000,
            )

            # Verify connection
            await cls.client.admin.command("ping")
            logger.info("MongoDB connection established successfully")

            cls.database = cls.client[settings.MONGODB_DATABASE]

            # Import models here to avoid circular imports
            from app.models.extracted_data_v2 import ExtractedDataV2
            from app.models.comparison import Comparison

            # Initialize Beanie with models
            await init_beanie(
                database=cls.database,
                document_models=[
                    ExtractedDataV2,
                    Comparison,
                ],
            )

            logger.info("Beanie ODM initialized successfully")

            # Create indexes
            await cls.create_indexes()

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise

    @classmethod
    async def create_indexes(cls):
        """Create database indexes for optimized queries."""
        try:
            from app.models.comparison import Comparison

            # ExtractedData indexes are defined in the model using Indexed fields
            logger.info("Creating database indexes...")

            # You can add additional custom indexes here if needed
            # Example:
            # await ExtractedData.get_motor_collection().create_index([
            #     ("card_name", "text"),
            #     ("benefits.description", "text")
            # ])

            logger.info("Database indexes created successfully")

        except Exception as e:
            logger.warning(f"Error creating indexes: {str(e)}")

    @classmethod
    async def disconnect(cls):
        """Close MongoDB connection."""
        if cls.client:
            logger.info("Closing MongoDB connection")
            cls.client.close()
            cls.client = None
            cls.database = None
            logger.info("MongoDB connection closed")

    @classmethod
    async def ping(cls) -> bool:
        """
        Ping MongoDB to check connection health.

        Returns:
            bool: True if connection is healthy, False otherwise.
        """
        try:
            if cls.client:
                await cls.client.admin.command("ping")
                return True
            return False
        except Exception as e:
            logger.error(f"MongoDB ping failed: {str(e)}")
            return False

    @classmethod
    def get_database(cls):
        """
        Get the database instance.

        Returns:
            Database instance.

        Raises:
            RuntimeError: If database is not connected.
        """
        if cls.database is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return cls.database

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        """
        Get the MongoDB client instance.

        Returns:
            AsyncIOMotorClient: MongoDB client.

        Raises:
            RuntimeError: If client is not connected.
        """
        if cls.client is None:
            raise RuntimeError("Database client is not connected. Call connect() first.")
        return cls.client


@asynccontextmanager
async def get_database_context():
    """
    Context manager for database operations.

    Usage:
        async with get_database_context() as db:
            # Use db
    """
    if Database.database is None:
        raise RuntimeError("Database is not connected")
    yield Database.database


async def get_database():
    """
    Get the database instance directly (not as context manager).
    
    Usage:
        db = await get_database()
        # Use db
    """
    if Database.database is None:
        raise RuntimeError("Database is not connected")
    return Database.database


# Global database instance
db = Database()
