-- Phase 2b: Add communicated flag to quant_events
-- Run once in Supabase SQL editor. Safe to run multiple times (IF NOT EXISTS equivalent).

ALTER TABLE quant_events
ADD COLUMN IF NOT EXISTS communicated BOOLEAN DEFAULT FALSE;
