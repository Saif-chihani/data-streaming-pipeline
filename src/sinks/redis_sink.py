"""
Redis sink for real-time aggregations and caching.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from uuid import UUID

import redis.asyncio as redis
import structlog

from config import settings
from models import EnrichedEngagementEvent, RedisAggregation

logger = structlog.get_logger(__name__)


class RedisSink:
    """Redis sink for real-time event processing and aggregations."""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.aggregation_buffer: Dict[UUID, Dict] = {}
        self.last_aggregation_flush = time.time()
        
    async def initialize(self):
        """Initialize Redis connection."""
        logger.info("Initializing Redis sink")
        
        try:
            self.redis_client = redis.from_url(
                settings.redis.url,
                db=settings.redis.db,
                max_connections=settings.redis.max_connections,
                socket_keepalive=settings.redis.socket_keepalive,
                socket_keepalive_options=settings.redis.socket_keepalive_options,
                decode_responses=True
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection established")
            
            # Initialize aggregation keys if they don't exist
            await self._initialize_aggregation_keys()
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise
    
    async def _initialize_aggregation_keys(self):
        """Initialize Redis keys for aggregations."""
        # Initialize sorted set for top content
        top_content_key = settings.redis.top_content_key
        if not await self.redis_client.exists(top_content_key):
            await self.redis_client.zadd(top_content_key, {})
            await self.redis_client.expire(top_content_key, settings.redis.aggregation_ttl_seconds)
    
    async def process_event(self, event: EnrichedEngagementEvent):
        """Process a single event for Redis aggregations."""
        try:
            # Add event to recent events list (for real-time monitoring)
            await self._add_to_recent_events(event)
            
            # Update real-time aggregations
            await self._update_content_aggregations(event)
            
            # Update top content rankings
            await self._update_top_content(event)
            
            # Store individual event data (with TTL)
            await self._store_event_data(event)
            
        except Exception as e:
            logger.error(f"Error processing event in Redis: {e}")
    
    async def _add_to_recent_events(self, event: EnrichedEngagementEvent):
        """Add event to recent events stream."""
        event_key = f"recent_events:{event.content_id}"
        
        event_data = {
            'event_id': event.id,
            'user_id': str(event.user_id),
            'event_type': event.event_type,
            'timestamp': event.event_ts.isoformat(),
            'engagement_seconds': float(event.engagement_seconds) if event.engagement_seconds else None,
            'engagement_pct': float(event.engagement_pct) if event.engagement_pct else None,
            'device': event.device
        }
        
        # Add to stream
        await self.redis_client.xadd(
            event_key,
            event_data,
            maxlen=1000  # Keep last 1000 events per content
        )
        
        # Set TTL on the stream
        await self.redis_client.expire(event_key, 3600)  # 1 hour TTL
    
    async def _update_content_aggregations(self, event: EnrichedEngagementEvent):
        """Update real-time content aggregations."""
        content_key = f"content_stats:{event.content_id}"
        window_key = f"content_window:{event.content_id}:10min"
        
        # Get current timestamp for windowing
        current_time = int(time.time())
        window_start = current_time - (settings.redis.aggregation_window_minutes * 60)
        
        async with self.redis_client.pipeline(transaction=True) as pipe:
            # Update overall content stats
            pipe.hincrby(content_key, 'total_events', 1)
            pipe.sadd(f"{content_key}:users", str(event.user_id))
            pipe.expire(content_key, settings.redis.aggregation_ttl_seconds)
            pipe.expire(f"{content_key}:users", settings.redis.aggregation_ttl_seconds)
            
            # Add engagement time if available
            if event.engagement_seconds:
                pipe.hincrbyfloat(content_key, 'total_engagement_seconds', float(event.engagement_seconds))
            
            # Update windowed stats
            pipe.zadd(window_key, {f"{event.id}:{current_time}": current_time})
            pipe.zremrangebyscore(window_key, '-inf', window_start)  # Remove old events
            pipe.expire(window_key, settings.redis.aggregation_ttl_seconds)
            
            await pipe.execute()
    
    async def _update_top_content(self, event: EnrichedEngagementEvent):
        """Update top content rankings."""
        top_content_key = settings.redis.top_content_key
        
        # Calculate score based on event type and engagement
        score = self._calculate_content_score(event)
        
        if score > 0:
            # Increment score for this content
            await self.redis_client.zincrby(top_content_key, score, str(event.content_id))
            
            # Set/update content metadata
            content_data = {
                'slug': event.slug,
                'title': event.title,
                'content_type': event.content_type,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            await self.redis_client.hset(
                f"content_meta:{event.content_id}",
                mapping=content_data
            )
            await self.redis_client.expire(
                f"content_meta:{event.content_id}",
                settings.redis.aggregation_ttl_seconds
            )
    
    def _calculate_content_score(self, event: EnrichedEngagementEvent) -> float:
        """Calculate content score based on event type and engagement."""
        base_scores = {
            'play': 1.0,
            'pause': 0.5,
            'finish': 3.0,
            'click': 0.3
        }
        
        score = base_scores.get(event.event_type, 0.0)
        
        # Boost score based on engagement percentage
        if event.engagement_pct:
            engagement_multiplier = min(float(event.engagement_pct) / 100, 1.0)
            score *= (1 + engagement_multiplier)
        
        return score
    
    async def _store_event_data(self, event: EnrichedEngagementEvent):
        """Store individual event data with TTL."""
        event_key = f"event:{event.id}"
        
        event_data = {
            'content_id': str(event.content_id),
            'user_id': str(event.user_id),
            'event_type': event.event_type,
            'timestamp': event.event_ts.isoformat(),
            'duration_ms': event.duration_ms or 0,
            'engagement_seconds': float(event.engagement_seconds) if event.engagement_seconds else 0,
            'engagement_pct': float(event.engagement_pct) if event.engagement_pct else 0,
            'device': event.device or '',
            'content_slug': event.slug,
            'content_title': event.title,
            'content_type': event.content_type
        }
        
        await self.redis_client.hset(event_key, mapping=event_data)
        await self.redis_client.expire(event_key, 86400)  # 24 hour TTL
    
    async def get_top_content(self, limit: int = 10) -> List[Dict]:
        """Get top content from the last aggregation window."""
        top_content_key = settings.redis.top_content_key
        
        # Get top content IDs with scores
        top_items = await self.redis_client.zrevrange(
            top_content_key, 0, limit - 1, withscores=True
        )
        
        result = []
        for content_id, score in top_items:
            # Get content metadata
            meta_key = f"content_meta:{content_id}"
            metadata = await self.redis_client.hgetall(meta_key)
            
            if metadata:
                # Get additional stats
                stats_key = f"content_stats:{content_id}"
                stats = await self.redis_client.hgetall(stats_key)
                
                # Get unique users count
                users_count = await self.redis_client.scard(f"{stats_key}:users")
                
                result.append({
                    'content_id': content_id,
                    'score': score,
                    'slug': metadata.get('slug', ''),
                    'title': metadata.get('title', ''),
                    'content_type': metadata.get('content_type', ''),
                    'total_events': int(stats.get('total_events', 0)),
                    'unique_users': users_count,
                    'total_engagement_seconds': float(stats.get('total_engagement_seconds', 0)),
                    'last_updated': metadata.get('last_updated', '')
                })
        
        return result
    
    async def get_content_stats(self, content_id: UUID, window_minutes: int = 10) -> Dict:
        """Get real-time stats for a specific content item."""
        content_key = f"content_stats:{content_id}"
        window_key = f"content_window:{content_id}:{window_minutes}min"
        
        # Get overall stats
        stats = await self.redis_client.hgetall(content_key)
        
        # Get unique users count
        users_count = await self.redis_client.scard(f"{content_key}:users")
        
        # Get windowed event count
        current_time = int(time.time())
        window_start = current_time - (window_minutes * 60)
        windowed_count = await self.redis_client.zcount(window_key, window_start, current_time)
        
        return {
            'content_id': str(content_id),
            'total_events': int(stats.get('total_events', 0)),
            'unique_users': users_count,
            'total_engagement_seconds': float(stats.get('total_engagement_seconds', 0)),
            'events_in_window': windowed_count,
            'window_minutes': window_minutes
        }
    
    async def get_recent_events(self, content_id: UUID, count: int = 50) -> List[Dict]:
        """Get recent events for a content item."""
        event_key = f"recent_events:{content_id}"
        
        # Get recent events from stream
        events = await self.redis_client.xrevrange(event_key, count=count)
        
        result = []
        for event_id, fields in events:
            result.append({
                'stream_id': event_id,
                **fields
            })
        
        return result
    
    async def cleanup_expired_data(self):
        """Clean up expired aggregation data."""
        logger.info("Cleaning up expired Redis data")
        
        try:
            # Clean up old windowed data
            current_time = int(time.time())
            pattern = "content_window:*"
            
            async for key in self.redis_client.scan_iter(match=pattern):
                # Remove events older than aggregation window
                window_minutes = settings.redis.aggregation_window_minutes
                cutoff_time = current_time - (window_minutes * 60)
                
                removed = await self.redis_client.zremrangebyscore(key, '-inf', cutoff_time)
                if removed > 0:
                    logger.debug(f"Removed {removed} expired events from {key}")
            
            # Clean up empty keys
            await self._cleanup_empty_keys()
            
        except Exception as e:
            logger.error(f"Error during Redis cleanup: {e}")
    
    async def _cleanup_empty_keys(self):
        """Remove empty Redis keys."""
        patterns = ["content_stats:*", "content_window:*", "recent_events:*"]
        
        for pattern in patterns:
            async for key in self.redis_client.scan_iter(match=pattern):
                key_type = await self.redis_client.type(key)
                
                is_empty = False
                if key_type == 'hash':
                    is_empty = await self.redis_client.hlen(key) == 0
                elif key_type == 'set':
                    is_empty = await self.redis_client.scard(key) == 0
                elif key_type == 'zset':
                    is_empty = await self.redis_client.zcard(key) == 0
                elif key_type == 'stream':
                    is_empty = await self.redis_client.xlen(key) == 0
                
                if is_empty:
                    await self.redis_client.delete(key)
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")


# Background task for cleaning up expired data
async def redis_cleanup_task():
    """Background task for Redis cleanup."""
    redis_sink = RedisSink()
    await redis_sink.initialize()
    
    try:
        while True:
            await redis_sink.cleanup_expired_data()
            await asyncio.sleep(300)  # Clean up every 5 minutes
    except asyncio.CancelledError:
        pass
    finally:
        await redis_sink.close()
