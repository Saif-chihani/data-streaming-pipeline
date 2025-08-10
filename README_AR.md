# نظام معالجة بيانات التفاعل في الوقت الفعلي

نظام تدفق البيانات في الوقت الفعلي لمعالجة أحداث تفاعل المستخدمين من PostgreSQL إلى BigQuery و Redis ونظام خارجي مع تحويلات وإثراءات البيانات.

## 🎯 الهدف

يقوم هذا المشروع بتنفيذ نظام تدفق البيانات الذي:

- **يلتقط** أحداث التفاعل في الوقت الفعلي من PostgreSQL
- **يُثري** البيانات عبر ربطها ببيانات تعريف المحتوى
- **يُحول** الأحداث (حساب المدد، نسب التفاعل)
- **يوزع** إلى 3 وجهات بالتوازي (Fan-out Multi-sink)
- **يضمن** معالجة exactly-once
- **يوفر** تجميعات الوقت الفعلي (Redis < 5 ثوانٍ)

## 🏗️ المعمارية

```
PostgreSQL (المصدر) 
     ↓ (CDC)
   Kafka Topic
     ↓
Stream Processor
     ↓ (Fan-out)
  ┌─────┬─────┬─────┐
  ↓     ↓     ↓     ↓
Redis BigQuery External Monitoring
```

### المكونات

1. **PostgreSQL** : قاعدة البيانات المصدر مع جداول `content` و `engagement_events`
2. **Kafka** : وسيط الرسائل لالتقاط تغييرات البيانات (CDC)
3. **Stream Processor** : تطبيق Python الرئيسي مع معالجة exactly-once
4. **Redis** : تجميعات الوقت الفعلي (< 5 ثوانٍ)
5. **BigQuery** : التحليلات والتقارير
6. **النظام الخارجي** : API REST للتكاملات الخارجية
7. **المراقبة** : API للصحة ومقاييس Prometheus

## 📊 نموذج البيانات

### المصدر (PostgreSQL)

```sql
-- كتالوج المحتوى
CREATE TABLE content (
    id              UUID PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    content_type    TEXT CHECK (content_type IN ('podcast', 'newsletter', 'video')),
    length_seconds  INTEGER, 
    publish_ts      TIMESTAMPTZ NOT NULL
);

-- أحداث التفاعل الخام
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

### التحويلات

لكل حدث، يحسب النظام:

- **engagement_seconds** = `duration_ms / 1000`
- **engagement_pct** = `(engagement_seconds / length_seconds) * 100`

## 🚀 التثبيت والتشغيل

### المتطلبات المسبقة

- Docker & Docker Compose
- Python 3.11+
- ذاكرة وصول عشوائي 8GB على الأقل
- المنافذ المتاحة: 5432, 6379, 9092, 8083, 8080

### البدء السريع

1. **استنساخ وتكوين المشروع**
```bash
git clone https://github.com/seifchihani/data-streaming-pipeline.git
cd data-streaming-pipeline
cp .env.example .env
```

2. **تعديل التكوين**
```bash
# قم بتحرير .env مع معاملاتك
nano .env
```

3. **تشغيل البنية التحتية**
```bash
# Linux/Mac
chmod +x start.sh
./start.sh

# Windows
docker-compose up -d
```

4. **التحقق من الحالة**
```bash
# صحة الخدمات
curl http://localhost:8080/health

# أفضل محتوى في الوقت الفعلي
curl http://localhost:8080/top-content
```

### الأوامر المفيدة

```bash
# عرض السجلات
docker-compose logs -f stream-processor
docker-compose logs -f data-generator

# إعادة تشغيل خدمة
docker-compose restart stream-processor

# إيقاف جميع الخدمات
docker-compose down

# تنظيف الأحجام (⚠️ فقدان البيانات)
docker-compose down -v
```

## ⚙️ التكوين

### متغيرات البيئة الرئيسية

```bash
# قاعدة البيانات
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

# المعالجة
BATCH_SIZE=100
PROCESSING_INTERVAL_SECONDS=1
ENABLE_EXACTLY_ONCE=true
```

### إعداد BigQuery

1. إنشاء مشروع GCP
2. تفعيل BigQuery API
3. إنشاء مفتاح خدمة
4. تحميل ملف JSON في `config/bigquery-credentials.json`

## 🔄 أوضاع التشغيل

### وضع التدفق (الوقت الفعلي)

```bash
docker exec -it stream_processor python -m src.stream_processor --mode stream
```

### وضع الملء الخلفي (البيانات التاريخية)

```bash
docker exec -it stream_processor python -m src.stream_processor \
  --mode backfill \
  --start-date 2025-08-01 \
  --end-date 2025-08-10
```

### توليد البيانات

```bash
# الوضع المستمر
docker exec -it data_generator python -m src.data_generator --mode continuous

# دفعة واحدة
docker exec -it data_generator python -m src.data_generator --mode batch --batch-size 100

# البيانات التاريخية
docker exec -it data_generator python -m src.data_generator --mode historical --historical-days 7
```

## 📈 المراقبة والمقاييس

### API الصحة

- **الصحة العامة** : `GET /health`
- **مقاييس النظام** : `GET /metrics`
- **Prometheus** : `GET /metrics/prometheus`
- **أفضل محتوى** : `GET /top-content`
- **إحصائيات المحتوى** : `GET /content/{id}/stats`

### Redis - بيانات الوقت الفعلي

```python
# المحتوى الأكثر تفاعلاً (آخر 10 دقائق)
top_content = await redis_sink.get_top_content(limit=10)

