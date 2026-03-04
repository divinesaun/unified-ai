import time
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import uvicorn
from contextlib import asynccontextmanager

from database import init_db
from routers import internal, public
from security import limiter

# Configure Loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")
    yield
    # Shutdown logic if any
    logger.info("Shutting down...")

app = FastAPI(
    title="Unified AI",
    description="An open-source backend for a unified AI API server backed by Ollama",
    version="1.0.0",
    lifespan=lifespan
)

# Add Rate Limiter Middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS (Allow all for now, or restrict if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Extract client info
    client_host = request.client.host if request.client else "unknown"
    
    # Process request
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    
    # Mask API Key in logs
    # We don't log headers here explicitly, but if we did, we should mask X-API-Key
    
    logger.info(
        f"Method={request.method} Path={request.url.path} "
        f"Status={response.status_code} Client={client_host} "
        f"Duration={process_time:.2f}ms"
    )
    
    return response

# Include Routers
app.include_router(internal.router)
app.include_router(public.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    # Example startup command
    # In production, run with: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
