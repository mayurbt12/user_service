#!/usr/bin/env python3
"""Create a manager user for the system."""

import sys
import crud
import database
from auth import validate_password_strength


def create_manager_user(mobile, password, first_name="Manager", last_name="User"):
    """Create a manager user"""
    # Validate password strength
    is_valid, error = validate_password_strength(password)
    if not is_valid:
        print(f"❌ Password validation failed: {error}")
        return False

    # Get database session
    db = database.SessionLocal()

    try:
        # Check if user already exists
        existing = crud.get_user_by_mobile(db, mobile)
        if existing:
            print(f"❌ User with mobile {mobile} already exists")
            print(f"   Current role: {existing.role.value}")

            # Offer to upgrade to manager
            response = input(f"\nWould you like to upgrade this user to manager? (yes/no): ")
            if response.lower() in ['yes', 'y']:
                updated = crud.update_user_role(db, existing.id, "manager")
                if updated:
                    print(f"✅ User {mobile} upgraded to manager role")
                    return True
            return False

        # Create new manager user
        profile = {
            "first_name": first_name,
            "last_name": last_name
        }

        user = crud.create_user(db, mobile, password, profile, role="manager")

        print("=" * 70)
        print("✅ MANAGER USER CREATED SUCCESSFULLY!")
        print("=" * 70)
        print(f"Mobile: {user.mobile}")
        print(f"Role: {user.role.value}")
        print(f"Name: {first_name} {last_name}")
        print(f"User ID: {user.id}")
        print("=" * 70)
        print("\n📱 Login Credentials:")
        print(f"   Mobile: {mobile}")
        print(f"   Password: {password}")
        print("=" * 70)
        print("\n✓ Manager Access:")
        print("  - User Management (view, create, edit, change roles)")
        print("  - Agent Management (full CRUD access)")
        print("\n✗ No Access To:")
        print("  - Dashboard")
        print("  - Voice Calling")
        print("  - Outgoing Calls")
        print("  - User Deletion/Deactivation")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"❌ Error creating manager user: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("CREATE MANAGER USER")
    print("=" * 70)

    # Get user input
    if len(sys.argv) >= 3:
        mobile = sys.argv[1]
        password = sys.argv[2]
        first_name = sys.argv[3] if len(sys.argv) > 3 else "Manager"
        last_name = sys.argv[4] if len(sys.argv) > 4 else "User"
    else:
        print("\nEnter manager user details:")
        mobile = input("Mobile number (E.164 format, e.g., +1234567890): ").strip()
        password = input("Password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special): ").strip()
        first_name = input("First name (default: Manager): ").strip() or "Manager"
        last_name = input("Last name (default: User): ").strip() or "User"

    create_manager_user(mobile, password, first_name, last_name)
