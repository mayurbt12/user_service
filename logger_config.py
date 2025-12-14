"""Centralized logging configuration for User Service.

Production-grade logging with rotation and structured formatting.
"""

import logging
from logging.handlers import RotatingFileHandler
import os

# Create logs directory
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logger(name: str, log_file: str = 'service.log') -> logging.Logger:
    """Setup production-grade logger with rotation.

    Args:
        name: Logger name (usually __name__)
        log_file: Log file name (e.g., 'api.log', 'mcp.log')

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Production formatter with timestamp
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler - 10MB max, keep 5 backups
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_file),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def configure_root_logger():
    """Reduce third-party library noise."""
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


# Auto-configure on import
configure_root_logger()
