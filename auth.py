# auth.py (root) - KOMPLETTE NEUE VERSION

import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Globale Variable für Config (wird lazy geladen)
_config = None

def get_config():
    """Lazy load config to avoid circular imports."""
    global _config
    if _config is None:
        from config import config
        _config = config
    return _config


class APIKeyAuth:
    def __init__(self):
        self._api_key = None
    
    @property
    def api_key(self):
        if self._api_key is None:
            self._api_key = self._get_api_key()
        return self._api_key
    
    def _get_api_key(self) -> str:
        config = get_config()
        key = config.get("api_key")
        
        if os.environ.get("GABI_API_KEY"):
            key = os.environ["GABI_API_KEY"]
            logger.debug("Using API key from environment")
        
        if not key:
            key = "sysop"
            logger.warning("Using default API key 'sysop' - change in production!")
        
        return key
    
    def verify_api_key(self, api_key: str) -> bool:
        return secrets.compare_digest(api_key, self.api_key)
    
    def __call__(self, x_api_key=None, credentials=Security(security), api_key_param=None):
        if x_api_key and self.verify_api_key(x_api_key):
            return x_api_key
        if credentials and self.verify_api_key(credentials.credentials):
            return credentials.credentials
        if api_key_param and self.verify_api_key(api_key_param):
            return api_key_param
        
        raise HTTPException(status_code=403, detail="Invalid API key")


api_key_auth = APIKeyAuth()


def verify_api_key(api_key: str) -> bool:
    return api_key_auth.verify_api_key(api_key)


def get_api_key() -> str:
    return api_key_auth.api_key


async def verify_token(x_api_key=None, credentials=Security(security), api_key_param=None):
    return api_key_auth(x_api_key, credentials, api_key_param)


async def verify_token_bool(x_api_key=None, credentials=Security(security), api_key_param=None):
    try:
        api_key_auth(x_api_key, credentials, api_key_param)
        return True
    except HTTPException:
        return False


async def require_auth(x_api_key=None, credentials=Security(security), api_key_param=None):
    return api_key_auth(x_api_key, credentials, api_key_param)


async def optional_auth(x_api_key=None, credentials=Security(security), api_key_param=None):
    try:
        return api_key_auth(x_api_key, credentials, api_key_param)
    except HTTPException:
        return None


class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._requests: Dict[str, list] = {}
    
    def _get_client_id(self, request):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
    
    def _cleanup_old_requests(self, client_id: str, now: datetime):
        if client_id in self._requests:
            cutoff = now - timedelta(minutes=1)
            self._requests[client_id] = [ts for ts in self._requests[client_id] if ts > cutoff]
    
    def check(self, request):
        client_id = self._get_client_id(request)
        now = datetime.now()
        self._cleanup_old_requests(client_id, now)
        
        current_count = len(self._requests.get(client_id, []))
        if current_count >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for {client_id}")
            return False
        
        if client_id not in self._requests:
            self._requests[client_id] = []
        self._requests[client_id].append(now)
        return True


class APIKeyManager:
    def __init__(self, keys_file: Optional[str] = None):
        self.keys_file = keys_file or "api_keys.json"
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._load_keys()
    
    def _load_keys(self):
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
    
    def _save_keys(self):
        import json
        from pathlib import Path
        
        try:
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(self._keys, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save API keys: {e}")
    
    def add_key(self, name: str, expires_days: int = 365) -> str:
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
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        if key_hash not in self._keys:
            return False
        
        key_info = self._keys[key_hash]
        if key_info.get("expires_at"):
            expires_at = datetime.fromisoformat(key_info["expires_at"])
            if expires_at < datetime.now():
                return False
        if not key_info.get("is_active", True):
            return False
        
        key_info["last_used"] = datetime.now().isoformat()
        self._save_keys()
        return True
    
    def revoke_key(self, key_hash: str) -> bool:
        if key_hash in self._keys:
            self._keys[key_hash]["is_active"] = False
            self._save_keys()
            logger.info(f"Revoked API key: {self._keys[key_hash].get('name')}")
            return True
        return False
    
    def list_keys(self) -> Dict[str, Dict[str, Any]]:
        return {key_hash: {k: v for k, v in info.items() if k != "last_used"} 
                for key_hash, info in self._keys.items()}


key_manager = None

def init_key_manager(keys_file: Optional[str] = None) -> APIKeyManager:
    global key_manager
    if key_manager is None:
        key_manager = APIKeyManager(keys_file)
    return key_manager


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def validate_api_key_format(key: str) -> bool:
    if len(key) < 32:
        return False
    import re
    if not re.match(r'^[A-Za-z0-9\-_]+$', key):
        return False
    return True


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