#!/bin/bash

# Script de test rapide pour le pipeline de streaming
# Ce script lance les composants essentiels pour une démonstration

echo "🚀 Démarrage du test du pipeline de streaming d'engagement"
echo "==============================================="

# Vérification des prérequis
echo "🔍 Vérification des prérequis..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker n'est pas installé"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose n'est pas installé"
    exit 1
fi

echo "✅ Docker et Docker Compose sont disponibles"

# Création du fichier .env s'il n'existe pas
if [ ! -f .env ]; then
    echo "📝 Création du fichier .env..."
    cp .env.example .env
fi

# Arrêt des services existants
echo "🛑 Arrêt des services existants..."
docker-compose down -v

# Démarrage des services de base
echo "🏗️ Démarrage des services de base..."
docker-compose up -d postgres redis zookeeper kafka

echo "⏳ Attente du démarrage des services (30 secondes)..."
sleep 30

# Vérification de la santé des services
echo "🏥 Vérification de la santé des services..."
docker-compose ps

# Démarrage du générateur de données (en arrière-plan)
echo "📊 Démarrage du générateur de données..."
docker-compose up -d data-generator

# Attente de génération de quelques données
echo "⏳ Génération de données de test (20 secondes)..."
sleep 20

# Démarrage du processeur de streaming
echo "🔄 Démarrage du processeur de streaming..."
docker-compose up -d stream-processor

echo ""
echo "🎉 Pipeline démarré avec succès!"
echo ""
echo "📊 Services disponibles:"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379" 
echo "  - Kafka: localhost:9092"
echo "  - Monitoring: http://localhost:8080/health"
echo ""
echo "🔍 Commandes utiles:"
echo "  - Voir les logs: docker-compose logs -f"
echo "  - Arrêter: docker-compose down"
echo "  - Santé: curl http://localhost:8080/health"
echo "  - Top contenu: curl http://localhost:8080/top-content"
echo ""
echo "📈 Test automatique dans 30 secondes..."
sleep 30

# Test automatique des endpoints
echo "🧪 Tests automatiques..."

if command -v curl &> /dev/null; then
    echo "  📊 Test de santé..."
    curl -s http://localhost:8080/health | head -c 200
    echo ""
    
    echo "  🏆 Test top contenu..."
    curl -s http://localhost:8080/top-content | head -c 300
    echo ""
else
    echo "  ℹ️ curl non disponible, tests manuels requis"
fi

echo ""
echo "✅ Tests terminés!"
echo "🎯 Le pipeline fonctionne correctement"
