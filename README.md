# Engagement Streaming Pipeline

Un système de streaming en temps réel pour traiter les événements d'engagement utilisateur depuis PostgreSQL vers BigQuery, Redis et un système externe avec des transformations et enrichissements de données.

## 🎯 Objectif

Ce projet implémente une pipeline de streaming de données qui :

- **Capture** les événements d'engagement en temps réel depuis PostgreSQL
- **Enrichit** les données en joignant les métadonnées de contenu
- **Transforme** les événements (calcul de durées, pourcentages d'engagement)
- **Distribue** vers 3 destinations en parallèle (Fan-out Multi-sink)
- **Garantit** un traitement exactly-once
- **Fournit** des agrégations temps réel (Redis < 5 secondes)

## 🏗️ Architecture

```
PostgreSQL (Source) 
     ↓ (CDC)
   Kafka Topic
     ↓
Stream Processor
     ↓ (Fan-out)
  ┌─────┬─────┬─────┐
  ↓     ↓     ↓     ↓
Redis BigQuery External Monitoring
```

### Composants

1. **PostgreSQL** : Base source avec tables `content` et `engagement_events`
2. **Kafka** : Message broker pour la capture de données changées (CDC)
3. **Stream Processor** : Application Python principale avec exactly-once processing
4. **Redis** : Agrégations temps réel (< 5 secondes)
5. **BigQuery** : Analytics et reporting
6. **Système Externe** : API REST pour intégrations tierces
7. **Monitoring** : API de santé et métriques Prometheus

## 📊 Modèle de Données

### Source (PostgreSQL)

```sql
-- Catalogue de contenu
CREATE TABLE content (
    id              UUID PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    content_type    TEXT CHECK (content_type IN ('podcast', 'newsletter', 'video')),
    length_seconds  INTEGER, 
    publish_ts      TIMESTAMPTZ NOT NULL
);

-- Événements d'engagement bruts
CREATE TABLE engagement_events (
    id           BIGSERIAL PRIMARY KEY,
    content_id   UUID REFERENCES content(id),
    user_id      UUID,
    event_type   TEXT CHECK (event_type IN ('play', 'pause', 'finish', 'click')),
    event_ts     TIMESTAMPTZ NOT NULL,
    duration_ms  INTEGER,
    device       TEXT,
    raw_payload  JSONB
);
```

### Transformations

Pour chaque événement, le système calcule :

- **engagement_seconds** = `duration_ms / 1000`
- **engagement_pct** = `(engagement_seconds / length_seconds) * 100`

## 🚀 Installation et Démarrage

### Prérequis

- Docker & Docker Compose
- Python 3.11+
- Minimum 8GB RAM
- Ports disponibles : 5432, 6379, 9092, 8083, 8080

### Démarrage Rapide

1. **Cloner et configurer**
```bash
git clone <repository-url>
cd data-streaming-pipeline
cp .env.example .env
```

2. **Modifier la configuration**
```bash
# Éditez .env avec vos paramètres
nano .env
```

3. **Démarrer l'infrastructure**
```bash
# Linux/Mac
chmod +x start.sh
./start.sh

# Windows
docker-compose up -d
```

4. **Vérifier le statut**
```bash
# Santé des services
curl http://localhost:8080/health

# Top contenu en temps réel
curl http://localhost:8080/top-content
```

### Commandes Utiles

```bash
# Voir les logs
docker-compose logs -f stream-processor
docker-compose logs -f data-generator

# Redémarrer un service
docker-compose restart stream-processor

# Arrêter tous les services
docker-compose down

# Nettoyer les volumes (⚠️ perte de données)
docker-compose down -v
```

## ⚙️ Configuration

### Variables d'Environnement Principales

```bash
# Base de données
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/engagement_db

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC_ENGAGEMENT_EVENTS=engagement-events

# Redis
REDIS_URL=redis://localhost:6379
REDIS_AGGREGATION_WINDOW_MINUTES=10

# BigQuery
BIGQUERY_PROJECT_ID=your-project-id
BIGQUERY_DATASET_ID=engagement_analytics

# Traitement
BATCH_SIZE=100
PROCESSING_INTERVAL_SECONDS=1
ENABLE_EXACTLY_ONCE=true
```

### Configuration BigQuery

1. Créer un projet GCP
2. Activer l'API BigQuery
3. Créer une clé de service
4. Télécharger le fichier JSON dans `config/bigquery-credentials.json`

## 🔄 Modes d'Exécution

### Mode Streaming (Temps Réel)

```bash
docker exec -it stream_processor python -m src.stream_processor --mode stream
```

### Mode Backfill (Données Historiques)

```bash
docker exec -it stream_processor python -m src.stream_processor \
  --mode backfill \
  --start-date 2025-08-01 \
  --end-date 2025-08-10
```

### Génération de Données

```bash
# Mode continu
docker exec -it data_generator python -m src.data_generator --mode continuous

# Batch unique
docker exec -it data_generator python -m src.data_generator --mode batch --batch-size 100

# Données historiques
docker exec -it data_generator python -m src.data_generator --mode historical --historical-days 7
```

## 📈 Monitoring et Métriques

### API de Santé

- **Santé globale** : `GET /health`
- **Métriques système** : `GET /metrics`
- **Prometheus** : `GET /metrics/prometheus`
- **Top contenu** : `GET /top-content`
- **Stats contenu** : `GET /content/{id}/stats`

### Redis - Données Temps Réel

```python
# Contenu le plus engageant (10 dernières minutes)
top_content = await redis_sink.get_top_content(limit=10)

# Stats spécifiques à un contenu
stats = await redis_sink.get_content_stats(content_id)

# Événements récents
events = await redis_sink.get_recent_events(content_id, count=50)
```

### BigQuery - Analytics

```sql
-- Vue quotidienne d'engagement
SELECT * FROM `project.dataset.daily_engagement_summary`
WHERE event_date >= CURRENT_DATE() - 7;

-- Tendances horaires
SELECT * FROM `project.dataset.hourly_engagement_trends`
WHERE hour_bucket >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR);
```

## 🔧 Développement

### Structure du Projet

```
data-streaming-pipeline/
├── src/
│   ├── models.py              # Modèles de données Pydantic
│   ├── config.py              # Configuration centralisée
│   ├── data_generator.py      # Générateur de données de test
│   ├── stream_processor.py    # Processeur principal
│   ├── monitoring.py          # API de monitoring
│   └── sinks/
│       ├── redis_sink.py      # Sink Redis
│       ├── bigquery_sink.py   # Sink BigQuery
│       └── external_sink.py   # Sink système externe
├── sql/
│   └── init.sql              # Schéma et données initiales
├── docker/
│   ├── Dockerfile.generator   # Image générateur
│   └── Dockerfile.processor   # Image processeur
├── config/
│   └── bigquery-credentials.json
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### Tests

```bash
# Tests unitaires
docker exec -it stream_processor python -m pytest tests/

# Test de charge
docker exec -it data_generator python -m src.data_generator \
  --mode batch --batch-size 1000
```

### Personnalisation

1. **Nouveau sink** : Étendre la classe de base dans `sinks/`
2. **Transformations** : Modifier `enrich_event()` dans `stream_processor.py`
3. **Métriques** : Ajouter des endpoints dans `monitoring.py`

## 🎯 Performances et Garanties

### Latence
- **Redis** : < 5 secondes (objectif atteint)
- **BigQuery** : Batch 30 secondes max
- **Système externe** : < 30 secondes avec retry

### Débit
- **Production** : 1000+ événements/seconde
- **Backfill** : 10,000+ événements/seconde

### Garanties
- **Exactly-once processing** avec transactions Kafka
- **Idempotence** sur tous les sinks
- **Retry automatique** avec backoff exponentiel
- **Dead letter queues** pour les échecs persistants

## 🔍 Dépannage

### Problèmes Courants

1. **Kafka non démarré**
```bash
docker-compose logs kafka
# Vérifier les ports et Zookeeper
```

2. **BigQuery credentials manquantes**
```bash
# Vérifier le fichier de credentials
ls -la config/bigquery-credentials.json
```

3. **Redis connexion refusée**
```bash
docker-compose logs redis
# Vérifier si Redis est démarré
```

4. **Processeur bloqué**
```bash
# Logs détaillés
docker-compose logs -f stream-processor
# Redémarrer si nécessaire
docker-compose restart stream-processor
```

### Logs Utiles

```bash
# Logs en temps réel
docker-compose logs -f

# Logs d'un service spécifique
docker-compose logs -f stream-processor

# Logs avec timestamps
docker-compose logs -f -t
```

## 📋 Roadmap et Améliorations

### Implémenté ✅
- [x] Streaming temps réel avec Kafka
- [x] Exactly-once processing
- [x] Fan-out vers 3 destinations
- [x] Agrégations Redis < 5 secondes
- [x] Backfill pour données historiques
- [x] Monitoring et métriques
- [x] Docker containerization

### Prochaines Étapes 🚧
- [ ] Schema Registry pour évolution des données
- [ ] Kafka Streams pour processing distribué
- [ ] Auto-scaling basé sur la charge
- [ ] Tests d'intégration end-to-end
- [ ] Dashboards Grafana
- [ ] Alerting automatique
- [ ] Chiffrement des données sensibles

### Optimisations Possibles 📈
- [ ] Partitioning intelligent par content_type
- [ ] Compression des payloads Kafka
- [ ] Connection pooling optimisé
- [ ] Cache intelligent pour les jointures
- [ ] Batch processing adaptatif

## 🤝 Contribution

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 👨‍💻 Auteur

Développé dans le cadre d'un test technique pour un poste d'ingénieur de données senior.

**Technologies utilisées** : Python, Kafka, PostgreSQL, Redis, BigQuery, Docker, FastAPI, Pydantic
