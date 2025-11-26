#!/usr/bin/env python3
"""Create a service account for microservice-to-microservice authentication."""

import sys
import crud
import database
from shared_libs.auth import validate_password_strength


def create_service_account(mobile, password, first_name="Service", last_name="Account"):
    """Create a service account with SYSTEM_ADMIN role for service-to-service auth"""
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

            # Offer to upgrade to system_admin
            response = input(f"\nWould you like to upgrade this user to system_admin? (yes/no): ")
            if response.lower() in ['yes', 'y']:
                updated = crud.update_user_role(db, existing.id, "system_admin")
                if updated:
                    print(f"✅ User {mobile} upgraded to system_admin role")
                    return True
            return False

        # Create new service account with system_admin role
        profile = {
            "first_name": first_name,
            "last_name": last_name
        }

        user = crud.create_user(db, mobile, password, profile, role="system_admin")

        print("=" * 70)
        print("✅ SERVICE ACCOUNT CREATED SUCCESSFULLY!")
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
        print("\n✓ Service Account Access:")
        print("  - Full system access for service-to-service authentication")
        print("  - Can query all user data")
        print("  - Can access all agent configurations")
        print("  - Intended for backend microservices, not end users")
        print("=" * 70)
        print("\n⚠️  IMPORTANT:")
        print("  - Store these credentials securely in environment variables")
        print("  - Do NOT commit credentials to version control")
        print("  - Use for service-to-service authentication only")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"❌ Error creating service account: {e}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("CREATE SERVICE ACCOUNT FOR MICROSERVICE AUTHENTICATION")
    print("=" * 70)

    # Get user input
    if len(sys.argv) >= 3:
        mobile = sys.argv[1]
        password = sys.argv[2]
        first_name = sys.argv[3] if len(sys.argv) > 3 else "Service"
        last_name = sys.argv[4] if len(sys.argv) > 4 else "Account"
    else:
        print("\nEnter service account details:")
        mobile = input("Mobile number (E.164 format, e.g., +919999999999): ").strip()
        password = input("Password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special): ").strip()
        first_name = input("First name (default: Service): ").strip() or "Service"
        last_name = input("Last name (default: Account): ").strip() or "Account"

    success = create_service_account(mobile, password, first_name, last_name)

    if success:
        print("\n🎉 Next Steps:")
        print("1. Set environment variables in your shell or .env file:")
        print(f"   export SERVICE_ACCOUNT_MOBILE='{mobile}'")
        print(f"   export SERVICE_ACCOUNT_PASSWORD='{password}'")
        print("\n2. Restart your voice_mate service to use the new credentials")
