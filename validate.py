#!/usr/bin/env python3
"""
Script de validation simple pour tester la syntaxe du code
"""

import sys
import os

# Ajouter le chemin src au PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test des imports principaux"""
    try:
        print("🔍 Test des imports...")
        
        # Test models.py
        print("   - Importation des modèles...", end=" ")
        from models import ContentModel, EngagementEventModel, EnrichedEngagementEvent
        print("✅")
        
        # Test config.py  
        print("   - Importation de la configuration...", end=" ")
        from config import Settings
        print("✅")
        
        print("\n✅ Tous les imports sont corrects!")
        return True
        
    except ImportError as e:
        print(f"\n❌ Erreur d'import: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        return False

def test_basic_functionality():
    """Test des fonctionnalités de base"""
    try:
        print("\n🧪 Test des fonctionnalités de base...")
        
        from models import EnrichedEngagementEvent
        from uuid import uuid4
        from datetime import datetime
        
        # Créer un événement d'exemple
        event = EnrichedEngagementEvent(
            id=1,
            content_id=uuid4(),
            user_id=uuid4(),
            event_type="play",
            event_ts=datetime.utcnow(),
            duration_ms=30000,
            device="ios",
            slug="test-content",
            title="Test Content",
            content_type="video",
            length_seconds=120
        )
        
        print(f"   - Événement créé: {event.event_type}")
        print(f"   - Engagement calculé: {event.engagement_seconds} secondes")
        print(f"   - Pourcentage: {event.engagement_pct}%")
        
        print("\n✅ Fonctionnalités de base OK!")
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur dans les fonctionnalités: {e}")
        return False

def validate_docker_files():
    """Valider la présence des fichiers Docker"""
    print("\n🐳 Validation des fichiers Docker...")
    
    required_files = [
        "docker-compose.yml",
        "docker/Dockerfile.generator",
        "docker/Dockerfile.processor",
        ".env",
        "requirements.txt"
    ]
    
    all_good = True
    for file in required_files:
        if os.path.exists(file):
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ {file} - MANQUANT")
            all_good = False
    
    return all_good

def main():
    """Fonction principale de validation"""
    print("🚀 Validation du pipeline de streaming d'engagement\n")
    
    success = True
    
    # Test des imports
    if not test_imports():
        success = False
    
    # Test des fonctionnalités
    if not test_basic_functionality():
        success = False
    
    # Validation Docker
    if not validate_docker_files():
        success = False
    
    if success:
        print("\n🎉 Validation complète réussie!")
        print("💡 Le projet est prêt à être testé avec Docker")
        return 0
    else:
        print("\n❌ Validation échouée")
        print("🔧 Veuillez corriger les erreurs avant de continuer")
        return 1

if __name__ == "__main__":
    sys.exit(main())
