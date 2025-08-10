"""
Data models for the engagement streaming pipeline.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


class ContentModel(BaseModel):
    """Content model representing media content."""
    
    id: UUID
    slug: str
    title: str
    content_type: str = Field(..., pattern="^(podcast|newsletter|video)$")
    length_seconds: Optional[int] = None
    publish_ts: datetime
    
    class Config:
        from_attributes = True


class EngagementEventModel(BaseModel):
    """Raw engagement event model."""
    
    id: int
    content_id: UUID
    user_id: UUID
    event_type: str = Field(..., pattern="^(play|pause|finish|click)$")
    event_ts: datetime
    duration_ms: Optional[int] = None
    device: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    
    @validator('duration_ms')
    def validate_duration(cls, v, values):
        """Validate duration based on event type."""
        event_type = values.get('event_type')
        if event_type in ['play', 'pause', 'finish'] and v is None:
            raise ValueError(f"Duration is required for {event_type} events")
        return v
    
    class Config:
        from_attributes = True


class EnrichedEngagementEvent(BaseModel):
    """Enriched engagement event with content metadata and computed fields."""
    
    # Original event fields
    id: int
    content_id: UUID
    user_id: UUID
    event_type: str
    event_ts: datetime
    duration_ms: Optional[int] = None
    device: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    
    # Content metadata
    slug: str
    title: str
    content_type: str
    length_seconds: Optional[int] = None
    
    # Computed fields
    engagement_seconds: Optional[Decimal] = None
    engagement_pct: Optional[Decimal] = None
    
    @validator('engagement_seconds', pre=True, always=True)
    def compute_engagement_seconds(cls, v, values):
        """Compute engagement seconds from duration_ms."""
        duration_ms = values.get('duration_ms')
        if duration_ms is not None:
            return round(Decimal(duration_ms) / 1000, 2)
        return None
    
    @validator('engagement_pct', pre=True, always=True)
    def compute_engagement_pct(cls, v, values):
        """Compute engagement percentage."""
        engagement_seconds = values.get('engagement_seconds')
        length_seconds = values.get('length_seconds')
        
        if engagement_seconds is not None and length_seconds is not None and length_seconds > 0:
            return round((engagement_seconds / Decimal(length_seconds)) * 100, 2)
        return None
    
    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat(),
            UUID: str
        }


class RedisAggregation(BaseModel):
    """Model for Redis aggregation data."""
    
    content_id: UUID
    slug: str
    title: str
    content_type: str
    total_events: int
    unique_users: int
    total_engagement_seconds: Decimal
    avg_engagement_pct: Optional[Decimal] = None
    last_updated: datetime
    
    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat(),
            UUID: str
        }


class BigQueryRecord(BaseModel):
    """Model for BigQuery records."""
    
    event_id: int
    content_id: str  # UUID as string for BigQuery
    user_id: str     # UUID as string for BigQuery
    event_type: str
    event_timestamp: datetime
    duration_ms: Optional[int] = None
    engagement_seconds: Optional[float] = None
    engagement_pct: Optional[float] = None
    device: Optional[str] = None
    content_slug: str
    content_title: str
    content_type: str
    content_length_seconds: Optional[int] = None
    raw_payload: Optional[Dict[str, Any]] = None
    processed_timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @classmethod
    def from_enriched_event(cls, event: EnrichedEngagementEvent) -> "BigQueryRecord":
        """Create BigQuery record from enriched event."""
        return cls(
            event_id=event.id,
            content_id=str(event.content_id),
            user_id=str(event.user_id),
            event_type=event.event_type,
            event_timestamp=event.event_ts,
            duration_ms=event.duration_ms,
            engagement_seconds=float(event.engagement_seconds) if event.engagement_seconds else None,
            engagement_pct=float(event.engagement_pct) if event.engagement_pct else None,
            device=event.device,
            content_slug=event.slug,
            content_title=event.title,
            content_type=event.content_type,
            content_length_seconds=event.length_seconds,
            raw_payload=event.raw_payload
        )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExternalSystemPayload(BaseModel):
    """Model for external system payload."""
    
    event_id: int
    content_id: str
    user_id: str
    event_type: str
    timestamp: str
    metadata: Dict[str, Any]
    
    @classmethod
    def from_enriched_event(cls, event: EnrichedEngagementEvent) -> "ExternalSystemPayload":
        """Create external system payload from enriched event."""
        return cls(
            event_id=event.id,
            content_id=str(event.content_id),
            user_id=str(event.user_id),
            event_type=event.event_type,
            timestamp=event.event_ts.isoformat(),
            metadata={
                "content_title": event.title,
                "content_type": event.content_type,
                "device": event.device,
                "engagement_seconds": float(event.engagement_seconds) if event.engagement_seconds else None,
                "engagement_pct": float(event.engagement_pct) if event.engagement_pct else None,
                "raw_payload": event.raw_payload
            }
        )


class HealthCheck(BaseModel):
    """Health check model."""
    
    service: str
    status: str = Field(..., pattern="^(healthy|unhealthy|degraded)$")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
