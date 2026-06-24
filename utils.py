import pandas as pd
import streamlit as st
from datetime import date, datetime
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or st.secrets["DATABASE_URL"]

@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL)

# ── Data loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)

def load_clients():

    engine = get_engine()

    df = pd.read_sql("SELECT * FROM clients", engine)

    df['last_login_date'] = pd.to_datetime(df['last_login_date'])

    return df

@st.cache_data(ttl=300)
def load_portfolios():
    engine = get_engine()
    return pd.read_sql("SELECT * FROM client_portfolios", engine)

@st.cache_data(ttl=300)
def load_quant_events():
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM quant_events", engine)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['etf_ticker'] = df['etf_ticker'].fillna('')
    df['client_specific_name'] = df['client_specific_name'].fillna('')
    if 'communicated' in df.columns:
        df['communicated'] = df['communicated'].fillna(False).astype(bool)
    else:
        df['communicated'] = False
    return df


ETF_TICKERS = ['AGGG.L', 'VWCE.DE', 'EIMI.L', 'IUSV.DE', 'WSML.L']


@st.cache_data
def load_etf_prices() -> dict:
    """Returns dict[ticker → pd.Series of daily Close prices]."""
    prices = {}
    for ticker in ETF_TICKERS:
        df = pd.read_csv(f'data/{ticker}.csv', header=[0, 1], index_col=0)
        df.index = pd.to_datetime(df.index)
        df.columns = df.columns.get_level_values(0)
        prices[ticker] = df['Close']
    return prices

@st.cache_data(ttl=300)
def load_notes():
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM client_notes", engine)
    df['date'] = pd.to_datetime(df['date'])
    return df


@st.cache_data(ttl=300)
def load_contacts():
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM client_contacts", engine)
    df['contact_date'] = pd.to_datetime(df['contact_date'])
    return df


@st.cache_data(ttl=300)
def load_aum_history():
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM aum_history", engine)
    df['date'] = pd.to_datetime(df['date'])
    return df

# ── Score computation ─────────────────────────────────────────────────────────

def compute_health_score(client_row) -> int:
    """
    Computes a 0–100 health score from four signals (25 pts each):
    - Login frequency this week
    - Deposit activity (monthly_deposit > 0)
    - Portfolio size (up to €50,000)
    - Recent login (within 30 days)
    """
    days_since_login = (pd.Timestamp(date.today()) - client_row['last_login_date']).days

    login_score     = min(client_row['login_count_this_week'], 5) / 5 * 25
    deposit_score   = 25.0 if client_row['monthly_deposit'] > 0 else 0.0
    portfolio_score = min(client_row['portfolio_value_eur'] / 50_000, 1.0) * 25
    recency_score   = 25.0 if days_since_login <= 30 else 0.0

    return int(login_score + deposit_score + portfolio_score + recency_score)


def compute_churn_risk(client_row) -> str:
    """
    Returns 'High', 'Medium', or 'Low' churn risk.
    High: ALL THREE signals triggered
    Medium: ANY ONE signal triggered
    Low: none triggered
    """
    s1 = client_row['missed_deposits_last_3_months'] >= 2
    s2 = client_row['login_count_this_week'] <= 1
    s3 = client_row['portfolio_performance_pct'] < -3.0

    if s1 and s2 and s3:
        return 'High'
    elif s1 or s2 or s3:
        return 'Medium'
    return 'Low'


def health_color(score: int) -> str:
    if score >= 70:
        return 'green'
    elif score >= 40:
        return 'orange'
    return 'red'


def churn_color(risk: str) -> str:
    return {'High': 'red', 'Medium': 'orange', 'Low': 'green'}.get(risk, 'gray')


# ── Pension & queue scoring ───────────────────────────────────────────────────

