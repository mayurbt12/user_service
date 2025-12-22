"""Organization validation and access control module.

This module provides validation functions for organization-based access control.
Implements Token + Validation Hybrid pattern:
- Read operations: Use token's organization_id for fast filtering
- Write operations: Validate against database for security

CRITICAL: Never use hasattr() per project requirements.
"""

from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from functools import lru_cache
from datetime import datetime, timezone, timedelta

from database import User, UserOrganization, Organization, RoleEnum, OrganizationRoleEnum
from logger_config import setup_logger

logger = setup_logger(__name__, 'api.log')


class OrganizationAccessDeniedError(Exception):
    """Raised when user doesn't have access to requested organization."""
    pass


class OrganizationValidator:
    """Organization validation and access control.

    Provides methods to validate user access to organizations with caching.
    """

    # Cache duration for organization memberships (5 minutes)
    CACHE_TTL_SECONDS = 300
    # Maximum cache size to prevent memory leaks
    MAX_CACHE_SIZE = 10000

    def __init__(self):
        """Initialize validator with cache."""
        self._cache = {}
        self._cache_timestamps = {}

    def _get_cache_key(self, user_id: str, organization_id: int) -> str:
        """Generate cache key for user-organization pair."""
        return f"{user_id}:{organization_id}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached value is still valid."""
        if cache_key not in self._cache_timestamps:
            return False

        timestamp = self._cache_timestamps[cache_key]
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return age < self.CACHE_TTL_SECONDS

    def _set_cache(self, cache_key: str, value: any):
        """Set cache value with timestamp. Evicts stale entries if cache is full."""
        if len(self._cache) >= self.MAX_CACHE_SIZE:
            self._evict_stale_entries()
        self._cache[cache_key] = value
        self._cache_timestamps[cache_key] = datetime.now(timezone.utc)

    def _get_cache(self, cache_key: str) -> Optional[any]:
        """Get cached value if valid."""
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key)
        return None

    def _evict_stale_entries(self):
        """Remove expired cache entries to prevent memory leaks."""
        now = datetime.now(timezone.utc)
        stale_keys = [
            k for k, ts in self._cache_timestamps.items()
            if (now - ts).total_seconds() > self.CACHE_TTL_SECONDS
        ]
        for key in stale_keys:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        if stale_keys:
            logger.debug(f"Evicted {len(stale_keys)} stale cache entries")

    def invalidate_cache_for_user(self, user_id: str):
        """Invalidate all cached entries for a user."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{user_id}:")]
        for key in keys_to_remove:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

        logger.debug(f"Invalidated cache for user {user_id}: {len(keys_to_remove)} entries")

    def get_user_organizations(self, db: Session, user_id: str) -> List[Tuple[int, OrganizationRoleEnum]]:
        """Get all active organizations for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            List of tuples (organization_id, role)
        """
        memberships = db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.is_active == True
            )
        ).all()

        return [(m.organization_id, m.role) for m in memberships]

    def is_organization_owner(self, db: Session, user_id: str, organization_id: int) -> bool:
        """Check if user is owner of the organization.

        Args:
            db: Database session
            user_id: User ID
            organization_id: Organization ID

        Returns:
            Boolean: True if user is owner
        """
        cache_key = f"{self._get_cache_key(user_id, organization_id)}:owner"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        membership = db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True,
                UserOrganization.role == OrganizationRoleEnum.OWNER
            )
        ).first()

        result = membership is not None
        self._set_cache(cache_key, result)
        return result

    def is_member_of_organization(self, db: Session, user_id: str, organization_id: int) -> bool:
        """Check if user is an active member of organization.

        Args:
            db: Database session
            user_id: User ID
            organization_id: Organization ID

        Returns:
            Boolean: True if user is active member
        """
        cache_key = f"{self._get_cache_key(user_id, organization_id)}:member"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        membership = db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True
            )
        ).first()

        result = membership is not None
        self._set_cache(cache_key, result)
        return result

    def get_organization_role(self, db: Session, user_id: str, organization_id: int) -> Optional[OrganizationRoleEnum]:
        """Get user's role in organization.

        Args:
            db: Database session
            user_id: User ID
            organization_id: Organization ID

        Returns:
            OrganizationRoleEnum or None
        """
        cache_key = f"{self._get_cache_key(user_id, organization_id)}:role"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        membership = db.query(UserOrganization).filter(
            and_(
                UserOrganization.user_id == user_id,
                UserOrganization.organization_id == organization_id,
                UserOrganization.is_active == True
            )
        ).first()

        result = membership.role if membership else None
        self._set_cache(cache_key, result)
        return result

    def validate_organization_access(
        self,
        db: Session,
        user_id: str,
        user_role: RoleEnum,
        organization_id: int,
        required_role: Optional[OrganizationRoleEnum] = None
    ) -> bool:
        """Validate user has access to organization with optional role requirement.

        System admins bypass all checks.

        Args:
            db: Database session
            user_id: User ID
            user_role: User's system role
            organization_id: Organization ID to validate
            required_role: Required organization role (OWNER or MEMBER)

        Returns:
            Boolean: True if access granted

        Raises:
            OrganizationAccessDeniedError: If access denied
        """
        # System admins bypass all organization checks
        if user_role == RoleEnum.SYSTEM_ADMIN:
            return True

        # Check if user is member of organization
        if not self.is_member_of_organization(db, user_id, organization_id):
            logger.warning(
                f"User {user_id} attempted to access organization {organization_id} "
                "but is not a member"
            )
            raise OrganizationAccessDeniedError(
                f"User does not have access to organization {organization_id}"
            )

        # Check role requirement if specified
        if required_role:
            user_org_role = self.get_organization_role(db, user_id, organization_id)

            if required_role == OrganizationRoleEnum.OWNER:
                if user_org_role != OrganizationRoleEnum.OWNER:
                    logger.warning(
                        f"User {user_id} attempted owner-only operation in "
                        f"organization {organization_id} but has role {user_org_role}"
                    )
                    raise OrganizationAccessDeniedError(
                        "This operation requires organization owner role"
                    )

        return True

    def validate_write_operation(
        self,
        db: Session,
        current_user_id: str,
        current_user_role: RoleEnum,
        target_user_id: str,
        organization_id: int,
        requires_owner: bool = False
    ) -> bool:
        """Validate a write operation on a user within an organization.

        System admins can modify any user.
        Organization owners can modify members of their organization.
        Regular members cannot modify other users.

        Args:
            db: Database session
            current_user_id: ID of user performing action
            current_user_role: System role of current user
            target_user_id: ID of user being modified
            organization_id: Organization context
            requires_owner: Whether operation requires owner role

        Returns:
            Boolean: True if operation allowed

        Raises:
            OrganizationAccessDeniedError: If operation not allowed
        """
        # System admins can do anything
        if current_user_role == RoleEnum.SYSTEM_ADMIN:
            return True

        # Check current user is member of organization
        if not self.is_member_of_organization(db, current_user_id, organization_id):
            raise OrganizationAccessDeniedError(
                "You don't have access to this organization"
            )

        # Check target user is member of same organization
        if not self.is_member_of_organization(db, target_user_id, organization_id):
            raise OrganizationAccessDeniedError(
                "Target user is not in your organization"
            )

        # Check if owner role is required
        if requires_owner or True:  # Most write operations require owner
            if not self.is_organization_owner(db, current_user_id, organization_id):
                raise OrganizationAccessDeniedError(
                    "This operation requires organization owner role"
                )

        return True

    def can_user_manage_organization(
        self,
        db: Session,
        user_id: str,
        user_role: RoleEnum,
        organization_id: int
    ) -> bool:
        """Check if user can manage organization (add/remove members, etc.).

        Args:
            db: Database session
            user_id: User ID
            user_role: User's system role
            organization_id: Organization ID

        Returns:
            Boolean: True if user can manage organization
        """
        # System admins can manage any organization
        if user_role == RoleEnum.SYSTEM_ADMIN:
            return True

        # Organization owners can manage their organization
        return self.is_organization_owner(db, user_id, organization_id)


# Global validator instance
org_validator = OrganizationValidator()


def get_organization_validator() -> OrganizationValidator:
    """Get the global organization validator instance.

    Returns:
        OrganizationValidator: Global validator instance
    """
    return org_validator
