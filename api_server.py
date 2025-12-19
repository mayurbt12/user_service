"""FastAPI REST API server for User Management Service.

This module provides HTTP endpoints for user management and authentication.
Designed for frontend/external application access.
"""

from fastapi import FastAPI, Depends, HTTPException, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta, datetime, timezone
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import crud
import schemas
import database
from config import settings
from shared_libs.auth import JWTHandler, validate_password_strength, TokenBlacklist, PasswordHasher
from database import RoleEnum, get_pool_stats, check_database_connection
from security_middleware import configure_security_middleware
from logger_config import setup_logger
from request_middleware import configure_request_middleware
from diagnostics import get_request_id

logger = setup_logger(__name__, 'api.log')

# Create rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI application
app = FastAPI(
    title="User Management Service API",
    description="Secure user management with JWT authentication and role-based access control",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allow your frontend origin
origins = [
    "http://localhost:1800",      # OneCall frontend (default)
    "http://localhost:3000",      # Alternative frontend port
    "http://3.6.152.132:3000",    # Public IP for your frontend
    "http://3.6.152.132:1800",    # Public IP for OneCall frontend
]

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Frontend origin
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Specific methods
    allow_headers=["Content-Type", "Authorization", "Accept"],  # Specific headers
)

# Configure security middleware (headers and request size limits)
configure_security_middleware(app)

# Configure request tracing middleware (timing and correlation IDs)
configure_request_middleware(app)

