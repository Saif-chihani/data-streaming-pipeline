"""
Health monitoring and metrics for the streaming pipeline.
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from sqlalchemy import create_engine, text

from config import settings
from sinks.bigquery_sink import BigQuerySink
from sinks.external_sink import ExternalSystemSink
from sinks.redis_sink import RedisSink

logger = structlog.get_logger(__name__)

# Prometheus metrics
EVENTS_PROCESSED = Counter('events_processed_total', 'Total number of events processed')
EVENTS_FAILED = Counter('events_failed_total', 'Total number of events that failed processing')
PROCESSING_TIME = Histogram('event_processing_seconds', 'Time spent processing events')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Number of active connections')
QUEUE_SIZE = Gauge('queue_size', 'Current queue size')

app = FastAPI(title="Engagement Streaming Pipeline Monitor", version="1.0.0")


class HealthMonitor:
    """Health monitoring for the streaming pipeline."""
    
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.last_health_check = None
        self.db_engine = create_engine(settings.database.url)
        self.redis_sink = RedisSink()
        self.bigquery_sink = BigQuerySink()
        self.external_sink = ExternalSystemSink()
        
    async def initialize(self):
        """Initialize health monitor."""
        await self.redis_sink.initialize()
        await self.bigquery_sink.initialize()
        await self.external_sink.initialize()
        
    async def check_database_health(self) -> Dict:
        """Check PostgreSQL database health."""
        try:
            with self.db_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
                
                # Check recent events
                result = conn.execute(text("""
                    SELECT COUNT(*) as count, MAX(event_ts) as last_event
                    FROM engagement_events 
                    WHERE event_ts >= NOW() - INTERVAL '5 minutes'
                """))
                row = result.fetchone()
                
                return {
                    'status': 'healthy',
                    'connection': 'ok',
                    'recent_events': row.count,
                    'last_event': row.last_event.isoformat() if row.last_event else None
                }
                
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def check_redis_health(self) -> Dict:
        """Check Redis health."""
        try:
            if not self.redis_sink.redis_client:
                return {'status': 'unhealthy', 'error': 'Redis client not initialized'}
                
            # Test basic operations
            await self.redis_sink.redis_client.ping()
            
            # Check data freshness
            top_content = await self.redis_sink.get_top_content(limit=5)
            
            return {
                'status': 'healthy',
                'connection': 'ok',
                'top_content_count': len(top_content),
                'last_updated': top_content[0].get('last_updated') if top_content else None
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def check_bigquery_health(self) -> Dict:
        """Check BigQuery health."""
        try:
            if not self.bigquery_sink.client:
                return {'status': 'degraded', 'error': 'BigQuery client not available'}
                
            # Test connection with a simple query
            query = f"""
            SELECT COUNT(*) as count 
            FROM `{settings.bigquery.project_id}.{settings.bigquery.dataset_id}.{settings.bigquery.table_id}`
            WHERE DATE(event_timestamp) = CURRENT_DATE()
            LIMIT 1
            """
            
            query_job = self.bigquery_sink.client.query(query)
            result = list(query_job.result())
            
            return {
                'status': 'healthy',
                'connection': 'ok',
                'today_events': result[0][0] if result else 0
            }
            
        except Exception as e:
            return {
                'status': 'degraded',
                'error': str(e)
            }
    
    async def check_external_system_health(self) -> Dict:
        """Check external system health."""
        try:
            if not self.external_sink.client:
                return {'status': 'degraded', 'error': 'External system client not available'}
                
            is_connected = await self.external_sink.test_connection()
            stats = await self.external_sink.get_stats()
            
            return {
                'status': 'healthy' if is_connected else 'degraded',
                'connection': 'ok' if is_connected else 'failed',
                **stats
            }
            
        except Exception as e:
            return {
                'status': 'degraded',
                'error': str(e)
            }
    
    async def check_kafka_health(self) -> Dict:
        """Check Kafka health."""
        try:
            # This would require a Kafka admin client
            # For now, we'll assume healthy if no recent errors
            return {
                'status': 'healthy',
                'note': 'Kafka health check not implemented yet'
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def get_system_metrics(self) -> Dict:
        """Get system-wide metrics."""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        # Get recent top content from Redis
        top_content = await self.redis_sink.get_top_content(limit=5)
        
        # Get database stats
        with self.db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_events,
                    COUNT(DISTINCT content_id) as unique_content,
                    COUNT(DISTINCT user_id) as unique_users,
                    MAX(event_ts) as last_event
                FROM engagement_events 
                WHERE event_ts >= NOW() - INTERVAL '1 hour'
            """))
            db_stats = result.fetchone()
        
        return {
            'uptime_seconds': uptime,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'database_stats': {
                'events_last_hour': db_stats.total_events,
                'unique_content_last_hour': db_stats.unique_content,
                'unique_users_last_hour': db_stats.unique_users,
                'last_event': db_stats.last_event.isoformat() if db_stats.last_event else None
            },
            'top_content': top_content[:3]  # Top 3 for overview
        }
    
    async def perform_health_check(self) -> Dict:
        """Perform comprehensive health check."""
        self.last_health_check = datetime.utcnow()
        
        health_checks = await asyncio.gather(
            self.check_database_health(),
            self.check_redis_health(),
            self.check_bigquery_health(),
            self.check_external_system_health(),
            self.check_kafka_health(),
            return_exceptions=True
        )
        
        database_health, redis_health, bigquery_health, external_health, kafka_health = health_checks
        
        # Determine overall status
        all_statuses = [
            database_health.get('status', 'unknown'),
            redis_health.get('status', 'unknown'),
            bigquery_health.get('status', 'unknown'),
            external_health.get('status', 'unknown'),
            kafka_health.get('status', 'unknown')
        ]
        
        if 'unhealthy' in all_statuses:
            overall_status = 'unhealthy'
        elif 'degraded' in all_statuses:
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'
        
        return {
            'overall_status': overall_status,
            'timestamp': self.last_health_check.isoformat(),
            'components': {
                'database': database_health,
                'redis': redis_health,
                'bigquery': bigquery_health,
                'external_system': external_health,
                'kafka': kafka_health
            }
        }


