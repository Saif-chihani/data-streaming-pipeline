"""
External system sink for sending events to third-party services.
"""

import asyncio
import json
from typing import Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models import EnrichedEngagementEvent, ExternalSystemPayload

logger = structlog.get_logger(__name__)


class ExternalSystemSink:
    """Sink for sending events to external systems."""
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.sent_count = 0
        self.error_count = 0
        
    async def initialize(self):
        """Initialize HTTP client for external system."""
        logger.info("Initializing External System sink")
        
        try:
            # Create HTTP client with custom settings
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.external_system.timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'engagement-stream-processor/1.0',
                    **settings.external_system.headers
                }
            )
            
            # Test connection
            await self._health_check()
            
            logger.info("External System sink initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize External System sink: {e}")
            # Continue without external system rather than failing
            self.client = None
    
    async def _health_check(self):
        """Perform health check on external system."""
        if not self.client:
            return
        
        try:
            # Try a simple GET request to check connectivity
            health_url = settings.external_system.url.replace('/post', '/status/200')
            response = await self.client.get(health_url, timeout=5)
            
            if response.status_code == 200:
                logger.info("External system health check passed")
            else:
                logger.warning(f"External system health check returned {response.status_code}")
                
        except Exception as e:
            logger.warning(f"External system health check failed: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def send_event(self, event: EnrichedEngagementEvent):
        """Send event to external system with retry logic."""
        if not self.client:
            logger.debug("External system client not available, skipping event")
            return
        
        try:
            # Create payload for external system
            payload = ExternalSystemPayload.from_enriched_event(event)
            
            # Send POST request
            response = await self.client.post(
                settings.external_system.url,
                json=payload.dict(),
                timeout=settings.external_system.timeout
            )
            
            # Check response
            if response.status_code in [200, 201, 202]:
                self.sent_count += 1
                logger.debug(f"Successfully sent event {event.id} to external system")
                
                # Log every 100 successful sends
                if self.sent_count % 100 == 0:
                    logger.info(f"Sent {self.sent_count} events to external system")
                    
            else:
                self.error_count += 1
                logger.error(
                    f"External system returned {response.status_code}: {response.text}",
                    event_id=event.id
                )
                
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error sending event {event.id} to external system: {e}")
            raise  # Re-raise for retry logic
    
    async def send_batch(self, events: list[EnrichedEngagementEvent]):
        """Send a batch of events to external system."""
        if not self.client or not events:
            return
        
        # Check if external system supports batch operations
        batch_url = settings.external_system.url.replace('/post', '/batch')
        
        try:
            # Create batch payload
            batch_payload = {
                'events': [
                    ExternalSystemPayload.from_enriched_event(event).dict()
                    for event in events
                ],
                'batch_id': f"batch_{int(asyncio.get_event_loop().time())}",
                'event_count': len(events)
            }
            
            response = await self.client.post(
                batch_url,
                json=batch_payload,
                timeout=settings.external_system.timeout * 2  # Longer timeout for batches
            )
            
            if response.status_code in [200, 201, 202]:
                self.sent_count += len(events)
                logger.info(f"Successfully sent batch of {len(events)} events to external system")
            else:
                # Fall back to individual sends
                logger.warning(f"Batch send failed ({response.status_code}), falling back to individual sends")
                tasks = [self.send_event(event) for event in events]
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Error sending batch to external system: {e}")
            # Fall back to individual sends
            tasks = [self.send_event(event) for event in events]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_heartbeat(self):
        """Send heartbeat to external system."""
        if not self.client:
            return
        
        try:
            heartbeat_payload = {
                'type': 'heartbeat',
                'timestamp': asyncio.get_event_loop().time(),
                'processor_id': 'engagement-stream-processor',
                'stats': {
                    'sent_count': self.sent_count,
                    'error_count': self.error_count,
                    'error_rate': self.error_count / max(self.sent_count + self.error_count, 1)
                }
            }
            
            heartbeat_url = settings.external_system.url.replace('/post', '/heartbeat')
            response = await self.client.post(
                heartbeat_url,
                json=heartbeat_payload,
                timeout=5
            )
            
            if response.status_code in [200, 201, 202]:
                logger.debug("Heartbeat sent successfully")
            else:
                logger.warning(f"Heartbeat failed: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Error sending heartbeat: {e}")
    
    async def get_stats(self) -> dict:
        """Get sink statistics."""
        total_attempts = self.sent_count + self.error_count
        error_rate = self.error_count / max(total_attempts, 1)
        
        return {
            'sink_type': 'external_system',
            'sent_count': self.sent_count,
            'error_count': self.error_count,
            'total_attempts': total_attempts,
            'error_rate': error_rate,
            'is_available': self.client is not None
        }
    
    async def test_connection(self) -> bool:
        """Test connection to external system."""
        if not self.client:
            return False
        
        try:
            test_payload = {
                'type': 'connection_test',
                'timestamp': asyncio.get_event_loop().time(),
                'message': 'Connection test from engagement stream processor'
            }
            
            response = await self.client.post(
                settings.external_system.url,
                json=test_payload,
                timeout=10
            )
            
            return response.status_code in [200, 201, 202]
            
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    async def close(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
            logger.info("External System sink closed")


# Background heartbeat task
async def external_system_heartbeat_task():
    """Background task for sending heartbeats to external system."""
    external_sink = ExternalSystemSink()
    await external_sink.initialize()
    
    try:
        while True:
            await external_sink.send_heartbeat()
            await asyncio.sleep(60)  # Send heartbeat every minute
    except asyncio.CancelledError:
        pass
    finally:
        await external_sink.close()


# Mock external system for testing
class MockExternalSystem:
    """Mock external system for testing purposes."""
    
    def __init__(self):
        self.received_events = []
        self.heartbeats = []
        
    async def receive_event(self, payload: dict):
        """Mock receiving an event."""
        self.received_events.append({
            'payload': payload,
            'timestamp': asyncio.get_event_loop().time()
        })
        
        # Simulate processing time
        await asyncio.sleep(0.01)
        
        return {
            'status': 'success',
            'event_id': payload.get('event_id'),
            'processed_at': asyncio.get_event_loop().time()
        }
    
    async def receive_batch(self, batch_payload: dict):
        """Mock receiving a batch of events."""
        events = batch_payload.get('events', [])
        
        for event in events:
            await self.receive_event(event)
        
        return {
            'status': 'success',
            'batch_id': batch_payload.get('batch_id'),
            'processed_count': len(events),
            'processed_at': asyncio.get_event_loop().time()
        }
    
    async def receive_heartbeat(self, heartbeat_payload: dict):
        """Mock receiving a heartbeat."""
        self.heartbeats.append({
            'payload': heartbeat_payload,
            'timestamp': asyncio.get_event_loop().time()
        })
        
        return {
            'status': 'alive',
            'server_time': asyncio.get_event_loop().time()
        }
    
    def get_stats(self) -> dict:
        """Get mock system stats."""
        return {
            'total_events': len(self.received_events),
            'total_heartbeats': len(self.heartbeats),
            'last_event_time': (
                self.received_events[-1]['timestamp'] 
                if self.received_events else None
            ),
            'last_heartbeat_time': (
                self.heartbeats[-1]['timestamp'] 
                if self.heartbeats else None
            )
        }
