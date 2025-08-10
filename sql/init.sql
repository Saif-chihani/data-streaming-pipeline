-- Create database schema for engagement tracking
-- This script will be executed automatically when PostgreSQL starts

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Content catalogue
CREATE TABLE content (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug            TEXT UNIQUE NOT NULL,
    title           TEXT        NOT NULL,
    content_type    TEXT CHECK (content_type IN ('podcast', 'newsletter', 'video')),
    length_seconds  INTEGER, 
    publish_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Raw engagement telemetry
CREATE TABLE engagement_events (
    id           BIGSERIAL PRIMARY KEY,
    content_id   UUID REFERENCES content(id),
    user_id      UUID NOT NULL,
    event_type   TEXT CHECK (event_type IN ('play', 'pause', 'finish', 'click')),
    event_ts     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms  INTEGER,      -- nullable for events without duration
    device       TEXT,         -- e.g. "ios", "web‑safari"
    raw_payload  JSONB         -- anything extra the client sends
);

-- Create indexes for better performance
CREATE INDEX idx_engagement_events_content_id ON engagement_events(content_id);
CREATE INDEX idx_engagement_events_user_id ON engagement_events(user_id);
CREATE INDEX idx_engagement_events_event_ts ON engagement_events(event_ts);
CREATE INDEX idx_engagement_events_event_type ON engagement_events(event_type);
CREATE INDEX idx_content_content_type ON content(content_type);
CREATE INDEX idx_content_publish_ts ON content(publish_ts);

-- Create a view for enriched events (useful for testing)
CREATE OR REPLACE VIEW enriched_engagement_events AS
SELECT 
    ee.id,
    ee.content_id,
    c.slug,
    c.title,
    c.content_type,
    c.length_seconds,
    ee.user_id,
    ee.event_type,
    ee.event_ts,
    ee.duration_ms,
    ROUND(ee.duration_ms::DECIMAL / 1000, 2) as engagement_seconds,
    CASE 
        WHEN c.length_seconds IS NOT NULL AND ee.duration_ms IS NOT NULL AND c.length_seconds > 0 
        THEN ROUND((ee.duration_ms::DECIMAL / 1000) / c.length_seconds * 100, 2)
        ELSE NULL 
    END as engagement_pct,
    ee.device,
    ee.raw_payload
FROM engagement_events ee
LEFT JOIN content c ON ee.content_id = c.id;

-- Insert sample content data
INSERT INTO content (slug, title, content_type, length_seconds, publish_ts) VALUES
('podcast-ai-trends-2025', 'AI Trends in 2025: What to Expect', 'podcast', 3600, '2025-01-15 10:00:00+00'),
('newsletter-data-science-weekly', 'Data Science Weekly Newsletter #45', 'newsletter', NULL, '2025-02-01 08:00:00+00'),
('video-python-streaming', 'Building Streaming Applications with Python', 'video', 2400, '2025-02-10 14:30:00+00'),
('podcast-tech-leadership', 'Tech Leadership in Remote Teams', 'podcast', 2700, '2025-02-15 16:00:00+00'),
('video-kafka-tutorial', 'Apache Kafka Complete Tutorial', 'video', 5400, '2025-02-20 11:00:00+00'),
('newsletter-ml-weekly', 'Machine Learning Weekly Digest', 'newsletter', NULL, '2025-02-25 09:00:00+00'),
('podcast-startup-stories', 'Startup Success Stories', 'podcast', 3300, '2025-03-01 12:00:00+00'),
('video-docker-kubernetes', 'Docker and Kubernetes Masterclass', 'video', 7200, '2025-03-05 13:00:00+00');

-- Create a function to generate random engagement events (for testing)
CREATE OR REPLACE FUNCTION generate_sample_engagement_event() RETURNS engagement_events AS $$
DECLARE
    content_ids UUID[];
    random_content_id UUID;
    random_user_id UUID;
    event_types TEXT[] := ARRAY['play', 'pause', 'finish', 'click'];
    random_event_type TEXT;
    devices TEXT[] := ARRAY['ios', 'android', 'web-chrome', 'web-safari', 'web-firefox'];
    random_device TEXT;
    random_duration INTEGER;
    new_event engagement_events;
BEGIN
    -- Get all content IDs
    SELECT ARRAY(SELECT id FROM content) INTO content_ids;
    
    -- Select random values
    random_content_id := content_ids[1 + floor(random() * array_length(content_ids, 1))];
    random_user_id := uuid_generate_v4();
    random_event_type := event_types[1 + floor(random() * array_length(event_types, 1))];
    random_device := devices[1 + floor(random() * array_length(devices, 1))];
    
    -- Generate duration based on event type
    random_duration := CASE 
        WHEN random_event_type IN ('play', 'pause') THEN 1000 + floor(random() * 30000)  -- 1-30 seconds
        WHEN random_event_type = 'finish' THEN 30000 + floor(random() * 120000)  -- 30-150 seconds
        ELSE NULL  -- click events don't have duration
    END;
    
    -- Insert the event
    INSERT INTO engagement_events (
        content_id, 
        user_id, 
        event_type, 
        event_ts, 
        duration_ms, 
        device, 
        raw_payload
    ) VALUES (
        random_content_id,
        random_user_id,
        random_event_type,
        NOW() - (random() * interval '1 hour'),  -- Random time in last hour
        random_duration,
        random_device,
        jsonb_build_object(
            'session_id', uuid_generate_v4(),
            'ip_address', 
            CONCAT(
                floor(random() * 255 + 1)::text, '.', 
                floor(random() * 255)::text, '.', 
                floor(random() * 255)::text, '.', 
                floor(random() * 255 + 1)::text
            ),
            'user_agent', random_device
        )
    ) RETURNING * INTO new_event;
    
    RETURN new_event;
END;
$$ LANGUAGE plpgsql;

-- Insert some initial sample data
SELECT generate_sample_engagement_event() FROM generate_series(1, 50);

-- Create a trigger to notify when new events are inserted (for Change Data Capture)
CREATE OR REPLACE FUNCTION notify_engagement_event() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('engagement_events_changes', row_to_json(NEW)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER engagement_events_notify 
    AFTER INSERT ON engagement_events 
    FOR EACH ROW 
    EXECUTE FUNCTION notify_engagement_event();

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
