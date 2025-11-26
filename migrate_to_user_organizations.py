#!/usr/bin/env python3
"""Migration script to populate UserOrganization table from existing User data.

This script migrates existing organization memberships from the deprecated
User.organization_id and User.organization_role fields to the new
UserOrganization junction table.

Run this script once after updating the database schema.

Usage:
    python migrate_to_user_organizations.py [--dry-run]
"""

import sys
import argparse
import uuid
from datetime import datetime, timezone
from sqlalchemy import and_

# Import database models
from database import (
    SessionLocal,
    User,
    UserOrganization,
    Organization,
    OrganizationRoleEnum
)


def migrate_user_organizations(dry_run=False):
    """Migrate user organization data to UserOrganization table.

    Args:
        dry_run: If True, only show what would be done without making changes

    Returns:
        Tuple of (success_count, skip_count, error_count)
    """
    db = SessionLocal()
    success_count = 0
    skip_count = 0
    error_count = 0

    try:
        # Get all users with organization_id set
        users = db.query(User).filter(
            User.organization_id.isnot(None)
        ).all()

        print(f"\n{'DRY RUN: ' if dry_run else ''}Found {len(users)} users with organization assignments")
        print("=" * 80)

        for user in users:
            try:
                # Check if UserOrganization record already exists
                existing = db.query(UserOrganization).filter(
                    and_(
                        UserOrganization.user_id == user.id,
                        UserOrganization.organization_id == user.organization_id
                    )
                ).first()

                if existing:
                    print(f"SKIP: User {user.mobile} ({user.id[:8]}...) "
                          f"already has membership in org {user.organization_id}")
                    skip_count += 1
                    continue

                # Verify organization exists
                org = db.query(Organization).filter(
                    Organization.id == user.organization_id
                ).first()

                if not org:
                    print(f"ERROR: Organization {user.organization_id} not found for "
                          f"user {user.mobile} ({user.id[:8]}...)")
                    error_count += 1
                    continue

                # Determine organization role
                org_role = user.organization_role or OrganizationRoleEnum.MEMBER

                # Create UserOrganization record
                user_org = UserOrganization(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    organization_id=user.organization_id,
                    role=org_role,
                    is_active=user.is_active,  # Match user's active status
                    joined_at=user.created_at or datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )

                if not dry_run:
                    db.add(user_org)

                print(f"{'WOULD MIGRATE' if dry_run else 'MIGRATED'}: "
                      f"User {user.mobile} ({user.id[:8]}...) -> "
                      f"Org {org.name} (ID: {org.id}) as {org_role.value}")

                success_count += 1

            except Exception as e:
                print(f"ERROR processing user {user.mobile} ({user.id[:8]}...): {e}")
                error_count += 1
                continue

        if not dry_run:
            db.commit()
            print("\n" + "=" * 80)
            print("Migration committed to database")
        else:
            print("\n" + "=" * 80)
            print("DRY RUN - No changes made to database")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        db.rollback()
        return 0, 0, -1

    finally:
        db.close()

    return success_count, skip_count, error_count


def verify_migration():
    """Verify migration was successful."""
    db = SessionLocal()

    try:
        # Count users with organization_id
        users_with_org = db.query(User).filter(
            User.organization_id.isnot(None)
        ).count()

        # Count UserOrganization records
        user_org_count = db.query(UserOrganization).count()

        # Count active UserOrganization records
        active_user_org_count = db.query(UserOrganization).filter(
            UserOrganization.is_active == True
        ).count()

        print("\n" + "=" * 80)
        print("MIGRATION VERIFICATION")
        print("=" * 80)
        print(f"Users with organization_id:          {users_with_org}")
        print(f"Total UserOrganization records:      {user_org_count}")
        print(f"Active UserOrganization records:     {active_user_org_count}")

        if user_org_count >= users_with_org:
            print("\n✓ Migration appears successful!")
        else:
            print("\n⚠ Warning: Some users may not have been migrated")

        # Show sample of migrated data
        print("\n" + "-" * 80)
        print("Sample UserOrganization records:")
        print("-" * 80)

        samples = db.query(UserOrganization).limit(5).all()
        for i, uo in enumerate(samples, 1):
            user = db.query(User).filter(User.id == uo.user_id).first()
            org = db.query(Organization).filter(Organization.id == uo.organization_id).first()

            print(f"{i}. User: {user.mobile if user else 'Unknown'} | "
                  f"Org: {org.name if org else 'Unknown'} | "
                  f"Role: {uo.role.value} | "
                  f"Active: {uo.is_active}")

    finally:
        db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate user organization data to UserOrganization table"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration results"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("USER ORGANIZATION MIGRATION SCRIPT")
    print("=" * 80)

    if args.verify:
        verify_migration()
        return 0

    if args.dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made")

    # Confirm before proceeding
    if not args.dry_run:
        response = input("\nThis will modify the database. Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Migration cancelled")
            return 0

    # Run migration
    success, skip, errors = migrate_user_organizations(dry_run=args.dry_run)

    # Print summary
    print("\n" + "=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print(f"Successfully migrated:  {success}")
    print(f"Skipped (already done): {skip}")
    print(f"Errors:                 {errors}")

    if errors == 0:
        print("\n✓ Migration completed successfully!")
        if not args.dry_run:
            print("\nRun with --verify to verify migration results")
        return 0
    else:
        print("\n⚠ Migration completed with errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
