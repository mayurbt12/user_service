"""Database module for User Management Service.

This module defines SQLAlchemy models and database session management.
IMPORTANT: All datetime fields are stored as DateTime objects with timezone support.
"""

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, JSON, Enum as SQLEnum, Index, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import enum

from config import settings

# SQLAlchemy Base
Base = declarative_base()


class RoleEnum(enum.Enum):
    """User role levels"""
    GUEST = "guest"
    USER = "user"
    MODERATOR = "moderator"
    MANAGER = "manager"
    SYSTEM_ADMIN = "system_admin"


class User(Base):
    """User model - stores user account data.

    CRITICAL: All datetime fields are DateTime objects with timezone support, NOT strings.
    """

    __tablename__ = "users"

    # Primary Key
    id = Column(String, primary_key=True, doc="Unique user ID (UUID)")

    # User Identification - Mobile number as primary identifier
    mobile = Column(String, nullable=False, unique=True, index=True, doc="User's mobile number (E.164 format)")

    # Authentication
    password_hash = Column(String, nullable=False, doc="Bcrypt hashed password")

    # Role and Status
    role = Column(SQLEnum(RoleEnum), default=RoleEnum.USER, index=True, doc="User role")
    is_active = Column(Boolean, default=True, index=True, doc="Whether user account is active")

    # Profile Data (stored as JSON for flexibility)
    profile = Column(JSON, default={}, doc="User profile data (name, avatar, etc.)")

    # Timestamps - CRITICAL: DateTime objects, NOT strings!
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When user account was created (timezone-aware)"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When user account was last updated (timezone-aware)"
    )
    last_login = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When user last logged in (timezone-aware)"
    )

    # Composite indexes for query performance
    __table_args__ = (
        Index('idx_mobile_active', 'mobile', 'is_active'),
        Index('idx_role_active', 'role', 'is_active'),
    )

    def __repr__(self):
        """String representation"""
        return (
            f"<User(id={self.id}, mobile={self.mobile}, "
            f"role={self.role.value}, active={self.is_active})>"
        )


class RefreshToken(Base):
    """Refresh token model - stores refresh tokens for revocation support.

    CRITICAL: All datetime fields are DateTime objects with timezone support.
    """

    __tablename__ = "refresh_tokens"

    # Primary Key
    id = Column(String, primary_key=True, doc="Unique token ID (UUID)")

    # Foreign Key to User
    user_id = Column(
        String,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        doc="Reference to user who owns this token"
    )

    # Token Data
    token_hash = Column(String, nullable=False, unique=True, doc="Hashed refresh token")

    # Token Status
    is_revoked = Column(Boolean, default=False, index=True, doc="Whether token has been revoked")

    # Timestamps - CRITICAL: DateTime objects!
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When token was created (timezone-aware)"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="When token expires (timezone-aware)"
    )

    # Composite indexes
    __table_args__ = (
        Index('idx_user_active', 'user_id', 'is_revoked'),
        Index('idx_expires_revoked', 'expires_at', 'is_revoked'),
    )

    def __repr__(self):
        """String representation"""
        return (
            f"<RefreshToken(id={self.id}, user_id={self.user_id}, "
            f"revoked={self.is_revoked}, expires={self.expires_at})>"
        )


# Database Engine Setup
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False  # Set to True for SQL debugging
)

# Session Factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Database session dependency for FastAPI.

    Yields:
        Session: SQLAlchemy database session

    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            # Use db here
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create all tables
Base.metadata.create_all(bind=engine)
