import hmac
import hashlib
import time
import base64
from typing import Optional
from loguru import logger

def generate_auth_token(user_id: int, secret: str) -> str:
    """
    Generates a secure, 24-hour auth token for the user.
    Uses HMAC-SHA256 for integrity and authenticity.
    """
    expires = int(time.time()) + 86400  # 24 hours
    payload = f"{user_id}:{expires}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    
    # Pack everything into a token
    token_str = f"{payload}:{signature}"
    # Base64 encode for URL safety
    token_bytes = token_str.encode()
    return base64.urlsafe_b64encode(token_bytes).decode().rstrip('=')

def verify_auth_token(token: str, secret: str) -> Optional[int]:
    """
    Verifies the token and returns the user_id if valid and not expired.
    Returns None if verification fails.
    """
    if not token:
        return None
        
    try:
        # Add padding back if needed
        padding = '=' * (4 - len(token) % 4)
        decoded_bytes = base64.urlsafe_b64decode(token + padding)
        decoded_str = decoded_bytes.decode()
        
        parts = decoded_str.split(':')
        if len(parts) != 3:
            logger.warning("Token verification failed: invalid format")
            return None
        
        user_id_str, expires_str, signature = parts
        user_id = int(user_id_str)
        expires = int(expires_str)
        
        # Check expiration
        if time.time() > expires:
            logger.warning(f"Token verification failed: expired (User: {user_id})")
            return None
        
        # Verify signature
        expected_payload = f"{user_id}:{expires}"
        expected_signature = hmac.new(secret.encode(), expected_payload.encode(), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(signature, expected_signature):
            return user_id
        else:
            logger.warning("Token verification failed: signature mismatch")
            return None
            
    except Exception as e:
        logger.error(f"Token verification Exception: {e}")
        return None
        
    return None
