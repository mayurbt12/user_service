"""MCP Server for User Management Service.

This module provides MCP tools for AI agents to manage users.
Uses the same database as the REST API for data consistency.

Transport Support:
- stdio: Standard input/output (local process communication)
- sse: Server-Sent Events over HTTP (network access, scalable)
"""

from mcp.server.fastmcp import FastMCP
from datetime import datetime, timezone
import os
import crud
import database
from config import settings
from auth import validate_password_strength

# Create FastMCP server with host and port from settings
mcp = FastMCP(
    "UserManagementService",
    host=settings.MCP_HOST,
    port=settings.MCP_PORT
)


@mcp.tool()
def register_user(
    mobile: str,
    password: str,
    first_name: str = None,
    last_name: str = None,
    role: str = "user"
) -> str:
    """Register a new user in the system.

    Args:
        mobile: User's mobile number (E.164 format, e.g., "+1234567890")
        password: User password (min 8 chars, must include uppercase, lowercase, digit, special char)
        first_name: Optional first name
        last_name: Optional last name
        role: User role - "guest", "user", "moderator", or "admin" (default: "user")

    Returns:
        Success message with user details or error message
    """
    db = database.SessionLocal()
    try:
        # Validate password strength
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            return f"✗ Password validation failed: {error_msg}"

        # Build profile
        profile = {}
        if first_name:
            profile["first_name"] = first_name
        if last_name:
            profile["last_name"] = last_name

        # Create user
        user = crud.create_user(db, mobile, password, profile, role)

        name = ""
        if first_name or last_name:
            name = f"\nName: {first_name or ''} {last_name or ''}".strip()

        return (
            f"✓ User registered successfully!\n"
            f"ID: {user.id}\n"
            f"Mobile: {user.mobile}{name}\n"
            f"Role: {user.role.value}\n"
            f"Created: {user.created_at.isoformat()}"
        )
    except ValueError as e:
        return f"✗ Registration failed: {str(e)}"
    except Exception as e:
        return f"✗ Error registering user: {str(e)}"
    finally:
        db.close()


@mcp.tool()
def authenticate_user(mobile: str, password: str) -> str:
    """Authenticate a user by mobile and password.

    Args:
        mobile: User's mobile number
        password: User password

    Returns:
        Success message with user details or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.authenticate_user(db, mobile, password)
        if not user:
            return "✗ Authentication failed: Invalid credentials or inactive account"

        # Update last login
        crud.update_last_login(db, user.id)

        return (
            f"✓ Authentication successful!\n"
            f"User ID: {user.id}\n"
            f"Mobile: {user.mobile}\n"
            f"Role: {user.role.value}\n"
            f"Active: {user.is_active}\n"
            f"Last Login: {user.last_login.isoformat() if user.last_login else 'First login'}"
        )
    finally:
        db.close()


@mcp.tool()
def get_user_profile(mobile: str) -> str:
    """Get detailed user profile information.

    Args:
        mobile: User's mobile number

    Returns:
        User profile details or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_mobile(db, mobile)
        if not user:
            return f"✗ User not found with mobile: {mobile}"

        profile_str = ""
        if user.profile:
            for key, value in user.profile.items():
                profile_str += f"\n  {key}: {value}"

        return (
            f"User Profile:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"ID: {user.id}\n"
            f"Mobile: {user.mobile}\n"
            f"Role: {user.role.value}\n"
            f"Active: {user.is_active}\n"
            f"Profile:{profile_str if profile_str else ' (empty)'}\n"
            f"Created: {user.created_at.isoformat()}\n"
            f"Updated: {user.updated_at.isoformat()}\n"
            f"Last Login: {user.last_login.isoformat() if user.last_login else 'Never'}"
        )
    finally:
        db.close()


