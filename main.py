#!/usr/bin/env python3
"""Unified entry point for User Management Service.

This module starts both services (API and MCP) using subprocess.
Designed to simplify service management and deployment.
"""

import subprocess
import signal
import sys
import time
import logging
import os
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global list to track all running processes
processes: List[subprocess.Popen] = []
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    if shutdown_requested:
        logger.warning("Force shutdown requested")
        sys.exit(1)

    shutdown_requested = True
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_services()


def shutdown_services():
    """Stop all running services."""
    global processes

    logger.info("Stopping all services...")
    for process in processes:
        if process.poll() is None:
            logger.info(f"Terminating process (PID: {process.pid})")
            process.terminate()

    # Wait for graceful termination (max 5 seconds per process)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning(f"Force killing process (PID: {process.pid})")
            process.kill()
            process.wait()

    logger.info("All services stopped")
    sys.exit(0)


def main():
    """Main entry point - start all services."""
    global processes

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("="*60)
    logger.info("User Management Service - Unified Startup")
    logger.info("="*60)

    # Get current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Start all processes
    try:
        logger.info("Starting API server...")
        api_process = subprocess.Popen(
            ["python3", "api_server.py"],
            cwd=current_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        processes.append(api_process)
        time.sleep(2)

        logger.info("Starting MCP server...")
        mcp_env = os.environ.copy()
        mcp_env['MCP_TRANSPORT'] = 'sse'
        mcp_process = subprocess.Popen(
            ["python3", "mcp_server.py"],
            cwd=current_dir,
            env=mcp_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        processes.append(mcp_process)
        time.sleep(2)

        logger.info("="*60)
        logger.info("All services started successfully!")
        logger.info("  - API Server: http://127.0.0.1:8007")
        logger.info("  - API Docs: http://127.0.0.1:8007/docs")
        logger.info("  - MCP Server: http://127.0.0.1:8008/sse")
        logger.info("="*60)

        # Monitor processes and restart if any crash
        while not shutdown_requested:
            for i, process in enumerate(processes):
                if process.poll() is not None:
                    logger.error(f"Process {i+1} (PID: {process.pid}) has stopped unexpectedly!")
                    shutdown_services()
            time.sleep(5)

    except Exception as e:
        logger.error(f"Error starting services: {e}")
        shutdown_services()


if __name__ == "__main__":
    main()
