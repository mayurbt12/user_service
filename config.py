"""Configuration module for User Management Service.

This module provides configuration settings using Pydantic Settings.
Environment variables can be used to override default values.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings for User Management Service.

    All settings can be overridden via environment variables.
    Example: export DATABASE_URL="postgresql://..."
    """

    # Database Configuration
    DATABASE_URL: str = "sqlite:///./users.db"
    """Database connection URL. Default: SQLite file in current directory"""

    # API Server Configuration
    API_HOST: str = "0.0.0.0"
    """API server host address"""

    API_PORT: int = 8007
    """API server port (unique to avoid conflicts)"""

    # MCP Server Configuration
    MCP_HOST: str = "127.0.0.1"
    """MCP server host address"""

    MCP_PORT: int = 8008
    """MCP server port for SSE transport (separate from REST API)"""

    MCP_TRANSPORT: str = "sse"
    """MCP transport type: 'stdio' for local, 'sse' for network access"""

    # JWT Configuration
    JWT_SECRET_KEY: str
    """Secret key for JWT token signing. MUST be set via environment variable!"""

    JWT_ALGORITHM: str = "HS256"
    """JWT signing algorithm"""

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    """Access token expiration time in minutes"""

    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    """Refresh token expiration time in days"""

    # Redis Configuration (for distributed token blacklist)
    REDIS_HOST: str = "localhost"
    """Redis server host"""

    REDIS_PORT: int = 6379
    """Redis server port"""

    REDIS_PASSWORD: str = ""
    """Redis password (empty if no auth)"""

    REDIS_DB: int = 0
    """Redis database number"""

    REDIS_TOKEN_BLACKLIST_PREFIX: str = "token_blacklist:"
    """Prefix for token blacklist keys in Redis"""

    # Password Configuration
    BCRYPT_ROUNDS: int = 12
    """Number of bcrypt hashing rounds (higher = more secure but slower)"""

    MIN_PASSWORD_LENGTH: int = 8
    """Minimum password length requirement"""

    # General Configuration
    TIMEZONE: str = "UTC"
    """Default timezone for datetime operations"""

    MAX_USERS: int = 10000
    """Maximum number of users allowed in the system"""

    # Diagnostics Configuration (Google SRE Golden Signals)
    SLOW_QUERY_THRESHOLD_MS: float = 100.0
    """Threshold in milliseconds for logging slow database queries"""

    SLOW_REQUEST_THRESHOLD_MS: float = 500.0
    """Threshold in milliseconds for logging slow HTTP requests"""

    # Database Connection Pool Configuration (SQLAlchemy best practices)
    DB_POOL_SIZE: int = 10
    """Base number of persistent database connections (increased from 5 to handle concurrent load)"""

    DB_MAX_OVERFLOW: int = 20
    """Maximum overflow connections beyond pool_size for burst traffic (increased from 10)"""

    DB_POOL_TIMEOUT: int = 5
    """Seconds to wait for available connection before timeout (reduced from 30 to match client timeouts)"""

    DB_POOL_RECYCLE: int = 600
    """Seconds before connection is recycled - 10 minutes (reduced from 30min to prevent stale connections)"""

    DB_POOL_PRE_PING: bool = True
    """Verify connection is alive before use (recommended for production)"""

    class Config:
        """Pydantic config"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
