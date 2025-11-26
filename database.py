"""Database module for User Management Service.

This module defines SQLAlchemy models and database session management.
IMPORTANT: All datetime fields are stored as DateTime objects with timezone support.
"""

from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, JSON, Enum as SQLEnum, Index, ForeignKey
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
    ADMIN = "admin"
    AI_AGENT = "ai_agent"


class OrganizationRoleEnum(enum.Enum):
    """Organization role levels"""
    OWNER = "owner"
    MEMBER = "member"


class Organization(Base):
    """Organization model - stores organization/tenant data.

    CRITICAL: All datetime fields are DateTime objects with timezone support, NOT strings.
    """

    __tablename__ = "organizations"

    # Primary Key - Auto-increment Integer
    id = Column(Integer, primary_key=True, autoincrement=True, doc="Unique organization ID")

    # Organization Details
    name = Column(String, nullable=False, doc="Organization name")
    description = Column(String, default="", doc="Organization description")

    # Owner Reference
    owner_user_id = Column(
        String,
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
        doc="User ID of the organization owner"
    )

    # Timestamps - CRITICAL: DateTime objects, NOT strings!
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When organization was created (timezone-aware)"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When organization was last updated (timezone-aware)"
    )

    def __repr__(self):
        """String representation"""
        return (
            f"<Organization(id={self.id}, name={self.name}, "
            f"owner_user_id={self.owner_user_id})>"
        )


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

    # Organization Association (DEPRECATED - Use UserOrganization table)
    # Kept for backward compatibility during migration
    organization_id = Column(
        Integer,
        ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=True,  # Nullable to allow user creation before organization assignment
        index=True,
        doc="[DEPRECATED] Organization ID - use UserOrganization table instead"
    )
    organization_role = Column(
        SQLEnum(OrganizationRoleEnum),
        default=OrganizationRoleEnum.MEMBER,
        index=True,
        doc="[DEPRECATED] User's role - use UserOrganization table instead"
    )

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
        Index('idx_org_user', 'organization_id', 'id'),
        Index('idx_org_role', 'organization_id', 'organization_role'),
    )

    def get_active_organizations(self, db_session):
        """Get all active organizations this user belongs to.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            List of tuples (organization_id, organization_role) for active memberships
        """
        from sqlalchemy import and_

        memberships = db_session.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == self.id,
                UserOrganization.is_active == True
            )
        ).all()

        return [(m.organization_id, m.role) for m in memberships]

    def get_default_organization_id(self, db_session):
        """Get the default organization ID for token generation.

        For backward compatibility, returns the first active organization.
        In the future, this could be user-configurable.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            Integer: Default organization ID or None
        """
        # Try new UserOrganization table first
        membership = db_session.query(UserOrganization).filter(
            UserOrganization.user_id == self.id,
            UserOrganization.is_active == True
        ).first()

        if membership:
            return membership.organization_id

        # Fallback to deprecated field for backward compatibility
        return self.organization_id

    def get_default_organization_role(self, db_session):
        """Get the default organization role for token generation.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            OrganizationRoleEnum: Default organization role or MEMBER
        """
        # Try new UserOrganization table first
        membership = db_session.query(UserOrganization).filter(
            UserOrganization.user_id == self.id,
            UserOrganization.is_active == True
        ).first()

        if membership:
            return membership.role

        # Fallback to deprecated field for backward compatibility
        return self.organization_role or OrganizationRoleEnum.MEMBER

    def is_member_of_organization(self, db_session, organization_id):
        """Check if user is an active member of the specified organization.

        Args:
            db_session: SQLAlchemy database session
            organization_id: Organization ID to check

        Returns:
            Boolean: True if user is active member, False otherwise
        """
        from sqlalchemy import and_

        membership = db_session.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == self.id,
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True
            )
        ).first()

        return membership is not None

    def get_organization_role_for(self, db_session, organization_id):
        """Get user's role in a specific organization.

        Args:
            db_session: SQLAlchemy database session
            organization_id: Organization ID

        Returns:
            OrganizationRoleEnum or None: User's role in the organization
        """
        from sqlalchemy import and_

        membership = db_session.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == self.id,
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True
            )
        ).first()

        return membership.role if membership else None

    def __repr__(self):
        """String representation"""
        return (
            f"<User(id={self.id}, mobile={self.mobile}, "
            f"role={self.role.value}, org_id={self.organization_id}, "
            f"org_role={self.organization_role.value if self.organization_role else None}, "
            f"active={self.is_active})>"
        )


class UserOrganization(Base):
    """User-Organization junction table - supports multi-organization membership.

    This table enables users to belong to multiple organizations with different roles.
    Provides scalable foundation for future multi-organization features.

    CRITICAL: All datetime fields are DateTime objects with timezone support.
    """

    __tablename__ = "user_organizations"

    # Primary Key
    id = Column(String, primary_key=True, doc="Unique junction record ID (UUID)")

    # Foreign Keys
    user_id = Column(
        String,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        doc="Reference to user"
    )
    organization_id = Column(
        Integer,
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        doc="Reference to organization"
    )

    # Organization Role
    role = Column(
        SQLEnum(OrganizationRoleEnum),
        default=OrganizationRoleEnum.MEMBER,
        nullable=False,
        index=True,
        doc="User's role within this organization"
    )

    # Status
    is_active = Column(
        Boolean,
        default=True,
        index=True,
        doc="Whether this membership is active"
    )

    # Timestamps - CRITICAL: DateTime objects!
    joined_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When user joined this organization (timezone-aware)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When this record was created (timezone-aware)"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        doc="When this record was last updated (timezone-aware)"
    )

    # Composite indexes and constraints
    __table_args__ = (
        Index('idx_user_org_membership', 'user_id', 'organization_id'),
        Index('idx_org_user_active_membership', 'organization_id', 'user_id', 'is_active'),
        Index('idx_user_active_membership', 'user_id', 'is_active'),
        # Ensure a user can only have one membership record per organization
        # (though is_active controls if it's currently active)
    )

    def __repr__(self):
        """String representation"""
        return (
            f"<UserOrganization(id={self.id}, user_id={self.user_id}, "
            f"org_id={self.organization_id}, role={self.role.value}, "
            f"active={self.is_active})>"
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
