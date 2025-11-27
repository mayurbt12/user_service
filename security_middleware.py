"""Security middleware for FastAPI applications.

This module provides:
- HTTP security headers middleware
- CORS configuration helpers
- Rate limiting helpers

SOLID Principles:
- Single Responsibility: Each class handles one aspect of security
- Open/Closed: Extensible through configuration
- Liskov Substitution: Middleware works with any FastAPI app
- Interface Segregation: Small, focused interfaces
- Dependency Inversion: Depends on abstractions (FastAPI interfaces)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import FastAPI
from typing import List, Optional


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all HTTP responses.
    
    Headers added:
    - X-Frame-Options: Prevents clickjacking
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-XSS-Protection: XSS filter
    - Strict-Transport-Security: Forces HTTPS
    - Content-Security-Policy: Prevents XSS
    - Referrer-Policy: Controls referrer information
    """
    
    async def dispatch(self, request: Request, call_next):
        """Add security headers to response."""
        response = await call_next(request)
        
        # Clickjacking protection
        response.headers["X-Frame-Options"] = "DENY"
        
        # MIME sniffing protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Force HTTPS (max-age=1 year)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy - Allow Swagger UI CDN resources
        if request.url.path in ["/docs", "/redoc"]:
            # Relaxed CSP for API documentation pages
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net"
            )
        else:
            # Strict CSP for all other endpoints
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        # Referrer policy
        response.headers["Referrer-Policy"] = "no-referrer"

        # Remove server header if present
        if "Server" in response.headers:
            del response.headers["Server"]

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size.
    
    Prevents DoS attacks through large payloads.
    """
    
    def __init__(self, app: FastAPI, max_size: int = 10_000_000):
        """Initialize with maximum request size (default: 10MB)."""
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next):
        """Check request size before processing."""
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"}
                )
        return await call_next(request)


def get_cors_origins(environment: str = "development") -> List[str]:
    """Get allowed CORS origins based on environment.
    
    Args:
        environment: "development", "staging", or "production"
    
    Returns:
        List of allowed origins
    """
    if environment == "production":
        return [
            "https://your-production-domain.com",
            "https://app.your-domain.com",
        ]
    elif environment == "staging":
        return [
            "https://staging.your-domain.com",
            "http://localhost:3000",
            "http://localhost:1800",
        ]
    else:  # development
        return [
            "http://localhost:3000",
            "http://localhost:1800",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:1800",
        ]


def configure_security_middleware(app: FastAPI, max_request_size: int = 10_000_000):
    """Configure all security middleware for a FastAPI app.
    
    Args:
        app: FastAPI application instance
        max_request_size: Maximum request body size in bytes (default: 10MB)
    """
    # Add security headers
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Add request size limits
    app.add_middleware(RequestSizeLimitMiddleware, max_size=max_request_size)
