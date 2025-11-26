"""Organization-aware middleware and dependency functions.

Provides enhanced dependency injection for FastAPI endpoints with organization
access control. Implements Token + Validation Hybrid pattern.

CRITICAL: Never use hasattr() per project requirements.
"""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import User, RoleEnum, OrganizationRoleEnum, get_db
from shared_libs.auth import JWTHandler, TokenBlacklist
from validators import get_organization_validator, OrganizationAccessDeniedError

logger = logging.getLogger(__name__)

security = HTTPBearer()


class CurrentUserContext:
    """Enhanced user context with organization validation capabilities.

    Provides both token-based information (for fast filtering) and database
    validation methods (for write operations).
    """

    def __init__(
        self,
        user: User,
        db_session: Session,
        token_organization_id: Optional[int] = None,
        token_organization_role: Optional[OrganizationRoleEnum] = None
    ):
        """Initialize user context.

        Args:
            user: User database model
            db_session: Database session for validation
            token_organization_id: Organization ID from JWT token
            token_organization_role: Organization role from JWT token
        """
        self.user = user
        self._db_session = db_session
        self.token_organization_id = token_organization_id
        self.token_organization_role = token_organization_role

    @property
    def user_id(self) -> str:
        """Get user ID."""
        return self.user.id

    @property
    def mobile(self) -> str:
        """Get user mobile number."""
        return self.user.mobile

    @property
    def role(self) -> RoleEnum:
        """Get user's system role."""
        return self.user.role

    @property
    def is_active(self) -> bool:
        """Check if user is active."""
        return self.user.is_active

    @property
    def profile(self) -> dict:
        """Get user profile data."""
        return self.user.profile or {}

    def is_system_admin(self) -> bool:
        """Check if user is system admin."""
        return self.user.role == RoleEnum.SYSTEM_ADMIN

    def get_organizations(self):
        """Get all active organizations for this user from database.

        Returns:
            List of tuples (organization_id, organization_role)
        """
        validator = get_organization_validator()
        return validator.get_user_organizations(self._db_session, self.user_id)

    def can_manage_organization(self, organization_id: int) -> bool:
        """Check if user can manage the organization (add/remove members).

        Args:
            organization_id: Organization ID

        Returns:
            Boolean: True if user can manage organization
        """
        validator = get_organization_validator()
        return validator.can_user_manage_organization(
            self._db_session,
            self.user_id,
            self.user.role,
            organization_id
        )

    def is_organization_owner(self, organization_id: int) -> bool:
        """Check if user is owner of organization.

        Args:
            organization_id: Organization ID

        Returns:
            Boolean: True if user is owner
        """
        validator = get_organization_validator()
        return validator.is_organization_owner(
            self._db_session,
            self.user_id,
            organization_id
        )

    def is_member_of_organization(self, organization_id: int) -> bool:
        """Check if user is member of organization.

        Args:
            organization_id: Organization ID

        Returns:
            Boolean: True if user is active member
        """
        validator = get_organization_validator()
        return validator.is_member_of_organization(
            self._db_session,
            self.user_id,
            organization_id
        )

    def get_organization_role(self, organization_id: int) -> Optional[OrganizationRoleEnum]:
        """Get user's role in organization.

        Args:
            organization_id: Organization ID

        Returns:
            OrganizationRoleEnum or None
        """
        validator = get_organization_validator()
        return validator.get_organization_role(
            self._db_session,
            self.user_id,
            organization_id
        )

    def validate_organization_access(
        self,
        organization_id: int,
        required_role: Optional[OrganizationRoleEnum] = None
    ) -> bool:
        """Validate user has access to organization.

        Args:
            organization_id: Organization ID
            required_role: Required organization role

        Returns:
            Boolean: True if access granted

        Raises:
            OrganizationAccessDeniedError: If access denied
        """
        validator = get_organization_validator()
        return validator.validate_organization_access(
            self._db_session,
            self.user_id,
            self.user.role,
            organization_id,
            required_role
        )

    def validate_write_operation(
        self,
        target_user_id: str,
        organization_id: int,
        requires_owner: bool = False
    ) -> bool:
        """Validate a write operation on another user.

        Args:
            target_user_id: ID of user being modified
            organization_id: Organization context
            requires_owner: Whether operation requires owner role

        Returns:
            Boolean: True if operation allowed

        Raises:
            OrganizationAccessDeniedError: If operation not allowed
        """
        validator = get_organization_validator()
        return validator.validate_write_operation(
            self._db_session,
            self.user_id,
            self.user.role,
            target_user_id,
            organization_id,
            requires_owner
        )


def get_current_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> CurrentUserContext:
    """Enhanced dependency to get current user with organization context.

    This replaces the basic get_current_user() dependency with an enhanced
    version that provides organization validation capabilities.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        CurrentUserContext: Enhanced user context

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials

    # Check if token is blacklisted
    if TokenBlacklist.is_blacklisted(token):
        logger.warning("Attempted access with blacklisted token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Verify and decode token
    payload = JWTHandler.verify_token(token, token_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Extract user information from token
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Extract organization info from token
    token_org_id = payload.get("organization_id")
    token_org_role_str = payload.get("organization_role")
    token_org_role = None

    if token_org_role_str:
        try:
            token_org_role = OrganizationRoleEnum(token_org_role_str)
        except ValueError:
            logger.warning(f"Invalid organization role in token: {token_org_role_str}")

    # Create and return enhanced context
    return CurrentUserContext(
        user=user,
        db_session=db,
        token_organization_id=token_org_id,
        token_organization_role=token_org_role
    )


def require_role_with_org_context(allowed_roles: list[str]):
    """Dependency factory for role-based access control with organization context.

    Args:
        allowed_roles: List of allowed role values (e.g., ["system_admin", "admin"])

    Returns:
        Dependency function that returns CurrentUserContext
    """
    def check_role(current_user: CurrentUserContext = Depends(get_current_user_context)):
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}"
            )
        return current_user

    return check_role


def require_organization_owner(organization_id: int):
    """Dependency factory to require organization owner role.

    Args:
        organization_id: Organization ID to check ownership

    Returns:
        Dependency function that returns CurrentUserContext
    """
    def check_owner(current_user: CurrentUserContext = Depends(get_current_user_context)):
        try:
            # System admins bypass check
            if current_user.is_system_admin():
                return current_user

            # Validate organization ownership
            if not current_user.is_organization_owner(organization_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This operation requires organization owner role"
                )

            return current_user

        except OrganizationAccessDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )

    return check_owner


def require_organization_member(organization_id: int):
    """Dependency factory to require organization membership.

    Args:
        organization_id: Organization ID to check membership

    Returns:
        Dependency function that returns CurrentUserContext
    """
    def check_member(current_user: CurrentUserContext = Depends(get_current_user_context)):
        try:
            # System admins bypass check
            if current_user.is_system_admin():
                return current_user

            # Validate organization membership
            if not current_user.is_member_of_organization(organization_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this organization"
                )

            return current_user

        except OrganizationAccessDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )

    return check_member
