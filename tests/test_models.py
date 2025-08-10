"""
Tests simples pour valider le code du pipeline de streaming
"""

import pytest
from datetime import datetime
from uuid import uuid4, UUID
from decimal import Decimal

from src.models import (
    ContentModel,
    EngagementEventModel,
    EnrichedEngagementEvent,
    BigQueryRecord,
    ExternalSystemPayload
)


def test_content_model():
    """Test du modèle Content"""
    content = ContentModel(
        id=uuid4(),
        slug="test-podcast",
        title="Test Podcast",
        content_type="podcast",
        length_seconds=3600,
        publish_ts=datetime.utcnow()
    )
    assert content.content_type == "podcast"
    assert content.length_seconds == 3600


def test_engagement_event_model():
    """Test du modèle EngagementEvent"""
    event = EngagementEventModel(
        id=1,
        content_id=uuid4(),
        user_id=uuid4(),
        event_type="play",
        event_ts=datetime.utcnow(),
        duration_ms=5000,
        device="ios"
    )
    assert event.event_type == "play"
    assert event.duration_ms == 5000


def test_enriched_engagement_event():
    """Test du modèle EnrichedEngagementEvent avec calculs"""
    event = EnrichedEngagementEvent(
        id=1,
        content_id=uuid4(),
        user_id=uuid4(),
        event_type="play",
        event_ts=datetime.utcnow(),
        duration_ms=30000,  # 30 secondes
        device="ios",
        slug="test-content",
        title="Test Content",
        content_type="video",
        length_seconds=120  # 2 minutes
    )
    
    # Vérifier les calculs automatiques
    assert event.engagement_seconds == Decimal('30.00')
    assert event.engagement_pct == Decimal('25.00')  # 30/120 * 100


def test_bigquery_record_conversion():
    """Test de conversion vers BigQueryRecord"""
    enriched_event = EnrichedEngagementEvent(
        id=1,
        content_id=uuid4(),
        user_id=uuid4(),
        event_type="finish",
        event_ts=datetime.utcnow(),
        duration_ms=60000,
        device="web-chrome",
        slug="test-video",
        title="Test Video",
        content_type="video",
        length_seconds=300
    )
    
    bq_record = BigQueryRecord.from_enriched_event(enriched_event)
    
    assert bq_record.event_type == "finish"
    assert bq_record.engagement_seconds == 60.0
    assert bq_record.engagement_pct == 20.0  # 60/300 * 100


def test_external_system_payload():
    """Test de création du payload pour système externe"""
    enriched_event = EnrichedEngagementEvent(
        id=1,
        content_id=uuid4(),
        user_id=uuid4(),
        event_type="click",
        event_ts=datetime.utcnow(),
        duration_ms=None,
        device="android",
        slug="newsletter-1",
        title="Newsletter 1",
        content_type="newsletter",
        length_seconds=None
    )
    
    payload = ExternalSystemPayload.from_enriched_event(enriched_event)
    
    assert payload.event_type == "click"
    assert payload.metadata["content_type"] == "newsletter"
    assert payload.metadata["engagement_seconds"] is None


if __name__ == "__main__":
    # Exécuter les tests
    print("🧪 Exécution des tests...")
    
    try:
        test_content_model()
        print("✅ test_content_model - PASSÉ")
        
        test_engagement_event_model()
        print("✅ test_engagement_event_model - PASSÉ")
        
        test_enriched_engagement_event()
        print("✅ test_enriched_engagement_event - PASSÉ")
        
        test_bigquery_record_conversion()
        print("✅ test_bigquery_record_conversion - PASSÉ")
        
        test_external_system_payload()
        print("✅ test_external_system_payload - PASSÉ")
        
        print("\n🎉 Tous les tests sont passés avec succès!")
        
    except Exception as e:
        print(f"❌ Erreur dans les tests: {e}")
        exit(1)
