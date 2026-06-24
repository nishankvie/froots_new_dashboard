# froots Intelligence Platform v2

An internal operational dashboard for the froots Customer Excellence (CE) team. One place for every advisor to see which clients need attention today, understand a client's full picture in seconds, react to market events intelligently, and have confident data-backed conversations about the froots pension product.

**Live demo:** https://froots.streamlit.app

---

## Why this exists

The ECB Household Finance and Consumption Survey (Wave 2021) shows that only **3.6% of Austrian 16–34 year olds own publicly traded shares** — the lowest in Europe, well below the euro area average of 10.1%. froots exists to close that gap.

But once a young Austrian decides to start investing, the harder challenge begins: keeping them engaged, informed, and calm through market volatility. That is where the CE team comes in — and this platform is built for them.

---

## What the platform does

### Today's Work — your morning briefing

Every time you open the app, it automatically scans all clients and builds a prioritised work queue across five streams. One client can appear in multiple streams simultaneously.

| Stream | When a client appears |
|--------|----------------------|
| 🔴 At-Risk Outreach | High churn risk, or 5+ logins with portfolio down >5% (panic signal), or 120+ days without login |
| 📉 Market Event Response | Client holds an ETF flagged by the quant team in the last 7 days |
| 🌱 New Client Onboarding | Client is in their first 6 months with froots |
| 🏦 Pension Conversions | Client scores ≥70 on the pension product fit model |
| ⭐ Milestone & Relationship | Anniversary year, or high-value client (>€20k) not contacted in 60+ days |

Each card shows: who, why, what to do, urgency level, estimated time. Four actions: **Open Profile**, **Mark Done**, **Snooze 7 days**, **Skip**. The queue rebuilds automatically each session and can be refreshed manually.

---

### Client Hub — find and segment clients

Seven tabs filter the client list by segment: All Clients, At Risk, High Value, New This Month, Pension Candidates, Dormant, Recently Contacted. Three filter controls (risk profile, portfolio value, monthly deposit) apply across all tabs simultaneously.

Select any row to get action buttons:
- **Open Profile** (single row) — goes directly to that client's full profile
- **Add to Queue (N)** — adds selected clients to the stream matching that segment tab
- **Export CSV** — downloads the selected subset

Score formulas are visible in a collapsible panel at the top of the page.

---

### Client Profile — the full picture

Navigate here from the Hub, from Today's Work, or directly by searching a client name in the dropdown at the top of the page. The sidebar also has global search across all client names and ETF tickers.

The profile page contains:

- **Queue status** — if the client is currently in the work queue, shows which stream(s) and why, right at the top
- **Header** — name, age, risk profile, investment goal, tenure; portfolio value, monthly deposit, YTD performance; health badge, churn risk badge, pension fit score with full component breakdown
- **Suggested action** — automatically derived from health and churn signals
- **Portfolio allocation** — pie chart (current) + grouped bar (current vs target)
- **Health Score gauge** — visual gauge with live component breakdown (all four signals with actual values)
- **Churn Risk panel** — live signal flags showing which of the three signals are triggered and their actual values
- **Panic Detection** — flags high login activity combined with negative performance
- **Portfolio Drift** — per-ETF comparison of current vs target weight with plain-English interpretation
- **Advisor Notes** — full history with an add-note form directly on the page
- **Recent ETF Alerts** — any quant alerts from the last 7 days matching this client's ETFs
- **Activity Timeline** (right panel) — every contact, note, ETF alert, and queue action for this client, newest first, capped at 20 with an overflow expander

---

### Market Pulse — live ETF signals

Loads daily price data for all five ETFs. For each ETF it computes:
- Today's return vs the ETF's historical daily volatility band
- Whether today's move is "notable" (outside the normal ±1σ range)
- Number of clients exposed and their health/churn breakdown
- A pre-drafted client email ready to copy and edit

---

### Crash Context — historical reassurance tool

Select one of three verified market events (COVID Crash 2020, 2022 Rate Spike, 2023 Banking Crisis) or a custom date range. The tool shows:
- Drawdown chart for selected ETFs over the period
- Maximum drawdown depth and recovery date
- A plain-English narrative explaining what happened and the key message to communicate to clients

---

### Quant & Support Feed — the event log

Every alert the quant team generates lives here: risk alerts, rebalance signals, information updates. Filter by event type, severity, ETF ticker, or keyword. Mark events as communicated once actioned. Pre-drafted email templates for each event type. The sidebar's global search can jump directly to a specific ETF or keyword in this feed.

---

### Pension Tool — six tabs for the Vorsorge product

