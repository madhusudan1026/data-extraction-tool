"""
Main FastAPI application.
Configures routes, middleware, and lifecycle events.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import db
from app.core.redis_client import redis_client
from app.api.routes import batch, comparison, schema
from app.api.routes import extraction_v2
from app.api.routes import extraction_unified
from app.api.routes import extraction_structured
from app.api.routes import vector_routes
from app.middleware.error_handler import setup_exception_handlers, error_handler_middleware
from app.middleware.rate_limiter import rate_limit_middleware
from app.utils.logger import logger
from app.schemas.extraction import HealthCheckResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting application...")

    try:
        # Connect to MongoDB
        await db.connect()
        logger.info("MongoDB connected")

        # Connect to Redis
        await redis_client.connect()
        logger.info("Redis connected")

        logger.info(f"Application started successfully on {settings.ENVIRONMENT} environment")

    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application...")

    try:
        await db.disconnect()
        logger.info("MongoDB disconnected")

        await redis_client.disconnect()
        logger.info("Redis disconnected")

        logger.info("Application shutdown complete")

    except Exception as e:
        logger.error(f"Shutdown error: {str(e)}")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-ready API for credit card data extraction",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)

# Add custom middleware
if settings.RATE_LIMIT_ENABLED:
    app.middleware("http")(rate_limit_middleware)

# Setup exception handlers
setup_exception_handlers(app)

# Include routers
app.include_router(extraction_v2.router, prefix="/api")
app.include_router(extraction_unified.router)  # V4 - Unified (already has /api prefix)
app.include_router(extraction_structured.router, prefix="/api")  # V5 - Structured hierarchical
app.include_router(vector_routes.router)  # Vector store / RAG endpoints
app.include_router(batch.router, prefix="/api")
app.include_router(comparison.router, prefix="/api")
app.include_router(schema.router, prefix="/api")


# Health check endpoint
@app.get("/health", response_model=HealthCheckResponse, tags=["health"])
async def health_check():
    """Health check endpoint."""
    database_healthy = await db.ping()
    redis_healthy = await redis_client.ping()

    # Test LLM connection
    from app.services.enhanced_llm_service import enhanced_llm_service

    llm_result = await enhanced_llm_service.test_connection()
    llm_healthy = llm_result.get("success", False)

    status = "healthy" if all([database_healthy, redis_healthy, llm_healthy]) else "unhealthy"

    return HealthCheckResponse(
        status=status,
        database=database_healthy,
        redis=redis_healthy,
        llm=llm_healthy,
    )


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/api/docs" if not settings.is_production else "disabled",
    }


# API info endpoint
@app.get("/api", tags=["root"])
async def api_info():
    """API information endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "endpoints": {
            "extraction_v2": "/api/v2/extraction",
            "extraction_unified": "/api/v4/extraction (Recommended)",
            "batch": "/api/batch",
            "comparison": "/api/comparison",
            "schema": "/api/schema",
            "health": "/health",
            "docs": "/api/docs" if not settings.is_production else "disabled",
        },
    }