@mcp.tool()
def update_user_profile(
    mobile: str,
    first_name: str = None,
    last_name: str = None,
    avatar_url: str = None
) -> str:
    """Update user profile information.

    Args:
        mobile: User's mobile number
        first_name: Optional updated first name
        last_name: Optional updated last name
        avatar_url: Optional avatar URL

    Returns:
        Success message with updated details or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_mobile(db, mobile)
        if not user:
            return f"✗ User not found with mobile: {mobile}"

        # Build profile updates
        profile = user.profile.copy()
        if first_name is not None:
            profile["first_name"] = first_name
        if last_name is not None:
            profile["last_name"] = last_name
        if avatar_url is not None:
            profile["avatar_url"] = avatar_url

        updates = {"profile": profile}
        updated_user = crud.update_user(db, user.id, updates)

        return (
            f"✓ Profile updated successfully!\n"
            f"Mobile: {updated_user.mobile}\n"
            f"Profile: {updated_user.profile}\n"
            f"Updated: {updated_user.updated_at.isoformat()}"
        )
    except Exception as e:
        return f"✗ Error updating profile: {str(e)}"
    finally:
        db.close()


@mcp.tool()
def list_users(
    role: str = None,
    is_active: bool = None,
    page: int = 1,
    page_size: int = 50
) -> str:
    """List users with optional filtering.

    Args:
        role: Optional role filter - "guest", "user", "moderator", or "admin"
        is_active: Optional active status filter (true/false)
        page: Page number (default: 1)
        page_size: Users per page (default: 50, max: 100)

    Returns:
        Formatted list of users or message if none found
    """
    db = database.SessionLocal()
    try:
        if page_size > 100:
            page_size = 100

        users, total = crud.list_users(db, role, is_active, page, page_size)

        if not users:
            filter_text = []
            if role:
                filter_text.append(f"role='{role}'")
            if is_active is not None:
                filter_text.append(f"active={is_active}")
            filter_str = " with " + ", ".join(filter_text) if filter_text else ""
            return f"No users found{filter_str}."

        result = [f"Found {len(users)} user(s) (Total: {total}, Page: {page}/{(total + page_size - 1) // page_size}):\n"]

        for user in users:
            name = ""
            if user.profile.get("first_name") or user.profile.get("last_name"):
                name = f" - {user.profile.get('first_name', '')} {user.profile.get('last_name', '')}".strip()

            status = "✓ Active" if user.is_active else "✗ Inactive"
            result.append(
                f"\n• [{user.role.value.upper()}] {user.mobile}{name}\n"
                f"  ID: {user.id}\n"
                f"  Status: {status}\n"
                f"  Created: {user.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"  Last Login: {user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never'}"
            )

        return "\n".join(result)
    finally:
        db.close()


@mcp.tool()
def change_user_role(mobile: str, new_role: str) -> str:
    """Change a user's role (admin operation).

    Args:
        mobile: User's mobile number
        new_role: New role to assign - "guest", "user", "moderator", or "admin"

    Returns:
        Success message or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_mobile(db, mobile)
        if not user:
            return f"✗ User not found with mobile: {mobile}"

        updated_user = crud.update_user_role(db, user.id, new_role)
        if not updated_user:
            return f"✗ Failed to update user role"

        return (
            f"✓ User role updated successfully!\n"
            f"Mobile: {updated_user.mobile}\n"
            f"Old Role: {user.role.value}\n"
            f"New Role: {updated_user.role.value}\n"
            f"Updated: {updated_user.updated_at.isoformat()}"
        )
    except Exception as e:
        return f"✗ Error updating role: {str(e)}"
    finally:
        db.close()


