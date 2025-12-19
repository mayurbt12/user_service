"""Centralized logging configuration for User Service.

Production-grade logging with:
- Hourly log rotation with 30-day retention (Google/Netflix pattern)
- Request ID context propagation for distributed tracing
- Async-safe queue-based logging (prevents event loop blocking)
- ISO 8601 timestamp naming for easy searching
- Millisecond precision timestamps
"""

import logging
import sys
from pathlib import Path

# Add shared_libs to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs.logging_utils import LogConfig, setup_hourly_logger

from diagnostics import get_request_id

# Create logs directory
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)


class RequestContextFilter(logging.Filter):
    """Inject request ID into log records for traceable logging.

    Implements OpenTelemetry-style correlation ID pattern.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id to log record."""
        record.request_id = get_request_id()
        return True


def setup_logger(name: str, log_file: str = 'service.log') -> logging.Logger:
    """Setup production-grade logger with hourly rotation.

    Creates a logger with:
    - Hourly rotation with 30-day retention
    - Queue-based handlers (non-blocking, async-safe)
    - Console handler for real-time monitoring
    - Request context filter for distributed tracing
    - ISO 8601 timestamp naming (api.log.2025-12-19_14)

    Args:
        name: Logger name (usually __name__)
        log_file: Log file name (without extension)

    Returns:
        Configured logger instance with request tracing
    """
    # Remove .log extension if present
    log_name = log_file.replace('.log', '')

    config = LogConfig(
        log_name=log_name,
        log_dir=str(LOG_DIR),
        log_level="INFO",
        rotation_when="H",          # Hourly rotation
        rotation_interval=1,        # Every 1 hour
        backup_count=720,           # 30 days retention
        console_logging=True,
        use_queue=True,             # Async-safe for FastAPI
        format_string='[%(asctime)s] [%(request_id)s] [%(name)s] %(levelname)s - %(message)s',
        date_format='%Y-%m-%d %H:%M:%S'
    )

    # Add request context filter
    logger = setup_hourly_logger(config, RequestContextFilter())
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