# Security scheme
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(database.get_db)
) -> database.User:
    """Dependency to get current authenticated user from JWT token.

    Args:
        credentials: Bearer token from Authorization header
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials

    # Check if token is blacklisted
    if TokenBlacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked"
        )

    # Verify token
    payload = JWTHandler.verify_token(token, token_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    # Get user from database
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


def require_role(allowed_roles: list[str]):
    """Dependency factory for role-based access control.

    Args:
        allowed_roles: List of allowed role names

    Returns:
        Dependency function
    """
    def check_role(current_user: database.User = Depends(get_current_user)):
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {allowed_roles}"
            )
        return current_user
    return check_role


@app.get("/")
def root():
    """Root endpoint - service information"""
    return {
        "service": "User Management Service API",
        "version": "1.0.0",
        "status": "healthy",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "auth": "/auth/*",
            "users": "/users/*"
        }
    }


@app.get("/health")
def health_check():
    """Liveness probe - basic health check for monitoring."""
    return {
        "status": "healthy",
        "service": "user_management_service",
        "database": settings.DATABASE_URL.split("://")[0]
    }


@app.get("/health/detailed")
def detailed_health_check():
    """Readiness probe - detailed health check with diagnostics.

    Returns comprehensive health information including:
    - Database connectivity and latency
    - Connection pool statistics (Saturation signal)
    - Service configuration thresholds
    """
    # Check database connection
    db_connected, db_latency_ms, db_error = check_database_connection()

    # Get pool statistics
    pool_stats = get_pool_stats()

    # Determine overall status
    status = "healthy" if db_connected else "degraded"

    return {
        "status": status,
        "service": "user_management_service",
        "request_id": get_request_id(),
        "database": {
            "connected": db_connected,
            "latency_ms": round(db_latency_ms, 2),
            "error": db_error,
            "type": settings.DATABASE_URL.split("://")[0]
        },
        "connection_pool": pool_stats.to_dict(),
        "thresholds": {
            "slow_query_ms": settings.SLOW_QUERY_THRESHOLD_MS,
            "slow_request_ms": settings.SLOW_REQUEST_THRESHOLD_MS
        }
    }


# Authentication Endpoints

@app.post("/auth/register", response_model=schemas.UserResponse, status_code=201)
@limiter.limit("30/hour")  # Max 30 registrations per hour per IP
def register_user(
    request: Request,
    user_data: schemas.UserCreate,
    db: Session = Depends(database.get_db)
):
    """Register a new user.

    Request body example:
    ```json
    {
        "mobile": "+1234567890",
        "password": "SecurePass@123",
        "profile": {"first_name": "John", "last_name": "Doe"}
    }
    ```
    """
    try:
        # Validate password strength
        is_valid, error_msg = validate_password_strength(user_data.password)
        if not is_valid:
            logger.warning(f"Registration failed: weak password for mobile={user_data.mobile}")
            raise HTTPException(status_code=400, detail=error_msg)

        # Create user
        user = crud.create_user(
            db,
            mobile=user_data.mobile,
            password=user_data.password,
            profile=user_data.profile,
            role=user_data.role,
            organization_id=user_data.organization_id,
            organization_role=user_data.organization_role
        )
        logger.info(f"User registered: mobile={user_data.mobile}, role={user_data.role}")
        return user

    except ValueError as e:
        logger.warning(f"Registration failed: mobile={user_data.mobile}, error={str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: mobile={user_data.mobile}, error={str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")


@app.post("/auth/login", response_model=schemas.TokenResponse)
@limiter.limit("5/minute")  # Max 5 login attempts per minute per IP
def login(
    request: Request,
    credentials: schemas.UserLogin,
    db: Session = Depends(database.get_db)
):
    """Authenticate user and return JWT tokens.

    Request body example:
    ```json
    {
        "mobile": "+1234567890",
        "password": "SecurePass@123"
    }
    ```
    """
    # Authenticate user
    user = crud.authenticate_user(db, credentials.mobile, credentials.password)
    if not user:
        logger.warning(f"Login failed: mobile={credentials.mobile} (invalid credentials)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Update last login
    crud.update_last_login(db, user.id)
    logger.info(f"Login successful: user_id={user.id}, mobile={user.mobile}")

    # Get organization info from UserOrganization table (or fallback to deprecated fields)
    org_id = user.get_default_organization_id(db)
    org_role = user.get_default_organization_role(db)

    # Create access token
    access_token_data = {
        "user_id": user.id,
        "mobile": user.mobile,
        "role": user.role.value,
        "organization_id": org_id,
        "organization_role": org_role.value if org_role else None
    }
    access_token = JWTHandler.create_access_token(access_token_data)

    # Create refresh token
    refresh_token_data = {"user_id": user.id}
    refresh_token = JWTHandler.create_refresh_token(refresh_token_data)

    # Save refresh token to database
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    crud.save_refresh_token(db, user.id, refresh_token, expires_at)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@app.post("/auth/refresh", response_model=schemas.TokenResponse)
@limiter.limit("10/minute")  # Max 10 refresh attempts per minute per IP
def refresh_token(
    request: Request,
    token_request: schemas.RefreshTokenRequest,
    db: Session = Depends(database.get_db)
):
    """Refresh access token using refresh token.

    Request body example:
    ```json
    {
        "refresh_token": "eyJhbGc..."
    }
    ```
    """
    # Verify refresh token
    payload = JWTHandler.verify_token(token_request.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    # Check if token exists and is not revoked
    db_token = crud.get_refresh_token(db, token_request.refresh_token)
    if not db_token or db_token.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked"
        )

    # Check if token is expired
    if db_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )

    user_id = payload.get("user_id")
    user = crud.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Create new access token
    access_token_data = {
        "user_id": user.id,
        "mobile": user.mobile,
        "role": user.role.value,
        "organization_id": user.organization_id,
        "organization_role": user.organization_role.value
    }
    access_token = JWTHandler.create_access_token(access_token_data)

    return {
        "access_token": access_token,
        "refresh_token": token_request.refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@app.post("/auth/logout", response_model=schemas.MessageResponse)
def logout(
    request: Request,
    token_request: schemas.RefreshTokenRequest,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Logout user by revoking both access and refresh tokens.

    Request body example:
    ```json
    {
        "refresh_token": "eyJhbGc..."
    }
    ```
    """
    # Blacklist the access token (from Authorization header)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.split(" ", 1)[1]
        # Add access token to blacklist with remaining TTL
        TokenBlacklist.add_token(access_token, expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    # Revoke the refresh token (from database)
    success = crud.revoke_refresh_token(db, token_request.refresh_token)
    if not success:
        raise HTTPException(status_code=404, detail="Refresh token not found")

    # Also blacklist the refresh token
    TokenBlacklist.add_token(token_request.refresh_token, expires_in_seconds=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600)

    logger.info(f"User logged out: user_id={current_user.id}")
    return {
        "message": "Logged out successfully",
        "success": True
    }


@app.post("/auth/verify-password", response_model=schemas.MessageResponse)
def verify_password(
    password_data: schemas.PasswordVerification,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Verify current user's password.

    Used by frontend before performing sensitive operations.

    Request body example:
    ```json
    {
        "password": "YourPassword@123"
    }
    ```
    """
    if not PasswordHasher.verify_password(password_data.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )

    return {
        "message": "Password verified successfully",
        "success": True
    }


# User Profile Endpoints

@app.get("/users/me", response_model=schemas.UserResponse)
def get_current_user_profile(
    current_user: database.User = Depends(get_current_user)
):
    """Get current user's profile."""
    return current_user


@app.put("/users/me", response_model=schemas.UserResponse)
def update_current_user_profile(
    updates: schemas.UserUpdate,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Update current user's profile.

    Request body example:
    ```json
    {
        "profile": {"first_name": "Jane", "last_name": "Smith"}
    }
    ```
    """
    try:
        update_dict = updates.model_dump(exclude_unset=True)
        user = crud.update_user(db, current_user.id, update_dict)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating profile: {str(e)}")


@app.put("/users/me/password", response_model=schemas.MessageResponse)
def change_current_user_password(
    password_data: schemas.PasswordChange,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Change current user's password.

    Request body example:
    ```json
    {
        "current_password": "OldPass@123",
        "new_password": "NewPass@456"
    }
    ```
    """
    # Validate new password strength
    is_valid, error_msg = validate_password_strength(password_data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    success, error = crud.change_password(
        db,
        current_user.id,
        password_data.current_password,
        password_data.new_password
    )

    if not success:
        logger.warning(f"Password change failed: user_id={current_user.id}")
        raise HTTPException(status_code=400, detail=error)

    # Revoke all existing refresh tokens for security
    crud.revoke_all_user_tokens(db, current_user.id)

    logger.info(f"Password changed: user_id={current_user.id}")
    return {
        "message": "Password changed successfully. Please login again.",
        "success": True
    }


# User Management Endpoints (Admin/Moderator)

@app.get("/users", response_model=schemas.UserListResponse)
def list_all_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """List users with organization filtering.

    System admins see all users.
    Organization owners/members see only their organization's users.

    Query parameters:
    - role: Optional role filter (guest, user, moderator, manager, system_admin)
    - is_active: Optional active status filter (true/false)
    - page: Page number (default: 1)
    - page_size: Users per page (default: 50, max: 100)
    """
    if page_size > 100:
        page_size = 100

    # Determine organization filter
    organization_filter = None
    if current_user.role != database.RoleEnum.SYSTEM_ADMIN:
        # Non-system-admins can only see their organization's users
        organization_filter = current_user.get_default_organization_id(db)

    users, total = crud.list_users(
        db,
        role=role,
        is_active=is_active,
        organization_id=organization_filter,
        page=page,
        page_size=page_size
    )

    return {
        "users": users,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@app.get("/users/{user_id}", response_model=schemas.UserResponse)
def get_user_by_id(
    user_id: str,
    db: Session = Depends(database.get_db)
):
    """Get user by ID (system_admin/manager/moderator/admin only)."""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/users/mobile/{mobile}", response_model=schemas.UserResponse)
def get_user_by_mobile_number(
    mobile: str,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get user by mobile number (authenticated service-to-service call).

    This endpoint is used for service-to-service communication.
    Requires a valid JWT token (typically from a service account).

    Args:
        mobile: User's mobile number to lookup

    Returns:
        User object if found

    Raises:
        404: User not found
    """
    user = crud.get_user_by_mobile(db, mobile)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with mobile {mobile} not found")
    return user


@app.put("/users/{user_id}/role", response_model=schemas.UserResponse)
def update_user_role(
    user_id: str,
    role_data: schemas.RoleUpdate,
    db: Session = Depends(database.get_db)
):
    """Update user role (system_admin/manager/admin only).

    Request body example:
    ```json
    {
        "role": "moderator"
    }
    ```
    """
    try:
        user = crud.update_user_role(db, user_id, role_data.role)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating role: {str(e)}")


@app.delete("/users/{user_id}", response_model=schemas.MessageResponse)
def delete_user(
    user_id: str,
    delete_request: schemas.UserDeleteRequest = None,
    current_user: database.User = Depends(require_role(["system_admin"])),
    db: Session = Depends(database.get_db)
):
    """Delete user (system_admin only) - password optional for service calls.

    Request body example (for direct calls):
    ```json
    {
        "admin_password": "YourAdminPassword@123"
    }
    ```

    For service-to-service calls, password can be omitted if already verified.
    """
    # Prevent system_admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Verify admin's password if provided
    if delete_request and delete_request.admin_password:
        if not PasswordHasher.verify_password(delete_request.admin_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password. Please enter your password to confirm deletion."
            )

    success, error = crud.delete_user(db, user_id)
    if not success:
        logger.warning(f"User deletion failed: target_id={user_id}, error={error}")
        raise HTTPException(status_code=400, detail=error)

    logger.info(f"User deleted: target_id={user_id}, by_admin={current_user.id}")
    return {
        "message": f"User {user_id} deleted successfully",
        "success": True
    }


@app.put("/users/{user_id}/deactivate", response_model=schemas.MessageResponse)
def deactivate_user(
    user_id: str,
    current_user: database.User = Depends(require_role(["system_admin"])),
    db: Session = Depends(database.get_db)
):
    """Deactivate user account (system_admin only)."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    success = crud.deactivate_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    # Revoke all user's refresh tokens
    crud.revoke_all_user_tokens(db, user_id)

    logger.info(f"User deactivated: target_id={user_id}, by_admin={current_user.id}")
    return {
        "message": f"User {user_id} deactivated successfully",
        "success": True
    }


@app.put("/users/{user_id}/activate", response_model=schemas.MessageResponse)
def activate_user(
    user_id: str,
    db: Session = Depends(database.get_db)
):
    """Activate user account (system_admin only)."""
    success = crud.activate_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(f"User activated: target_id={user_id}")
    return {
        "message": f"User {user_id} activated successfully",
        "success": True
    }


@app.put("/users/{user_id}/password", response_model=schemas.MessageResponse)
def admin_reset_user_password(
    user_id: str,
    password_data: schemas.AdminPasswordReset,
    current_user: database.User = Depends(require_role(["system_admin"])),
    db: Session = Depends(database.get_db)
):
    """Reset user password (system_admin only).

    Request body example:
    ```json
    {
        "new_password": "NewSecurePass@123"
    }
    ```
    """
    # Prevent admin from resetting their own password via this endpoint
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot reset your own password. Use /users/me/password instead"
        )

    # Validate password strength
    is_valid, error_msg = validate_password_strength(password_data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    success, error = crud.admin_reset_password(
        db,
        user_id,
        password_data.new_password
    )

    if not success:
        raise HTTPException(status_code=404, detail=error)

    # Revoke all user's refresh tokens for security
    crud.revoke_all_user_tokens(db, user_id)

    logger.info(f"Admin password reset: target_id={user_id}, by_admin={current_user.id}")
    return {
        "message": f"Password reset successfully for user {user_id}. User must login with new password.",
        "success": True
    }


# Statistics Endpoint

@app.get("/users/stats/overview")
def get_user_statistics(
    db: Session = Depends(database.get_db)
):
    """Get user statistics (system_admin/manager/moderator/admin only)."""
    total = crud.get_users_count(db)

    active_users, _ = crud.list_users(db, is_active=True, page=1, page_size=10000)
    inactive_users, _ = crud.list_users(db, is_active=False, page=1, page_size=10000)

    system_admins, _ = crud.list_users(db, role="system_admin", page=1, page_size=10000)
    managers, _ = crud.list_users(db, role="manager", page=1, page_size=10000)
    moderators, _ = crud.list_users(db, role="moderator", page=1, page_size=10000)
    users, _ = crud.list_users(db, role="user", page=1, page_size=10000)
    guests, _ = crud.list_users(db, role="guest", page=1, page_size=10000)

    return {
        "total_users": total,
        "active_users": len(active_users),
        "inactive_users": len(inactive_users),
        "by_role": {
            "system_admin": len(system_admins),
            "manager": len(managers),
            "moderator": len(moderators),
            "user": len(users),
            "guest": len(guests)
        }
    }


# ============================================================================
# ORGANIZATION ENDPOINTS
# ============================================================================

@app.post("/organizations", response_model=schemas.OrganizationResponse, status_code=201)
def create_organization_endpoint(
    org_data: schemas.OrganizationCreate,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Create a new organization (system_admin only).

    Request body example:
    ```json
    {
        "name": "Acme Corporation",
        "description": "Our company organization",
        "owner_user_id": "abc-123-def-456"
    }
    ```
    """
    # Only system_admin can manually create organizations
    if current_user.role != database.RoleEnum.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only system administrators can create organizations"
        )

    try:
        org = crud.create_organization(
            db,
            name=org_data.name,
            owner_user_id=org_data.owner_user_id,
            description=org_data.description
        )
        return org

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating organization: {str(e)}")


@app.get("/organizations/{org_id}", response_model=schemas.OrganizationResponse)
def get_organization_endpoint(
    org_id: int,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get organization details.

    Accessible by:
    - Organization owner
    - Organization members
    - System administrators
    """
    org = crud.get_organization_by_id(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check access permissions
    if current_user.role != database.RoleEnum.SYSTEM_ADMIN:
        if current_user.organization_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this organization"
            )

    return org


@app.put("/organizations/{org_id}", response_model=schemas.OrganizationResponse)
def update_organization_endpoint(
    org_id: int,
    org_data: schemas.OrganizationUpdate,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Update organization details.

    Accessible by:
    - Organization owner
    - System administrators

    Request body example:
    ```json
    {
        "name": "Updated Name",
        "description": "Updated description"
    }
    ```
    """
    org = crud.get_organization_by_id(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check access permissions
    is_owner = (current_user.organization_id == org_id and
                current_user.organization_role == database.OrganizationRoleEnum.OWNER)
    is_system_admin = current_user.role == database.RoleEnum.SYSTEM_ADMIN

    if not (is_owner or is_system_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owner or system admin can update organization"
        )

    try:
        updates = org_data.model_dump(exclude_unset=True)
        updated_org = crud.update_organization(db, org_id, updates)
        return updated_org

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating organization: {str(e)}")


@app.post("/organizations/{org_id}/members", response_model=schemas.UserResponse, status_code=201)
def add_team_member_endpoint(
    org_id: int,
    member_data: schemas.AddTeamMemberRequest,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Add a team member to an organization.

    Only organization owner can add team members.

    Request body example:
    ```json
    {
        "mobile": "+1234567890",
        "password": "SecurePass@123",
        "profile": {"first_name": "John", "last_name": "Doe"},
        "role": "user"
    }
    ```
    """
    org = crud.get_organization_by_id(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Only organization owner can add team members
    is_owner = (current_user.organization_id == org_id and
                current_user.organization_role == database.OrganizationRoleEnum.OWNER)

    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owner can add team members"
        )

    try:
        # Validate password strength
        is_valid, error_msg = validate_password_strength(member_data.password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # Add team member
        user = crud.add_team_member_to_organization(
            db,
            org_id=org_id,
            mobile=member_data.mobile,
            password=member_data.password,
            profile=member_data.profile,
            role=member_data.role or "user"
        )
        return user

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding team member: {str(e)}")


@app.get("/organizations/{org_id}/members", response_model=schemas.UserListResponse)
def list_team_members_endpoint(
    org_id: int,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """List all members of an organization.

    Accessible by:
    - Organization owner
    - Organization members
    - System administrators
    """
    org = crud.get_organization_by_id(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check access permissions
    if current_user.role != database.RoleEnum.SYSTEM_ADMIN:
        if current_user.organization_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this organization"
            )

    try:
        members = crud.list_organization_members(db, org_id)
        return {
            "users": members,
            "total": len(members),
            "page": 1,
            "page_size": len(members)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing team members: {str(e)}")


@app.delete("/organizations/{org_id}/members/{user_id}", response_model=schemas.MessageResponse)
def remove_team_member_endpoint(
    org_id: int,
    user_id: str,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Remove a team member from an organization.

    Only organization owner can remove team members.
    Cannot remove the organization owner.
    """
    org = crud.get_organization_by_id(db, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Only organization owner can remove team members
    is_owner = (current_user.organization_id == org_id and
                current_user.organization_role == database.OrganizationRoleEnum.OWNER)

    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owner can remove team members"
        )

    try:
        success, error_msg = crud.remove_team_member_from_organization(db, org_id, user_id)
        if not success:
            raise HTTPException(status_code=400, detail=error_msg)

        return {"message": "Team member removed successfully", "success": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing team member: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info"
    )
