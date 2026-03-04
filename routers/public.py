import os
import httpx
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import models
import security
from security import limiter
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal

router = APIRouter(tags=["public"])

# Use environment variables as per the guideline article
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "tinyllama")

async def log_usage(key_id: str, endpoint: str, model: str, status_code: int, processing_time_ms: float):
    """
    Background task to log API usage.
    """
    async with AsyncSessionLocal() as db:
        try:
            log = models.ApiUsageLog(
                key_id=key_id,
                endpoint=endpoint,
                model=model,
                status_code=status_code,
                processing_time_ms=processing_time_ms
            )
            db.add(log)
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to log usage stats: {e}")

# Retry configuration for Ollama connection
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout))
)
async def fetch_ollama_completion(client: httpx.AsyncClient, payload: dict):
    """
    Fetch completion from Ollama (non-streaming).
    """
    try:
        if "model" not in payload:
            payload["model"] = DEFAULT_MODEL

        response = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Ollama API error: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Ollama Error: {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Ollama connection error: {e}")
        raise

async def stream_ollama_generator(payload: dict):
    """
    Generator that handles the lifecycle of the httpx client for streaming responses.
    """
    if "model" not in payload:
        payload["model"] = DEFAULT_MODEL

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("POST", f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120.0) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama API error during stream: {e}")
            yield f'{{"error": "Ollama Provider Error: {e.response.status_code}"}}\n'.encode()
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f'{{"error": "Internal Stream Error"}}\n'.encode()

@router.post("/chat", dependencies=[Depends(security.get_api_key)])
@limiter.limit("10/minute") 
async def chat_endpoint(
    request: Request,
    chat_request: models.ChatRequest,
    background_tasks: BackgroundTasks,
    api_key: models.ApiKey = Depends(security.get_api_key)
):
    """
    Public chat endpoint that proxies to Ollama.
    Requires a valid API key.
    """
    start_time = time.time()
    
    # Convert Pydantic model to dict, filtering out None
    payload = chat_request.model_dump(exclude_none=True)
    
    # Use default model from env if not specified
    if not payload.get("model"):
        payload["model"] = DEFAULT_MODEL
    
    stream = chat_request.stream
    model_name = payload["model"]
    
    logger.info(f"Forwarding request to Ollama at {OLLAMA_HOST} (model={model_name}, stream={stream})")

    try:
        payload["model"] = DEFAULT_MODEL
        if stream:
            response = StreamingResponse(
                stream_ollama_generator(payload),
                media_type="application/x-ndjson"
            )
            process_time = (time.time() - start_time) * 1000
            background_tasks.add_task(log_usage, api_key.key_id, "/chat", DEFAULT_MODEL, 200, process_time)
            return response
        else:
            async with httpx.AsyncClient() as client:
                try:
                    response_data = await fetch_ollama_completion(client, payload)
                    process_time = (time.time() - start_time) * 1000
                    background_tasks.add_task(log_usage, api_key.key_id, "/chat", DEFAULT_MODEL, 200, process_time)
                    return JSONResponse(content=response_data)
                except httpx.RequestError:
                     process_time = (time.time() - start_time) * 1000
                     background_tasks.add_task(log_usage, api_key.key_id, "/chat", DEFAULT_MODEL, 503, process_time)
                     raise HTTPException(status_code=503, detail="Ollama Service Unavailable")
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        background_tasks.add_task(log_usage, api_key.key_id, "/chat", DEFAULT_MODEL, 500, process_time)
        raise e
