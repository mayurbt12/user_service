"""Diagnostics module for User Service timeout debugging.

Provides request correlation, timing utilities, and database pool monitoring.
Implements OpenTelemetry-style distributed tracing patterns.
"""

import contextvars
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, List


# Request correlation ID context (async-safe via contextvars)
request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    'request_id', default='no-request'
)


def generate_request_id() -> str:
    """Generate unique request ID for correlation tracking."""
    return f"req_{uuid.uuid4().hex[:12]}"


def set_request_id(request_id: str) -> None:
    """Set request ID in context for current request."""
    request_id_context.set(request_id)


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_context.get()


def clear_request_id() -> None:
    """Clear request ID from context after request completes."""
    request_id_context.set('no-request')


@dataclass
class TimingStats:
    """Container for request timing statistics (Google SRE Latency signal)."""
    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None
    db_time_ms: float = 0.0
    query_count: int = 0
    slow_queries: List[Dict] = field(default_factory=list)

    def elapsed_ms(self) -> float:
        """Calculate total elapsed time in milliseconds."""
        end = self.end_time if self.end_time else time.perf_counter()
        return (end - self.start_time) * 1000

    def service_time_ms(self) -> float:
        """Calculate service processing time (total - db time)."""
        return self.elapsed_ms() - self.db_time_ms


# Request timing context (async-safe)
request_timing_context: contextvars.ContextVar[Optional[TimingStats]] = contextvars.ContextVar(
    'request_timing', default=None
)


def start_request_timing() -> TimingStats:
    """Initialize timing for current request."""
    stats = TimingStats()
    request_timing_context.set(stats)
    return stats


def get_request_timing() -> Optional[TimingStats]:
    """Get timing stats for current request."""
    return request_timing_context.get()


def add_db_time(duration_ms: float, query_info: Optional[Dict] = None) -> None:
    """Add database query time to current request stats."""
    stats = request_timing_context.get()
    if stats is not None:
        stats.db_time_ms += duration_ms
        stats.query_count += 1
        if query_info is not None:
            stats.slow_queries.append(query_info)


def end_request_timing() -> Optional[TimingStats]:
    """Finalize timing for current request."""
    stats = request_timing_context.get()
    if stats is not None:
        stats.end_time = time.perf_counter()
    return stats


def clear_request_timing() -> None:
    """Clear timing context after request completes."""
    request_timing_context.set(None)


@dataclass
class PoolStats:
    """Database connection pool statistics (Google SRE Saturation signal)."""
    pool_size: int = 0
    checked_out: int = 0
    overflow: int = 0
    checked_in: int = 0
    invalidated: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        available = self.pool_size - self.checked_out + self.overflow
        return {
            "pool_size": self.pool_size,
            "checked_out": self.checked_out,
            "checked_in": self.checked_in,
            "overflow": self.overflow,
            "invalidated": self.invalidated,
            "available": max(0, available),
            "timestamp": self.timestamp.isoformat()
        }
