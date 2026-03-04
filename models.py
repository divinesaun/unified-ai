import uuid
import os
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
from pydantic import BaseModel, ConfigDict

# SQLAlchemy Models
class ApiKey(Base):
    __tablename__ = "api_keys"

    # key_id as UUID primary key
    key_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Optional name for the API key (e.g. "Mobile App", "Internal Dashboard")
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Store ONLY the hashed version of the key
    hashed_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Relationship to usage logs
    usage_logs: Mapped[list["ApiUsageLog"]] = relationship(back_populates="api_key", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ApiKey(key_id={self.key_id}, name={self.name}, active={self.is_active})>"

class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[str] = mapped_column(ForeignKey("api_keys.key_id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    endpoint: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True) # If we can capture this
    status_code: Mapped[int] = mapped_column(Integer)
    processing_time_ms: Mapped[float] = mapped_column(Float)
    
    api_key: Mapped["ApiKey"] = relationship(back_populates="usage_logs")

# Pydantic Schemas
class ApiKeyRequest(BaseModel):
    name: str | None = None

class ApiKeyResponse(BaseModel):
    key_id: str
    name: str | None
    api_key: str  # The plain key (only returned on generation)
    created_at: datetime
    created_by: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class ApiKeyInfo(BaseModel):
    key_id: str
    name: str | None
    created_at: datetime
    created_by: str
    is_active: bool
    last_used_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class UsageLogSchema(BaseModel):
    timestamp: datetime
    endpoint: str
    model: str | None
    status_code: int
    processing_time_ms: float

    model_config = ConfigDict(from_attributes=True)

class ApiKeyStats(BaseModel):
    key_id: str
    name: str | None
    total_requests: int
    last_used_at: datetime | None
    recent_logs: list[UsageLogSchema]

    model_config = ConfigDict(from_attributes=True)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    stream: bool = False
