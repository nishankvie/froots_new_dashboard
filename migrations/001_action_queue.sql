-- Phase 1: Action Queue table
-- Run this once in the Supabase SQL editor.
-- Safe to run multiple times (uses IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS action_queue (
    id                  SERIAL PRIMARY KEY,
    client_id           INTEGER NOT NULL,
    stream              VARCHAR(50) NOT NULL,   -- at_risk | market_event | onboarding | pension | milestone
    reason              TEXT NOT NULL,
    suggested_action    TEXT NOT NULL,
    urgency_score       FLOAT NOT NULL DEFAULT 0,
    estimated_minutes   INTEGER NOT NULL DEFAULT 5,
    status              VARCHAR(20) NOT NULL DEFAULT 'open',  -- open | done | snoozed | skipped
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMP,
    snooze_until        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_action_queue_status   ON action_queue(status);
CREATE INDEX IF NOT EXISTS idx_action_queue_client   ON action_queue(client_id);
CREATE INDEX IF NOT EXISTS idx_action_queue_stream   ON action_queue(stream);
