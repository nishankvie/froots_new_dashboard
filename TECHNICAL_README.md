# froots Intelligence Platform — Technical Reference

This document is a complete code-level reference. It explains every file, every function, every formula, every database table, and every connection in the system. The goal is that you can read this and understand exactly how any piece of the platform works without having to trace through the source code yourself.

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Database schema](#2-database-schema)
3. [utils.py — the shared engine](#3-utilspy--the-shared-engine)
4. [app.py — entry point](#4-apppy--entry-point)
5. [Page 0 — Today's Work](#5-page-0--todays-work-0_todays_workpy)
6. [Page 1 — Client Hub](#6-page-1--client-hub-1_customer_intelligencepy)
7. [Page 2 — Client Profile](#7-page-2--client-profile-2_client_portfoliopy)
8. [Page 3 — Market Pulse](#8-page-3--market-pulse-3_risk_metricspy)
9. [Page 4 — Crash Context](#9-page-4--crash-context-4_crash_recoverypy)
10. [Page 5 — Quant & Support Feed](#10-page-5--quant--support-feed-5_quant_feedpy)
11. [Page 6 — Pension Tool](#11-page-6--pension-tool-6_pension_toolpy)
12. [Data files](#12-data-files)
13. [Migrations](#13-migrations)
14. [Session state and cross-page navigation](#14-session-state-and-cross-page-navigation)
15. [Caching strategy](#15-caching-strategy)
16. [Google Analytics integration](#16-google-analytics-integration)

---

## 1. Architecture overview

```
Browser
  │
  └─► Streamlit runtime
          │
          ├─► app.py                  (sets page config, immediately switch_page to page 0)
          │
          ├─► pages/0_todays_work.py
          ├─► pages/1_customer_intelligence.py
          ├─► pages/2_client_portfolio.py
          ├─► pages/3_risk_metrics.py
          ├─► pages/4_crash_recovery.py
          ├─► pages/5_quant_feed.py
          └─► pages/6_pension_tool.py
                    │
                    └─► utils.py      (imported by every page)
                              │
                              ├─► SQLAlchemy engine  ──► PostgreSQL (Supabase)
                              └─► local CSV files    ──► data/*.csv
```

Every page does `import utils` (after inserting the project root into `sys.path`). All data loading, score computation, queue generation, and the sidebar renderer live in `utils.py`. Pages are responsible only for layout and UI.

**State that persists across pages:** `st.session_state` (in-memory, per browser session). The only cross-page state key that matters is `selected_client_id` — set when a CE advisor opens a client profile and read by `2_client_portfolio.py` and the sidebar.

**Data flow summary:**

```
PostgreSQL tables
    clients              ──► load_clients()        ──► every page
    client_portfolios    ──► load_portfolios()      ──► pages 2, 3, 6
    client_contacts      ──► load_contacts()        ──► pages 0, 1, 2
    client_notes         ──► load_notes()           ──► page 2
    quant_events         ──► load_quant_events()    ──► pages 2, 3, 5
    aum_history          ──► load_aum_history()     ──► page 1
    action_queue         ──► load_action_queue()    ──► pages 0, 2
    pension_product_config ► load_pension_config()  ──► page 6

CSV files (read-only)
    data/VWCE.DE.csv etc ──► load_etf_prices()     ──► pages 3, 4, 6
```

---

## 2. Database schema

### Table: `clients`

| Column | Type | Description |
|--------|------|-------------|
| client_id | INTEGER (NOT SERIAL) | Primary key — must be inserted explicitly |
| name | TEXT | Full name |
| age | INTEGER | Client age (used in pension fit score) |
| risk_profile | TEXT | 'conservative', 'balanced', 'return-oriented' |
| investment_goal | TEXT | Free text, e.g. 'retirement savings' |
| months_since_joining | INTEGER | Tenure in months |
| portfolio_value_eur | NUMERIC | Current portfolio value |
| monthly_deposit | NUMERIC | Current standing order amount |
| last_login_date | DATE | Most recent app login |
| login_count_this_week | INTEGER | Logins in the current calendar week |
| missed_deposits_last_3_months | INTEGER | Count of missed standing orders |
| portfolio_performance_pct | NUMERIC | YTD performance as a percentage |

### Table: `client_portfolios`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| client_id | INTEGER | FK → clients.client_id |
| etf | TEXT | ETF ticker, e.g. 'VWCE.DE' |
| weight_pct | NUMERIC | Current allocation percentage |
| target_pct | NUMERIC | Target allocation percentage |

### Table: `client_contacts`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| client_id | INTEGER | FK → clients.client_id |
| contact_date | DATE | Date of contact |
| contact_type | TEXT | 'Phone Call', 'Email', 'Meeting', 'Chat' |
| description | TEXT | Notes on what was discussed |

### Table: `client_notes`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| client_id | INTEGER | FK → clients.client_id |
| date | TIMESTAMP | When the note was added |
| note_text | TEXT | Note body |
| added_by | TEXT | Advisor name |

### Table: `quant_events`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| timestamp | TIMESTAMP | When the event was generated |
| event_type | TEXT | 'Risk Alert', 'Rebalance Alert', 'Information Update' |
| reason | TEXT | Plain-English explanation |
| affected_clients | INTEGER | Count of clients holding the relevant ETF |
| severity | TEXT | 'info', 'warning', 'critical' |
| etf_ticker | TEXT | Relevant ETF (nullable for non-ETF events) |
| client_specific_name | TEXT | If event is for a single client (nullable) |
| communicated | BOOLEAN | Whether CE team has acted on it |

### Table: `aum_history`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| date | DATE | Month-end date |
| total_aum_eur | NUMERIC | Total assets under management at that date |

### Table: `action_queue`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| client_id | INTEGER | FK → clients.client_id |
| stream | TEXT | One of: 'at_risk', 'market_event', 'onboarding', 'pension', 'milestone' |
| reason | TEXT | Why this client is in this stream |
| suggested_action | TEXT | What the CE agent should do |
| urgency_score | NUMERIC | Higher = more urgent; used for ordering within a stream |
| estimated_minutes | INTEGER | Estimated time to complete the action |
| status | TEXT | 'open', 'done', 'snoozed', 'skipped' |
| created_at | TIMESTAMP | When the row was inserted or last revived |
| snooze_until | TIMESTAMP | Only set when status='snoozed'; NULL otherwise |
| resolved_at | TIMESTAMP | When status changed to done/skipped |

**Key design choice: multi-stream, per-(client, stream) lifecycle.** A single client can have multiple rows in action_queue simultaneously — one per qualifying stream. Snooze/done/skip state is tracked per (client_id, stream) pair. When a snoozed row expires, it is revived (status reset to 'open') rather than a new row being inserted.

### Table: `pension_product_config`

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| annual_all_in_fee_pct | NUMERIC | froots wrapper annual fee (e.g. 1.0 = 1.0%) |
| kest_rate_inside_pct | NUMERIC | KeSt rate inside wrapper (0 = tax-free) |
| insurance_tax_pct | NUMERIC | Versicherungssteuer rate (4 = 4%) |
| classic_flv_fee_pct | NUMERIC | Classic FLV annual management fee |
| classic_flv_kest_pct | NUMERIC | KeSt on classic FLV gains at exit (27.5) |
| min_lump_sum_eur | NUMERIC | Minimum lump sum to enter wrapper |
| min_monthly_eur | NUMERIC | Minimum monthly contribution |
| insurance_partners | TEXT | Comma-separated list of partner insurer names |

---

## 3. utils.py — the shared engine

`utils.py` is imported by every page. It contains: the SQLAlchemy engine, all data loaders (cached), all scoring functions, the queue generation and management functions, and the sidebar renderer.

### 3.1 Database connection

```python
DATABASE_URL = os.getenv("DATABASE_URL") or st.secrets["DATABASE_URL"]

@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL)
```

`@st.cache_resource` caches the engine object across all reruns for the lifetime of the Streamlit server process. There is only ever one engine per server process. The connection pool is managed by SQLAlchemy.

`DATABASE_URL` is read from the `.env` file (via `python-dotenv`) or from Streamlit secrets. The `.env` approach works locally; Streamlit secrets works in Cloud deployment.

### 3.2 Data loaders

All loaders use `@st.cache_data(ttl=300)` — results are cached for 5 minutes per unique set of arguments. After 5 minutes Streamlit re-executes the function on the next call. Callers can explicitly clear the cache by calling `utils.load_action_queue.clear()` (used after queue mutations).

| Function | SQL / source | Key transforms |
|----------|-------------|----------------|
| `load_clients()` | `SELECT * FROM clients` | `last_login_date` → datetime |
| `load_portfolios()` | `SELECT * FROM client_portfolios` | none |
| `load_quant_events()` | `SELECT * FROM quant_events` | `timestamp` → datetime; NULLs in `etf_ticker` and `client_specific_name` → empty string; `communicated` → bool |
| `load_etf_prices()` | `data/{ticker}.csv` | Multi-level CSV header; keeps only the `Close` column; index → datetime |
| `load_notes()` | `SELECT * FROM client_notes` | `date` → datetime |
| `load_contacts()` | `SELECT * FROM client_contacts` | `contact_date` → datetime |
| `load_aum_history()` | `SELECT * FROM aum_history` | `date` → datetime |
| `load_action_queue()` | JOIN query (see below) | Returns only `status='open'` rows, ordered by stream then urgency DESC |
| `load_pension_config()` | `SELECT * FROM pension_product_config LIMIT 1` | Returns `df.iloc[0]` (a Series) or None |

`load_action_queue` SQL:
```sql
SELECT aq.id, aq.client_id, c.name AS client_name,
       aq.stream, aq.reason, aq.suggested_action,
       aq.urgency_score, aq.estimated_minutes,
       aq.status, aq.created_at
FROM action_queue aq
JOIN clients c ON c.client_id = aq.client_id
WHERE aq.status = 'open'
ORDER BY aq.stream, aq.urgency_score DESC
```

`load_etf_prices` reads five CSV files and returns a `dict[ticker → pd.Series]`. The CSVs were downloaded from Yahoo Finance using `yfinance` and have a multi-level header (top level = field name, second level = ticker). The code reads both levels, then extracts just the `Close` level-0 column:

```python
df = pd.read_csv(f'data/{ticker}.csv', header=[0, 1], index_col=0)
df.columns = df.columns.get_level_values(0)
prices[ticker] = df['Close']
```

### 3.3 Health Score — `compute_health_score(client_row) → int`

Returns an integer 0–100. Four components, each worth exactly 25 points:

**Component 1 — Login frequency:**
```
login_score = min(login_count_this_week, 5) / 5 × 25
```
- 0 logins → 0 pts
- 3 logins → 15 pts
- 5+ logins → 25 pts (capped at 5)

**Component 2 — Deposit activity:**
```
deposit_score = 25 if monthly_deposit > 0 else 0
```
Binary — any standing deposit earns full 25 pts.

**Component 3 — Portfolio size:**
```
portfolio_score = min(portfolio_value_eur / 50,000, 1.0) × 25
```
- €0 → 0 pts
- €25,000 → 12.5 pts
- €50,000 → 25 pts (capped)

**Component 4 — Login recency:**
```
days_since_login = today - last_login_date (in days)
recency_score = 25 if days_since_login ≤ 30 else 0
```
Binary — logged in within 30 days earns full 25 pts.

**Total:**
```
health_score = int(login_score + deposit_score + portfolio_score + recency_score)
```

**Colour thresholds:**
- ≥ 70 → green (Healthy)
- 40–69 → orange (Moderate)
- < 40 → red (At Risk)

### 3.4 Churn Risk — `compute_churn_risk(client_row) → str`

Three binary signals:

```
s1 = missed_deposits_last_3_months >= 2
s2 = login_count_this_week <= 1
s3 = portfolio_performance_pct < -3.0
```

**Classification:**
```
if s1 AND s2 AND s3:  return 'High'
elif s1 OR s2 OR s3:  return 'Medium'
else:                 return 'Low'
```

All three must be simultaneously triggered for High. A single triggered signal is enough for Medium.

### 3.5 Pension Fit Score — `compute_pension_fit_score(client_row) → int`

Five additive components, total 0–100:

| Component | Points | Condition |
|-----------|--------|-----------|
| Age in range | 30 | 25 ≤ age ≤ 50 |
| Deposit consistency | 25 | missed_deposits_last_3_months == 0 |
| Portfolio size | 20 | portfolio_value_eur > 10,000 |
| Risk profile | 15 | risk_profile in ('balanced', 'growth') |
| Investment goal | 10 | goal contains 'pension', 'retirement', 'long-term', or 'long term' |

**Fit labels:**
- ≥ 70 → ✅ Strong Fit
- 40–69 → ⚠️ Moderate
- < 40 → — (Not a candidate)

### 3.6 `compute_last_contact_days(contacts_df) → pd.Series`

Groups `client_contacts` by `client_id`, takes the maximum `contact_date` per client, and returns days since that date as a Series indexed by `client_id`:

```python
(today - contacts_df.groupby('client_id')['contact_date'].max()).dt.days
```

Clients with no contact record are absent from the Series. Callers do `.fillna(999)` to treat no-contact as 999 days ago.

### 3.7 `generate_action_queue(engine) → None`

This is the core queue engine. It is called once per browser session on page load (guarded by `'last_regenerated_at' in st.session_state`) and can be triggered again by clicking the Refresh Queue button.

**Step 1 — Load all data from the database:**
- All clients with scores computed
- Contact history → `days_since_last_contact` per client
- Recent market events (last 7 days, severity warning/critical, with a non-null ETF ticker)
- All client portfolios → which clients hold which ETFs
- All non-open action_queue rows → prior state for snooze/done/skip detection

**Step 2 — Build `market_affected` dict:**

```python
severity_rank = {'critical': 3, 'warning': 2, 'info': 1}
market_affected = {}  # client_id → max severity numeric

for each portfolio row where etf is in affected_etfs:
    max_severity = max severity rank of all alerts for that ETF
    market_affected[client_id] = max(current, max_severity)
```

**Step 3 — `_stream_state(cid, stream)` — per-(client, stream) state check:**

Filters `existing` (non-open rows) to rows matching BOTH `client_id == cid` AND `stream == stream`.

Returns one of:
- `('active_snooze', row_id)` — snoozed row exists where `snooze_until > now`
- `('expired_snooze', row_id)` — snoozed row exists but `snooze_until ≤ now`
- `('resolved_today', None)` — done/skipped row with `resolved_at >= today midnight`
- `('free', None)` — no blocking row in this stream

**Step 4 — Classify each client:**

For each client, collect `candidates = []` of qualifying (stream, reason, action, urgency, mins) tuples. Each stream is checked with an independent `if` (not `elif`) so a client can qualify for multiple streams simultaneously.

**at_risk triggers (any one of three, checked with if/elif):**

```python
if churn == 'High':
    urgency = churn_numeric[churn] × days_since_last_contact
    # "All 3 churn signals active"

elif login_count_this_week >= 5 AND portfolio_performance_pct < -5.0:
    # Panic behaviour detected

elif days_since_login > 120:
    # Disengaging client
```

**market_event trigger:**
```python
if cid in market_affected:
    urgency = severity_numeric × days_since_last_contact
```

**onboarding trigger:**
```python
if months_since_joining <= 6:
    urgency = max(6 - months, 1) × 10
    # Higher urgency for newer clients (month 1 gets urgency 50, month 6 gets urgency 10)
```

**pension trigger:**
```python
if pension_fit_score >= 70:
    urgency = pension_fit_score
```

**milestone triggers (either condition, checked with if/elif):**
```python
if months_since_joining > 0 AND months_since_joining % 12 == 0:
    urgency = (portfolio_value / 10,000) × (days_contact / 30)
    # Anniversary year

elif portfolio_value > 20,000 AND days_since_last_contact > 60:
    urgency = same formula
    # High-value client overdue for contact
```

**Step 5 — Apply stream state and write to DB:**

For each (client, stream) candidate:
- `active_snooze` → skip (do nothing)
- `resolved_today` → skip (already handled today)
- `expired_snooze` → add to `revive_rows` (will UPDATE existing row back to 'open')
- `free` → add to `new_rows` (will INSERT a new row)

**Step 6 — DB writes (single transaction):**

```sql
-- 1. Clear all currently open rows
DELETE FROM action_queue WHERE status = 'open'

-- 2. Revive expired snoozes
UPDATE action_queue SET status='open', stream=..., reason=...,
    suggested_action=..., urgency_score=..., estimated_minutes=...,
    snooze_until=NULL, created_at=NOW()
WHERE id=:id

-- 3. Insert fresh rows
INSERT INTO action_queue (client_id, stream, reason, suggested_action,
    urgency_score, estimated_minutes, status, created_at)
VALUES (..., 'open', NOW())
```

The DELETE + re-INSERT on every regeneration ensures the queue always reflects current client state, not stale data from a previous session.

### 3.8 `add_clients_to_queue_direct(engine, client_ids, stream, reason, suggested_action, estimated_minutes=5) → int`

Manual queue addition from the Client Hub. The rule: skip a client only if they already have an `open` row in the **same stream**. A client open in `at_risk` can still be added to `pension`.

```sql
SELECT client_id FROM action_queue WHERE status='open' AND stream=:stream
```

Uses `text()` wrapper for SQLAlchemy parameterised query (`:stream` style).

Returns the count of rows actually inserted (total requested minus skipped).

### 3.9 `render_sidebar()`

Called at the top of every page. Does:
1. Injects the Google Analytics 4 tracking script via `st.components.v1.components.html()` (see §16)
2. Loads clients and computes KPI metrics: total clients, total AUM, annual fee revenue (AUM × 1%)
3. Renders the logo
4. Renders the Global Search box — searches client names (substring match, case-insensitive) and ETF tickers
5. If a single client is found → "Go to Profile" button sets `selected_client_id` and switches to page 2
6. If multiple clients match → selectbox + "Go to Profile" button
7. If input matches an ETF ticker → "View in Quant Feed" button sets `session_state['search_etf']` and switches to page 5
8. Renders KPI metrics below the search
9. If `selected_client_id` is in session state → shows "Viewing: [Name]" and a "Back to Profile" button

---

## 4. app.py — entry point

```python
st.set_page_config(
    page_title='froots Intelligence Platform',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)
st.logo("assets/froots_logo.png", size="large")
st.switch_page('pages/0_todays_work.py')
```

`app.py` exists only to set the global page config (which Streamlit reads before rendering any page) and immediately redirect to Today's Work. Streamlit requires the `set_page_config` call to happen in the entry-point file for it to apply globally.

---

## 5. Page 0 — Today's Work (`0_todays_work.py`)

### Stream metadata

```python
STREAMS = {
    'at_risk':      {'label': 'At-Risk Outreach',        'icon': '🔴'},
    'market_event': {'label': 'Market Event Response',   'icon': '📉'},
    'onboarding':   {'label': 'New Client Onboarding',   'icon': '🌱'},
    'pension':      {'label': 'Pension Conversions',     'icon': '🏦'},
    'milestone':    {'label': 'Milestone & Relationship','icon': '⭐'},
}
```

### Urgency label derivation — `_urgency_label(stream, urgency_score) → str`

The raw `urgency_score` from the database is a float that means different things per stream. This function converts it to a human-readable label:

| Stream | High | Medium | Low |
|--------|------|--------|-----|
| at_risk | always High | — | — |
| market_event | urgency_score > 200 | otherwise | — |
| onboarding | score ≥ 30 | 10 ≤ score < 30 | score < 10 |
| pension | score ≥ 90 | 80 ≤ score < 90 | score < 80 |
| milestone | score > 30 | otherwise | — |

### Queue lifecycle

**Session guard:** `generate_action_queue` is called once per browser session:
```python
if 'last_regenerated_at' not in st.session_state:
    utils.generate_action_queue(engine)
    utils.load_action_queue.clear()
    st.session_state['last_regenerated_at'] = datetime.now()
```

**Manual refresh:** "🔄 Refresh Queue" button re-runs `generate_action_queue` and clears the cache.

**KPI strip:**
- "Clients contacted this week" — count of distinct client_ids in `client_contacts` where `contact_date >= today - 7 days`
- "Est. time saved today" — `done_today_count × 0.25` hours (each completed item = 15 min)
- "Open queue items" — COUNT of rows in `action_queue` where `status='open'`

### Action handlers

```python
def _mark_done(row_id):
    UPDATE action_queue SET status='done', resolved_at=NOW() WHERE id=:id
    load_action_queue.clear()

def _snooze(row_id):
    snooze_until = datetime.now() + timedelta(days=7)
    UPDATE action_queue SET status='snoozed', snooze_until=:su WHERE id=:id
    load_action_queue.clear()

def _skip(row_id):
    UPDATE action_queue SET status='skipped', resolved_at=NOW() WHERE id=:id
    load_action_queue.clear()
```

All three clear the `load_action_queue` cache so the UI refreshes on the next `st.rerun()`.

### Layout

- Single-stream filter → full-width column, all cards stacked vertically
- All streams → `st.columns(5)` with one stream per column; each card is `st.container(border=True)`

---

## 6. Page 1 — Client Hub (`1_customer_intelligence.py`)

### Computed columns added to clients DataFrame

```python
clients['health_score']      = clients.apply(compute_health_score, axis=1)
clients['churn_risk']        = clients.apply(compute_churn_risk, axis=1)
clients['pension_fit_score'] = clients.apply(compute_pension_fit_score, axis=1)
clients['days_since_login']  = (today - clients['last_login_date']).dt.days
clients['days_since_contact'] = clients['client_id'].map(last_contact_days).fillna(999).astype(int)
```

`last_contact_days` is computed by `compute_last_contact_days(contacts)` which returns a Series indexed by client_id.

### Suggested next action

```python
def _suggested_action(row):
    if row['churn_risk'] == 'High':    return '📞 Call'
    if row['health_score'] < 40:       return '📧 Reassure'
    if row['days_since_contact'] > 60: return '📅 Check-in'
    return '✅ Engaged'
```

Checked in priority order (if/elif chain).

### Segment definitions

```python
hv_threshold = clients['portfolio_value_eur'].quantile(0.80)

SEGMENTS = {
    'All Clients':        mask = True for all,                          stream = None
    'At Risk':            (health_score < 40) | (churn_risk == 'High'), stream = 'at_risk'
    'High Value':         portfolio_value_eur >= 80th percentile,       stream = 'milestone'
    'New This Month':     months_since_joining <= 1,                    stream = 'onboarding'
    'Pension Candidates': pension_fit_score >= 70,                      stream = 'pension'
    'Dormant':            days_since_login > 60,                        stream = 'at_risk'
    'Recently Contacted': days_since_contact <= 7,                      stream = None
}
```

`stream = None` means the "Add to Queue" button is disabled for that segment tab.

### Cross-segment filter

Three filter widgets apply on top of the segment mask:
- `risk_profile` multiselect
- `portfolio_value_eur` range slider
- `monthly_deposit` range slider

Final mask = `segment_mask AND filter_mask`. Both masks are boolean Series aligned on the clients DataFrame index.

### Table interaction

```python
event = st.dataframe(
    styled_df,
    selection_mode='multi-row',
    on_select='rerun',   # triggers Streamlit rerun when selection changes
    key=f'table_{tab_name}'
)
selected_indices = event.selection.rows
```

`event.selection.rows` returns a list of integer row indices in the displayed DataFrame. `segment_clients.iloc[selected_indices]` retrieves the original rows including `client_id`.

### Bulk add to queue

```python
n_added = utils.add_clients_to_queue_direct(
    engine, selected_ids, stream, segment_reason, segment_action
)
utils.load_action_queue.clear()
```

### Business Health expander

- `clients_at_risk = ((health_score < 40) | (churn_risk == 'High')).sum()`
- `total_aum = portfolio_value_eur.sum()`
- `annual_fee_rev = total_aum × 0.01`
- AUM line chart uses `load_aum_history()` — 24 data points, one per month

---

## 7. Page 2 — Client Profile (`2_client_portfolio.py`)

### Client selection

At the top of the page (before any data loading), a `st.selectbox` shows all client names alphabetically. The native Streamlit selectbox supports typing to filter. If `selected_client_id` is already in `st.session_state` (set by Client Hub or Today's Work), the matching name is pre-selected:

```python
_default_idx = _options.index(_default_name) if _default_name in _options else 0
```

On selection change, the new `cid` is written to session state and the page renders the new client's data.

### Computed values

```python
health_score     = compute_health_score(client)
churn_risk       = compute_churn_risk(client)
days_since_login = (today - client['last_login_date']).days
annual_fee       = client['portfolio_value_eur'] × 0.01

pension_score = compute_pension_fit_score(client)

# Pension component breakdown (re-computed inline for display)
age_pts       = 30 if 25 ≤ age ≤ 50 else 0
deposit_pts   = 25 if missed_deposits_last_3_months == 0 else 0
portfolio_pts = 20 if portfolio_value_eur > 10,000 else 0
profile_pts   = 15 if risk_profile in ('balanced', 'growth') else 0
goal_pts      = 10 if goal contains 'pension'/'retirement'/'long-term' else 0
```

### Health score component breakdown (for display)

```python
login_score     = min(login_count_this_week, 5) / 5 × 25
deposit_score   = 25 if monthly_deposit > 0 else 0
portfolio_score = min(portfolio_value_eur / 50,000, 1.0) × 25
recency_score   = 25 if days_since_login ≤ 30 else 0
```

These are re-computed inline (not imported from utils) to have the individual component values for the breakdown display.

### Activity timeline construction

Four sources are merged into a single timeline:

1. **Contacts** — from `client_contacts` filtered to this client
2. **Notes** — from `client_notes` filtered to this client
3. **ETF alerts** — from `quant_events` where `etf_ticker` is in `client_etfs` and `timestamp >= today - 30 days`
4. **Queue history** — from `action_queue` where `client_id = cid AND status != 'open'`

All four are unified into dicts `{date, icon, label, detail}`, sorted newest-first, capped at 20 visible items, remainder in a "Show N older" expander.

### Portfolio drift

```python
drift = weight_pct - target_pct
if drift > 1.0:  "above target — may be rebalanced down"
elif drift < -1.0: "below target — may receive additional allocation"
else: "on target"
```

Threshold is ±1 percentage point.

### Panic detection

```python
high_login_flag    = login_count_this_week >= 5
negative_perf_flag = portfolio_performance_pct < -5.0

Critical: both flags = True
Warning (login): high_login_flag only
Warning (perf): negative_perf_flag only
All clear: neither flag
```

### Suggested action (derived from health/churn)

```python
if churn_risk == 'High':       "Recommend immediate phone call"
elif health_score < 40:        "Send reassurance email"
elif days_since_contact >= 60: "Schedule monthly check-in"
else:                          "No action needed"
```

### Recent ETF alerts (Section 6)

Shows events from `quant_events` where `etf_ticker in client_etfs` and `timestamp >= today - 7 days`.

For each alert, a "Draft Email" expander opens with a pre-written message template using the alert's `reason` and `etf_ticker`.

### Add note form

```sql
INSERT INTO client_notes (client_id, date, note_text, added_by)
VALUES (:cid, NOW(), :note, :author)
```

After insert, calls `utils.load_notes.clear()` and `st.rerun()` so the new note appears immediately.

---

## 8. Page 3 — Market Pulse (`3_risk_metrics.py`)

### Daily return computation

```python
returns_df = pd.DataFrame({t: price_data[t].pct_change() for t in tickers})
```

`pct_change()` on a `pd.Series` of closing prices gives `(P_t - P_{t-1}) / P_{t-1}` for each day.

### Signal detection — "notable move"

For each ETF ticker:

```python
recent_return = price_series.pct_change().iloc[-1]        # today's return
daily_vol     = price_series.pct_change().std()           # historical std of daily returns
is_notable    = abs(recent_return) > daily_vol            # outside ±1σ
```

If notable, the ticker appears as a signal card with:
- Direction and percentage: `"up 1.2%"` or `"down 2.3%"`
- Normal daily swing: `f"±{daily_vol*100:.1f}%"`
- Pre-drafted email using `DRAFT_TEMPLATE` with the ETF, direction, percentage, and normal swing substituted

**Annualised volatility:**
```python
annualised_vol = daily_vol × sqrt(252)
```
252 = trading days per year.

### Client exposure section

```python
portfolios_merged = portfolios.merge(clients, on='client_id')
ticker_clients    = portfolios_merged[portfolios_merged['etf'] == selected_ticker]
```

Shows: count of clients holding the ETF, their health score distribution, churn risk breakdown, and a table of names with portfolio values.

### Risk metrics section

For each ETF:

**Maximum drawdown:**
```python
cummax = prices.cummax()        # rolling maximum
drawdown = (prices - cummax) / cummax    # drawdown at each point
max_drawdown = drawdown.min()   # worst point
```

**Sharpe ratio (simplified, assumes 0% risk-free rate):**
```python
sharpe = (daily_returns.mean() / daily_returns.std()) × sqrt(252)
```

**Correlation matrix:**
```python
returns_df.corr()
```
Displayed as a Plotly heatmap. High correlation (>0.8) between ETFs reduces diversification benefit.

---

## 9. Page 4 — Crash Context (`4_crash_recovery.py`)

### Event definitions

```python
EVENTS = {
    'COVID Crash 2020':    ('2020-01-01', '2021-06-30'),
    '2022 Rate Spike':     ('2021-12-01', '2023-06-30'),
    '2023 Banking Crisis': ('2023-01-01', '2023-12-31'),
    'Custom Date Range':   None,   # user picks start/end via date_input
}
```

### Drawdown computation for a selected period

```python
period_prices = prices.loc[start_date:end_date]
normalised    = period_prices / period_prices.iloc[0]   # index to 1.0 at start
```

**Maximum drawdown within period:**
```python
rolling_max   = normalised.cummax()
drawdown      = (normalised - rolling_max) / rolling_max
max_dd        = drawdown.min()                           # most negative value
```

**Recovery check:**
For each date after the drawdown trough, check whether `normalised >= 1.0` (back to starting level). The first such date is the recovery date.

**Annualised return over the period:**
```python
total_return  = normalised.iloc[-1] - 1
years         = (end_date - start_date).days / 365.25
ann_return    = (1 + total_return) ^ (1 / years) - 1
```

### Narrative system

Each named event maps to a plain-English narrative string in `EVENT_NARRATIVES`. A `GENERIC_NARRATIVE` fallback is used for 'Custom Date Range' and any event key not in the dict. The narrative explains what happened and provides the key message for client communication.

---

## 10. Page 5 — Quant & Support Feed (`5_quant_feed.py`)

### Pre-populated search from sidebar

```python
default_keyword = st.session_state.pop('search_keyword', '')
default_etf     = st.session_state.pop('search_etf', '')
```

`pop()` removes the key after reading so it does not persist across reruns. The sidebar sets these keys before calling `st.switch_page('pages/5_quant_feed.py')`.

### Filters applied to quant_events

- `event_type` multiselect (Risk Alert, Rebalance Alert, Information Update)
- `severity` multiselect (info, warning, critical)
- `etf_ticker` text input (substring match)
- `keyword` text input (searches the `reason` column)

All filters are ANDed together using boolean masks on the DataFrame.

### "Mark as communicated"

```sql
UPDATE quant_events SET communicated=TRUE WHERE id=:id
```

Followed by `load_quant_events.clear()` and `st.rerun()`.

### Draft email templates

Three templates keyed by `event_type`:

```python
DRAFT_TEMPLATES = {
    'Risk Alert':        "Subject: Update on recent market activity\n\n...",
    'Rebalance Alert':   "Subject: Your portfolio has been reviewed\n\n...",
    'Information Update':"Subject: Important update for your froots account\n\n...",
}
```

Displayed in a `st.expander` per event with `st.text_area` (pre-filled, editable).

---

## 11. Page 6 — Pension Tool (`6_pension_tool.py`)

### Configuration loading

```python
cfg = utils.load_pension_config()

FROOTS_FEE     = 0.012   # Hardcoded override: 1.0% mgmt + 0.17% ETF + 0.03% risk premium (fynup benchmark, age 35)
FROOTS_KEST    = float(cfg['kest_rate_inside_pct']) / 100 if cfg else 0.0     # 0% (KeSt-free)
FROOTS_INS_TAX = float(cfg['insurance_tax_pct'])    / 100 if cfg else 0.04    # 4% Versicherungssteuer
CLASSIC_FEE    = float(cfg['classic_flv_fee_pct'])  / 100 if cfg else 0.015   # 1.5% (fynup benchmark)
CLASSIC_KEST   = float(cfg['classic_flv_kest_pct']) / 100 if cfg else 0.275   # 27.5% KeSt at exit
```

`FROOTS_FEE` is hardcoded to 0.012 (1.2%) regardless of DB config. This reflects the actual cost breakdown:

| Component | Rate |
|-----------|------|
| froots management fee | 1.00% |
| ETF product costs (weighted average) | 0.17% |
| Risk premium (35-year-old profile) | 0.03% |
| **Total** | **1.20%** |

Source: fynup benchmark data for comparable Austrian insurance wrapper products.

---

### `_project_lumpsum(principal, r, years, fee, ins_tax, kest)`

Models a one-time lump sum investment over N years.

**Step 1 — Apply Versicherungssteuer on entry:**
```python
after_tax_premium = principal × (1 - ins_tax)
```
For froots: `ins_tax = 0.04`, so €10,000 → €9,600 net invested.
For classic FLV: `ins_tax = 0.0`, so full amount is invested.

**Step 2 — Annual compound growth minus annual fee:**
```python
for each year:
    growth   = value × r
    fee_paid = value × fee
    value    = value + growth - fee_paid
```

Equivalent to: `value_n = value_0 × (1 + r - fee)^n` (linear approximation; the code iterates explicitly).

**Step 3 — Exit tax on gains:**
```python
gains    = max(gross_final - principal, 0)
tax_paid = gains × kest
net_final = gross_final - tax_paid
```

For froots: `kest = 0`, so `net_final = gross_final`.
For classic FLV: `kest = 0.275`, so 27.5% of gains are taxed at exit.

**Returns:** `(net_final, gross_final, total_fees, tax_paid, series_by_year)`

---

### `_project_monthly(monthly, r, years, fee, ins_tax, kest)`

Models a regular monthly contribution investment over N years.

**Step 1 — Versicherungssteuer per contribution:**
```python
monthly_eff = monthly / (1 + ins_tax)
```

This is the Austrian Versicherungssteuer calculation: the 4% tax is applied such that the net invested amount is `monthly / 1.04`. The tax deducted per month is:

```
tax_per_month = monthly - monthly_eff
             = monthly - monthly/(1 + ins_tax)
             = monthly × ins_tax / (1 + ins_tax)
```

At C = €300/month, ins_tax = 4%:
```
monthly_eff   = 300 / 1.04 = 288.4615...
tax_per_month = 300 × 0.04 / 1.04 = 11.5385...
total_VSt     = 11.5385 × 360 months = €4,153.8 ≈ €4,154
```

For classic FLV: `ins_tax = 0.0`, so `monthly_eff = 300 / 1.0 = 300` (unchanged).

**Step 2 — Linear fee drag (monthly):**
```python
net_monthly_r = (r - fee) / 12
monthly_fee   = fee / 12          # for tracking only
```

This uses the linear approximation of annual fee drag, distributed monthly. For froots:
```
net_monthly_r = (0.07 - 0.012) / 12 = 0.058 / 12 = 0.004833... per month
```

**Step 3 — Monthly compound iteration:**
```python
value = 0
for m in range(years × 12):
    value      = (value + monthly_eff) × (1 + net_monthly_r)
    fee_month  = (value - monthly_eff) × monthly_fee   # approximate fee on balance
    total_fees += fee_month
    if (m+1) % 12 == 0:
        series_by_year.append(value)
```

Each month: add the net contribution, then compound at the net monthly rate. Fee tracking is approximate (computed on the post-contribution balance).

**Final value approximation (closed-form FV of annuity):**

The iterative result is approximately equal to the Future Value of an ordinary annuity:

```
FV = monthly_eff × [(1 + net_monthly_r)^(years×12) - 1] / net_monthly_r
```

At defaults (C=300, r=7%, n=30, froots fee=1.2%, ins_tax=4%):
- `monthly_eff = 288.46`
- `net_monthly_r = 0.004833`
- `(1.004833)^360 ≈ 5.674`
- `FV ≈ 288.46 × 4.674 / 0.004833 ≈ €278,985`

**Step 4 — Exit tax:**
```python
gains     = max(gross_final - total_invested, 0)
tax_paid  = gains × kest
net_final = gross_final - tax_paid
```

`total_invested = monthly × 12 × years` (the full gross monthly amount, not the net).

**Returns:** `(net_final, gross_final, total_fees, tax_paid, series_by_year, total_invested)`

---

### froots vs Classic FLV comparison at defaults (C=300, r=7%, n=30)

| | froots Vorsorge | Classic FLV |
|--|----------------|-------------|
| Monthly effective | 300/1.04 = 288.46 | 300/1.0 = 300 |
| Net monthly rate | (7%-1.2%)/12 = 0.4833% | (7%-1.5%)/12 = 0.4583% |
| Gross final | ≈ €278,985 | ≈ €274,140 |
| KeSt at exit | €0 (0%) | ≈ €45,689 (27.5% on gains) |
| **Net final** | **≈ €278,985** | **≈ €228,451** |
| **Advantage** | **≈ €50,534** | — |

Target range from fynup benchmark: €45,000–€55,000. ✓

---

### Back-Calculation — actual historical return

VWCE.DE is used as the primary ETF (largest allocation in all three risk profiles):

```python
period        = vwce_prices.loc[str(start_date):]
total_return  = (period.iloc[-1] / period.iloc[0]) - 1
actual_return = (1 + total_return)^(1/years) - 1
```

This is the geometric mean annual return (CAGR) over the selected look-back period. Used as the `r` parameter in `_project_monthly` for the back-calculation.

### PDF generation — `_build_projection_pdf(...) → bytes`

Builds an HTML string with an inline `<style>` block and a structured table layout, then uses WeasyPrint to render it to PDF bytes:

```python
import weasyprint
return weasyprint.HTML(string=html).write_pdf()
```

The `extra_sections` parameter (used in tab 7.6) allows injecting additional HTML sections (ETF allocation table, Q&A from the question library) into the PDF body.

Returns `None` if WeasyPrint is not installed (graceful fallback — user sees an error message instead).

---

## 12. Data files

### ETF price CSVs (`data/VWCE.DE.csv` etc.)

Downloaded via `yfinance`. Each CSV has a two-level column header:

```
            AGGG.L
Close Open High  Low Volume
date
2018-01-02  ...
```

The code reads `header=[0, 1]`, then `.get_level_values(0)` to get `['Close', 'Open', 'High', 'Low', 'Volume']` as flat column names, then extracts only `df['Close']`.

### Other CSVs (`clients.csv`, `client_portfolios.csv`, etc.)

Used only as a backup/import source during development. In production, all reads go to PostgreSQL. The CSVs are not read at runtime (except ETF prices which are not in the DB).

---

## 13. Migrations

Migrations are plain SQL files in the `migrations/` directory, meant to be run once in order in the Supabase SQL editor.

### `001_action_queue.sql`
Creates the `action_queue` table with all columns: `id` (SERIAL PK), `client_id`, `stream`, `reason`, `suggested_action`, `urgency_score`, `estimated_minutes`, `status`, `created_at`, `snooze_until`, `resolved_at`.

### `002_pension_product_config.sql`
Creates the `pension_product_config` table and inserts one seed row with the product defaults.

### `003_quant_events_communicated.sql`
Adds the `communicated BOOLEAN DEFAULT FALSE` column to the existing `quant_events` table.

### `004_seed_stream_data.sql`
A DO block that inserts six new onboarding clients (Emma Kirchner through Michael Steiner, months 1–6) with associated portfolios, then inserts three market event alerts (VWCE.DE warning, AGGG.L critical, EIMI.L warning) within the last 7 days, then backfills the `affected_clients` count using the actual `client_portfolios` data.

Key pattern for safe seeding with integer primary keys:
```sql
DECLARE v_base INTEGER; v_id INTEGER;
BEGIN
    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;
    IF NOT EXISTS (SELECT 1 FROM clients WHERE name = 'Emma Kirchner') THEN
        v_base := v_base + 1;
        INSERT INTO clients (client_id, ...) VALUES (v_base, ...);
    END IF;
    -- re-read max before each insert to handle concurrent inserts
    SELECT COALESCE(MAX(client_id), 0) INTO v_base FROM clients;
    ...
END $$;
```

---

## 14. Session state and cross-page navigation

Streamlit's `st.session_state` is a dictionary that persists across reruns within a single browser session (tab). It is cleared when the browser tab is closed.

### Keys used across the app

| Key | Set by | Read by | Purpose |
|-----|--------|---------|---------|
| `selected_client_id` | pages 0, 1, sidebar | page 2, sidebar | Which client profile to show |
| `last_regenerated_at` | page 0 | page 0 | Prevents queue from regenerating on every rerun |
| `search_etf` | sidebar | page 5 (popped on read) | Pre-populates ETF search in Quant Feed |
| `search_keyword` | sidebar | page 5 (popped on read) | Pre-populates keyword search in Quant Feed |
| `saved_projection` | page 6 tab 7.2 | page 6 tab 7.6 | Passes a saved scenario from Custom Projection to Report Export |

### Navigation pattern

```python
# Set state first, then switch page
st.session_state['selected_client_id'] = int(client_id)
st.switch_page('pages/2_client_portfolio.py')
```

`st.switch_page` triggers an immediate page navigation. The target page reads `st.session_state['selected_client_id']` on its next render.

---

## 15. Caching strategy

| Cache type | Used for | TTL | Clear method |
|-----------|----------|-----|-------------|
| `@st.cache_resource` | SQLAlchemy engine | Forever (process lifetime) | Restart server |
| `@st.cache_data(ttl=300)` | All DB data loaders | 5 minutes | `.clear()` on the function |
| `@st.cache_data(ttl=60)` | `load_action_queue` | 1 minute | `.clear()` after queue mutations |
| `@st.cache_data` (no TTL) | `load_etf_prices` | Forever (process lifetime) | Restart server |

ETF prices are not cached with a TTL because the CSV files do not change at runtime.

When a CE agent marks a queue item done/snoozed/skipped, the handler immediately calls `utils.load_action_queue.clear()` before `st.rerun()`. This forces the cache to be repopulated on the next call, so the updated queue appears immediately rather than waiting for the 60-second TTL to expire.

---

## 16. Google Analytics integration

GA4 tracking is injected via `render_sidebar()` using `streamlit.components.v1.components.html()` with `height=0` (invisible):

```python
components.html(f"""
<script>
(function() {{
    var GA_ID = '{GA_ID}';
    var p = window.parent;

    // Inject gtag library into parent document <head> once
    if (!p.document.querySelector('script[src*="' + GA_ID + '"]')) {{
        var s = p.document.createElement('script');
        s.async = true;
        s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
        p.document.head.appendChild(s);
    }}

    // Initialise dataLayer and gtag in parent window
    p.dataLayer = p.dataLayer || [];
    p.gtag = p.gtag || function() {{ p.dataLayer.push(arguments); }};

    // Fire page_view with parent URL and title
    p.gtag('js', new Date());
    p.gtag('config', GA_ID, {{
        'page_location': p.location.href,
        'page_title': p.document.title,
        'send_page_view': true
    }});
}})();
</script>
""", height=0)
```

**Why this is necessary:** Streamlit renders each component in its own `<iframe>`. Tracking scripts injected inside an iframe only see the iframe's origin (typically `localhost` or the Streamlit Cloud internal URL), not the actual app URL. By accessing `window.parent` from inside the component iframe, the script injects the gtag library into the parent document's `<head>` and fires the page_view event with the real parent URL and title. The `if (!p.document.querySelector(...))` guard prevents the library from being loaded more than once per session.

GA tracking ID: `G-3NB5QZVMMX`

---

## File-to-file dependency map

```
app.py
  └── utils.render_sidebar (via page redirects)

pages/0_todays_work.py
  ├── utils.render_sidebar()
  ├── utils.get_engine()
  ├── utils.generate_action_queue(engine)
  ├── utils.load_action_queue()
  ├── utils.load_contacts()
  └── [writes to]: action_queue (done/snooze/skip)

pages/1_customer_intelligence.py
  ├── utils.render_sidebar()
  ├── utils.load_clients()
  ├── utils.load_contacts()
  ├── utils.load_aum_history()
  ├── utils.compute_health_score()
  ├── utils.compute_churn_risk()
  ├── utils.compute_pension_fit_score()
  ├── utils.compute_last_contact_days()
  ├── utils.add_clients_to_queue_direct()
  └── [writes to]: action_queue (manual bulk add)

pages/2_client_portfolio.py
  ├── utils.render_sidebar()
  ├── utils.load_clients()
  ├── utils.load_portfolios()
  ├── utils.load_quant_events()
  ├── utils.load_notes()
  ├── utils.load_contacts()
  ├── utils.get_engine()
  ├── utils.compute_health_score()
  ├── utils.compute_churn_risk()
  ├── utils.compute_pension_fit_score()
  ├── utils.health_color()
  ├── utils.churn_color()
  ├── [reads from]: action_queue (open items for "why in queue" panel)
  ├── [reads from]: action_queue (history for timeline)
  └── [writes to]: client_notes (add note form)

pages/3_risk_metrics.py
  ├── utils.render_sidebar()
  ├── utils.load_etf_prices()
  ├── utils.load_portfolios()
  ├── utils.load_clients()
  ├── utils.compute_churn_risk()
  └── utils.compute_health_score()

pages/4_crash_recovery.py
  ├── utils.render_sidebar()
  └── utils.load_etf_prices()

pages/5_quant_feed.py
  ├── utils.render_sidebar()
  ├── utils.load_quant_events()
  ├── utils.load_portfolios()
  ├── utils.load_clients()
  ├── utils.get_engine()
  └── [writes to]: quant_events (mark communicated)

pages/6_pension_tool.py
  ├── utils.render_sidebar()
  ├── utils.load_clients()
  ├── utils.load_etf_prices()
  ├── utils.load_pension_config()
  ├── utils.get_engine()
  ├── utils.add_clients_to_queue_direct()
  ├── utils.compute_pension_fit_score()
  └── [writes to]: action_queue (bulk add from Fit Finder)
```
