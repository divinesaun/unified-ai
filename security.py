import secrets
# from passlib.context import CryptContext # Removed due to incompatibility with bcrypt 4.0+
import bcrypt
from fastapi import HTTPException, Security, status, Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address
import models
from database import get_db
from datetime import datetime

# API Key Header definition
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password using constant-time comparison (handled by bcrypt).
    """
    try:
        # bcrypt requires bytes
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False

def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def generate_api_key() -> str:
    """
    Generate a secure random API key (32 bytes, URL-safe).
    Example: 43 bytes base64 string
    """
    return secrets.token_urlsafe(32)

async def get_api_key(
    api_key_header: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> models.ApiKey:
    """
    Dependency to validate the API key from the header.
    Returns the ApiKey model if valid, raises HTTPException otherwise.
    The key format is expected to be `key_id.secret`.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    try:
        if "." not in api_key_header:
            # Fallback or invalid format
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key format")
            
        key_id, plain_secret = api_key_header.split(".", 1)
        
        # Async lookup by ID (efficient)
        stmt = select(models.ApiKey).where(models.ApiKey.key_id == key_id)
        result = await db.execute(stmt)
        api_key_record = result.scalar_one_or_none()
        
        if not api_key_record:
            # Key ID not found
            # Use constant time comparison to avoid timing attacks on ID existence?
            # Ideally yes, but here we just return 403.
            # To be strictly secure against timing attacks for ID enumeration, we could do a dummy hash verification.
            # But IDs are UUIDs, so enumeration is hard.
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")
            
        if not api_key_record.is_active:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key is inactive")

        # Verify hash of the secret part
        if not verify_password(plain_secret, api_key_record.hashed_key):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")
             
        # Update usage stats (async)
        # We update strictly on successful validation
        api_key_record.last_used_at = datetime.utcnow()
        await db.commit()
        
        return api_key_record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Could not validate credentials")
