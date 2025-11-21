#!/usr/bin/env python3
"""Reset password for service account."""

import sys
import crud
import database
from auth import validate_password_strength, PasswordHasher


def reset_service_password(mobile, new_password):
    """Reset password for service account"""
    # Validate password strength
    is_valid, error = validate_password_strength(new_password)
    if not is_valid:
        print(f"❌ Password validation failed: {error}")
        return False

    # Get database session
    db = database.SessionLocal()

    try:
        # Check if user exists
        existing = crud.get_user_by_mobile(db, mobile)
        if not existing:
            print(f"❌ User with mobile {mobile} not found")
            return False

        print(f"Found user: {mobile}")
        print(f"Current role: {existing.role.value}")
        print(f"User ID: {existing.id}")

        # Hash the new password
        print("\n⚙️  Resetting password...")
        password_hash = PasswordHasher.hash_password(new_password)

        # Update password in database
        existing.password_hash = password_hash
        db.commit()
        db.refresh(existing)

        print("\n" + "=" * 70)
        print("✅ PASSWORD RESET SUCCESSFULLY!")
        print("=" * 70)
        print(f"Mobile: {existing.mobile}")
        print(f"Role: {existing.role.value}")
        print("=" * 70)
        print("\n📱 New Credentials:")
        print(f"   Mobile: {mobile}")
        print(f"   Password: {new_password}")
        print("=" * 70)
        print("\n⚠️  Remember to update environment variables:")
        print(f"   export SERVICE_ACCOUNT_MOBILE='{mobile}'")
        print(f"   export SERVICE_ACCOUNT_PASSWORD='{new_password}'")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"❌ Error resetting password: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 reset_service_password.py <mobile_number> <new_password>")
        print("Example: python3 reset_service_password.py +919999999999 'ServicePass@123'")
        sys.exit(1)

    mobile = sys.argv[1]
    new_password = sys.argv[2]

    success = reset_service_password(mobile, new_password)

    if success:
        print("\n🎉 Password reset complete!")
        print("The service account is ready for authentication.")
    else:
        sys.exit(1)
