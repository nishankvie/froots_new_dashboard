-- Phase 1: Pension product config table
-- Run this once in the Supabase SQL editor.
-- Safe to run multiple times (idempotent INSERT via WHERE NOT EXISTS).

CREATE TABLE IF NOT EXISTS pension_product_config (
    id                    SERIAL PRIMARY KEY,
    wrapper_type          TEXT,
    kest_rate_inside_pct  DECIMAL DEFAULT 0.0,
    annual_all_in_fee_pct DECIMAL DEFAULT 1.0,
    insurance_tax_pct     DECIMAL DEFAULT 4.0,
    min_lump_sum_eur      DECIMAL DEFAULT 5000,
    min_monthly_eur       DECIMAL DEFAULT 100,
    target_horizon_years  INTEGER DEFAULT 15,
    insurance_partners    TEXT,
    classic_flv_fee_pct   DECIMAL DEFAULT 1.5,
    classic_flv_kest_pct  DECIMAL DEFAULT 27.5
);

-- Seed the single config row (will not insert if a row already exists)
INSERT INTO pension_product_config (
    wrapper_type,
    kest_rate_inside_pct,
    annual_all_in_fee_pct,
    insurance_tax_pct,
    min_lump_sum_eur,
    min_monthly_eur,
    target_horizon_years,
    insurance_partners,
    classic_flv_fee_pct,
    classic_flv_kest_pct
)
SELECT
    'fondsgebundene Lebensversicherung',
    0.0,
    1.0,
    4.0,
    5000,
    100,
    15,
    'Zurich, Donau, Österreichische Beamtenversicherung, Helvetia, Standard Life',
    1.5,
    27.5
WHERE NOT EXISTS (SELECT 1 FROM pension_product_config);
