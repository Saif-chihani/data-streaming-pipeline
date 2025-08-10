"""
Sinks package for the engagement streaming pipeline.
"""

from .bigquery_sink import BigQuerySink
from .external_sink import ExternalSystemSink
from .redis_sink import RedisSink

__all__ = ['BigQuerySink', 'ExternalSystemSink', 'RedisSink']
