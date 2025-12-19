"""Request middleware for request tracing and timing.

Implements Google SRE Golden Signals:
- Latency: Request timing breakdown (total, db, service)
- Errors: Error logging with context
- Traffic: Request logging

Follows OpenTelemetry distributed tracing patterns.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import FastAPI

from diagnostics import (
    generate_request_id,
    set_request_id,
    clear_request_id,
    start_request_timing,
    end_request_timing,
    clear_request_timing
)
from logger_config import setup_logger
from config import settings

logger = setup_logger(__name__, 'api.log')

# Paths excluded from detailed timing logs
EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}


class DiagnosticsMiddleware(BaseHTTPMiddleware):
    """Middleware for request tracing and performance diagnostics.

    Features:
    - Generates unique request ID for each request
    - Tracks total request time, DB time, and service time
    - Logs slow requests with detailed breakdown
    - Adds X-Request-ID header to response
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with timing and correlation."""
        # Skip timing for health checks and docs
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        # Generate and set request ID
        request_id = generate_request_id()
        set_request_id(request_id)

        # Start timing
        timing = start_request_timing()

        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}"
        )

        try:
            response = await call_next(request)

            # End timing
            end_request_timing()

            # Add request ID to response header
            response.headers["X-Request-ID"] = request_id

            # Calculate timing breakdown
            total_ms = timing.elapsed_ms()
            db_ms = timing.db_time_ms
            service_ms = timing.service_time_ms()
            query_count = timing.query_count

            log_message = (
                f"Request completed: {request.method} {request.url.path} "
                f"status={response.status_code} "
                f"total={total_ms:.2f}ms db={db_ms:.2f}ms "
                f"service={service_ms:.2f}ms queries={query_count}"
            )

            # Log as warning if slow
            is_slow_request = total_ms > settings.SLOW_REQUEST_THRESHOLD_MS
            is_slow_db = db_ms > settings.SLOW_QUERY_THRESHOLD_MS

            if is_slow_request or is_slow_db:
                logger.warning(f"Slow request: {log_message}")
                if timing.slow_queries:
                    logger.warning(f"Slow queries: {timing.slow_queries}")
            else:
                logger.info(log_message)

            return response

        except Exception as e:
            # End timing on error
            end_request_timing()
            total_ms = timing.elapsed_ms()

            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"error={type(e).__name__}: {str(e)[:100]} "
                f"elapsed={total_ms:.2f}ms"
            )
            raise

        finally:
            clear_request_id()
            clear_request_timing()


def configure_request_middleware(app: FastAPI) -> None:
    """Add request tracing middleware to FastAPI application."""
    app.add_middleware(DiagnosticsMiddleware)
