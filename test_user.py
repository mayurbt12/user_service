"""Comprehensive test script for User Management Service.

Tests CRUD operations, authentication, and role management.
"""

from datetime import datetime, timezone
import crud
import database
from shared_libs.auth import PasswordHasher, JWTHandler, validate_password_strength


def test_user_service():
    """Test user management operations"""
    print("=" * 70)
    print("Testing User Management Service - Comprehensive Test Suite")
    print("=" * 70)

    # Get database session
    db = database.SessionLocal()

    try:
        # Test 1: Password strength validation
        print("\n[1] Testing password strength validation...")
        is_valid, error = validate_password_strength("weakpass")
        assert not is_valid, "Weak password should fail validation"
        print(f"  ✓ Weak password rejected: {error}")

        is_valid, error = validate_password_strength("StrongPass@123")
        assert is_valid, "Strong password should pass validation"
        print("  ✓ Strong password accepted")

        # Test 2: Password hashing and verification
        print("\n[2] Testing password hashing...")
        password = "TestPassword@123"
        hashed = PasswordHasher.hash_password(password)
        print(f"  ✓ Password hashed successfully (length: {len(hashed)})")

        assert PasswordHasher.verify_password(password, hashed), "Password verification should succeed"
        print("  ✓ Password verification successful")

        assert not PasswordHasher.verify_password("WrongPass@123", hashed), "Wrong password should fail"
        print("  ✓ Wrong password correctly rejected")

        # Test 3: Create a user
        print("\n[3] Creating test users...")
        mobile1 = "+1234567890"
        password1 = "User1Pass@123"
        profile1 = {"first_name": "John", "last_name": "Doe"}

        user1 = crud.create_user(db, mobile1, password1, profile1, "user")
        print(f"  ✓ User 1 created: {user1.id}")
        print(f"    Mobile: {user1.mobile}")
        print(f"    Role: {user1.role.value}")
        print(f"    Profile: {user1.profile}")
        assert isinstance(user1.created_at, datetime), "created_at should be datetime object"

        # Create admin user
        mobile2 = "+9876543210"
        password2 = "Admin1Pass@456"
        profile2 = {"first_name": "Jane", "last_name": "Admin"}

        user2 = crud.create_user(db, mobile2, password2, profile2, "admin")
        print(f"  ✓ User 2 (Admin) created: {user2.id}")
        print(f"    Mobile: {user2.mobile}")
        print(f"    Role: {user2.role.value}")

        # Test 4: Get user by mobile
        print("\n[4] Testing get user by mobile...")
        fetched = crud.get_user_by_mobile(db, mobile1)
        assert fetched is not None, "User should be found"
        assert fetched.mobile == mobile1, "Mobile should match"
        print(f"  ✓ Retrieved user: {fetched.mobile}")

        # Test 5: Authenticate user
        print("\n[5] Testing user authentication...")
        auth_user = crud.authenticate_user(db, mobile1, password1)
        assert auth_user is not None, "Authentication should succeed"
        print(f"  ✓ Authentication successful for {auth_user.mobile}")

        wrong_auth = crud.authenticate_user(db, mobile1, "WrongPassword@123")
        assert wrong_auth is None, "Wrong password should fail authentication"
        print("  ✓ Wrong password correctly rejected")

        # Test 6: JWT token generation and validation
        print("\n[6] Testing JWT token operations...")
        token_data = {
            "user_id": user1.id,
            "mobile": user1.mobile,
            "role": user1.role.value
        }

        access_token = JWTHandler.create_access_token(token_data)
        print(f"  ✓ Access token created (length: {len(access_token)})")

        payload = JWTHandler.verify_token(access_token, "access")
        assert payload is not None, "Token verification should succeed"
        assert payload["user_id"] == user1.id, "User ID should match"
        assert payload["role"] == user1.role.value, "Role should match"
        print("  ✓ Access token verified successfully")

        refresh_token = JWTHandler.create_refresh_token({"user_id": user1.id})
        print(f"  ✓ Refresh token created (length: {len(refresh_token)})")

        refresh_payload = JWTHandler.verify_token(refresh_token, "refresh")
        assert refresh_payload is not None, "Refresh token verification should succeed"
        print("  ✓ Refresh token verified successfully")

        # Test 7: Update user profile
        print("\n[7] Testing user profile update...")
        updates = {"profile": {"first_name": "Johnny", "last_name": "Doe", "avatar": "http://example.com/avatar.jpg"}}
        updated_user = crud.update_user(db, user1.id, updates)
        assert updated_user is not None, "Update should succeed"
        assert updated_user.profile["first_name"] == "Johnny", "First name should be updated"
        print(f"  ✓ Profile updated: {updated_user.profile}")

        # Test 8: Change password
        print("\n[8] Testing password change...")
        new_password = "NewPassword@789"
        success, error = crud.change_password(db, user1.id, password1, new_password)
        assert success, f"Password change should succeed: {error}"
        print("  ✓ Password changed successfully")

        # Verify new password works
        auth_new = crud.authenticate_user(db, mobile1, new_password)
        assert auth_new is not None, "New password should work"
        print("  ✓ New password authentication successful")

        # Verify old password doesn't work
        auth_old = crud.authenticate_user(db, mobile1, password1)
        assert auth_old is None, "Old password should not work"
        print("  ✓ Old password correctly rejected")

        # Test 9: Update user role
        print("\n[9] Testing role update...")
        updated_role_user = crud.update_user_role(db, user1.id, "moderator")
        assert updated_role_user is not None, "Role update should succeed"
        assert updated_role_user.role.value == "moderator", "Role should be updated"
        print(f"  ✓ Role updated to: {updated_role_user.role.value}")

        # Test 10: List users
        print("\n[10] Testing list users...")
        all_users, total = crud.list_users(db, page=1, page_size=50)
        print(f"  ✓ Found {len(all_users)} users (Total: {total})")

        moderators, mod_count = crud.list_users(db, role="moderator", page=1, page_size=50)
        print(f"  ✓ Found {len(moderators)} moderator(s)")

        admins, admin_count = crud.list_users(db, role="admin", page=1, page_size=50)
        print(f"  ✓ Found {len(admins)} admin(s)")

        # Test 11: Deactivate user
        print("\n[11] Testing user deactivation...")
        success = crud.deactivate_user(db, user1.id)
        assert success, "Deactivation should succeed"
        print("  ✓ User deactivated successfully")

        # Verify deactivated user can't authenticate
        auth_inactive = crud.authenticate_user(db, mobile1, new_password)
        assert auth_inactive is None, "Deactivated user should not authenticate"
        print("  ✓ Deactivated user cannot authenticate")

        # Test 12: Activate user
        print("\n[12] Testing user activation...")
        success = crud.activate_user(db, user1.id)
        assert success, "Activation should succeed"
        print("  ✓ User activated successfully")

        # Verify activated user can authenticate
        auth_active = crud.authenticate_user(db, mobile1, new_password)
        assert auth_active is not None, "Activated user should authenticate"
        print("  ✓ Activated user can authenticate")

        # Test 13: Refresh token management
        print("\n[13] Testing refresh token management...")
        expires_at = datetime.now(timezone.utc)
        from datetime import timedelta
        expires_at += timedelta(days=7)

        saved_token = crud.save_refresh_token(db, user1.id, refresh_token, expires_at)
        assert saved_token is not None, "Token save should succeed"
        print(f"  ✓ Refresh token saved: {saved_token.id}")

        retrieved_token = crud.get_refresh_token(db, refresh_token)
        assert retrieved_token is not None, "Token retrieval should succeed"
        assert not retrieved_token.is_revoked, "Token should not be revoked"
        print("  ✓ Refresh token retrieved successfully")

        # Revoke token
        success = crud.revoke_refresh_token(db, refresh_token)
        assert success, "Token revocation should succeed"
        print("  ✓ Refresh token revoked")

        retrieved_revoked = crud.get_refresh_token(db, refresh_token)
        assert retrieved_revoked.is_revoked, "Token should be revoked"
        print("  ✓ Token revocation verified")

        # Test 14: Update last login
        print("\n[14] Testing last login update...")
        success = crud.update_last_login(db, user1.id)
        assert success, "Last login update should succeed"
        updated_user = crud.get_user_by_id(db, user1.id)
        assert updated_user.last_login is not None, "Last login should be set"
        assert isinstance(updated_user.last_login, datetime), "Last login should be datetime"
        print(f"  ✓ Last login updated: {updated_user.last_login.isoformat()}")

        # Test 15: Delete user
        print("\n[15] Testing user deletion...")
        success = crud.delete_user(db, user1.id)
        assert success, "Deletion should succeed"
        print(f"  ✓ User {user1.id} deleted successfully")

        # Verify user is deleted
        deleted_user = crud.get_user_by_id(db, user1.id)
        assert deleted_user is None, "User should be deleted"
        print("  ✓ Verified user deletion")

        # Clean up admin user
        crud.delete_user(db, user2.id)
        print(f"  ✓ Cleanup: Admin user {user2.id} deleted")

        print("\n" + "=" * 70)
        print("✓ All tests passed successfully!")
        print("✓ User Management Service is working correctly")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n✗ Test assertion failed: {str(e)}")
        raise
    except Exception as e:
        print(f"\n✗ Test failed with error: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    test_user_service()
