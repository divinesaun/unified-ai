import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Using SQLite file-based storage as requested
DATABASE_URL = "sqlite+aiosqlite:///./api_keys.db"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging during debug
    connect_args={"check_same_thread": False},  # Needed for SQLite
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass

# Dependency to get DB session
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Helper to initialize DB tables
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
