"""
BigQuery sink for analytics and reporting.
"""

import asyncio
import os
from datetime import datetime
from typing import List, Optional

import structlog
from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from google.oauth2 import service_account

from config import settings
from models import BigQueryRecord, EnrichedEngagementEvent

logger = structlog.get_logger(__name__)


class BigQuerySink:
    """BigQuery sink for analytics data."""
    
    def __init__(self):
        self.client: Optional[bigquery.Client] = None
        self.table_ref: Optional[bigquery.TableReference] = None
        self.batch_buffer: List[BigQueryRecord] = []
        self.batch_start_time = datetime.utcnow()
        
    async def initialize(self):
        """Initialize BigQuery client and ensure table exists."""
        logger.info("Initializing BigQuery sink")
        
        try:
            # Initialize client with credentials
            if os.path.exists(settings.bigquery.credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    settings.bigquery.credentials_path
                )
                self.client = bigquery.Client(
                    credentials=credentials,
                    project=settings.bigquery.project_id,
                    location=settings.bigquery.location
                )
            else:
                # Use default credentials (useful for GCP environments)
                logger.warning("BigQuery credentials file not found, using default credentials")
                self.client = bigquery.Client(
                    project=settings.bigquery.project_id,
                    location=settings.bigquery.location
                )
            
            # Ensure dataset and table exist
            await self._ensure_dataset_exists()
            await self._ensure_table_exists()
            
            logger.info("BigQuery sink initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery: {e}")
            # Don't raise - we'll handle this gracefully
            self.client = None
    
    async def _ensure_dataset_exists(self):
        """Ensure the BigQuery dataset exists."""
        if not self.client:
            return
            
        dataset_id = f"{settings.bigquery.project_id}.{settings.bigquery.dataset_id}"
        
        try:
            self.client.get_dataset(dataset_id)
            logger.info(f"Dataset {dataset_id} already exists")
        except NotFound:
            # Create dataset
            dataset = bigquery.Dataset(dataset_id)
            dataset.location = settings.bigquery.location
            dataset.description = "Engagement analytics dataset"
            
            dataset = self.client.create_dataset(dataset, timeout=30)
            logger.info(f"Created dataset {dataset_id}")
    
    async def _ensure_table_exists(self):
        """Ensure the BigQuery table exists with proper schema."""
        if not self.client:
            return
            
        dataset_ref = self.client.dataset(settings.bigquery.dataset_id)
        self.table_ref = dataset_ref.table(settings.bigquery.table_id)
        
        try:
            self.client.get_table(self.table_ref)
            logger.info(f"Table {self.table_ref} already exists")
        except NotFound:
            # Define schema
            schema = [
                bigquery.SchemaField("event_id", "INTEGER", mode="REQUIRED"),
                bigquery.SchemaField("content_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("event_timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("duration_ms", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("engagement_seconds", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("engagement_pct", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("device", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("content_slug", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("content_title", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("content_type", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("content_length_seconds", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("raw_payload", "JSON", mode="NULLABLE"),
                bigquery.SchemaField("processed_timestamp", "TIMESTAMP", mode="REQUIRED"),
            ]
            
            # Create table
            table = bigquery.Table(self.table_ref, schema=schema)
            table.description = "Enriched engagement events for analytics"
            
            # Partitioning by event_timestamp for better performance
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="event_timestamp"
            )
            
            # Clustering for better performance
            table.clustering_fields = ["content_type", "event_type", "content_id"]
            
            table = self.client.create_table(table, timeout=30)
            logger.info(f"Created table {self.table_ref}")
    
    async def add_to_batch(self, event: EnrichedEngagementEvent):
        """Add event to batch buffer."""
        if not self.client:
            logger.warning("BigQuery client not available, skipping event")
            return
        
        try:
            record = BigQueryRecord.from_enriched_event(event)
            self.batch_buffer.append(record)
            
            # Check if we should flush the batch
            should_flush = (
                len(self.batch_buffer) >= settings.bigquery.batch_size or
                (datetime.utcnow() - self.batch_start_time).total_seconds() > settings.bigquery.max_batch_time_seconds
            )
            
            if should_flush:
                await self.flush_batch()
                
        except Exception as e:
            logger.error(f"Error adding event to BigQuery batch: {e}")
    
    async def flush_batch(self):
        """Flush the current batch to BigQuery."""
        if not self.client or not self.batch_buffer:
            return
        
        try:
            logger.info(f"Flushing batch of {len(self.batch_buffer)} events to BigQuery")
            
            # Convert records to dictionaries
            rows_to_insert = []
            for record in self.batch_buffer:
                row_dict = record.dict()
                
                # Convert datetime objects to string format for BigQuery
                if row_dict.get('event_timestamp'):
                    row_dict['event_timestamp'] = row_dict['event_timestamp'].isoformat()
                if row_dict.get('processed_timestamp'):
                    row_dict['processed_timestamp'] = row_dict['processed_timestamp'].isoformat()
                
                rows_to_insert.append(row_dict)
            
            # Insert rows
            errors = self.client.insert_rows_json(
                self.table_ref,
                rows_to_insert,
                retry=bigquery.DEFAULT_RETRY
            )
            
            if errors:
                logger.error(f"BigQuery insert errors: {errors}")
            else:
                logger.info(f"Successfully inserted {len(rows_to_insert)} rows to BigQuery")
            
            # Clear batch buffer
            self.batch_buffer.clear()
            self.batch_start_time = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error flushing batch to BigQuery: {e}")
            # Don't clear buffer on error - we'll retry on next flush
    
    async def insert_batch(self, records: List[BigQueryRecord]):
        """Insert a batch of records directly."""
        if not self.client:
            logger.warning("BigQuery client not available")
            return
        
        try:
            rows_to_insert = []
            for record in records:
                row_dict = record.dict()
                
                # Convert datetime objects
                if row_dict.get('event_timestamp'):
                    row_dict['event_timestamp'] = row_dict['event_timestamp'].isoformat()
                if row_dict.get('processed_timestamp'):
                    row_dict['processed_timestamp'] = row_dict['processed_timestamp'].isoformat()
                
                rows_to_insert.append(row_dict)
            
            errors = self.client.insert_rows_json(
                self.table_ref,
                rows_to_insert,
                retry=bigquery.DEFAULT_RETRY
            )
            
            if errors:
                logger.error(f"BigQuery batch insert errors: {errors}")
                return False
            else:
                logger.info(f"Successfully inserted {len(rows_to_insert)} rows to BigQuery")
                return True
                
        except Exception as e:
            logger.error(f"Error inserting batch to BigQuery: {e}")
            return False
    
    async def query_engagement_stats(self, start_date: str, end_date: str) -> List[dict]:
        """Query engagement statistics from BigQuery."""
        if not self.client:
            return []
        
        query = f"""
        SELECT 
            content_type,
            content_slug,
            content_title,
            COUNT(*) as total_events,
            COUNT(DISTINCT user_id) as unique_users,
            AVG(engagement_seconds) as avg_engagement_seconds,
            AVG(engagement_pct) as avg_engagement_pct,
            SUM(CASE WHEN event_type = 'finish' THEN 1 ELSE 0 END) as completion_count
        FROM `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.{settings.bigquery.table_id}`
        WHERE DATE(event_timestamp) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY content_type, content_slug, content_title
        ORDER BY total_events DESC
        LIMIT 100
        """
        
        try:
            query_job = self.client.query(query)
            results = query_job.result()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error querying BigQuery: {e}")
            return []
    
    async def query_top_content(self, hours_back: int = 24, limit: int = 10) -> List[dict]:
        """Query top performing content from BigQuery."""
        if not self.client:
            return []
        
        query = f"""
        SELECT 
            content_id,
            content_slug,
            content_title,
            content_type,
            COUNT(*) as total_events,
            COUNT(DISTINCT user_id) as unique_users,
            AVG(engagement_pct) as avg_engagement_pct,
            SUM(engagement_seconds) as total_engagement_seconds,
            SUM(CASE WHEN event_type = 'finish' THEN 1 ELSE 0 END) as completions
        FROM `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.{settings.bigquery.table_id}`
        WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)
        GROUP BY content_id, content_slug, content_title, content_type
        ORDER BY total_events DESC, avg_engagement_pct DESC
        LIMIT {limit}
        """
        
        try:
            query_job = self.client.query(query)
            results = query_job.result()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error querying top content: {e}")
            return []
    
    async def create_analytics_views(self):
        """Create useful views for analytics."""
        if not self.client:
            return
        
        views = [
            {
                'name': 'daily_engagement_summary',
                'query': f"""
                CREATE OR REPLACE VIEW `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.daily_engagement_summary` AS
                SELECT 
                    DATE(event_timestamp) as event_date,
                    content_type,
                    COUNT(*) as total_events,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT content_id) as unique_content,
                    AVG(engagement_seconds) as avg_engagement_seconds,
                    AVG(engagement_pct) as avg_engagement_pct,
                    SUM(CASE WHEN event_type = 'finish' THEN 1 ELSE 0 END) as total_completions
                FROM `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.{settings.bigquery.table_id}`
                GROUP BY event_date, content_type
                ORDER BY event_date DESC, content_type
                """
            },
            {
                'name': 'hourly_engagement_trends',
                'query': f"""
                CREATE OR REPLACE VIEW `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.hourly_engagement_trends` AS
                SELECT 
                    DATETIME_TRUNC(event_timestamp, HOUR) as hour_bucket,
                    content_type,
                    event_type,
                    COUNT(*) as event_count,
                    COUNT(DISTINCT user_id) as unique_users,
                    AVG(engagement_seconds) as avg_engagement_seconds
                FROM `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.{settings.bigquery.table_id}`
                WHERE event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                GROUP BY hour_bucket, content_type, event_type
                ORDER BY hour_bucket DESC, content_type, event_type
                """
            }
        ]
        
        for view in views:
            try:
                query_job = self.client.query(view['query'])
                query_job.result()  # Wait for completion
                logger.info(f"Created/updated view: {view['name']}")
            except Exception as e:
                logger.error(f"Error creating view {view['name']}: {e}")
    
    async def close(self):
        """Close BigQuery connection and flush remaining data."""
        if self.batch_buffer:
            await self.flush_batch()
        
        # BigQuery client doesn't need explicit closing
        logger.info("BigQuery sink closed")
