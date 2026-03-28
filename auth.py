# gateway/auth.py
"""Authentication and authorization for GABI Gateway."""

import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from gateway.config import config

logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer(auto_error=False)


class APIKeyAuth:
    """
    API Key authentication handler.
    
    Supports:
    - Header: X-API-Key
    - Header: Authorization: Bearer <token>
    - Query parameter: api_key
    - Environment variable override
    """
    
    def __init__(self):
        self.api_key = self._get_api_key()
    
    def _get_api_key(self) -> str:
        """
        Get API key from config or environment.
        
        Returns:
            API key string
        """
        # Try config first
        key = config.get("api_key")
        
        # Override with environment variable
        if os.environ.get("GABI_API_KEY"):
            key = os.environ["GABI_API_KEY"]
            logger.debug("Using API key from environment")
        
        # Default for development
        if not key:
            key = "sysop"
            logger.warning("Using default API key 'sysop' - change in production!")
        
        return key
    
    def verify_api_key(self, api_key: str) -> bool:
        """
        Verify if the provided API key is valid.
        
        Args:
            api_key: The API key to verify
            
        Returns:
            True if valid, False otherwise
        """
        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(api_key, self.api_key)
    
    def __call__(
        self,
        x_api_key: Optional[str] = None,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
        api_key_param: Optional[str] = None,
    ) -> str:
        """
        Authenticate request using multiple methods.
        
        Priority:
        1. X-API-Key header
        2. Authorization: Bearer header
        3. api_key query parameter
        
        Args:
            x_api_key: X-API-Key header value
            credentials: Bearer token credentials
            api_key_param: api_key query parameter
            
        Returns:
            The validated API key
            
        Raises:
            HTTPException 403 if authentication fails
        """
        # Try X-API-Key header
        if x_api_key:
            if self.verify_api_key(x_api_key):
                return x_api_key
            logger.warning(f"Invalid X-API-Key: {x_api_key[:4]}***")
        
        # Try Bearer token
        if credentials:
            token = credentials.credentials
            if self.verify_api_key(token):
                return token
            logger.warning(f"Invalid Bearer token: {token[:4]}***")
        
        # Try query parameter
        if api_key_param:
            if self.verify_api_key(api_key_param):
                return api_key_param
            logger.warning(f"Invalid api_key parameter")
        
        # All methods failed
        raise HTTPException(
            status_code=403,
            detail="Invalid API key. Provide via X-API-Key header, Authorization: Bearer, or api_key parameter."
        )


# Create global auth instance
api_key_auth = APIKeyAuth()


# Convenience functions
def verify_api_key(api_key: str) -> bool:
    """
    Verify a single API key.
    
    Args:
        api_key: The API key to verify
        
    Returns:
        True if valid, False otherwise
    """
    return api_key_auth.verify_api_key(api_key)


def get_api_key() -> str:
    """
    Get the configured API key.
    
    Returns:
        The API key string
    """
    return api_key_auth.api_key


# Dependency for FastAPI endpoints
async def verify_token(
    x_api_key: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key_param: Optional[str] = None,
) -> str:
    """
    FastAPI dependency for authentication.
    
    Use in endpoints: `_api_key: str = Depends(verify_token)`
    
    Args:
        x_api_key: X-API-Key header
        credentials: Bearer token
        api_key_param: api_key query parameter
        
    Returns:
        The validated API key
    """
    return api_key_auth(x_api_key, credentials, api_key_param)


# Simplified version for endpoints that don't need the key
async def verify_token_bool(
    x_api_key: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key_param: Optional[str] = None,
) -> bool:
    """
    FastAPI dependency that returns boolean.
    
    Returns:
        True if authenticated
    """
    try:
        api_key_auth(x_api_key, credentials, api_key_param)
        return True
    except HTTPException:
        return False


