#!/usr/bin/env python3
"""Database migration script to rename 'admin' role to 'system_admin'.

This script updates all existing users with role='admin' to role='system_admin'.
This is a one-time migration needed when introducing the new role system.

Usage:
    python3 migrate_admin_to_system_admin.py
"""

import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import settings


def migrate_roles():
    """Migrate admin roles to system_admin."""

    print("=" * 60)
    print("Database Migration: admin → system_admin")
    print("=" * 60)

    # Create engine and session
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Count current admin users (check both lowercase and uppercase)
        result = db.execute(text("SELECT COUNT(*) FROM users WHERE role IN ('admin', 'ADMIN')"))
        admin_count = result.scalar()

        print(f"\nFound {admin_count} user(s) with role='admin' or 'ADMIN'")

        if admin_count == 0:
            print("\nNo users with 'admin' role found. Nothing to migrate.")
            print("✓ Migration completed successfully!\n")
            return True

        # Confirm migration
        print(f"\nThis will update {admin_count} user(s) from role='admin'/'ADMIN' to role='SYSTEM_ADMIN'")
        confirm = input("Continue with migration? (yes/no): ").strip().lower()

        if confirm not in ['yes', 'y']:
            print("\nMigration cancelled by user.")
            return False

        # Perform migration (update both lowercase and uppercase)
        print("\nMigrating roles...")
        db.execute(text("UPDATE users SET role = 'SYSTEM_ADMIN' WHERE role IN ('admin', 'ADMIN')"))
        db.commit()

        # Verify migration
        result = db.execute(text("SELECT COUNT(*) FROM users WHERE role IN ('system_admin', 'SYSTEM_ADMIN')"))
        system_admin_count = result.scalar()

        result = db.execute(text("SELECT COUNT(*) FROM users WHERE role IN ('admin', 'ADMIN')"))
        remaining_admin = result.scalar()

        print(f"\n✓ Migration completed successfully!")
        print(f"  - Users with 'system_admin' role: {system_admin_count}")
        print(f"  - Users with 'admin' role remaining: {remaining_admin}")

        if remaining_admin > 0:
            print(f"\n⚠ WARNING: {remaining_admin} user(s) still have 'admin' role!")
            return False

        print("\n" + "=" * 60)
        print("All admin users successfully migrated to system_admin!")
        print("=" * 60 + "\n")

        return True

    except Exception as e:
        print(f"\n✗ Error during migration: {str(e)}")
        db.rollback()
        return False

    finally:
        db.close()


def verify_migration():
    """Verify migration was successful."""

    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check all roles
        result = db.execute(text("""
            SELECT role, COUNT(*) as count
            FROM users
            GROUP BY role
            ORDER BY role
        """))

        print("\nCurrent Role Distribution:")
        print("-" * 40)
        for row in result:
            print(f"  {row[0]:<20} : {row[1]:>3} user(s)")
        print("-" * 40 + "\n")

    except Exception as e:
        print(f"Error verifying migration: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("User Service - Role Migration Script")
    print("=" * 60 + "\n")

    success = migrate_roles()

    if success:
        verify_migration()
        sys.exit(0)
    else:
        print("\nMigration failed or was cancelled.\n")
        sys.exit(1)