@mcp.tool()
def deactivate_user(mobile: str) -> str:
    """Deactivate a user account (admin operation).

    Args:
        mobile: User's mobile number

    Returns:
        Success or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_mobile(db, mobile)
        if not user:
            return f"✗ User not found with mobile: {mobile}"

        success = crud.deactivate_user(db, user.id)
        if success:
            # Revoke all user's refresh tokens
            count = crud.revoke_all_user_tokens(db, user.id)
            return (
                f"✓ User deactivated successfully!\n"
                f"Mobile: {mobile}\n"
                f"Revoked {count} refresh token(s)"
            )
        else:
            return f"✗ Failed to deactivate user"
    finally:
        db.close()


@mcp.tool()
def activate_user(mobile: str) -> str:
    """Activate a user account (admin operation).

    Args:
        mobile: User's mobile number

    Returns:
        Success or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_mobile(db, mobile)
        if not user:
            return f"✗ User not found with mobile: {mobile}"

        success = crud.activate_user(db, user.id)
        if success:
            return f"✓ User activated successfully!\nMobile: {mobile}"
        else:
            return f"✗ Failed to activate user"
    finally:
        db.close()


@mcp.tool()
def delete_user(mobile: str) -> str:
    """Delete a user account permanently (admin operation).

    Args:
        mobile: User's mobile number

    Returns:
        Success or error message
    """
    db = database.SessionLocal()
    try:
        user = crud.get_user_by_mobile(db, mobile)
        if not user:
            return f"✗ User not found with mobile: {mobile}"

        user_id = user.id
        success = crud.delete_user(db, user_id)
        if success:
            return f"✓ User {mobile} (ID: {user_id}) deleted permanently"
        else:
            return f"✗ Failed to delete user"
    finally:
        db.close()


@mcp.tool()
def search_users_by_role(role: str) -> str:
    """Search users by role.

    Args:
        role: Role to search for - "guest", "user", "moderator", or "admin"

    Returns:
        List of users with specified role
    """
    db = database.SessionLocal()
    try:
        users, total = crud.list_users(db, role=role, page=1, page_size=1000)

        if not users:
            return f"No users found with role '{role}'."

        result = [f"Found {total} user(s) with role '{role}':\n"]
        for user in users:
            status = "✓" if user.is_active else "✗"
            result.append(
                f"\n{status} {user.mobile}\n"
                f"  ID: {user.id}\n"
                f"  Active: {user.is_active}\n"
                f"  Created: {user.created_at.strftime('%Y-%m-%d')}"
            )

        return "\n".join(result)
    finally:
        db.close()


@mcp.tool()
def get_user_statistics() -> str:
    """Get overall user statistics.

    Returns:
        Statistical summary of user accounts
    """
    db = database.SessionLocal()
    try:
        total = crud.get_users_count(db)
        active_users, _ = crud.list_users(db, is_active=True, page=1, page_size=10000)
        inactive_users, _ = crud.list_users(db, is_active=False, page=1, page_size=10000)

        admins, _ = crud.list_users(db, role="admin", page=1, page_size=10000)
        moderators, _ = crud.list_users(db, role="moderator", page=1, page_size=10000)
        users, _ = crud.list_users(db, role="user", page=1, page_size=10000)
        guests, _ = crud.list_users(db, role="guest", page=1, page_size=10000)

        return (
            f"User Management Statistics:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Total Users: {total}\n"
            f"\n"
            f"By Status:\n"
            f"  • Active: {len(active_users)}\n"
            f"  • Inactive: {len(inactive_users)}\n"
            f"\n"
            f"By Role:\n"
            f"  • Admin: {len(admins)}\n"
            f"  • Moderator: {len(moderators)}\n"
            f"  • User: {len(users)}\n"
            f"  • Guest: {len(guests)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    # Get transport from environment or config
    transport = os.getenv("MCP_TRANSPORT", settings.MCP_TRANSPORT).lower()

    if transport == "sse":
        # Run MCP server with SSE transport for network access
        host = settings.MCP_HOST
        port = settings.MCP_PORT

        print(f"Starting MCP server with SSE transport on {host}:{port}")
        print(f"SSE endpoint: http://{host}:{port}/sse")

        mcp.run(transport="sse")
    else:
        # Run MCP server with stdio transport for local process communication
        print("Starting MCP server with stdio transport")
        mcp.run(transport="stdio")
