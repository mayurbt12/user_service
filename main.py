#!/usr/bin/env python3
"""Entry point for User Management Service.

This module starts the API server.
Designed to simplify service management and deployment.

FIX: Changed stdout from subprocess.PIPE to file logging to prevent
deadlock when pipe buffer fills (64KB). This follows the pattern used
by call_history_service and ticket_service which have 0 restarts.
See: https://docs.python.org/3/library/subprocess.html (PIPE deadlock warning)
"""

import subprocess
import signal
import sys
import time
import os
from typing import List

from logger_config import setup_logger

logger = setup_logger(__name__, 'service.log')

# Global list to track all running processes
processes: List[subprocess.Popen] = []
log_files: List = []  # Track log file handles for cleanup
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
    global processes, log_files

    logger.info("Stopping all services...")

    # Dispose database connections to prevent leaks
    try:
        from database import engine
        engine.dispose()
        logger.info("Database connections disposed")
    except Exception as e:
        logger.warning(f"Failed to dispose database connections: {e}")

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

    # Close log files
    for log_file in log_files:
        try:
            log_file.close()
        except Exception:
            pass

    logger.info("All services stopped")
    sys.exit(0)


def main():
    """Main entry point - start all services."""
    global processes, log_files

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("="*60)
    logger.info("User Management Service - Unified Startup")
    logger.info("="*60)

    # Get current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(current_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Start all processes
    try:
        # FIX: Use file logging instead of subprocess.PIPE to prevent deadlock
        # when the 64KB pipe buffer fills. This pattern is proven working in
        # call_history_service and ticket_service (0 restarts).

        logger.info("Starting API server...")
        api_log = open(os.path.join(logs_dir, 'api.log'), 'a')
        log_files.append(api_log)
        api_process = subprocess.Popen(
            ["python3", "api_server.py"],
            cwd=current_dir,
            stdout=api_log,  # Write to file, not PIPE (prevents deadlock)
            stderr=subprocess.STDOUT
        )
        processes.append(api_process)
        logger.info(f"API Server started with PID {api_process.pid}")
        time.sleep(2)

        logger.info("="*60)
        logger.info("Service started successfully!")
        logger.info("  - API Server: http://127.0.0.1:8007")
        logger.info("  - API Docs: http://127.0.0.1:8007/docs")
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
