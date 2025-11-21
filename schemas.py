"""Pydantic schemas for User Management Service.

This module defines request and response schemas for API validation.
"""

from pydantic import BaseModel, Field, field_validator, field_serializer
from datetime import datetime
from typing import Optional, Dict


class UserCreate(BaseModel):
    """Schema for user registration."""

    mobile: str = Field(
        ...,
        pattern=r'^\+?[1-9]\d{1,14}$',
        description="User's mobile number (E.164 format, e.g., +1234567890)",
        examples=["+1234567890", "+919876543210"]
    )

    password: str = Field(
        ...,
        min_length=8,
        description="User password (min 8 chars, must include uppercase, lowercase, digit, special char)",
        examples=["SecurePass@123"]
    )

    profile: Optional[Dict] = Field(
        default_factory=dict,
        description="Optional user profile data (name, avatar, etc.)",
        examples=[{"first_name": "John", "last_name": "Doe"}]
    )


class UserLogin(BaseModel):
    """Schema for user login."""

    mobile: str = Field(
        ...,
        pattern=r'^\+?[1-9]\d{1,14}$',
        description="User's mobile number",
        examples=["+1234567890"]
    )

    password: str = Field(
        ...,
        description="User password",
        examples=["SecurePass@123"]
    )


class UserUpdate(BaseModel):
    """Schema for updating user profile.

    All fields are optional - only provided fields will be updated.
    """

    profile: Optional[Dict] = Field(
        None,
        description="Updated profile data"
    )


class PasswordChange(BaseModel):
    """Schema for password change."""

    current_password: str = Field(
        ...,
        description="Current password for verification"
    )

    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (min 8 chars, must include uppercase, lowercase, digit, special char)"
    )


class RoleUpdate(BaseModel):
    """Schema for updating user role (system_admin only)."""

    role: str = Field(
        ...,
        pattern="^(guest|user|moderator|manager|system_admin)$",
        description="New role: guest, user, moderator, manager, or system_admin"
    )


class TokenResponse(BaseModel):
    """Schema for authentication token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration time in seconds")


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str = Field(
        ...,
        description="Refresh token to exchange for new access token"
    )


class UserResponse(BaseModel):
    """Schema for user response.

    CRITICAL: datetime fields are datetime objects that get
    automatically serialized to ISO strings in JSON responses.
    Role field is automatically normalized to lowercase for frontend compatibility.
    """

    id: str = Field(..., description="Unique user ID")
    mobile: str = Field(..., description="User's mobile number")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether user account is active")
    profile: Dict = Field(..., description="User profile data")

    # CRITICAL: These are datetime objects
    created_at: datetime = Field(..., description="When user account was created")
    updated_at: datetime = Field(..., description="When user account was last updated")
    last_login: Optional[datetime] = Field(None, description="When user last logged in")

    @field_serializer('role')
    def normalize_role(self, role: str) -> str:
        """Normalize role to lowercase for frontend compatibility.

        Database may store roles as uppercase (MANAGER, SYSTEM_ADMIN), but
        frontend expects lowercase (manager, system_admin) for role checking.
        """
        return role.lower() if role else None

    class Config:
        """Pydantic configuration"""
        from_attributes = True  # Enable ORM mode for SQLAlchemy models
        json_schema_extra = {
            "example": {
                "id": "abc-123-def-456",
                "mobile": "+1234567890",
                "role": "user",
                "is_active": True,
                "profile": {"first_name": "John", "last_name": "Doe"},
                "created_at": "2025-10-26T10:30:00+00:00",
                "updated_at": "2025-10-26T10:30:00+00:00",
                "last_login": "2025-10-26T11:00:00+00:00"
            }
        }


class UserListResponse(BaseModel):
    """Schema for paginated user list response."""

    users: list[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of users per page")


class MessageResponse(BaseModel):
    """Schema for simple message responses."""

    message: str = Field(..., description="Response message")
    success: bool = Field(default=True, description="Whether operation was successful")
