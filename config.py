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
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production-min-32-chars-recommended"
    """Secret key for JWT token signing. MUST be changed in production!"""

    JWT_ALGORITHM: str = "HS256"
    """JWT signing algorithm"""

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    """Access token expiration time in minutes"""

    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    """Refresh token expiration time in days"""

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

    # Default Admin User (created on first run)
    DEFAULT_ADMIN_MOBILE: str = "+1234567890"
    """Default admin user mobile number"""

    DEFAULT_ADMIN_PASSWORD: str = "Admin@123"
    """Default admin password (CHANGE IMMEDIATELY IN PRODUCTION!)"""

    class Config:
        """Pydantic config"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
