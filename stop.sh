#!/bin/bash
# Unified stop script for User Management Service
# Stops both REST API and MCP server

# Change to script directory
cd "$(dirname "$0")"

# Activate virtual environment (for any cleanup tasks)
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================="
echo "  User Management Service - Shutdown"
echo "========================================="
echo ""

STOPPED=0
ERRORS=0

# Stop API Server
echo -e "${GREEN}[1/2]${NC} Stopping REST API server..."
if [ -f .pids/api.pid ]; then
    API_PID=$(cat .pids/api.pid)

    if ps -p $API_PID > /dev/null 2>&1; then
        echo "  Sending SIGTERM to API server (PID: $API_PID)..."
        kill $API_PID 2>/dev/null

        # Wait for graceful shutdown (max 5 seconds)
        for i in {1..5}; do
            if ! ps -p $API_PID > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} API server stopped gracefully"
                rm -f .pids/api.pid
                STOPPED=$((STOPPED + 1))
                break
            fi
            sleep 1
        done

        # Force kill if still running
        if ps -p $API_PID > /dev/null 2>&1; then
            echo "  Forcing shutdown with SIGKILL..."
            kill -9 $API_PID 2>/dev/null
            sleep 1
            if ! ps -p $API_PID > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} API server stopped (forced)"
                rm -f .pids/api.pid
                STOPPED=$((STOPPED + 1))
            else
                echo -e "  ${RED}✗${NC} Failed to stop API server"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} API server not running (cleaning up PID file)"
        rm -f .pids/api.pid
    fi
else
    # Try to find and kill by process name (fallback)
    API_PIDS=$(pgrep -f "python3 api_server.py")
    if [ -n "$API_PIDS" ]; then
        echo "  Found API server by name, stopping..."
        echo "$API_PIDS" | xargs kill 2>/dev/null
        sleep 1
        echo -e "  ${GREEN}✓${NC} API server stopped"
        STOPPED=$((STOPPED + 1))
    else
        echo "  API server not running"
    fi
fi

echo ""

# Stop MCP Server
echo -e "${GREEN}[2/2]${NC} Stopping MCP server..."
if [ -f .pids/mcp.pid ]; then
    MCP_PID=$(cat .pids/mcp.pid)

    if ps -p $MCP_PID > /dev/null 2>&1; then
        echo "  Sending SIGTERM to MCP server (PID: $MCP_PID)..."
        kill $MCP_PID 2>/dev/null

        # Wait for graceful shutdown (max 5 seconds)
        for i in {1..5}; do
            if ! ps -p $MCP_PID > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} MCP server stopped gracefully"
                rm -f .pids/mcp.pid
                STOPPED=$((STOPPED + 1))
                break
            fi
            sleep 1
        done

        # Force kill if still running
        if ps -p $MCP_PID > /dev/null 2>&1; then
            echo "  Forcing shutdown with SIGKILL..."
            kill -9 $MCP_PID 2>/dev/null
            sleep 1
            if ! ps -p $MCP_PID > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} MCP server stopped (forced)"
                rm -f .pids/mcp.pid
                STOPPED=$((STOPPED + 1))
            else
                echo -e "  ${RED}✗${NC} Failed to stop MCP server"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} MCP server not running (cleaning up PID file)"
        rm -f .pids/mcp.pid
    fi
else
    # Try to find and kill by process name (fallback)
    MCP_PIDS=$(pgrep -f "python3 mcp_server.py")
    if [ -n "$MCP_PIDS" ]; then
        echo "  Found MCP server by name, stopping..."
        echo "$MCP_PIDS" | xargs kill 2>/dev/null
        sleep 1
        echo -e "  ${GREEN}✓${NC} MCP server stopped"
        STOPPED=$((STOPPED + 1))
    else
        echo "  MCP server not running"
    fi
fi

echo ""

# Clean up any remaining PID files
if [ -d .pids ]; then
    rm -f .pids/*.pid 2>/dev/null
fi

echo "========================================="
if [ $ERRORS -eq 0 ]; then
    if [ $STOPPED -eq 0 ]; then
        echo -e "${YELLOW}⚠ No services were running${NC}"
    else
        echo -e "${GREEN}✓ All services stopped successfully!${NC}"
        echo "  ($STOPPED service(s) stopped)"
    fi
else
    echo -e "${RED}✗ Some services failed to stop${NC}"
    echo "  You may need to manually kill processes"
fi
echo "========================================="
echo ""
