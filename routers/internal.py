import os
import getpass
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from loguru import logger
import models
from database import get_db
import security

router = APIRouter(prefix="/internal", tags=["internal"])

def require_local_access(request: Request):
    """
    Dependency to ensure the request is coming from localhost.
    """
    client_host = request.client.host
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        logger.warning(f"Blocked external access to internal endpoint from {client_host}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    if request.headers.get("x-forwarded-for") or request.headers.get("ngrok-skip-browser-warning"):
        logger.warning(f"Blocked proxied access to internal endpoint from {client_host}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

@router.post("/generate-key", response_model=models.ApiKeyResponse, dependencies=[Depends(require_local_access)])
async def generate_api_key(request: models.ApiKeyRequest = None, db: AsyncSession = Depends(get_db)):
    """
    Generate a new API key with optional name/description.
    """
    try:
        # 1. Generate secure random key
        plain_secret = security.generate_api_key()
        
        # 2. Get system user
        try:
            try:
                created_by = os.getlogin()
            except OSError:
                created_by = getpass.getuser()
        except Exception:
            created_by = "unknown_system_user"

        # 3. Create DB record
        import uuid
        key_id = str(uuid.uuid4())
        
        hashed_key = security.get_password_hash(plain_secret)
        
        # Extract name from request if provided
        key_name = request.name if request else None
        
        new_key = models.ApiKey(
            key_id=key_id,
            hashed_key=hashed_key,
            name=key_name,
            created_by=created_by,
            is_active=True
        )
        
        db.add(new_key)
        await db.commit()
        await db.refresh(new_key)
        
        full_api_key = f"{key_id}.{plain_secret}"
        
        logger.info(f"Generated new API key {key_id} ({key_name or 'unnamed'}) for user {created_by}")
        
        return models.ApiKeyResponse(
            key_id=new_key.key_id,
            name=new_key.name,
            api_key=full_api_key,
            created_at=new_key.created_at,
            created_by=new_key.created_by,
            is_active=new_key.is_active
        )
        
    except Exception as e:
        logger.error(f"Error generating API key: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/revoke-key/{key_id}", response_model=models.ApiKeyInfo, dependencies=[Depends(require_local_access)])
async def revoke_api_key(key_id: str, db: AsyncSession = Depends(get_db)):
    """
    Revoke an API key.
    """
    stmt = select(models.ApiKey).where(models.ApiKey.key_id == key_id)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    api_key.is_active = False
    await db.commit()
    await db.refresh(api_key)
    
    logger.info(f"Revoked API key {key_id}")
    
    return api_key

@router.get("/keys", response_model=list[models.ApiKeyInfo], dependencies=[Depends(require_local_access)])
async def list_keys(db: AsyncSession = Depends(get_db)):
    """
    List all API keys.
    """
    stmt = select(models.ApiKey).order_by(models.ApiKey.created_at.desc())
    result = await db.execute(stmt)
    keys = result.scalars().all()
    return keys

@router.get("/usage-stats/{key_id}", response_model=models.ApiKeyStats, dependencies=[Depends(require_local_access)])
async def get_key_usage_stats(key_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """
    Get detailed usage stats for a specific API key.
    """
    # Check if key exists
    stmt = select(models.ApiKey).where(models.ApiKey.key_id == key_id)
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    # Get total requests count
    count_stmt = select(func.count()).select_from(models.ApiUsageLog).where(models.ApiUsageLog.key_id == key_id)
    count_result = await db.execute(count_stmt)
    total_requests = count_result.scalar()
    
    # Get recent logs
    logs_stmt = (
        select(models.ApiUsageLog)
        .where(models.ApiUsageLog.key_id == key_id)
        .order_by(models.ApiUsageLog.timestamp.desc())
        .limit(limit)
    )
    logs_result = await db.execute(logs_stmt)
    recent_logs = logs_result.scalars().all()
    
    return models.ApiKeyStats(
        key_id=api_key.key_id,
        name=api_key.name,
        total_requests=total_requests,
        last_used_at=api_key.last_used_at,
        recent_logs=recent_logs
    )
