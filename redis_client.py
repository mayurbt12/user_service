"""Redis client for distributed token blacklist.

This module provides a Redis-based token blacklist that works across
multiple service instances and survives restarts.

SOLID Principles:
- Single Responsibility: Only handles Redis connection and token blacklist
- Open/Closed: Extensible for other Redis use cases
- Dependency Inversion: Depends on Redis abstraction
"""

import redis
from typing import Optional
from config import settings
import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client with connection pooling for token blacklist.
    
    This class manages the Redis connection and provides methods for
    token blacklist operations with automatic TTL (time-to-live).
    """
    
    _instance: Optional['RedisClient'] = None
    _redis_client: Optional[redis.Redis] = None
    
    def __new__(cls):
        """Singleton pattern to ensure only one Redis connection pool."""
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Redis connection pool."""
        if self._redis_client is None:
            try:
                self._redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                    db=settings.REDIS_DB,
                    decode_responses=True,  # Return strings instead of bytes
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                # Test connection
                self._redis_client.ping()
                logger.info(f"✓ Redis connected: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            except redis.ConnectionError as e:
                logger.error(f"✗ Redis connection failed: {e}")
                logger.warning("⚠ Falling back to in-memory token blacklist")
                self._redis_client = None
            except Exception as e:
                logger.error(f"✗ Redis initialization error: {e}")
                self._redis_client = None
    
    @property
    def client(self) -> Optional[redis.Redis]:
        """Get Redis client instance."""
        return self._redis_client
    
    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        if self._redis_client is None:
            return False
        try:
            self._redis_client.ping()
            return True
        except:
            return False
    
    def blacklist_token(self, token: str, expires_in_seconds: int) -> bool:
        """Add token to blacklist with TTL.
        
        Args:
            token: JWT token to blacklist
            expires_in_seconds: Time until token naturally expires
        
        Returns:
            True if successfully blacklisted, False otherwise
        """
        if not self.is_available:
            logger.warning("Redis not available, token not blacklisted")
            return False
        
        try:
            key = f"{settings.REDIS_TOKEN_BLACKLIST_PREFIX}{token}"
            # Set with TTL equal to token expiration
            self._redis_client.setex(key, expires_in_seconds, "1")
            return True
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")
            return False
    
    def is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted.
        
        Args:
            token: JWT token to check
        
        Returns:
            True if blacklisted, False otherwise
        """
        if not self.is_available:
            # If Redis is down, we can't verify blacklist
            # For security, we could either:
            # 1. Allow the token (availability)
            # 2. Deny the token (security)
            # We choose availability but log the issue
            logger.warning("Redis not available, cannot verify token blacklist")
            return False
        
        try:
            key = f"{settings.REDIS_TOKEN_BLACKLIST_PREFIX}{token}"
            return self._redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check token blacklist: {e}")
            return False
    
    def get_blacklist_size(self) -> int:
        """Get number of blacklisted tokens.
        
        Returns:
            Number of tokens in blacklist
        """
        if not self.is_available:
            return 0
        
        try:
            pattern = f"{settings.REDIS_TOKEN_BLACKLIST_PREFIX}*"
            return len(list(self._redis_client.scan_iter(match=pattern)))
        except Exception as e:
            logger.error(f"Failed to get blacklist size: {e}")
            return 0
    
    def clear_blacklist(self) -> bool:
        """Clear all blacklisted tokens (admin only).
        
        WARNING: This should only be used for testing or emergency situations.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_available:
            return False
        
        try:
            pattern = f"{settings.REDIS_TOKEN_BLACKLIST_PREFIX}*"
            keys = list(self._redis_client.scan_iter(match=pattern))
            if keys:
                self._redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} blacklisted tokens")
            return True
        except Exception as e:
            logger.error(f"Failed to clear blacklist: {e}")
            return False


# Global Redis client instance
redis_client = RedisClient()
