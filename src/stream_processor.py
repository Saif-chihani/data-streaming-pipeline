"""
Main streaming processor for engagement events.
Handles real-time processing with exactly-once semantics.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import settings
from models import EnrichedEngagementEvent, EngagementEventModel
from sinks.bigquery_sink import BigQuerySink
from sinks.redis_sink import RedisSink
from sinks.external_sink import ExternalSystemSink

logger = structlog.get_logger(__name__)


class StreamProcessor:
    """Main stream processor for engagement events."""
    
    def __init__(self):
        self.db_engine = create_engine(settings.database.url)
        self.db_session = sessionmaker(bind=self.db_engine)
        
        # Kafka consumer with exactly-once semantics
        self.consumer = KafkaConsumer(
            settings.kafka.topic_engagement_events,
            bootstrap_servers=settings.kafka.bootstrap_servers.split(','),
            group_id=settings.kafka.consumer_group_id,
            auto_offset_reset=settings.kafka.auto_offset_reset,
            enable_auto_commit=settings.kafka.enable_auto_commit,
            session_timeout_ms=settings.kafka.session_timeout_ms,
            max_poll_records=settings.kafka.max_poll_records,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            consumer_timeout_ms=1000  # Timeout for polling
        )
        
        # Initialize sinks
        self.bigquery_sink = BigQuerySink()
        self.redis_sink = RedisSink()
        self.external_sink = ExternalSystemSink()
        
        # Processing metrics
        self.processed_count = 0
        self.error_count = 0
        self.last_processed_time = None
        self.processing_times = []
        
        # Batch processing
        self.batch_buffer = []
        self.last_batch_time = time.time()
        
        self.running = False
    
    async def initialize(self):
        """Initialize the stream processor."""
        logger.info("Initializing stream processor")
        
        # Initialize sinks
        await self.bigquery_sink.initialize()
        await self.redis_sink.initialize()
        await self.external_sink.initialize()
        
        logger.info("Stream processor initialized successfully")
    
    def enrich_event(self, raw_event: dict) -> Optional[EnrichedEngagementEvent]:
        """Enrich a raw event with content metadata and computed fields."""
        try:
            # Validate the raw event
            event = EngagementEventModel(**raw_event)
            
            # Fetch content metadata from database
            with self.db_session() as session:
                result = session.execute(
                    text("""
                        SELECT c.slug, c.title, c.content_type, c.length_seconds
                        FROM content c
                        WHERE c.id = :content_id
                    """),
                    {'content_id': event.content_id}
                )
                content_row = result.first()
                
                if not content_row:
                    logger.warning(f"Content not found for event {event.id}")
                    return None
                
                # Create enriched event
                enriched = EnrichedEngagementEvent(
                    id=event.id,
                    content_id=event.content_id,
                    user_id=event.user_id,
                    event_type=event.event_type,
                    event_ts=event.event_ts,
                    duration_ms=event.duration_ms,
                    device=event.device,
                    raw_payload=event.raw_payload,
                    slug=content_row.slug,
                    title=content_row.title,
                    content_type=content_row.content_type,
                    length_seconds=content_row.length_seconds
                )
                
                return enriched
                
        except Exception as e:
            logger.error(f"Error enriching event: {e}", event_data=raw_event)
            return None
    
    async def process_event(self, enriched_event: EnrichedEngagementEvent):
        """Process a single enriched event through all sinks."""
        start_time = time.time()
        
        try:
            # Process in parallel for better performance
            tasks = [
                self.redis_sink.process_event(enriched_event),
                self.bigquery_sink.add_to_batch(enriched_event),
                self.external_sink.send_event(enriched_event)
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Update metrics
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            self.processed_count += 1
            self.last_processed_time = datetime.utcnow()
            
            # Keep only last 1000 processing times for moving average
            if len(self.processing_times) > 1000:
                self.processing_times = self.processing_times[-1000:]
            
            # Log progress every 100 events
            if self.processed_count % 100 == 0:
                avg_processing_time = sum(self.processing_times) / len(self.processing_times)
                logger.info(
                    f"Processed {self.processed_count} events. "
                    f"Avg processing time: {avg_processing_time:.3f}s"
                )
                
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error processing event {enriched_event.id}: {e}")
    
    async def process_batch(self, events: List[dict]):
        """Process a batch of events."""
        if not events:
            return
        
        enriched_events = []
        
        # Enrich all events
        for raw_event in events:
            enriched = self.enrich_event(raw_event)
            if enriched:
                enriched_events.append(enriched)
        
        if not enriched_events:
            return
        
        logger.info(f"Processing batch of {len(enriched_events)} events")
        
        # Process events in parallel
        tasks = [self.process_event(event) for event in enriched_events]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flush batched sinks
        await self.bigquery_sink.flush_batch()
    
    async def run(self):
        """Run the main processing loop."""
        self.running = True
        logger.info("Starting stream processor")
        
        try:
            while self.running:
                # Poll for messages
                message_pack = self.consumer.poll(timeout_ms=1000)
                
                if not message_pack:
                    # No messages, check if we should flush pending batches
                    current_time = time.time()
                    if (current_time - self.last_batch_time) > settings.processing.processing_interval_seconds:
                        if self.batch_buffer:
                            await self.process_batch(self.batch_buffer)
                            self.batch_buffer.clear()
                            self.last_batch_time = current_time
                    continue
                
                # Process messages
                for topic_partition, messages in message_pack.items():
                    for message in messages:
                        try:
                            # Add to batch buffer
                            self.batch_buffer.append(message.value)
                            
                            # Process batch if it's full or time-based trigger
                            current_time = time.time()
                            should_process = (
                                len(self.batch_buffer) >= settings.processing.batch_size or
                                (current_time - self.last_batch_time) > settings.processing.processing_interval_seconds
                            )
                            
                            if should_process:
                                await self.process_batch(self.batch_buffer)
                                self.batch_buffer.clear()
                                self.last_batch_time = current_time
                                
                                # Commit offsets after successful processing
                                if settings.processing.enable_exactly_once:
                                    self.consumer.commit()
                                    
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                            self.error_count += 1
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Stream processor error: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up stream processor")
        
        self.running = False
        
        # Process any remaining events in buffer
        if self.batch_buffer:
            await self.process_batch(self.batch_buffer)
        
        # Close sinks
        await self.bigquery_sink.close()
        await self.redis_sink.close()
        await self.external_sink.close()
        
        # Close Kafka consumer
        if self.consumer:
            self.consumer.close()
        
        # Close database
        if self.db_engine:
            self.db_engine.dispose()
    
    def get_metrics(self) -> Dict:
        """Get processing metrics."""
        avg_processing_time = (
            sum(self.processing_times) / len(self.processing_times)
            if self.processing_times else 0
        )
        
        return {
            'processed_count': self.processed_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.processed_count, 1),
            'avg_processing_time_seconds': avg_processing_time,
            'last_processed_time': self.last_processed_time.isoformat() if self.last_processed_time else None,
            'batch_buffer_size': len(self.batch_buffer),
            'is_running': self.running
        }


class BackfillProcessor:
    """Processor for backfilling historical data."""
    
    def __init__(self):
        self.stream_processor = StreamProcessor()
    
    async def backfill_date_range(self, start_date: str, end_date: str):
        """Backfill data for a specific date range."""
        logger.info(f"Starting backfill from {start_date} to {end_date}")
        
        await self.stream_processor.initialize()
        
        try:
            with self.stream_processor.db_session() as session:
                # Fetch events in batches
                offset = 0
                batch_size = settings.backfill.batch_size
                
                while True:
                    result = session.execute(
                        text("""
                            SELECT ee.*, c.slug, c.title, c.content_type, c.length_seconds
                            FROM engagement_events ee
                            LEFT JOIN content c ON ee.content_id = c.id
                            WHERE ee.event_ts >= :start_date 
                            AND ee.event_ts < :end_date
                            ORDER BY ee.event_ts
                            LIMIT :limit OFFSET :offset
                        """),
                        {
                            'start_date': start_date,
                            'end_date': end_date,
                            'limit': batch_size,
                            'offset': offset
                        }
                    )
                    
                    rows = result.fetchall()
                    if not rows:
                        break
                    
                    # Convert to enriched events
                    enriched_events = []
                    for row in rows:
                        try:
                            enriched = EnrichedEngagementEvent(
                                id=row.id,
                                content_id=row.content_id,
                                user_id=row.user_id,
                                event_type=row.event_type,
                                event_ts=row.event_ts,
                                duration_ms=row.duration_ms,
                                device=row.device,
                                raw_payload=row.raw_payload,
                                slug=row.slug,
                                title=row.title,
                                content_type=row.content_type,
                                length_seconds=row.length_seconds
                            )
                            enriched_events.append(enriched)
                        except Exception as e:
                            logger.error(f"Error creating enriched event: {e}")
                    
                    # Process batch
                    if enriched_events:
                        tasks = [self.stream_processor.process_event(event) for event in enriched_events]
                        await asyncio.gather(*tasks, return_exceptions=True)
                        
                        await self.stream_processor.bigquery_sink.flush_batch()
                        
                        logger.info(f"Processed backfill batch: {len(enriched_events)} events")
                    
                    offset += batch_size
                    
                    # Small delay to avoid overwhelming the system
                    await asyncio.sleep(0.1)
                    
        finally:
            await self.stream_processor.cleanup()


async def main():
    """Main function for running the stream processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Engagement Events Stream Processor')
    parser.add_argument('--mode', choices=['stream', 'backfill'], 
                       default='stream', help='Processing mode')
    parser.add_argument('--start-date', help='Start date for backfill (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date for backfill (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Configure logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    if args.mode == 'stream':
        processor = StreamProcessor()
        try:
            await processor.initialize()
            await processor.run()
        except KeyboardInterrupt:
            logger.info("Stopping stream processor")
        finally:
            await processor.cleanup()
            
    elif args.mode == 'backfill':
        if not args.start_date or not args.end_date:
            logger.error("Start date and end date are required for backfill mode")
            return
            
        processor = BackfillProcessor()
        await processor.backfill_date_range(args.start_date, args.end_date)


if __name__ == "__main__":
    asyncio.run(main())
