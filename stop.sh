#!/bin/bash
# Stop script for User Service
# Stops all services by finding processes on ports from .env

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
echo "  User Service - Shutdown"
echo "========================================="
echo ""

STOPPED=0
ERRORS=0

# Load .env file and extract ports
if [ -f .env ]; then
    echo "Reading ports from .env..."
    API_PORT=$(grep "^API_PORT=" .env | cut -d '=' -f2)
    MCP_PORT=$(grep "^MCP_PORT=" .env | cut -d '=' -f2)
    echo "  API Port: $API_PORT"
    echo "  MCP Port: $MCP_PORT"
    echo ""
else
    echo -e "${RED}✗${NC} .env file not found!"
    exit 1
fi

# Collect all PIDs from both ports
ALL_PIDS=()

# Find processes on API port
if [ -n "$API_PORT" ]; then
    echo "Checking for processes on port $API_PORT..."
    API_PIDS=$(lsof -ti :$API_PORT 2>/dev/null)
    if [ -n "$API_PIDS" ]; then
        echo -e "  ${GREEN}Found${NC} process(es): $API_PIDS"
        ALL_PIDS+=($API_PIDS)
    else
        echo "  No process found on port $API_PORT"
    fi
fi

# Find processes on MCP port
if [ -n "$MCP_PORT" ]; then
    echo "Checking for processes on port $MCP_PORT..."
    MCP_PIDS=$(lsof -ti :$MCP_PORT 2>/dev/null)
    if [ -n "$MCP_PIDS" ]; then
        echo -e "  ${GREEN}Found${NC} process(es): $MCP_PIDS"
        ALL_PIDS+=($MCP_PIDS)
    else
        echo "  No process found on port $MCP_PORT"
    fi
fi

# Remove duplicates from PID list
UNIQUE_PIDS=($(echo "${ALL_PIDS[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))

if [ ${#UNIQUE_PIDS[@]} -eq 0 ]; then
    echo ""
    echo "  Service not running on configured ports"
else
    echo ""
    echo "Stopping processes: ${UNIQUE_PIDS[@]}..."

    for PID in "${UNIQUE_PIDS[@]}"; do
        if ps -p $PID > /dev/null 2>&1; then
            echo "  Sending SIGTERM to PID $PID..."
            kill $PID 2>/dev/null
        fi
    done

    # Wait for graceful shutdown (max 10 seconds)
    echo "  Waiting for graceful shutdown..."
    for i in {1..10}; do
        ALL_STOPPED=true
        for PID in "${UNIQUE_PIDS[@]}"; do
            if ps -p $PID > /dev/null 2>&1; then
                ALL_STOPPED=false
                break
            fi
        done

        if $ALL_STOPPED; then
            echo -e "  ${GREEN}✓${NC} All services stopped gracefully"
            STOPPED=${#UNIQUE_PIDS[@]}
            break
        fi
        sleep 1
    done

    # Force kill any remaining processes
    for PID in "${UNIQUE_PIDS[@]}"; do
        if ps -p $PID > /dev/null 2>&1; then
            echo "  Forcing shutdown of PID $PID with SIGKILL..."
            kill -9 $PID 2>/dev/null
            sleep 1
            if ! ps -p $PID > /dev/null 2>&1; then
                echo -e "  ${GREEN}✓${NC} Process $PID stopped (forced)"
                STOPPED=$((STOPPED + 1))
            else
                echo -e "  ${RED}✗${NC} Failed to stop process $PID"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    done
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
        echo -e "${GREEN}✓ User Service stopped successfully!${NC}"
    fi
else
    echo -e "${RED}✗ Failed to stop service${NC}"
    echo "  You may need to manually kill processes"
fi
echo "========================================="
echo ""