def compute_pension_fit_score(client_row) -> int:
    """
    0-100 pension product fit score.
    Deposit consistency uses missed_deposits_last_3_months as a proxy for the
    spec's 6-month window — it is the only available column.
    """
    score = 0
    age = client_row.get('age', 0)
    if 25 <= age <= 50:
        score += 30
    if client_row.get('missed_deposits_last_3_months', 99) == 0:
        score += 25
    if client_row.get('portfolio_value_eur', 0) > 10_000:
        score += 20
    if str(client_row.get('risk_profile', '')).lower() in ('balanced', 'growth'):
        score += 15
    goal = str(client_row.get('investment_goal', '')).lower()
    if 'pension' in goal or 'retirement' in goal or 'long-term' in goal or 'long term' in goal:
        score += 10
    return score


def compute_last_contact_days(contacts_df: pd.DataFrame) -> 'pd.Series':
    """
    Series indexed by client_id: days since most recent contact.
    Clients with no contact record are absent from the series (callers fillna(999)).
    """
    if contacts_df.empty:
        return pd.Series(dtype=float)
    today = pd.Timestamp(date.today())
    return (
        contacts_df.groupby('client_id')['contact_date']
        .max()
        .apply(lambda d: (today - pd.Timestamp(d)).days)
    )


def generate_action_queue(engine) -> None:
    """
    Rebuilds the open action queue from current client state.

    A client can appear in MULTIPLE streams simultaneously — one row per
    qualifying condition. Each stream row has its own lifecycle (done/snoozed/skipped).
    Snooze/done state is tracked per (client_id, stream) pair.
    """
    today     = pd.Timestamp(date.today())
    now       = pd.Timestamp(datetime.now())
    today_mid = pd.Timestamp(today.date())

    # ── Load data ──────────────────────────────────────────────────────────────
    clients = pd.read_sql("SELECT * FROM clients", engine)
    clients['last_login_date'] = pd.to_datetime(clients['last_login_date'])
    clients['churn_risk']       = clients.apply(compute_churn_risk,        axis=1)
    clients['health_score']     = clients.apply(compute_health_score,      axis=1)
    clients['pension_fit_score']= clients.apply(compute_pension_fit_score, axis=1)
    clients['days_since_login'] = (today - clients['last_login_date']).dt.days

    contacts = pd.read_sql("SELECT client_id, contact_date FROM client_contacts", engine)
    contacts['contact_date'] = pd.to_datetime(contacts['contact_date'])
    last_contact = compute_last_contact_days(contacts)
    clients['days_since_last_contact'] = (
        clients['client_id'].map(last_contact).fillna(999).astype(int)
    )

    # Market event exposure: clients whose ETFs had warning/critical alerts in last 7 days
    events = pd.read_sql("""
        SELECT etf_ticker, severity FROM quant_events
        WHERE timestamp >= NOW() - INTERVAL '7 days'
          AND severity IN ('warning', 'critical')
          AND etf_ticker IS NOT NULL AND etf_ticker != ''
    """, engine)
    portfolios = pd.read_sql("SELECT client_id, etf FROM client_portfolios", engine)

    severity_rank   = {'critical': 3, 'warning': 2, 'info': 1}
    market_affected = {}  # client_id → max severity numeric
    if not events.empty and not portfolios.empty:
        affected_etfs = set(events['etf_ticker'].unique())
        for _, pr in portfolios[portfolios['etf'].isin(affected_etfs)].iterrows():
            cid     = int(pr['client_id'])
            sevs    = events[events['etf_ticker'] == pr['etf']]['severity']
            max_sev = max((severity_rank.get(s, 1) for s in sevs), default=1)
            market_affected[cid] = max(market_affected.get(cid, 0), max_sev)

    # Existing non-open rows — keyed per (client_id, stream) for per-stream state
    existing = pd.read_sql(
        "SELECT id, client_id, stream, status, snooze_until, resolved_at "
        "FROM action_queue WHERE status != 'open'",
        engine
    )
    if not existing.empty:
        existing['snooze_until'] = pd.to_datetime(existing['snooze_until'], errors='coerce')
        existing['resolved_at']  = pd.to_datetime(existing['resolved_at'],  errors='coerce')

    def _stream_state(cid, stream):
        """State for a specific (client, stream) pair."""
        if existing.empty:
            return ('free', None)
        rows = existing[(existing['client_id'] == cid) & (existing['stream'] == stream)]
        if rows.empty:
            return ('free', None)
        snoozed = rows[rows['status'] == 'snoozed']
        if not snoozed.empty:
            row = snoozed.iloc[0]
            if pd.notna(row['snooze_until']) and row['snooze_until'] > now:
                return ('active_snooze', int(row['id']))
            return ('expired_snooze', int(row['id']))
        resolved = rows[
            rows['status'].isin(['done', 'skipped']) &
            rows['resolved_at'].notna() &
            (rows['resolved_at'] >= today_mid)
        ]
        if not resolved.empty:
            return ('resolved_today', None)
        return ('free', None)

    # ── Classify clients — each client collects ALL qualifying streams ─────────
    churn_numeric = {'High': 3, 'Medium': 2, 'Low': 1}
    new_rows    = []
    revive_rows = []

    for _, c in clients.iterrows():
        cid          = int(c['client_id'])
        churn        = c['churn_risk']
        cn           = churn_numeric[churn]
        days_contact = int(c['days_since_last_contact'])
        days_login   = int(c['days_since_login'])
        perf         = float(c['portfolio_performance_pct'])
        logins       = int(c['login_count_this_week'])
        months       = int(c['months_since_joining'])
        pfit         = int(c['pension_fit_score'])
        pval         = float(c['portfolio_value_eur'])

        # Each entry: (stream, reason, suggested_action, urgency_score, estimated_minutes)
        candidates = []

        # ── at_risk ───────────────────────────────────────────────────────────
        if churn == 'High':
            candidates.append((
                'at_risk',
                'All 3 churn signals active — missed deposits, low logins, negative performance',
                'Call client to understand situation',
                float(cn * days_contact), 5,
            ))
        elif logins >= 5 and perf < -5.0:
            candidates.append((
                'at_risk',
                'High login activity with portfolio down >5% — possible panic',
                'Proactive reassurance call',
                float(cn * days_contact), 5,
            ))
        elif days_login > 120:
            candidates.append((
                'at_risk',
                f'No login for {days_login} days — client may be disengaging',
                'Re-engagement email or call',
                float(cn * days_contact), 5,
            ))

        # ── market_event ──────────────────────────────────────────────────────
        if cid in market_affected:
            sev_num = market_affected[cid]
            candidates.append((
                'market_event',
                'Portfolio affected by a recent market alert (last 7 days)',
                'Share market context and reassurance',
                float(sev_num * days_contact), 5,
            ))

        # ── onboarding ────────────────────────────────────────────────────────
        if months <= 6:
            candidates.append((
                'onboarding',
                f'New client — month {months} of onboarding (first 6 months)',
                'Onboarding check-in call',
                float(max(6 - months, 1) * 10), 10,
            ))

        # ── pension ───────────────────────────────────────────────────────────
        if pfit >= 70:
            candidates.append((
                'pension',
                f'Pension fit score {pfit}/100 — strong candidate for Vorsorge ohne KeSt',
                'Book pension product introduction',
                float(pfit), 15,
            ))

        # ── milestone ─────────────────────────────────────────────────────────
        if months > 0 and months % 12 == 0:
            yrs = months // 12
            candidates.append((
                'milestone',
                f'{yrs}-year anniversary with froots',
                'Send personalised milestone message',
                (pval / 10_000) * (days_contact / 30), 5,
            ))
        elif pval > 20_000 and days_contact > 60:
            candidates.append((
                'milestone',
                f'High-value client (€{pval:,.0f}), no contact in {days_contact} days',
                'Relationship check-in',
                (pval / 10_000) * (days_contact / 30), 5,
            ))

        # ── Write each qualifying stream ───────────────────────────────────────
        for (stream, reason, suggested_action, urgency_score, estimated_minutes) in candidates:
            state, row_id = _stream_state(cid, stream)

            if state == 'active_snooze':
                continue
            elif state == 'resolved_today':
                continue
            elif state == 'expired_snooze':
                revive_rows.append({
                    'id': row_id, 'stream': stream, 'reason': reason,
                    'suggested_action': suggested_action,
                    'urgency_score': urgency_score,
                    'estimated_minutes': estimated_minutes,
                })
            else:
                new_rows.append({
                    'client_id': cid, 'stream': stream, 'reason': reason,
                    'suggested_action': suggested_action,
                    'urgency_score': urgency_score,
                    'estimated_minutes': estimated_minutes,
                })

    # ── Write to DB ────────────────────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM action_queue WHERE status = 'open'"))

        for upd in revive_rows:
            conn.execute(text("""
                UPDATE action_queue
                SET status='open', stream=:stream, reason=:reason,
                    suggested_action=:suggested_action,
                    urgency_score=:urgency_score,
                    estimated_minutes=:estimated_minutes,
                    snooze_until=NULL, created_at=NOW()
                WHERE id=:id
            """), upd)

        for row in new_rows:
            conn.execute(text("""
                INSERT INTO action_queue
                    (client_id, stream, reason, suggested_action,
                     urgency_score, estimated_minutes, status, created_at)
                VALUES
                    (:client_id, :stream, :reason, :suggested_action,
                     :urgency_score, :estimated_minutes, 'open', NOW())
            """), row)


