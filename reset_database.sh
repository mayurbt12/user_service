#!/bin/bash
# Reset User Service Database
# This script drops and recreates the one_call_users database

echo "=========================================="
echo "  Reset User Service Database"
echo "=========================================="
echo ""
echo "This will:"
echo "  1. Terminate all connections to one_call_users database"
echo "  2. Drop the one_call_users database"
echo "  3. Create a fresh one_call_users database"
echo "  4. Tables will be auto-created when service starts"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "[1/3] Terminating existing connections..."
sudo -u postgres psql << 'EOF'
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = 'one_call_users'
  AND pid <> pg_backend_pid();
EOF

echo ""
echo "[2/3] Dropping database..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS one_call_users;"

echo ""
echo "[3/3] Creating fresh database..."
sudo -u postgres psql -c "CREATE DATABASE one_call_users OWNER one_call_user;"

echo ""
echo "=========================================="
echo "✓ Database reset complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Start the user service: ./start.sh"
echo "  2. Tables will be created automatically"
echo "  3. Register your first user to create organization"
echo ""