# Global health monitor instance
health_monitor = HealthMonitor()


@app.on_event("startup")
async def startup_event():
    """Initialize health monitor on startup."""
    await health_monitor.initialize()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        health_data = await health_monitor.perform_health_check()
        
        if health_data['overall_status'] == 'healthy':
            status_code = 200
        elif health_data['overall_status'] == 'degraded':
            status_code = 200  # Still operational
        else:
            status_code = 503  # Service unavailable
            
        return JSONResponse(content=health_data, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={
                'overall_status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            },
            status_code=503
        )


@app.get("/metrics")
async def get_metrics():
    """Get system metrics."""
    try:
        metrics = await health_monitor.get_system_metrics()
        return JSONResponse(content=metrics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics/prometheus")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


@app.get("/top-content")
async def get_top_content():
    """Get top performing content."""
    try:
        top_content = await health_monitor.redis_sink.get_top_content(limit=20)
        return JSONResponse(content={'top_content': top_content})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/content/{content_id}/stats")
async def get_content_stats(content_id: str):
    """Get stats for a specific content item."""
    try:
        from uuid import UUID
        content_uuid = UUID(content_id)
        stats = await health_monitor.redis_sink.get_content_stats(content_uuid)
        return JSONResponse(content=stats)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        'service': 'Engagement Streaming Pipeline Monitor',
        'version': '1.0.0',
        'status': 'running',
        'endpoints': {
            'health': '/health',
            'metrics': '/metrics',
            'prometheus': '/metrics/prometheus',
            'top_content': '/top-content',
            'content_stats': '/content/{content_id}/stats'
        }
    }


if __name__ == "__main__":
    import uvicorn
    
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
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=settings.monitoring.metrics_port,
        log_level=settings.monitoring.log_level.lower()
    )
