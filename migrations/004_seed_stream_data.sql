-- ============================================================
-- Migration 004 — Seed data to populate all 5 queue streams
-- Run once in the Supabase SQL editor. Safe to re-run
-- (idempotent: skips inserts if the names already exist).
-- client_id is a plain INTEGER — we pick IDs above the current max.
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- A.  New onboarding clients  →  "New Client Onboarding" stream
-- ────────────────────────────────────────────────────────────

DO $$
DECLARE
    v_base INTEGER;
    v_id   INTEGER;
BEGIN
    -- Start IDs above whatever exists now
    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;

    -- 1 · Emma Kirchner — balanced, month 1
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Emma Kirchner') THEN
        v_base := v_base + 1;
        v_id   := v_base;
        INSERT INTO clients
            (client_id, name, age, risk_profile, investment_goal,
             months_since_joining, portfolio_value_eur, monthly_deposit,
             last_login_date, login_count_this_week,
             missed_deposits_last_3_months, portfolio_performance_pct)
        VALUES
            (v_id, 'Emma Kirchner', 29, 'balanced', 'long-term wealth building',
             1, 8500, 300,
             CURRENT_DATE - INTERVAL '2 days', 3, 0, 1.2);

        INSERT INTO client_portfolios (client_id, etf, weight_pct, target_pct) VALUES
            (v_id, 'VWCE.DE', 40, 40),
            (v_id, 'AGGG.L',  20, 20),
            (v_id, 'EIMI.L',  15, 15),
            (v_id, 'IUSV.DE', 15, 15),
            (v_id, 'WSML.L',  10, 10);
    END IF;

    -- Re-read max in case the above inserted
    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;

    -- 2 · Lukas Berger — return-oriented, month 2
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Lukas Berger') THEN
        v_base := v_base + 1;
        v_id   := v_base;
        INSERT INTO clients
            (client_id, name, age, risk_profile, investment_goal,
             months_since_joining, portfolio_value_eur, monthly_deposit,
             last_login_date, login_count_this_week,
             missed_deposits_last_3_months, portfolio_performance_pct)
        VALUES
            (v_id, 'Lukas Berger', 34, 'return-oriented', 'retirement savings',
             2, 12000, 250,
             CURRENT_DATE - INTERVAL '5 days', 2, 0, 0.8);

        INSERT INTO client_portfolios (client_id, etf, weight_pct, target_pct) VALUES
            (v_id, 'VWCE.DE', 45, 45),
            (v_id, 'EIMI.L',  20, 20),
            (v_id, 'IUSV.DE', 20, 20),
            (v_id, 'WSML.L',  10, 10),
            (v_id, 'AGGG.L',   5,  5);
    END IF;

    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;

    -- 3 · Sophie Maier — conservative, month 3
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Sophie Maier') THEN
        v_base := v_base + 1;
        v_id   := v_base;
        INSERT INTO clients
            (client_id, name, age, risk_profile, investment_goal,
             months_since_joining, portfolio_value_eur, monthly_deposit,
             last_login_date, login_count_this_week,
             missed_deposits_last_3_months, portfolio_performance_pct)
        VALUES
            (v_id, 'Sophie Maier', 26, 'conservative', 'first investment',
             3, 5000, 150,
             CURRENT_DATE - INTERVAL '1 day', 4, 0, -0.5);

        INSERT INTO client_portfolios (client_id, etf, weight_pct, target_pct) VALUES
            (v_id, 'AGGG.L',  40, 40),
            (v_id, 'VWCE.DE', 30, 30),
            (v_id, 'IUSV.DE', 15, 15),
            (v_id, 'EIMI.L',  10, 10),
            (v_id, 'WSML.L',   5,  5);
    END IF;

    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;

    -- 4 · Tobias Fuchs — balanced, month 4
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Tobias Fuchs') THEN
        v_base := v_base + 1;
        v_id   := v_base;
        INSERT INTO clients
            (client_id, name, age, risk_profile, investment_goal,
             months_since_joining, portfolio_value_eur, monthly_deposit,
             last_login_date, login_count_this_week,
             missed_deposits_last_3_months, portfolio_performance_pct)
        VALUES
            (v_id, 'Tobias Fuchs', 31, 'balanced', 'pension supplement',
             4, 15000, 400,
             CURRENT_DATE - INTERVAL '3 days', 1, 0, 2.1);

        INSERT INTO client_portfolios (client_id, etf, weight_pct, target_pct) VALUES
            (v_id, 'VWCE.DE', 40, 40),
            (v_id, 'AGGG.L',  20, 20),
            (v_id, 'EIMI.L',  15, 15),
            (v_id, 'IUSV.DE', 15, 15),
            (v_id, 'WSML.L',  10, 10);
    END IF;

    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;

    -- 5 · Anna Bauer — return-oriented, month 5
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Anna Bauer') THEN
        v_base := v_base + 1;
        v_id   := v_base;
        INSERT INTO clients
            (client_id, name, age, risk_profile, investment_goal,
             months_since_joining, portfolio_value_eur, monthly_deposit,
             last_login_date, login_count_this_week,
             missed_deposits_last_3_months, portfolio_performance_pct)
        VALUES
            (v_id, 'Anna Bauer', 28, 'return-oriented', 'long term wealth',
             5, 9000, 200,
             CURRENT_DATE - INTERVAL '4 days', 2, 0, 1.5);

        INSERT INTO client_portfolios (client_id, etf, weight_pct, target_pct) VALUES
            (v_id, 'VWCE.DE', 45, 45),
            (v_id, 'EIMI.L',  20, 20),
            (v_id, 'IUSV.DE', 20, 20),
            (v_id, 'WSML.L',  10, 10),
            (v_id, 'AGGG.L',   5,  5);
    END IF;

    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;

    -- 6 · Michael Steiner — balanced, month 6
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Michael Steiner') THEN
        v_base := v_base + 1;
        v_id   := v_base;
        INSERT INTO clients
            (client_id, name, age, risk_profile, investment_goal,
             months_since_joining, portfolio_value_eur, monthly_deposit,
             last_login_date, login_count_this_week,
             missed_deposits_last_3_months, portfolio_performance_pct)
        VALUES
            (v_id, 'Michael Steiner', 33, 'balanced', 'wealth preservation',
             6, 11000, 350,
             CURRENT_DATE - INTERVAL '6 days', 2, 0, 0.3);

        INSERT INTO client_portfolios (client_id, etf, weight_pct, target_pct) VALUES
            (v_id, 'VWCE.DE', 40, 40),
            (v_id, 'AGGG.L',  20, 20),
            (v_id, 'EIMI.L',  15, 15),
            (v_id, 'IUSV.DE', 15, 15),
            (v_id, 'WSML.L',  10, 10);
    END IF;

