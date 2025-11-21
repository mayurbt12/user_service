"""Authentication and security module for User Management Service.

This module provides JWT token generation/validation and password hashing utilities.
Avoids using hasattr per project constraints.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
import bcrypt
from jose import JWTError, jwt

from config import settings


class PasswordHasher:
    """Password hashing and verification using bcrypt."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password to hash

        Returns:
            Hashed password as a string

        Raises:
            ValueError: If password is empty or None
        """
        if not password:
            raise ValueError("Password cannot be empty")

        # Generate salt and hash the password
        salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
        password_bytes = password.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Hashed password to compare against

        Returns:
            True if password matches, False otherwise
        """
        if not plain_password or not hashed_password:
            return False

        try:
            password_bytes = plain_password.encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception:
            return False


class JWTHandler:
    """JWT token generation and validation."""

    @staticmethod
    def create_access_token(data: Dict[str, any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token.

        Args:
            data: Payload data to encode in the token (should include user_id, mobile, role)
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT token as string
        """
        to_encode = data.copy()

        # Set expiration time
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode.update({"exp": expire, "type": "access"})

        # Encode the token
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: Dict[str, any], expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT refresh token.

        Args:
            data: Payload data to encode (should include user_id)
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT refresh token as string
        """
        to_encode = data.copy()

        # Set expiration time
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )

        to_encode.update({"exp": expire, "type": "refresh"})

        # Encode the token
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, any]]:
        """Verify and decode a JWT token.

        Args:
            token: JWT token to verify
            token_type: Expected token type ("access" or "refresh")

        Returns:
            Decoded token payload if valid, None otherwise
        """
        try:
            # Decode the token
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )

            # Verify token type
            if payload.get("type") != token_type:
                return None

            return payload

        except JWTError:
            return None
        except Exception:
            return None

    @staticmethod
    def decode_token(token: str) -> Optional[Dict[str, any]]:
        """Decode a JWT token without verification (for debugging).

        Args:
            token: JWT token to decode

        Returns:
            Decoded token payload if valid format, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        except Exception:
            return None


class TokenBlacklist:
    """In-memory token blacklist for logout functionality.

    Note: In production, use Redis or database for distributed systems.
    """

    _blacklist = set()

    @classmethod
    def add_token(cls, token: str) -> None:
        """Add a token to the blacklist.

        Args:
            token: JWT token to blacklist
        """
        cls._blacklist.add(token)

    @classmethod
    def is_blacklisted(cls, token: str) -> bool:
        """Check if a token is blacklisted.

        Args:
            token: JWT token to check

        Returns:
            True if token is blacklisted, False otherwise
        """
        return token in cls._blacklist

    @classmethod
    def clear(cls) -> None:
        """Clear all blacklisted tokens (mainly for testing)."""
        cls._blacklist.clear()


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength.

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not password:
        return False, "Password cannot be empty"

    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"

    # Check for at least one uppercase letter
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    # Check for at least one lowercase letter
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    # Check for at least one digit
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    # Check for at least one special character
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character"

    return True, ""