# الإحصائيات الخاصة بمحتوى معين
stats = await redis_sink.get_content_stats(content_id)

# الأحداث الأخيرة
events = await redis_sink.get_recent_events(content_id, count=50)
```

### BigQuery - التحليلات

```sql
-- العرض اليومي للتفاعل
SELECT * FROM `project.dataset.daily_engagement_summary`
WHERE event_date >= CURRENT_DATE() - 7;

-- الاتجاهات بالساعة
SELECT * FROM `project.dataset.hourly_engagement_trends`
WHERE hour_bucket >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR);
```

## 🔧 التطوير

### هيكل المشروع

```
data-streaming-pipeline/
├── src/
│   ├── models.py              # نماذج البيانات Pydantic
│   ├── config.py              # التكوين المركزي
│   ├── data_generator.py      # مولد بيانات الاختبار
│   ├── stream_processor.py    # المعالج الرئيسي
│   ├── monitoring.py          # API المراقبة
│   └── sinks/
│       ├── redis_sink.py      # Redis sink
│       ├── bigquery_sink.py   # BigQuery sink
│       └── external_sink.py   # النظام الخارجي sink
├── sql/
│   └── init.sql              # المخطط والبيانات الأولية
├── docker/
│   ├── Dockerfile.generator   # صورة المولد
│   └── Dockerfile.processor   # صورة المعالج
├── config/
│   └── bigquery-credentials.json
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### الاختبارات

```bash
# اختبارات الوحدة
docker exec -it stream_processor python -m pytest tests/

# اختبار الحمل
docker exec -it data_generator python -m src.data_generator \
  --mode batch --batch-size 1000
```

## 🎯 الأداء والضمانات

### زمن الاستجابة
- **Redis** : < 5 ثوانٍ (الهدف محقق)
- **BigQuery** : دفعة 30 ثانية كحد أقصى
- **النظام الخارجي** : < 30 ثانية مع إعادة المحاولة

### الإنتاجية
- **الإنتاج** : 1000+ حدث/ثانية
- **الملء الخلفي** : 10,000+ حدث/ثانية

### الضمانات
- **معالجة exactly-once** مع معاملات Kafka
- **Idempotence** على جميع المصارف
- **إعادة المحاولة التلقائية** مع backoff أسي
- **Dead letter queues** للإخفاقات المستمرة

## 🔍 استكشاف الأخطاء

### المشاكل الشائعة

1. **Kafka لم يبدأ**
```bash
docker-compose logs kafka
# تحقق من المنافذ و Zookeeper
```

2. **بيانات اعتماد BigQuery مفقودة**
```bash
# تحقق من ملف بيانات الاعتماد
ls -la config/bigquery-credentials.json
```

3. **رفض اتصال Redis**
```bash
docker-compose logs redis
# تحقق من تشغيل Redis
```

4. **المعالج متوقف**
```bash
# سجلات مفصلة
docker-compose logs -f stream-processor
# إعادة تشغيل إذا لزم الأمر
docker-compose restart stream-processor
```

## 📋 خارطة الطريق والتحسينات

### مُنفذ ✅
- [x] التدفق في الوقت الفعلي مع Kafka
- [x] معالجة Exactly-once
- [x] Fan-out إلى 3 وجهات
- [x] تجميعات Redis < 5 ثوانٍ
- [x] الملء الخلفي للبيانات التاريخية
- [x] المراقبة والمقاييس
- [x] حاوية Docker

### الخطوات التالية 🚧
- [ ] Schema Registry لتطوير البيانات
- [ ] Kafka Streams للمعالجة الموزعة
- [ ] التوسع التلقائي على أساس الحمل
- [ ] اختبارات التكامل end-to-end
- [ ] لوحات معلومات Grafana
- [ ] التنبيه التلقائي
- [ ] تشفير البيانات الحساسة

## 🔗 المستودع

```bash
git clone https://github.com/seifchihani/data-streaming-pipeline.git
```

**الرابط**: [https://github.com/seifchihani/data-streaming-pipeline](https://github.com/seifchihani/data-streaming-pipeline)

## 📄 الترخيص

هذا المشروع مرخص تحت رخصة MIT. انظر ملف `LICENSE` لمزيد من التفاصيل.

## 👨‍💻 المطور

تم تطويره في إطار اختبار تقني لمنصب مهندس بيانات أول.

**التقنيات المستخدمة**: Python, Kafka, PostgreSQL, Redis, BigQuery, Docker, FastAPI, Pydantic

---

## Installation Guide | دليل التثبيت

### English Instructions
1. Clone the repository: `git clone https://github.com/seifchihani/data-streaming-pipeline.git`
2. Navigate to project: `cd data-streaming-pipeline`
3. Start services: `docker-compose up -d`
4. Check health: `curl http://localhost:8080/health`

### التعليمات بالعربية
1. استنساخ المستودع: `git clone https://github.com/seifchihani/data-streaming-pipeline.git`
2. الانتقال للمشروع: `cd data-streaming-pipeline`
3. تشغيل الخدمات: `docker-compose up -d`
4. فحص الصحة: `curl http://localhost:8080/health`