END $$;


-- ────────────────────────────────────────────────────────────
-- B.  Recent market events  →  "Market Event Response" stream
--     generate_action_queue looks for events within last 7 days
--     with severity warning/critical and a non-null etf_ticker.
--     The UPDATE at the end sets accurate affected_clients counts.
-- ────────────────────────────────────────────────────────────

INSERT INTO quant_events
    (timestamp, event_type, reason, affected_clients, severity, etf_ticker, communicated)
SELECT ts, etype, reason, 0, sev, etf, FALSE
FROM (VALUES
    (NOW(),
     'Risk Alert',
     'VWCE.DE fell 2.3% today — above the normal daily swing (±0.8%). Global equity selloff triggered by US macro data.',
     'warning',
     'VWCE.DE'),

    (NOW() - INTERVAL '1 day',
     'Risk Alert',
     'AGGG.L dropped 1.9% amid rising Eurozone rate expectations. Bond allocation affected.',
     'critical',
     'AGGG.L'),

    (NOW() - INTERVAL '2 days',
     'Risk Alert',
     'EIMI.L experiencing elevated volatility following EM currency selloff.',
     'warning',
     'EIMI.L')
) AS t(ts, etype, reason, sev, etf)
WHERE NOT EXISTS (
    SELECT 1 FROM quant_events
    WHERE etf_ticker = t.etf
      AND timestamp >= NOW() - INTERVAL '7 days'
      AND severity IN ('warning', 'critical')
);

-- Backfill affected_clients counts from actual holdings
UPDATE quant_events qe
SET affected_clients = (
    SELECT COUNT(DISTINCT cp.client_id)
    FROM client_portfolios cp
    WHERE cp.etf = qe.etf_ticker
)
WHERE qe.timestamp >= NOW() - INTERVAL '7 days'
  AND qe.severity IN ('warning', 'critical')
  AND qe.etf_ticker IS NOT NULL;
