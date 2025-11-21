"""FastAPI REST API server for User Management Service.

This module provides HTTP endpoints for user management and authentication.
Designed for frontend/external application access.
"""

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta, datetime, timezone

import crud
import schemas
import database
from config import settings
from auth import JWTHandler, validate_password_strength, TokenBlacklist
from database import RoleEnum

# Create FastAPI application
app = FastAPI(
    title="User Management Service API",
    description="Secure user management with JWT authentication and role-based access control",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

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
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "service": "user_management_service",
        "database": settings.DATABASE_URL.split("://")[0]
    }


# Authentication Endpoints

@app.post("/auth/register", response_model=schemas.UserResponse, status_code=201)
def register_user(
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
            raise HTTPException(status_code=400, detail=error_msg)

        # Create user
        user = crud.create_user(
            db,
            mobile=user_data.mobile,
            password=user_data.password,
            profile=user_data.profile
        )
        return user

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Update last login
    crud.update_last_login(db, user.id)

    # Create access token
    access_token_data = {
        "user_id": user.id,
        "mobile": user.mobile,
        "role": user.role.value
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
def refresh_token(
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
        "role": user.role.value
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
    token_request: schemas.RefreshTokenRequest,
    current_user: database.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Logout user by revoking refresh token.

    Request body example:
    ```json
    {
        "refresh_token": "eyJhbGc..."
    }
    ```
    """
    # Revoke the refresh token
    success = crud.revoke_refresh_token(db, token_request.refresh_token)
    if not success:
        raise HTTPException(status_code=404, detail="Refresh token not found")

    return {
        "message": "Logged out successfully",
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
        raise HTTPException(status_code=400, detail=error)

    # Revoke all existing refresh tokens for security
    crud.revoke_all_user_tokens(db, current_user.id)

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
    current_user: database.User = Depends(require_role(["system_admin", "manager", "moderator"]))
):
    """List all users (system_admin/manager/moderator only).

    Query parameters:
    - role: Optional role filter (guest, user, moderator, manager, system_admin)
    - is_active: Optional active status filter (true/false)
    - page: Page number (default: 1)
    - page_size: Users per page (default: 50, max: 100)
    """
    if page_size > 100:
        page_size = 100

    users, total = crud.list_users(
        database.SessionLocal(),
        role=role,
        is_active=is_active,
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
    current_user: database.User = Depends(require_role(["system_admin", "manager", "moderator"])),
    db: Session = Depends(database.get_db)
):
    """Get user by ID (system_admin/manager/moderator only)."""
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
    current_user: database.User = Depends(require_role(["system_admin", "manager"])),
    db: Session = Depends(database.get_db)
):
    """Update user role (system_admin/manager only).

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
    current_user: database.User = Depends(require_role(["system_admin"])),
    db: Session = Depends(database.get_db)
):
    """Delete user (system_admin only)."""
    # Prevent system_admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    success = crud.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

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

    return {
        "message": f"User {user_id} deactivated successfully",
        "success": True
    }


@app.put("/users/{user_id}/activate", response_model=schemas.MessageResponse)
def activate_user(
    user_id: str,
    current_user: database.User = Depends(require_role(["system_admin"])),
    db: Session = Depends(database.get_db)
):
    """Activate user account (system_admin only)."""
    success = crud.activate_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "message": f"User {user_id} activated successfully",
        "success": True
    }


# Statistics Endpoint

@app.get("/users/stats/overview")
def get_user_statistics(
    current_user: database.User = Depends(require_role(["system_admin", "manager", "moderator"])),
    db: Session = Depends(database.get_db)
):
    """Get user statistics (system_admin/manager/moderator only)."""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info"
    )
