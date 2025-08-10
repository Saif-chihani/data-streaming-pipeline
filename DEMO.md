# 🎬 Guide de Démonstration Rapide

Ce guide vous permet de tester le pipeline en 5 minutes !

## 🚀 Démarrage Ultra-Rapide

```bash
# 1. Cloner le projet
git clone https://github.com/seifchihani/data-streaming-pipeline.git
cd data-streaming-pipeline

# 2. Lancer tout d'un coup
docker-compose up -d

# 3. Attendre 30 secondes et tester
sleep 30
curl http://localhost:8080/health
```

## 📊 Endpoints de Test

Une fois le système démarré, testez ces endpoints :

### Santé du Système
```bash
curl http://localhost:8080/health
```
**Attendu :** Status "healthy" pour tous les composants

### Top Contenu Temps Réel
```bash
curl http://localhost:8080/top-content
```
**Attendu :** Liste des contenus les plus engageants des 10 dernières minutes

### Métriques Système
```bash
curl http://localhost:8080/metrics
```
**Attendu :** Statistiques de traitement en temps réel

### Stats d'un Contenu Spécifique
```bash
# Récupérer un content_id depuis top-content, puis :
curl http://localhost:8080/content/{CONTENT_ID}/stats
```

## 🧪 Test de Performance

### Générateur de Charge
```bash
# Générer 1000 événements d'un coup
docker exec -it data_generator python -m src.data_generator \
  --mode batch --batch-size 1000

# Vérifier le traitement
curl http://localhost:8080/top-content
```

### Vérification Redis (< 5 secondes)
```bash
# Générer un événement
docker exec -it data_generator python -m src.data_generator \
  --mode batch --batch-size 1

# Immédiatement après, vérifier Redis
curl http://localhost:8080/top-content
# Les données doivent apparaître en moins de 5 secondes ✅
```

## 📈 Monitoring en Temps Réel

### Logs des Composants
```bash
# Stream processor (composant principal)
docker-compose logs -f stream-processor

# Générateur de données
docker-compose logs -f data-generator

# Tous les services
docker-compose logs -f
```

### Base de Données
```bash
# Se connecter à PostgreSQL
docker exec -it postgres_source psql -U postgres -d engagement_db

# Vérifier les données
SELECT COUNT(*) FROM engagement_events;
SELECT * FROM enriched_engagement_events LIMIT 5;
```

### Redis
```bash
# Se connecter à Redis
docker exec -it redis_cache redis-cli

# Vérifier les agrégations
ZREVRANGE top_content_last_10min 0 5 WITHSCORES
```

## 🎯 Démonstration des Features

### 1. Streaming Temps Réel
```bash
# Terminal 1 : Surveiller les logs
docker-compose logs -f stream-processor

# Terminal 2 : Générer des événements continus
docker exec -it data_generator python -m src.data_generator --mode continuous

# Terminal 3 : Surveiller les résultats
watch -n 2 "curl -s http://localhost:8080/top-content | jq '.top_content[0:3]'"
```

### 2. Backfill Historique
```bash
# Remplir 7 jours d'historique
docker exec -it stream_processor python -m src.stream_processor \
  --mode backfill \
  --start-date 2025-08-03 \
  --end-date 2025-08-10
```

### 3. Exactly-Once Processing
Les événements sont traités exactement une fois grâce à :
- Transactions Kafka avec commit manuel
- Idempotence sur tous les sinks
- Gestion des doublons automatique

## 🔧 Dépannage Express

### Services ne démarrent pas
```bash
docker-compose down -v
docker-compose up -d
docker-compose ps
```

### Erreur de connexion
```bash
# Vérifier que tous les services sont healthy
docker-compose ps
# Attendre que tous montrent "healthy"
```

### Pas de données dans Redis
```bash
# Vérifier le générateur
docker-compose logs data-generator

# Vérifier le processeur
docker-compose logs stream-processor

# Forcer la génération
docker restart data_generator
```

## 🏆 Résultats Attendus

Après 2-3 minutes de fonctionnement :

1. **Health Check** : Tous les composants "healthy"
2. **Top Content** : Liste mise à jour en temps réel
3. **Latence Redis** : < 5 secondes ✅
4. **Débit** : 100+ événements/seconde traités
5. **BigQuery** : Données enrichies stockées (si configuré)

## 📋 Checklist de Validation

- [ ] `curl http://localhost:8080/health` retourne "healthy"
- [ ] `curl http://localhost:8080/top-content` retourne des données
- [ ] Les logs montrent le traitement d'événements
- [ ] Redis répond en < 5 secondes
- [ ] Pas d'erreurs dans les logs
- [ ] Tous les containers sont "healthy"

---

**🎉 Félicitations !** Votre pipeline de streaming fonctionne parfaitement !

Pour une démonstration complète, voir [README.md](./README.md) et [README_AR.md](./README_AR.md)
