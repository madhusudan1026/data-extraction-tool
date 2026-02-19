"""
Core configuration management using pydantic-settings.
Handles environment variables and application settings.
"""
from typing import Optional, List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    APP_NAME: str = "Credit Card Data Extraction API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    RELOAD: bool = False

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: List[str] = ["*"]
    CORS_HEADERS: List[str] = ["*"]

    # MongoDB
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "credit_card_extraction"
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_MAX_POOL_SIZE: int = 50

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_DB: int = 0
    REDIS_DECODE_RESPONSES: bool = True
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    # LLM / Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"  # Base URL without endpoint path
    OLLAMA_URL: str = "http://localhost:11434/api/generate"  # Legacy, for backward compatibility
    DEFAULT_MODEL: str = "phi"
    DEFAULT_TEMPERATURE: float = 0.1
    LLM_TIMEOUT: int = 180  # Allow enough time for comprehensive extraction
    LLM_MAX_RETRIES: int = 2
    LLM_NUM_PREDICT: int = 4096  # Enough tokens for full structured JSON output

    # Vector Store (ChromaDB)
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    EMBED_MODEL: str = "nomic-embed-text"
    VECTOR_AUTO_INDEX: bool = True  # Auto-index after saving approved raw data

    # Extraction
    MAX_CONTENT_LENGTH: int = 100000
    MIN_TEXT_LENGTH: int = 100
    PDF_MAX_SIZE_MB: int = 50
    EXTRACTION_TIMEOUT: int = 600

    # Batch Processing
    BATCH_MAX_SIZE: int = 100
    BATCH_CONCURRENCY: int = 5
    BATCH_CHUNK_SIZE: int = 10

    # Caching
    CACHE_TTL_DEFAULT: int = 7200  # 2 hours
    CACHE_TTL_LLM: int = 86400  # 24 hours
    CACHE_TTL_EXTRACTION: int = 3600  # 1 hour
    ENABLE_CACHING: bool = True

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds

    # Validation
    MIN_CONFIDENCE_SCORE: float = 0.3
    AUTO_VALIDATE_THRESHOLD: float = 0.8

    # Logging
    LOG_LEVEL: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    LOG_FORMAT: str = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    LOG_ROTATION: str = "500 MB"
    LOG_RETENTION: str = "10 days"
    LOG_FILE: str = "logs/app.log"
    LOG_ERROR_FILE: str = "logs/error.log"

    # Security
    API_KEY_HEADER: str = "X-API-Key"
    SECRET_KEY: str = "your-secret-key-change-in-production"

    # Web Scraping
    SCRAPER_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    SCRAPER_TIMEOUT: int = 30
    SCRAPER_MAX_REDIRECTS: int = 5
    SCRAPER_RETRY_ATTEMPTS: int = 3
    SCRAPER_MAX_DEEP_LINKS: int = 10  # Maximum related links to follow

    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def mongodb_url_safe(self) -> str:
        """Return MongoDB URL without credentials for logging."""
        return self.MONGODB_URL.split("@")[-1] if "@" in self.MONGODB_URL else self.MONGODB_URL

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == "development"

    def get_pdf_max_size_bytes(self) -> int:
        """Get PDF max size in bytes."""
        return self.PDF_MAX_SIZE_MB * 1024 * 1024


# Global settings instance
settings = Settings()