def add_clients_to_queue_direct(engine, client_ids: list, stream: str,
                                 reason: str, suggested_action: str,
                                 estimated_minutes: int = 5) -> int:
    """
    Directly inserts clients into action_queue as open items.
    Skips clients who already have an open row in the SAME stream.
    Allows insert into a different stream — a CE agent manually selecting
    a client for the pension or milestone stream is an intentional decision
    that should not be silently dropped because the client is also in at_risk.
    Returns count of rows actually inserted.
    """
    if not client_ids:
        return 0
    existing_open = pd.read_sql(
        text("SELECT client_id FROM action_queue WHERE status='open' AND stream=:stream"),
        engine, params={'stream': stream}
    )
    already_open = set(existing_open['client_id'].tolist())
    to_insert = [cid for cid in client_ids if cid not in already_open]
    if not to_insert:
        return 0
    with engine.begin() as conn:
        for cid in to_insert:
            conn.execute(text("""
                INSERT INTO action_queue
                    (client_id, stream, reason, suggested_action,
                     estimated_minutes, status, created_at)
                VALUES (:cid, :stream, :reason, :suggested_action, :mins, 'open', NOW())
            """), {
                'cid': cid, 'stream': stream, 'reason': reason,
                'suggested_action': suggested_action, 'mins': estimated_minutes,
            })
    return len(to_insert)