| Tab | What it does |
|-----|-------------|
| **7.1 Product Snapshot** | What the product is, the tax advantage in concrete numbers, ETF allocations by risk profile |
| **7.2 Custom Projection** | Model lump sum or monthly contributions for any client, froots vs classic FLV, interactive chart, PDF export |
| **7.3 Client Fit Finder** | Every client ranked by pension fit score, formula visible, bulk add top N to queue |
| **7.4 Back-Calculation** | "If this client had been in the wrapper for the past N years, what would the euro difference be?" — uses actual VWCE.DE historical returns |
| **7.5 Question Library** | Most common client objections with fact-based answers and canned email responses |
| **7.6 Report Export** | Save a scenario and download a branded PDF |

---

## Running locally

**Requirements:** Python 3.11+, a PostgreSQL database (Supabase recommended), the five ETF CSV files in `data/`.

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Set your database URL
echo "DATABASE_URL=postgresql://..." > .env

# 3. Run migrations in order (in Supabase SQL editor or psql)
# migrations/001_action_queue.sql
# migrations/002_pension_product_config.sql
# migrations/003_quant_events_communicated.sql
# migrations/004_seed_stream_data.sql

# 4. Start the app
streamlit run app.py
```

For PDF export (Pension Tool → Report Export), install system packages:
```bash
apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```
These are in `packages.txt` and are installed automatically on Streamlit Cloud.

---

## Deploying to Streamlit Cloud

1. Push the repo to GitHub
2. Connect the repo in Streamlit Cloud
3. Add `DATABASE_URL` in the app's Secrets panel
4. Streamlit Cloud reads `packages.txt` for system-level dependencies automatically
5. Done — the app is live at your `.streamlit.app` URL

---

## Project structure

```
app.py                            Entry point — sets page config, redirects to Today's Work
utils.py                          All shared logic: DB loaders, score functions, queue engine, sidebar
pages/
  0_todays_work.py                Work queue with 5 streams and card actions
  1_customer_intelligence.py      Client Hub with 7 segment tabs and bulk actions
  2_client_portfolio.py           Individual client profile — all sections
  3_risk_metrics.py               Market Pulse — live ETF signal cards
  4_crash_recovery.py             Crash Context — historical drawdown viewer
  5_quant_feed.py                 Quant & Support Feed — event log and communication drafts
  6_pension_tool.py               Pension Tool — 6-tab projection and advisory tool
data/
  clients.csv                     Client master data (also synced to DB)
  client_portfolios.csv           ETF weights per client (also synced to DB)
  client_contacts.csv             Contact history
  client_notes.csv                Advisor notes
  aum_history.csv                 24-month AUM history
  VWCE.DE.csv  EIMI.L.csv  AGGG.L.csv  IUSV.DE.csv  WSML.L.csv   (Yahoo Finance price data)
migrations/
  001_action_queue.sql            Creates the action_queue table with all columns
  002_pension_product_config.sql  Creates the pension product config table
  003_quant_events_communicated.sql  Adds communicated boolean to quant_events
  004_seed_stream_data.sql        Seeds 6 onboarding clients and 3 market event alerts
assets/
  froots_logo.png
requirements.txt
packages.txt                      System deps for Streamlit Cloud (WeasyPrint PDF engine)
.env                              DATABASE_URL — not committed to git
```

---

## Score formulas at a glance

**Health Score (0–100)** — 25 points per component:
- Logins this week (max 5 = full 25 pts, linear)
- Monthly deposit > €0 → 25 pts
- Portfolio value: linear up to €50 k (€25 k = 12 pts, €50 k+ = 25 pts)
- Last login within 30 days → 25 pts

**Churn Risk** — three binary signals, any triggered = Medium, all three = High:
- ≥ 2 missed deposits in the last 3 months
- ≤ 1 login this week
- YTD performance < −3%

**Pension Fit Score (0–100)**:
- Age 25–50 → 30 pts
- No missed deposits (last 3 months) → 25 pts
- Portfolio > €10 k → 20 pts
- Balanced or Growth risk profile → 15 pts
- Investment goal mentions pension / retirement / long-term → 10 pts

---

## Tech stack

| Layer | Tool |
|-------|------|
| Language | Python 3.11 |
| UI framework | Streamlit (multi-page) |
| Database | PostgreSQL via Supabase |
| ORM / queries | SQLAlchemy + pandas.read\_sql |
| Charts | Plotly (line, bar, pie, gauge, heatmap) |
| PDF export | WeasyPrint (HTML → PDF) |
| Analytics | Google Analytics 4 (GA4) injected via iframe parent |
| Price data | Yahoo Finance CSVs (VWCE.DE, EIMI.L, AGGG.L, IUSV.DE, WSML.L) |

---

## About

Built by Nishank — Mathematics and Data Science student at the University of Vienna (previously Computer Science at IIIT Delhi). Built independently to think seriously about the operational challenges of a CE team at a robo-advisor, and to demonstrate that interest in a more meaningful way than a cover letter.

See [TECHNICAL_README.md](TECHNICAL_README.md) for a complete code-level reference covering every formula, every file, every database table, and every connection in the system.
