#!/bin/bash
# Unified startup script for User Management Service
# Starts both REST API and MCP server together

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

# Check if services are already running
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

if [ -f .pids/mcp.pid ]; then
    MCP_PID=$(cat .pids/mcp.pid)
    if ps -p $MCP_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ MCP server already running (PID: $MCP_PID)${NC}"
        SKIP_MCP=true
    else
        echo "Cleaning up stale MCP PID file..."
        rm -f .pids/mcp.pid
        SKIP_MCP=false
    fi
else
    SKIP_MCP=false
fi


# Start API Server
if [ "$SKIP_API" = false ]; then
    echo -e "${GREEN}[1/2]${NC} Starting REST API server..."
    nohup python3 api_server.py > logs/api.log 2>&1 &
    API_PID=$!
    echo $API_PID > .pids/api.pid
    echo "  ✓ API server started (PID: $API_PID)"
    echo "  ✓ API URL: http://127.0.0.1:8007"
    echo "  ✓ API Docs: http://127.0.0.1:8007/docs"
    echo "  ✓ Logs: logs/api.log"
else
    echo -e "${GREEN}[1/2]${NC} API server already running"
fi

echo ""

# Start MCP Server with SSE transport
if [ "$SKIP_MCP" = false ]; then
    echo -e "${GREEN}[2/2]${NC} Starting MCP server (SSE transport)..."
    export MCP_TRANSPORT=sse
    nohup python3 mcp_server.py > logs/mcp.log 2>&1 &
    MCP_PID=$!
    echo $MCP_PID > .pids/mcp.pid
    echo "  ✓ MCP server started (PID: $MCP_PID)"
    echo "  ✓ MCP SSE endpoint: http://127.0.0.1:8008/sse"
    echo "  ✓ Transport: SSE (scalable, network-based)"
    echo "  ✓ Logs: logs/mcp.log"
else
    echo -e "${GREEN}[2/2]${NC} MCP server already running"
fi

echo ""

# Wait a moment for services to fully initialize
sleep 2

# Verify services
echo "Verifying services..."
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

# Check MCP server
if [ -f .pids/mcp.pid ]; then
    MCP_PID=$(cat .pids/mcp.pid)
    if ps -p $MCP_PID > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} MCP server is running (PID: $MCP_PID)"

        # Test MCP SSE endpoint (simple check)
        if command -v curl &> /dev/null; then
            sleep 1  # Give MCP server a moment to fully start
            if curl -s http://127.0.0.1:8008/sse -m 2 > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} MCP SSE endpoint responding"
            else
                echo -e "  ${YELLOW}⚠${NC} MCP SSE endpoint not responding yet (may still be starting)"
            fi
        fi
    else
        echo -e "  ${RED}✗${NC} MCP server failed to start (check logs/mcp.log)"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "  ${RED}✗${NC} MCP server PID file not found"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo ""
echo "========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ User Management Service started successfully!${NC}"
    echo ""
    echo "Available Services:"
    echo "  • REST API: http://127.0.0.1:8007"
    echo "  • API Docs: http://127.0.0.1:8007/docs"
    echo "  • MCP Server (SSE): http://127.0.0.1:8008/sse"
    echo ""
    echo "Default Admin Account:"
    echo "  • Mobile: +1234567890"
    echo "  • Password: Admin@123"
    echo "  • IMPORTANT: Change password immediately!"
    echo ""
    echo "Transport:"
    echo "  • REST API: HTTP (frontend access)"
    echo "  • MCP Protocol: SSE (AI agent access)"
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo "Check log files:"
    echo "  • API: logs/api.log"
    echo "  • MCP: logs/mcp.log"
fi
echo "========================================="
echo ""
echo "Commands:"
echo "  • Stop services: ./stop.sh"
echo "  • View API logs: tail -f logs/api.log"
echo "  • View MCP logs: tail -f logs/mcp.log"
echo ""