@st.cache_data(ttl=60)
def load_action_queue() -> pd.DataFrame:
    """Open queue items joined to client names, sorted by stream then urgency desc."""
    engine = get_engine()
    df = pd.read_sql("""
        SELECT aq.id, aq.client_id, c.name AS client_name,
               aq.stream, aq.reason, aq.suggested_action,
               aq.urgency_score, aq.estimated_minutes,
               aq.status, aq.created_at
        FROM action_queue aq
        JOIN clients c ON c.client_id = aq.client_id
        WHERE aq.status = 'open'
        ORDER BY aq.stream, aq.urgency_score DESC
    """, engine)
    return df


@st.cache_data(ttl=300)
def load_pension_config():
    """Single pension product config row, or None if table is empty."""
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM pension_product_config LIMIT 1", engine)
    return df.iloc[0] if not df.empty else None


# ── Sidebar renderer ──────────────────────────────────────────────────────────

def render_sidebar():
    """
    Renders the persistent froots sidebar on every page.
    Includes: GA4 tracking, branding, KPI metrics, global search, and active client indicator.
    Call this at the top of every page.
    """
    import streamlit.components.v1 as components

    GA_ID = 'G-3NB5QZVMMX'
    components.html(f"""
<script>
(function() {{
    var GA_ID = '{GA_ID}';
    var p = window.parent;

    // Inject gtag library into parent document head once
    if (!p.document.querySelector('script[src*="' + GA_ID + '"]')) {{
        var s = p.document.createElement('script');
        s.async = true;
        s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
        p.document.head.appendChild(s);
    }}

    // Set up dataLayer and gtag in parent window
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

    clients = load_clients()

    total_aum     = clients['portfolio_value_eur'].sum()
    annual_fee    = total_aum * 0.01
    total_clients = len(clients)
    st.logo("assets/froots_logo.png", size="large")
    with st.sidebar:

        # ── Global Search ──────────────────────────────────────────────────
        st.markdown('**🔍 Global Search**')
        query = st.text_input(
            'Search clients or ETF tickers',
            key='sidebar_search',
            placeholder='Name or ticker…',
            label_visibility='collapsed'
        )

        if query and query.strip():
            q = query.strip()

            # Client name match
            name_matches = clients[
                clients['name'].str.contains(q, case=False, na=False)
            ]

            # ETF ticker match (exact or partial)
            etf_tickers = ['VWCE.DE', 'EIMI.L', 'AGGG.L', 'IUSV.DE', 'WSML.L']
            is_etf = any(q.upper() in t.upper() for t in etf_tickers)

            if not name_matches.empty:
                if len(name_matches) == 1:
                    match = name_matches.iloc[0]
                    st.success(f'Found: {match["name"]}')
                    if st.button('Go to Profile', key='sidebar_go'):
                        st.session_state['selected_client_id'] = int(match['client_id'])
                        st.switch_page('pages/2_client_portfolio.py')
                else:
                    st.info(f'{len(name_matches)} clients match "{q}"')
                    sel = st.selectbox(
                        'Select client',
                        name_matches['name'].tolist(),
                        key='sidebar_select'
                    )
                    if st.button('Go to Profile', key='sidebar_go_multi'):
                        cid = int(
                            name_matches[name_matches['name'] == sel]['client_id'].iloc[0]
                        )
                        st.session_state['selected_client_id'] = cid
                        st.switch_page('pages/2_client_portfolio.py')
            elif is_etf:
                matched_ticker = next(
                    (t for t in etf_tickers if q.upper() in t.upper()), q.upper()
                )
                st.info(f'ETF search: {matched_ticker}')
                if st.button('View in Quant Feed', key='sidebar_etf'):
                    st.session_state['search_etf'] = matched_ticker
                    st.switch_page('pages/5_quant_feed.py')
            else:
                st.info(f'Keyword search: "{q}"')
                if st.button('Search Quant Feed', key='sidebar_kw'):
                    st.session_state['search_keyword'] = q
                    st.switch_page('pages/5_quant_feed.py')

        st.divider()

        st.metric('Total Clients', total_clients)
        st.metric('Total AUM', f'€{total_aum:,.0f}')
        st.metric('Annual Fee Revenue', f'€{annual_fee:,.0f}')

        st.divider()

        # ── Active client indicator ────────────────────────────────────────
        if 'selected_client_id' in st.session_state:
            cid = st.session_state['selected_client_id']
            match = clients[clients['client_id'] == cid]
            if not match.empty:
                client_name = match.iloc[0]['name']
                st.markdown(f'**Viewing:** {client_name}')
                if st.button('↩ Back to Profile', key='sidebar_back'):
                    st.switch_page('pages/2_client_portfolio.py')
