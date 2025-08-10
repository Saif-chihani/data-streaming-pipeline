"""
Data generator for creating realistic engagement events.
"""

import asyncio
import json
import random
import time
from datetime import datetime, timedelta
from typing import List
from uuid import UUID, uuid4

import psycopg2
import structlog
from kafka import KafkaProducer
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import settings
from models import EngagementEventModel

logger = structlog.get_logger(__name__)


class DataGenerator:
    """Generates realistic engagement events for testing."""
    
    def __init__(self):
        self.db_engine = create_engine(settings.database.url)
        self.db_session = sessionmaker(bind=self.db_engine)
        
        # Kafka producer for CDC simulation
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=settings.kafka.bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
            key_serializer=lambda k: str(k).encode('utf-8') if k else None,
            acks='all',
            retries=3,
            batch_size=16384,
            linger_ms=5
        )
        
        self.content_ids: List[UUID] = []
        self.user_pool: List[UUID] = []
        self.event_types = ['play', 'pause', 'finish', 'click']
        self.devices = ['ios', 'android', 'web-chrome', 'web-safari', 'web-firefox', 'web-edge']
        
        # Event type probabilities
        self.event_type_weights = {
            'play': 0.4,
            'pause': 0.25,
            'finish': 0.2,
            'click': 0.15
        }
    
    async def initialize(self):
        """Initialize the data generator."""
        logger.info("Initializing data generator")
        
        # Load content IDs
        with self.db_session() as session:
            result = session.execute(text("SELECT id FROM content"))
            self.content_ids = [row[0] for row in result]
        
        # Generate a pool of user IDs for more realistic patterns
        self.user_pool = [uuid4() for _ in range(1000)]
        
        logger.info(f"Loaded {len(self.content_ids)} content items and {len(self.user_pool)} users")
    
    def generate_engagement_event(self) -> dict:
        """Generate a single realistic engagement event."""
        content_id = random.choice(self.content_ids)
        user_id = random.choice(self.user_pool)
        
        # Weighted random event type selection
        event_type = random.choices(
            list(self.event_type_weights.keys()),
            weights=list(self.event_type_weights.values())
        )[0]
        
        device = random.choice(self.devices)
        
        # Generate duration based on event type and device
        duration_ms = None
        if event_type in ['play', 'pause']:
            # Shorter durations for mobile, longer for web
            base_duration = 15000 if device.startswith('web') else 8000
            duration_ms = random.randint(1000, base_duration)
        elif event_type == 'finish':
            # Longer durations for finish events
            base_duration = 180000 if device.startswith('web') else 120000
            duration_ms = random.randint(30000, base_duration)
        
        # Generate realistic raw payload
        raw_payload = {
            'session_id': str(uuid4()),
            'ip_address': f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}",
            'user_agent': device,
            'referrer': random.choice([
                'https://google.com',
                'https://twitter.com',
                'https://linkedin.com',
                'direct',
                None
            ]),
            'screen_resolution': random.choice([
                '1920x1080',
                '1366x768',
                '375x667',  # iPhone
                '414x896',  # iPhone X+
                '360x640'   # Android
            ]) if device != 'podcast' else None
        }
        
        # Add some randomness to timestamp (within last few seconds)
        event_ts = datetime.utcnow() - timedelta(seconds=random.randint(0, 10))
        
        return {
            'content_id': content_id,
            'user_id': user_id,
            'event_type': event_type,
            'event_ts': event_ts,
            'duration_ms': duration_ms,
            'device': device,
            'raw_payload': raw_payload
        }
    
    def insert_event_to_db(self, event_data: dict) -> int:
        """Insert event to database and return the event ID."""
        with self.db_session() as session:
            result = session.execute(
                text("""
                    INSERT INTO engagement_events 
                    (content_id, user_id, event_type, event_ts, duration_ms, device, raw_payload)
                    VALUES (:content_id, :user_id, :event_type, :event_ts, :duration_ms, :device, :raw_payload)
                    RETURNING id
                """),
                event_data
            )
            event_id = result.scalar()
            session.commit()
            return event_id
    
    def publish_to_kafka(self, event_data: dict, event_id: int):
        """Publish event to Kafka topic (simulating CDC)."""
        # Add event ID to the data
        kafka_event = {**event_data, 'id': event_id}
        
        try:
            # Use content_id as partition key for better distribution
            self.kafka_producer.send(
                topic=settings.kafka.topic_engagement_events,
                key=str(event_data['content_id']),
                value=kafka_event
            )
            self.kafka_producer.flush()
        except Exception as e:
            logger.error(f"Failed to publish event to Kafka: {e}")
    
    async def generate_batch(self, batch_size: int = None) -> List[dict]:
        """Generate a batch of events."""
        batch_size = batch_size or settings.data_generator.events_per_batch
        events = []
        
        for _ in range(batch_size):
            event_data = self.generate_engagement_event()
            
            # Insert to database
            event_id = self.insert_event_to_db(event_data)
            
            # Publish to Kafka (simulating CDC)
            self.publish_to_kafka(event_data, event_id)
            
            events.append({**event_data, 'id': event_id})
            
            # Small delay to avoid overwhelming the system
            await asyncio.sleep(0.1)
        
        return events
    
    async def generate_continuous(self):
        """Generate events continuously."""
        logger.info("Starting continuous event generation")
        
        events_generated = 0
        max_events = settings.data_generator.max_events_per_day
        
        while events_generated < max_events:
            try:
                batch = await self.generate_batch()
                events_generated += len(batch)
                
                logger.info(
                    f"Generated batch of {len(batch)} events. "
                    f"Total: {events_generated}/{max_events}"
                )
                
                # Wait before next batch
                await asyncio.sleep(settings.data_generator.generation_interval)
                
            except Exception as e:
                logger.error(f"Error generating events: {e}")
                await asyncio.sleep(5)  # Wait longer on error
    
    async def generate_historical_data(self, days_back: int = 7):
        """Generate historical data for testing backfill."""
        logger.info(f"Generating historical data for {days_back} days")
        
        current_time = datetime.utcnow()
        
        for day in range(days_back, 0, -1):
            day_start = current_time - timedelta(days=day)
            events_for_day = random.randint(100, 500)  # Random events per day
            
            for _ in range(events_for_day):
                event_data = self.generate_engagement_event()
                
                # Set timestamp to historical date
                event_data['event_ts'] = day_start + timedelta(
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                    seconds=random.randint(0, 59)
                )
                
                event_id = self.insert_event_to_db(event_data)
                
                # Don't publish historical events to Kafka (they're already "processed")
                
            logger.info(f"Generated {events_for_day} events for {day_start.date()}")
    
    def close(self):
        """Close connections."""
        if self.kafka_producer:
            self.kafka_producer.close()
        if self.db_engine:
            self.db_engine.dispose()


async def main():
    """Main function for running the data generator."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Engagement Events Data Generator')
    parser.add_argument('--mode', choices=['continuous', 'batch', 'historical'], 
                       default='continuous', help='Generation mode')
    parser.add_argument('--batch-size', type=int, default=10, 
                       help='Batch size for batch mode')
    parser.add_argument('--historical-days', type=int, default=7,
                       help='Days of historical data to generate')
    
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
    
    generator = DataGenerator()
    
    try:
        await generator.initialize()
        
        if args.mode == 'continuous':
            await generator.generate_continuous()
        elif args.mode == 'batch':
            batch = await generator.generate_batch(args.batch_size)
            logger.info(f"Generated batch of {len(batch)} events")
        elif args.mode == 'historical':
            await generator.generate_historical_data(args.historical_days)
            
    except KeyboardInterrupt:
        logger.info("Stopping data generator")
    finally:
        generator.close()


if __name__ == "__main__":
    asyncio.run(main())
