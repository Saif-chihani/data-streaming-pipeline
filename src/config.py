"""
Configuration settings for the engagement streaming pipeline.
"""

from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    
    url: str = Field("postgresql://postgres:postgres@localhost:5432/engagement_db", env="DATABASE_URL")
    pool_size: int = Field(10, env="DB_POOL_SIZE")
    max_overflow: int = Field(20, env="DB_MAX_OVERFLOW")
    echo: bool = Field(False, env="DB_ECHO")
    
    class Config:
        env_prefix = "DB_"


class KafkaSettings(BaseSettings):
    """Kafka configuration."""
    
    bootstrap_servers: str = Field("localhost:9092", env="KAFKA_BOOTSTRAP_SERVERS")
    topic_engagement_events: str = Field("engagement-events", env="KAFKA_TOPIC_ENGAGEMENT_EVENTS")
    consumer_group_id: str = Field("engagement-processor", env="KAFKA_CONSUMER_GROUP_ID")
    auto_offset_reset: str = Field("earliest", env="KAFKA_AUTO_OFFSET_RESET")
    enable_auto_commit: bool = Field(False, env="KAFKA_ENABLE_AUTO_COMMIT")
    session_timeout_ms: int = Field(30000, env="KAFKA_SESSION_TIMEOUT_MS")
    max_poll_records: int = Field(500, env="KAFKA_MAX_POLL_RECORDS")
    
    # Producer settings
    acks: str = Field("all", env="KAFKA_ACKS")
    retries: int = Field(3, env="KAFKA_RETRIES")
    batch_size: int = Field(16384, env="KAFKA_BATCH_SIZE")
    linger_ms: int = Field(5, env="KAFKA_LINGER_MS")
    
    # Transactional settings for exactly-once
    transactional_id: Optional[str] = Field(None, env="KAFKA_TRANSACTIONAL_ID")
    enable_idempotence: bool = Field(True, env="KAFKA_ENABLE_IDEMPOTENCE")
    
    class Config:
        env_prefix = "KAFKA_"


class RedisSettings(BaseSettings):
    """Redis configuration."""
    
    url: str = Field("redis://localhost:6379", env="REDIS_URL")
    db: int = Field(0, env="REDIS_DB")
    max_connections: int = Field(20, env="REDIS_MAX_CONNECTIONS")
    socket_keepalive: bool = Field(True, env="REDIS_SOCKET_KEEPALIVE")
    socket_keepalive_options: Dict = Field(default_factory=dict, env="REDIS_SOCKET_KEEPALIVE_OPTIONS")
    
    # Aggregation settings
    aggregation_window_minutes: int = Field(10, env="REDIS_AGGREGATION_WINDOW_MINUTES")
    top_content_key: str = Field("top_content_last_10min", env="REDIS_TOP_CONTENT_KEY")
    aggregation_ttl_seconds: int = Field(900, env="REDIS_AGGREGATION_TTL_SECONDS")
    
    class Config:
        env_prefix = "REDIS_"


class BigQuerySettings(BaseSettings):
    """BigQuery configuration."""
    
    credentials_path: str = Field("config/bigquery-credentials.json", env="GOOGLE_APPLICATION_CREDENTIALS")
    project_id: str = Field("your-project-id", env="BIGQUERY_PROJECT_ID")
    dataset_id: str = Field("engagement_analytics", env="BIGQUERY_DATASET_ID")
    table_id: str = Field("enriched_events", env="BIGQUERY_TABLE_ID")
    location: str = Field("US", env="BIGQUERY_LOCATION")
    
    # Batch settings
    batch_size: int = Field(1000, env="BIGQUERY_BATCH_SIZE")
    max_batch_time_seconds: int = Field(30, env="BIGQUERY_MAX_BATCH_TIME_SECONDS")
    
    class Config:
        env_prefix = "BIGQUERY_"


class ExternalSystemSettings(BaseSettings):
    """External system configuration."""
    
    url: str = Field("https://httpbin.org/post", env="EXTERNAL_SYSTEM_URL")
    timeout: int = Field(30, env="EXTERNAL_SYSTEM_TIMEOUT")
    retry_attempts: int = Field(3, env="EXTERNAL_SYSTEM_RETRY_ATTEMPTS")
    headers: Dict[str, str] = Field(default_factory=dict, env="EXTERNAL_SYSTEM_HEADERS")
    
    class Config:
        env_prefix = "EXTERNAL_SYSTEM_"


class ProcessingSettings(BaseSettings):
    """Processing configuration."""
    
    batch_size: int = Field(100, env="BATCH_SIZE")
    processing_interval_seconds: int = Field(1, env="PROCESSING_INTERVAL_SECONDS")
    max_processing_time_seconds: int = Field(300, env="MAX_PROCESSING_TIME_SECONDS")
    enable_exactly_once: bool = Field(True, env="ENABLE_EXACTLY_ONCE")
    
    # Parallel processing
    max_workers: int = Field(4, env="MAX_WORKERS")
    queue_size: int = Field(1000, env="QUEUE_SIZE")
    
    class Config:
        env_prefix = "PROCESSING_"


class MonitoringSettings(BaseSettings):
    """Monitoring configuration."""
    
    metrics_port: int = Field(8080, env="METRICS_PORT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    enable_health_checks: bool = Field(True, env="ENABLE_HEALTH_CHECKS")
    health_check_interval: int = Field(30, env="HEALTH_CHECK_INTERVAL")
    
    class Config:
        env_prefix = "MONITORING_"


class DataGeneratorSettings(BaseSettings):
    """Data generator configuration."""
    
    generation_interval: int = Field(2, env="GENERATION_INTERVAL")
    events_per_batch: int = Field(5, env="EVENTS_PER_BATCH")
    max_events_per_day: int = Field(10000, env="MAX_EVENTS_PER_DAY")
    
    class Config:
        env_prefix = "GENERATOR_"


class BackfillSettings(BaseSettings):
    """Backfill configuration."""
    
    batch_size: int = Field(1000, env="BACKFILL_BATCH_SIZE")
    start_date: str = Field("2025-01-01", env="BACKFILL_START_DATE")
    end_date: str = Field("2025-08-10", env="BACKFILL_END_DATE")
    parallel_workers: int = Field(2, env="BACKFILL_PARALLEL_WORKERS")
    
    class Config:
        env_prefix = "BACKFILL_"


class Settings(BaseSettings):
    """Main application settings."""
    
    # Component settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    bigquery: BigQuerySettings = Field(default_factory=BigQuerySettings)
    external_system: ExternalSystemSettings = Field(default_factory=ExternalSystemSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    data_generator: DataGeneratorSettings = Field(default_factory=DataGeneratorSettings)
    backfill: BackfillSettings = Field(default_factory=BackfillSettings)
    
    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    debug: bool = Field(False, env="DEBUG")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore les champs supplémentaires


# Global settings instance
settings = Settings()
