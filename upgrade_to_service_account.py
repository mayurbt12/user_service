#!/usr/bin/env python3
"""Upgrade an existing user to system_admin role for service account."""

import sys
import crud
import database


def upgrade_to_service_account(mobile):
    """Upgrade an existing user to system_admin role"""
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
        print(f"Name: {existing.profile.get('first_name', 'N/A')} {existing.profile.get('last_name', 'N/A')}")

        # Upgrade to system_admin
        print("\n⚙️  Upgrading to system_admin role...")
        updated = crud.update_user_role(db, existing.id, "system_admin")

        if updated:
            print("\n" + "=" * 70)
            print("✅ USER UPGRADED TO SERVICE ACCOUNT SUCCESSFULLY!")
            print("=" * 70)
            print(f"Mobile: {updated.mobile}")
            print(f"New Role: {updated.role.value}")
            print(f"User ID: {updated.id}")
            print("=" * 70)
            print("\n✓ Service Account Access:")
            print("  - Full system access for service-to-service authentication")
            print("  - Can query all user data")
            print("  - Can access all agent configurations")
            print("=" * 70)
            return True
        else:
            print("❌ Failed to upgrade user role")
            return False

    except Exception as e:
        print(f"❌ Error upgrading user: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 upgrade_to_service_account.py <mobile_number>")
        print("Example: python3 upgrade_to_service_account.py +919999999999")
        sys.exit(1)

    mobile = sys.argv[1]
    success = upgrade_to_service_account(mobile)

    if success:
        print("\n🎉 Service account is ready!")
        print("The existing credentials can now be used for service-to-service authentication.")
    else:
        sys.exit(1)
