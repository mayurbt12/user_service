#!/bin/bash
# Startup script for User Management Service
# Starts REST API server

# Change to script directory
cd "$(dirname "$0")"

# Activate virtual environment
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
else
    echo "Warning: Virtual environment not found at .venv/"
    echo "Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Set PYTHONPATH to include parent directory for shared_libs access
export PYTHONPATH="$(cd .. && pwd):$PYTHONPATH"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================="
echo "  User Management Service - Startup"
echo "========================================="
echo ""

# Create directories if they don't exist
mkdir -p .pids logs

# Check if service is already running
if [ -f .pids/api.pid ]; then
    API_PID=$(cat .pids/api.pid)
    if ps -p $API_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ API server already running (PID: $API_PID)${NC}"
        SKIP_API=true
    else
        echo "Cleaning up stale API PID file..."
        rm -f .pids/api.pid
        SKIP_API=false
    fi
else
    SKIP_API=false
fi

# Start API Server
if [ "$SKIP_API" = false ]; then
    echo -e "${GREEN}Starting REST API server...${NC}"
    nohup python3 api_server.py > logs/api.log 2>&1 &
    API_PID=$!
    echo $API_PID > .pids/api.pid
    echo "  ✓ API server started (PID: $API_PID)"
    echo "  ✓ API URL: http://127.0.0.1:8007"
    echo "  ✓ API Docs: http://127.0.0.1:8007/docs"
    echo "  ✓ Logs: logs/api.log"
else
    echo -e "${GREEN}API server already running${NC}"
fi

echo ""

# Wait a moment for service to fully initialize
sleep 2

# Verify service
echo "Verifying service..."
ERRORS=0

# Check API server
if [ -f .pids/api.pid ]; then
    API_PID=$(cat .pids/api.pid)
    if ps -p $API_PID > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} API server is running (PID: $API_PID)"

        # Test API health endpoint
        if command -v curl &> /dev/null; then
            if curl -s http://127.0.0.1:8007/health > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} API health check passed"
            else
                echo -e "  ${YELLOW}⚠${NC} API not responding yet (may still be starting)"
            fi
        fi
    else
        echo -e "  ${RED}✗${NC} API server failed to start (check logs/api.log)"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "  ${RED}✗${NC} API server PID file not found"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ User Management Service started successfully!${NC}"
    echo ""
    echo "Available Services:"
    echo "  • REST API: http://127.0.0.1:8007"
    echo "  • API Docs: http://127.0.0.1:8007/docs"
    echo ""
    echo "Default Admin Account:"
    echo "  • Mobile: +1234567890"
    echo "  • Password: Admin@123"
    echo "  • IMPORTANT: Change password immediately!"
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo "Check log file: logs/api.log"
fi
echo "========================================="
echo ""
echo "Commands:"
echo "  • Stop service: ./stop.sh"
echo "  • View logs: tail -f logs/api.log"
echo ""
