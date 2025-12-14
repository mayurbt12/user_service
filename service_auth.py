"""Service-to-Service Authentication Module.

This module provides authentication utilities for service-to-service communication.
Services can obtain JWT tokens to authenticate their requests to other microservices.
"""

import requests
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
import os

from logger_config import setup_logger

logger = setup_logger(__name__, 'service.log')


class ServiceAuthManager:
    """Manages JWT tokens for service-to-service authentication.

    This class handles:
    - Service account login to obtain JWT tokens
    - Token caching to avoid repeated authentication
    - Automatic token refresh when expired
    """

    def __init__(self, user_service_url: str, service_mobile: str, service_password: str):
        """Initialize the Service Auth Manager.

        Args:
            user_service_url: Base URL of the User Service (e.g., "http://localhost:8007")
            service_mobile: Mobile number of the service account
            service_password: Password of the service account
        """
        self.user_service_url = user_service_url.rstrip('/')
        self.service_mobile = service_mobile
        self.service_password = service_password

        # Token cache
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def get_access_token(self) -> Optional[str]:
        """Get a valid access token (cached or newly obtained).

        Returns:
            str: Valid JWT access token, or None if authentication fails
        """
        # Check if we have a cached token that's still valid
        if self._access_token and self._token_expires_at:
            # Add 60 second buffer before expiration
            if datetime.now(timezone.utc) < (self._token_expires_at - timedelta(seconds=60)):
                logger.debug("Using cached access token")
                return self._access_token

        # Try to refresh the token if we have a refresh token
        if self._refresh_token:
            logger.info("Access token expired, attempting refresh")
            if self._refresh_access_token():
                return self._access_token

        # No valid token, need to login
        logger.info("No valid token available, performing service login")
        if self._login():
            return self._access_token

        logger.error("Failed to obtain access token")
        return None

    def _login(self) -> bool:
        """Perform service account login to obtain tokens.

        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            url = f"{self.user_service_url}/auth/login"
            payload = {
                "mobile": self.service_mobile,
                "password": self.service_password
            }

            response = requests.post(url, json=payload, timeout=5)

            if response.status_code == 200:
                data = response.json()
                self._access_token = data["access_token"]
                self._refresh_token = data["refresh_token"]

                # Calculate expiration time (expires_in is in seconds)
                expires_in = data.get("expires_in", 3600)  # Default 1 hour
                self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                logger.info(f"Service login successful, token expires at {self._token_expires_at}")
                return True
            else:
                logger.error(f"Service login failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error during service login: {e}")
            return False

    def _refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token.

        Returns:
            bool: True if refresh successful, False otherwise
        """
        try:
            url = f"{self.user_service_url}/auth/refresh"
            payload = {
                "refresh_token": self._refresh_token
            }

            response = requests.post(url, json=payload, timeout=5)

            if response.status_code == 200:
                data = response.json()
                self._access_token = data["access_token"]
                # Refresh token might be the same or a new one
                self._refresh_token = data.get("refresh_token", self._refresh_token)

                # Calculate expiration time
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                logger.info(f"Token refresh successful, new token expires at {self._token_expires_at}")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                # Clear tokens since refresh failed
                self._access_token = None
                self._refresh_token = None
                self._token_expires_at = None
                return False

        except Exception as e:
            logger.error(f"Error during token refresh: {e}")
            return False

    def get_auth_headers(self) -> Dict[str, str]:
        """Get HTTP headers with authorization token.

        Returns:
            dict: Headers dictionary with Authorization bearer token
        """
        token = self.get_access_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        else:
            return {"Content-Type": "application/json"}


def create_service_account_if_not_exists():
    """Helper function to create a service account on first run.

    This should be run during User Service initialization to ensure
    a service account exists for inter-service communication.
    """
    from database import SessionLocal
    import crud

    # Read from environment
    service_mobile = os.getenv("SERVICE_ACCOUNT_MOBILE", "+919999999999")
    service_password = os.getenv("SERVICE_ACCOUNT_PASSWORD", "ServicePass@123")

    db = SessionLocal()
    try:
        # Check if service account exists
        existing_user = crud.get_user_by_mobile(db, service_mobile)
        if existing_user:
            logger.info(f"Service account already exists: {service_mobile}")
            return

        # Create service account with system_service role
        user = crud.create_user(
            db,
            mobile=service_mobile,
            password=service_password,
            profile={
                "first_name": "Service",
                "last_name": "Account",
                "description": "System service account for inter-service communication"
            },
            role="system_admin"  # Use system_admin for maximum permissions
        )

        logger.info(f"Service account created successfully: {service_mobile}")

    except Exception as e:
        logger.error(f"Error creating service account: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # Test the service auth manager
    manager = ServiceAuthManager(
        user_service_url="http://localhost:8007",
        service_mobile=os.getenv("SERVICE_ACCOUNT_MOBILE", "+919999999999"),
        service_password=os.getenv("SERVICE_ACCOUNT_PASSWORD", "ServicePass@123")
    )

    token = manager.get_access_token()
    if token:
        print(f"Successfully obtained token: {token[:50]}...")
        headers = manager.get_auth_headers()
        print(f"Auth headers: {headers}")
    else:
        print("Failed to obtain token")