class RateLimiter:
    """
    Simple rate limiter for API endpoints.
    
    Uses in-memory storage - not suitable for distributed deployments.
    """
    
    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute per client
        """
        self.requests_per_minute = requests_per_minute
        self._requests: Dict[str, list] = {}  # ip -> list of timestamps
    
    def _get_client_id(self, request) -> str:
        """
        Get client identifier from request.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Client identifier (IP address)
        """
        # Try X-Forwarded-For header first (for proxies)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Fall back to client host
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _cleanup_old_requests(self, client_id: str, now: datetime) -> None:
        """
        Remove requests older than 1 minute.
        
        Args:
            client_id: Client identifier
            now: Current timestamp
        """
        if client_id in self._requests:
            cutoff = now - timedelta(minutes=1)
            self._requests[client_id] = [
                ts for ts in self._requests[client_id]
                if ts > cutoff
            ]
    
    def check(self, request) -> bool:
        """
        Check if request is allowed.
        
        Args:
            request: FastAPI request object
            
        Returns:
            True if allowed, False if rate limited
        """
        client_id = self._get_client_id(request)
        now = datetime.now()
        
        self._cleanup_old_requests(client_id, now)
        
        current_count = len(self._requests.get(client_id, []))
        
        if current_count >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for {client_id}")
            return False
        
        # Add current request
        if client_id not in self._requests:
            self._requests[client_id] = []
        self._requests[client_id].append(now)
        
        return True


class APIKeyManager:
    """
    Manage multiple API keys (for multi-tenant support).
    
    Keys are stored in a separate file for persistence.
    """
    
    def __init__(self, keys_file: Optional[str] = None):
        """
        Initialize API key manager.
        
        Args:
            keys_file: Path to keys file (default: api_keys.json)
        """
        self.keys_file = keys_file or "api_keys.json"
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._load_keys()
    
    def _load_keys(self) -> None:
        """Load API keys from file."""
        import json
        from pathlib import Path
        
        keys_path = Path(self.keys_file)
        if keys_path.exists():
            try:
                with open(keys_path, 'r', encoding='utf-8') as f:
                    self._keys = json.load(f)
                logger.info(f"Loaded {len(self._keys)} API keys")
            except Exception as e:
                logger.error(f"Failed to load API keys: {e}")
                self._keys = {}
        else:
            logger.info(f"No API keys file found: {self.keys_file}")
            self._keys = {}
    
    def _save_keys(self) -> None:
        """Save API keys to file."""
        import json
        from pathlib import Path
        
        try:
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(self._keys, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self._keys)} API keys")
        except Exception as e:
            logger.error(f"Failed to save API keys: {e}")
    
    def add_key(self, name: str, expires_days: int = 365) -> str:
        """
        Generate and add a new API key.
        
        Args:
            name: Name/description for the key
            expires_days: Days until expiration (default: 365)
            
        Returns:
            The generated API key
        """
        # Generate random key
        key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        expires_at = datetime.now() + timedelta(days=expires_days)
        
        self._keys[key_hash] = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_used": None,
            "is_active": True
        }
        
        self._save_keys()
        logger.info(f"Created API key for: {name}")
        
        return key
    
    def verify_key(self, key: str) -> bool:
        """
        Verify an API key.
        
        Args:
            key: The API key to verify
            
        Returns:
            True if valid, False otherwise
        """
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        if key_hash not in self._keys:
            return False
        
        key_info = self._keys[key_hash]
        
        # Check expiration
        if key_info.get("expires_at"):
            expires_at = datetime.fromisoformat(key_info["expires_at"])
            if expires_at < datetime.now():
                return False
        
        # Check if active
        if not key_info.get("is_active", True):
            return False
        
        # Update last used
        key_info["last_used"] = datetime.now().isoformat()
        self._save_keys()
        
        return True
    
    def revoke_key(self, key_hash: str) -> bool:
        """
        Revoke an API key by its hash.
        
        Args:
            key_hash: SHA256 hash of the key
            
        Returns:
            True if revoked, False if not found
        """
        if key_hash in self._keys:
            self._keys[key_hash]["is_active"] = False
            self._save_keys()
            logger.info(f"Revoked API key: {self._keys[key_hash].get('name')}")
            return True
        return False
    
    def list_keys(self) -> Dict[str, Dict[str, Any]]:
        """
        List all API keys (without the actual key values).
        
        Returns:
            Dict of key hashes with metadata
        """
        return {
            key_hash: {k: v for k, v in info.items() if k != "last_used"}
            for key_hash, info in self._keys.items()
        }


# Optional: Multi-key manager (disabled by default)
key_manager = None  # Initialize only if needed


def init_key_manager(keys_file: Optional[str] = None) -> APIKeyManager:
    """
    Initialize the API key manager for multi-tenant support.
    
    Args:
        keys_file: Path to keys file
        
    Returns:
        APIKeyManager instance
    """
    global key_manager
    if key_manager is None:
        key_manager = APIKeyManager(keys_file)
    return key_manager


# ===== HELPER FUNCTIONS =====

def hash_api_key(key: str) -> str:
    """
    Hash an API key for storage.
    
    Args:
        key: The API key to hash
        
    Returns:
        SHA256 hash of the key
    """
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """
    Generate a new random API key.
    
    Returns:
        A secure random API key
    """
    return secrets.token_urlsafe(32)


def validate_api_key_format(key: str) -> bool:
    """
    Validate API key format.
    
    Args:
        key: The API key to validate
        
    Returns:
        True if format is valid
    """
    # API keys should be at least 32 characters
    if len(key) < 32:
        return False
    
    # Should contain only URL-safe characters
    import re
    if not re.match(r'^[A-Za-z0-9\-_]+$', key):
        return False
    
    return True


# ===== FASTAPI DEPENDENCY =====

async def require_auth(
    x_api_key: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key_param: Optional[str] = None,
) -> str:
    """
    FastAPI dependency that requires authentication.
    
    Use in endpoints: `_api_key: str = Depends(require_auth)`
    
    Returns:
        The validated API key
    """
    return api_key_auth(x_api_key, credentials, api_key_param)


async def optional_auth(
    x_api_key: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    api_key_param: Optional[str] = None,
) -> Optional[str]:
    """
    FastAPI dependency that allows optional authentication.
    
    Returns:
        API key if valid, None otherwise
    """
    try:
        return api_key_auth(x_api_key, credentials, api_key_param)
    except HTTPException:
        return None


# ===== PUBLIC EXPORTS =====

__all__ = [
    "verify_api_key",
    "verify_token",
    "verify_token_bool",
    "require_auth",
    "optional_auth",
    "generate_api_key",
    "hash_api_key",
    "validate_api_key_format",
    "APIKeyAuth",
    "RateLimiter",
    "APIKeyManager",
    "init_key_manager",
]