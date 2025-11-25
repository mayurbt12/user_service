"""CRUD operations for User Management Service.

This module provides database operations for users and tokens.
IMPORTANT: All datetime parameters and return values are datetime objects, NOT strings.
"""

from sqlalchemy.orm import Session
from typing import List, Optional, Tuple
import uuid
from datetime import datetime, timedelta, timezone
import hashlib

from database import User, RefreshToken, RoleEnum, Organization, OrganizationRoleEnum
from auth import PasswordHasher


def create_user(
    db: Session,
    mobile: str,
    password: str,
    profile: dict = None,
    role: str = "admin",
    organization_id: Optional[int] = None,
    organization_role: str = "member"
) -> User:
    """Create a new user in the database.

    If organization_id is not provided, automatically creates an organization for the user.
    If organization_id is provided, joins the user to that organization.

    Args:
        db: Database session
        mobile: User's mobile number (E.164 format)
        password: Plain text password (will be hashed)
        profile: Optional profile data dictionary
        role: User role (default: "user")
        organization_id: Optional organization ID to join (if None, creates new org)
        organization_role: Organization role (default: "member", "owner" for new orgs)

    Returns:
        User: Created user object with datetime fields

    Raises:
        ValueError: If user with mobile already exists
        SQLAlchemyError: On database errors
    """
    # Check if user already exists
    existing = get_user_by_mobile(db, mobile)
    if existing:
        raise ValueError(f"User with mobile {mobile} already exists")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Hash the password
    password_hash = PasswordHasher.hash_password(password)

    # Convert string role to enum
    role_enum = RoleEnum[role.upper()]

    # Convert organization_role string to enum
    org_role_enum = OrganizationRoleEnum[organization_role.upper()]

    # Handle organization creation/joining
    if organization_id is None:
        # For new organizations, user should be owner
        org_role_enum = OrganizationRoleEnum.OWNER

        # Create user first without organization_id
        db_user = User(
            id=user_id,
            mobile=mobile,
            password_hash=password_hash,
            role=role_enum,
            is_active=True,
            profile=profile or {},
            organization_id=None,  # Will be set after org creation
            organization_role=org_role_enum,
            created_at=now,
            updated_at=now,
            last_login=None
        )
        db.add(db_user)
        db.flush()  # Flush to persist user before creating org

        # Now create organization with the user_id
        org_name = f"{mobile}'s Organization"
        db_org = Organization(
            name=org_name,
            description="",
            owner_user_id=user_id,
            created_at=now,
            updated_at=now
        )
        db.add(db_org)
        db.flush()  # Flush to get the auto-generated org ID

        # Update user with organization_id
        db_user.organization_id = db_org.id
        db.commit()
        db.refresh(db_user)
        return db_user
    else:
        # Joining existing organization
        final_org_id = organization_id

        # Create user
        db_user = User(
            id=user_id,
            mobile=mobile,
            password_hash=password_hash,
            role=role_enum,
            is_active=True,
            profile=profile or {},
            organization_id=final_org_id,
            organization_role=org_role_enum,
            created_at=now,
            updated_at=now,
            last_login=None
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user


def get_user_by_mobile(db: Session, mobile: str) -> Optional[User]:
    """Get a user by mobile number.

    Args:
        db: Database session
        mobile: User's mobile number

    Returns:
        Optional[User]: User object if found, None otherwise
    """
    return db.query(User).filter(User.mobile == mobile).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Get a user by ID.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Optional[User]: User object if found, None otherwise
    """
    return db.query(User).filter(User.id == user_id).first()


def authenticate_user(db: Session, mobile: str, password: str) -> Optional[User]:
    """Authenticate a user by mobile and password.

    Args:
        db: Database session
        mobile: User's mobile number
        password: Plain text password

    Returns:
        Optional[User]: User object if authentication successful, None otherwise
    """
    user = get_user_by_mobile(db, mobile)
    if not user:
        return None

    if not user.is_active:
        return None

    # Verify password
    if not PasswordHasher.verify_password(password, user.password_hash):
        return None

    return user


def update_last_login(db: Session, user_id: str) -> bool:
    """Update user's last login timestamp.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        bool: True if updated, False if user not found
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False

    user.last_login = datetime.now(timezone.utc)
    db.commit()
    return True


def update_user(db: Session, user_id: str, updates: dict) -> Optional[User]:
    """Update user data.

    Args:
        db: Database session
        user_id: User UUID
        updates: Dictionary of fields to update (profile, etc.)

    Returns:
        Optional[User]: Updated user object if found, None otherwise
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    # Update fields
    for key, value in updates.items():
        if value is not None and key in ['profile']:
            setattr(user, key, value)

    # Update timestamp
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user_id: str, current_password: str, new_password: str) -> Tuple[bool, str]:
    """Change user password.

    Args:
        db: Database session
        user_id: User UUID
        current_password: Current password for verification
        new_password: New password to set

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False, "User not found"

    # Verify current password
    if not PasswordHasher.verify_password(current_password, user.password_hash):
        return False, "Current password is incorrect"

    # Hash and set new password
    user.password_hash = PasswordHasher.hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    return True, ""


def admin_reset_password(db: Session, user_id: str, new_password: str) -> Tuple[bool, str]:
    """Admin reset user password (no current password verification required).

    Args:
        db: Database session
        user_id: User UUID
        new_password: New password to set

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False, "User not found"

    # Hash and set new password
    user.password_hash = PasswordHasher.hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    return True, ""


def update_user_role(db: Session, user_id: str, new_role: str) -> Optional[User]:
    """Update user role (admin only operation).

    Args:
        db: Database session
        user_id: User UUID
        new_role: New role to assign

    Returns:
        Optional[User]: Updated user object if found, None otherwise
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    # Convert string role to enum
    role_enum = RoleEnum[new_role.upper()]
    user.role = role_enum
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user_id: str) -> bool:
    """Deactivate a user account.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        bool: True if deactivated, False if user not found
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False

    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def activate_user(db: Session, user_id: str) -> bool:
    """Activate a user account.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        bool: True if activated, False if user not found
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False

    user.is_active = True
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def delete_user(db: Session, user_id: str) -> Tuple[bool, str]:
    """Delete a user (hard delete).

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Tuple[bool, str]: (success, error_message)
            - (True, "") if deleted successfully
            - (False, error_message) if deletion failed
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False, "User not found"

    # Check if user owns an organization
    org = db.query(Organization).filter(Organization.owner_user_id == user_id).first()
    if org:
        return False, f"Cannot delete user. User owns organization '{org.name}'. Please transfer ownership or delete the organization first."

    try:
        db.delete(user)
        db.commit()
        return True, ""
    except Exception as e:
        db.rollback()
        return False, f"Error deleting user: {str(e)}"


def list_users(
    db: Session,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    organization_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50
) -> Tuple[List[User], int]:
    """List users with optional filtering and pagination.

    Args:
        db: Database session
        role: Optional role filter
        is_active: Optional active status filter
        organization_id: Optional organization filter (for non-system_admin users)
        page: Page number (1-indexed)
        page_size: Number of users per page

    Returns:
        Tuple[List[User], int]: (list of users, total count)
    """
    query = db.query(User)

    # Apply filters
    if role:
        role_enum = RoleEnum[role.upper()]
        query = query.filter(User.role == role_enum)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    if organization_id is not None:
        query = query.filter(User.organization_id == organization_id)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

    return users, total


def get_users_count(db: Session) -> int:
    """Get total number of users.

    Args:
        db: Database session

    Returns:
        int: Total user count
    """
    return db.query(User).count()


# Refresh Token CRUD Operations

def save_refresh_token(db: Session, user_id: str, token: str, expires_at: datetime) -> RefreshToken:
    """Save a refresh token to the database.

    Args:
        db: Database session
        user_id: User UUID
        token: Refresh token (will be hashed)
        expires_at: Token expiration datetime

    Returns:
        RefreshToken: Created refresh token object
    """
    token_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Hash the token before storing
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    db_token = RefreshToken(
        id=token_id,
        user_id=user_id,
        token_hash=token_hash,
        is_revoked=False,
        created_at=now,
        expires_at=expires_at
    )

    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


def get_refresh_token(db: Session, token: str) -> Optional[RefreshToken]:
    """Get a refresh token by its value.

    Args:
        db: Database session
        token: Refresh token

    Returns:
        Optional[RefreshToken]: Token object if found, None otherwise
    """
    # Hash the token to match stored hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()


def revoke_refresh_token(db: Session, token: str) -> bool:
    """Revoke a refresh token.

    Args:
        db: Database session
        token: Refresh token to revoke

    Returns:
        bool: True if revoked, False if not found
    """
    db_token = get_refresh_token(db, token)
    if not db_token:
        return False

    db_token.is_revoked = True
    db.commit()
    return True


def revoke_all_user_tokens(db: Session, user_id: str) -> int:
    """Revoke all refresh tokens for a user.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        int: Number of tokens revoked
    """
    tokens = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked == False
    ).all()

    count = 0
    for token in tokens:
        token.is_revoked = True
        count += 1

    db.commit()
    return count


def cleanup_expired_tokens(db: Session) -> int:
    """Delete expired refresh tokens.

    Args:
        db: Database session

    Returns:
        int: Number of tokens deleted
    """
    now = datetime.now(timezone.utc)
    tokens = db.query(RefreshToken).filter(RefreshToken.expires_at < now).all()

    count = len(tokens)
    for token in tokens:
        db.delete(token)

    db.commit()
    return count


# Organization CRUD Operations

def create_organization(db: Session, name: str, owner_user_id: str, description: str = "") -> Organization:
    """Create a new organization.

    Args:
        db: Database session
        name: Organization name
        owner_user_id: User ID of the organization owner
        description: Organization description (optional)

    Returns:
        Organization: Created organization object with auto-increment ID
    """
    now = datetime.now(timezone.utc)

    db_org = Organization(
        name=name,
        description=description,
        owner_user_id=owner_user_id,
        created_at=now,
        updated_at=now
    )

    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    return db_org


def get_organization_by_id(db: Session, org_id: int) -> Optional[Organization]:
    """Get an organization by ID.

    Args:
        db: Database session
        org_id: Organization ID

    Returns:
        Optional[Organization]: Organization object if found, None otherwise
    """
    return db.query(Organization).filter(Organization.id == org_id).first()


def update_organization(db: Session, org_id: int, updates: dict) -> Optional[Organization]:
    """Update organization data.

    Args:
        db: Database session
        org_id: Organization ID
        updates: Dictionary of fields to update (name, description)

    Returns:
        Optional[Organization]: Updated organization object if found, None otherwise
    """
    org = get_organization_by_id(db, org_id)
    if not org:
        return None

    # Update fields
    for key, value in updates.items():
        if value is not None and key in ['name', 'description']:
            setattr(org, key, value)

    # Update timestamp
    org.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(org)
    return org


def add_team_member_to_organization(
    db: Session,
    org_id: int,
    mobile: str,
    password: str,
    profile: dict = None,
    role: str = "user"
) -> User:
    """Add a new team member to an organization.

    Args:
        db: Database session
        org_id: Organization ID
        mobile: Team member's mobile number
        password: Plain text password (will be hashed)
        profile: Optional profile data dictionary
        role: User role (default: "user")

    Returns:
        User: Created user object

    Raises:
        ValueError: If user with mobile already exists or organization not found
    """
    # Check if organization exists
    org = get_organization_by_id(db, org_id)
    if not org:
        raise ValueError(f"Organization with ID {org_id} not found")

    # Check if user already exists
    existing = get_user_by_mobile(db, mobile)
    if existing:
        raise ValueError(f"User with mobile {mobile} already exists")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Hash the password
    password_hash = PasswordHasher.hash_password(password)

    # Convert string role to enum
    role_enum = RoleEnum[role.upper()]

    db_user = User(
        id=user_id,
        mobile=mobile,
        password_hash=password_hash,
        role=role_enum,
        is_active=True,
        profile=profile or {},
        organization_id=org_id,
        organization_role=OrganizationRoleEnum.MEMBER,
        created_at=now,
        updated_at=now,
        last_login=None
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def list_organization_members(db: Session, org_id: int) -> List[User]:
    """List all members of an organization.

    Args:
        db: Database session
        org_id: Organization ID

    Returns:
        List[User]: List of users in the organization
    """
    return db.query(User).filter(User.organization_id == org_id).order_by(User.created_at.desc()).all()


def remove_team_member_from_organization(db: Session, org_id: int, user_id: str) -> Tuple[bool, str]:
    """Remove a team member from an organization (deactivate the user).

    Args:
        db: Database session
        org_id: Organization ID
        user_id: User ID to remove

    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return False, "User not found"

    if user.organization_id != org_id:
        return False, "User does not belong to this organization"

    if user.organization_role == OrganizationRoleEnum.OWNER:
        return False, "Cannot remove organization owner"

    # Deactivate the user
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True, ""
