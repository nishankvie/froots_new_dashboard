import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import utils
from sqlalchemy import text

st.set_page_config(
    page_title='Client Portfolio — froots',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
utils.render_sidebar()

# ── Client selector ───────────────────────────────────────────────────────────
_all_clients  = utils.load_clients()
_sorted_names = sorted(_all_clients['name'].tolist())
_options      = ['— select a client —'] + _sorted_names

_current_cid  = st.session_state.get('selected_client_id')
_default_name = None
if _current_cid is not None:
    _m = _all_clients[_all_clients['client_id'] == _current_cid]
    if not _m.empty:
        _default_name = _m.iloc[0]['name']
_default_idx = _options.index(_default_name) if _default_name in _options else 0

_selected_name = st.selectbox(
    'Client',
    _options,
    index=_default_idx,
    key='profile_client_picker',
    help='Type to search by name',
    label_visibility='collapsed',
)

if _selected_name == '— select a client —':
    st.markdown('## Client Profile')
    st.divider()
    st.info('Select a client from the dropdown above to view their profile.')
    st.stop()

cid = int(_all_clients[_all_clients['name'] == _selected_name].iloc[0]['client_id'])
st.session_state['selected_client_id'] = cid

# ── Load remaining data ────────────────────────────────────────────────────────
clients      = utils.load_clients()
portfolios   = utils.load_portfolios()
events       = utils.load_quant_events()
notes_all    = utils.load_notes()
contacts_all = utils.load_contacts()
engine       = utils.get_engine()

client = clients[clients['client_id'] == cid]
if client.empty:
    st.error('Client not found.')
    st.stop()

client = client.iloc[0]
today  = pd.Timestamp(date.today())

health_score     = utils.compute_health_score(client)
churn_risk       = utils.compute_churn_risk(client)
days_since_login = (today - client['last_login_date']).days
annual_fee       = client['portfolio_value_eur'] * 0.01

health_badge = {
    'green':  '🟢 Healthy',
    'orange': '🟡 Moderate',
    'red':    '🔴 At Risk',
}[utils.health_color(health_score)]

churn_badge = {
    'red':    '🔴 High Risk',
    'orange': '🟡 Medium Risk',
    'green':  '🟢 Low Risk',
}[utils.churn_color(churn_risk)]

client_portfolio = portfolios[portfolios['client_id'] == cid]
client_etfs      = client_portfolio['etf'].tolist() if not client_portfolio.empty else []

client_contacts = contacts_all[contacts_all['client_id'] == cid].sort_values('contact_date', ascending=False)
client_notes    = notes_all[notes_all['client_id'] == cid].sort_values('date', ascending=False)

days_since_contact = (
    (today - client_contacts.iloc[0]['contact_date']).days
    if not client_contacts.empty else 999
)

# ── "Why in queue" panel ──────────────────────────────────────────────────────
try:
    queue_items = pd.read_sql(
        "SELECT stream, reason, suggested_action FROM action_queue "
        "WHERE client_id=%(cid)s AND status='open'",
        engine, params={'cid': cid}
    )
    if not queue_items.empty:
        stream_labels = {
            'at_risk':      'At-Risk Outreach',
            'market_event': 'Market Event Response',
            'onboarding':   'New Client Onboarding',
            'pension':      'Pension Conversions',
            'milestone':    'Milestone & Relationship',
        }
        for _, item in queue_items.iterrows():
            st.info(
                f"**In queue — {stream_labels.get(item['stream'], item['stream'])}**\n\n"
                f"Reason: {item['reason']}\n\n"
                f"Suggested action: {item['suggested_action']}"
            )
except Exception:
    pass  # action_queue may not exist yet

# ── Page title ────────────────────────────────────────────────────────────────
st.title(f'Client Profile — {client["name"]}')
st.divider()

# ── Build activity timeline data ──────────────────────────────────────────────
timeline = []

for _, r in client_contacts.iterrows():
    timeline.append({
        'date':   r['contact_date'],
        'icon':   {'Phone Call': '📞', 'Email': '📧', 'Meeting': '🗓️', 'Chat': '💬'}.get(r['contact_type'], '📬'),
        'label':  r['contact_type'],
        'detail': str(r.get('description', ''))[:80],
    })

for _, r in client_notes.iterrows():
    timeline.append({
        'date':   r['date'],
        'icon':   '📝',
        'label':  'Note',
        'detail': str(r['note_text'])[:80],
    })

cutoff_30 = today - pd.Timedelta(days=30)
etf_alerts = events[
    events['etf_ticker'].isin(client_etfs) & (events['timestamp'] >= cutoff_30)
] if client_etfs else pd.DataFrame()
for _, r in etf_alerts.iterrows():
    timeline.append({
        'date':   r['timestamp'],
        'icon':   '⚡',
        'label':  f"Alert: {r['etf_ticker']}",
        'detail': str(r['reason'])[:80],
    })

try:
    queue_hist = pd.read_sql(
        "SELECT status, stream, created_at, resolved_at FROM action_queue "
        "WHERE client_id=%(cid)s AND status != 'open'",
        engine, params={'cid': cid}
    )
    for _, r in queue_hist.iterrows():
        status_icon = {'done': '✅', 'skipped': '⏭️', 'snoozed': '💤'}.get(r['status'], '•')
        timeline.append({
            'date':   r['resolved_at'] if r['resolved_at'] is not None else r['created_at'],
            'icon':   status_icon,
            'label':  f"Queue: {r['status']}",
            'detail': str(r['stream']),
        })
except Exception:
    pass

timeline_sorted = sorted(timeline, key=lambda x: pd.Timestamp(x['date']), reverse=True)
timeline_recent  = timeline_sorted[:20]
timeline_archive = timeline_sorted[20:]

# ── Main layout: content (left) + activity timeline (right) ──────────────────
col_main, _, col_timeline = st.columns([3, 0.15, 1.85])

with col_timeline:
    st.markdown('**Activity**')
    if not timeline_recent:
        st.caption('No activity recorded yet.')
    for ev in timeline_recent:
        date_str = pd.Timestamp(ev['date']).strftime('%d %b')
        with st.container(border=True):
            st.caption(f"{ev['icon']} {date_str} · **{ev['label']}**")
            if ev['detail']:
                st.caption(ev['detail'])
    if timeline_archive:
        with st.expander(f'Show {len(timeline_archive)} older entries'):
            for ev in timeline_archive:
                date_str = pd.Timestamp(ev['date']).strftime('%d %b %Y')
                st.caption(f"{ev['icon']} {date_str} · **{ev['label']}** — {ev['detail']}")

with col_main:

    # ── Section 1: Client Profile Header ─────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown(f'### {client["name"]}')
        st.markdown(f'**Age:** {int(client["age"])}')
        st.markdown(f'**Risk Profile:** {client["risk_profile"].capitalize()}')
        st.markdown(f'**Investment Goal:** {client["investment_goal"]}')
        st.markdown(f'**Member for:** {int(client["months_since_joining"])} months')

    with col_right:
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric('Portfolio Value', f'€{client["portfolio_value_eur"]:,.0f}')
        with m2:
            st.metric('Monthly Deposit', f'€{client["monthly_deposit"]:,.0f}')
        with m3:
            perf = client['portfolio_performance_pct']
            st.metric('YTD Performance', f'{perf:+.1f}%', delta=f'{perf:+.1f}%')

        b1, b2, b3 = st.columns(3)
        with b1:
            st.markdown(f'**Health:** {health_badge}')
        with b2:
            st.markdown(f'**Churn Risk:** {churn_badge}')
        with b3:
            pension_score = utils.compute_pension_fit_score(client)
            age_pts       = 30 if 25 <= int(client['age']) <= 50 else 0
            deposit_pts   = 25 if client['missed_deposits_last_3_months'] == 0 else 0
            portfolio_pts = 20 if client['portfolio_value_eur'] > 10_000 else 0
            profile_pts   = 15 if client['risk_profile'].lower() in ('balanced', 'growth') else 0
            goal_pts      = 10 if any(w in str(client['investment_goal']).lower()
                                       for w in ('pension', 'retirement', 'long-term', 'long term')) else 0
            fit_label = '✅ Strong' if pension_score >= 70 else ('⚠️ Moderate' if pension_score >= 40 else '—')
            st.metric('Pension Fit', f'{pension_score}/100')
            st.caption(fit_label)

    with st.expander('📐 Pension fit score breakdown', expanded=False):
        pb1, pb2, pb3, pb4, pb5 = st.columns(5)
        pb1.metric('Age 25–50', f'{age_pts}/30', delta='✓' if age_pts else '—', delta_color='normal' if age_pts else 'off')
        pb1.caption(f'Age: {int(client["age"])}')
        pb2.metric('No missed deposits', f'{deposit_pts}/25', delta='✓' if deposit_pts else '—', delta_color='normal' if deposit_pts else 'off')
        pb2.caption(f'Missed last 3 mo: {int(client["missed_deposits_last_3_months"])}')
        pb3.metric('Portfolio > €10 k', f'{portfolio_pts}/20', delta='✓' if portfolio_pts else '—', delta_color='normal' if portfolio_pts else 'off')
        pb3.caption(f'Portfolio: €{client["portfolio_value_eur"]:,.0f}')
        pb4.metric('Balanced/Growth', f'{profile_pts}/15', delta='✓' if profile_pts else '—', delta_color='normal' if profile_pts else 'off')
        pb4.caption(f'Profile: {client["risk_profile"].capitalize()}')
        pb5.metric('Pension/retirement goal', f'{goal_pts}/10', delta='✓' if goal_pts else '—', delta_color='normal' if goal_pts else 'off')
        pb5.caption(f'Goal: {client["investment_goal"][:30]}')

    st.info(f'💶 Annual fee contribution to froots: **€{annual_fee:,.0f}**')

    if churn_risk == 'High':
        st.error('📞 **Suggested Action:** Recommend immediate phone call — high churn risk detected.')
    elif health_score < 40:
        st.warning('📧 **Suggested Action:** Send reassurance email — health score is below threshold.')
    elif days_since_contact >= 60:
        st.warning(f'📅 **Suggested Action:** Schedule monthly check-in — last contacted {days_since_contact} days ago.')
    else:
        st.success('✅ **Suggested Action:** No action needed — client is engaged and on track.')

    st.divider()

    # ── Section 2: Portfolio Allocation Charts ────────────────────────────────
    st.subheader('Portfolio Allocation')

    if client_portfolio.empty:
        st.warning('No portfolio data found for this client.')
    else:
        col_pie, col_bar = st.columns(2)

        with col_pie:
            fig_pie = px.pie(
                client_portfolio,
                names='etf',
                values='weight_pct',
                title='Current Allocation',
                hole=0.4
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_bar:
            melted = pd.melt(
                client_portfolio,
                id_vars=['etf'],
                value_vars=['target_pct', 'weight_pct'],
                var_name='type',
                value_name='value'
            )
            melted['type'] = melted['type'].map({'target_pct': 'Target', 'weight_pct': 'Current'})
            fig_bar = px.bar(
                melted, x='etf', y='value', color='type', barmode='group',
                title='Target vs Current',
                labels={'value': 'Allocation (%)', 'etf': 'ETF'}
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # ── Section 3: Health Score and Churn Risk ────────────────────────────────
    st.subheader('Health Score & Churn Risk')

    login_score     = min(client['login_count_this_week'], 5) / 5 * 25
    deposit_score   = 25.0 if client['monthly_deposit'] > 0 else 0.0
    portfolio_score = min(client['portfolio_value_eur'] / 50_000, 1.0) * 25
    recency_score   = 25.0 if days_since_login <= 30 else 0.0

    col_gauge, col_churn = st.columns(2)

    with col_gauge:
        hcolor = utils.health_color(health_score)
        fig_gauge = go.Figure(go.Indicator(
            mode='gauge+number',
            value=health_score,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f'Health Score — {health_badge}'},
            gauge={
                'axis': {'range': [0, 100]},
                'bar': {'color': hcolor},
                'steps': [
                    {'range': [0, 40],   'color': '#ffe0e0'},
                    {'range': [40, 70],  'color': '#fff3cd'},
                    {'range': [70, 100], 'color': '#d4edda'},
                ],
                'threshold': {
                    'line': {'color': 'black', 'width': 3},
                    'thickness': 0.8,
                    'value': health_score
                }
            }
        ))
        fig_gauge.update_layout(height=280, margin=dict(t=40, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

        st.caption('**Score formula — 25 pts each:**')
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric('Login Activity', f'{int(login_score)}/25')
            st.caption(f'Logins this week: {int(client["login_count_this_week"])} (max 5 = full 25 pts)')
        with s2:
            st.metric('Deposit Active', f'{int(deposit_score)}/25')
            st.caption('Monthly deposit > €0 → 25 pts, else 0 pts')
        with s3:
            st.metric('Portfolio Size', f'{int(portfolio_score)}/25')
            st.caption('€0 = 0 pts · €25 k = 12 pts · €50 k+ = 25 pts (linear)')
        with s4:
            st.metric('Recent Login', f'{int(recency_score)}/25')
            st.caption(f'Last login {days_since_login}d ago — within 30 days → 25 pts, else 0 pts')

    with col_churn:
        ccolor = utils.churn_color(churn_risk)
        badge_style = {
            'red':    ('#f8d7da', '#721c24'),
            'orange': ('#fff3cd', '#856404'),
            'green':  ('#d4edda', '#155724'),
        }[ccolor]

        st.markdown(
            f'<div style="background:{badge_style[0]};color:{badge_style[1]};'
            f'padding:20px;border-radius:8px;text-align:center;font-size:1.4rem;font-weight:bold;">'
            f'Churn Risk: {churn_risk}</div>',
            unsafe_allow_html=True
        )
        st.markdown('')
        st.markdown('**Risk Signals:**')

        sig1 = client['missed_deposits_last_3_months'] >= 2
        sig2 = client['login_count_this_week'] <= 1
        sig3 = client['portfolio_performance_pct'] < -3.0

        st.markdown(
            f'{"❌" if sig1 else "✅"} Missed deposits: '
            f'{int(client["missed_deposits_last_3_months"])} in last 3 months '
            f'(threshold: ≥ 2)'
        )
        st.markdown(
            f'{"❌" if sig2 else "✅"} Login activity: '
            f'{int(client["login_count_this_week"])} logins this week '
            f'(threshold: ≤ 1)'
        )
        st.markdown(
            f'{"❌" if sig3 else "✅"} Performance: '
            f'{client["portfolio_performance_pct"]:+.1f}% YTD '
            f'(threshold: < -3%)'
        )

    st.divider()

    # ── Section 4: Panic Detection ────────────────────────────────────────────
    st.subheader('Panic Detection')

    high_login_flag    = client['login_count_this_week'] >= 5
    negative_perf_flag = client['portfolio_performance_pct'] < -5.0

    if high_login_flag and negative_perf_flag:
        st.error(
            f'🔴 **Critical — Potential Panic Behaviour Detected**\n\n'
            f'- Login count this week: **{int(client["login_count_this_week"])}** (threshold: ≥ 5)\n'
            f'- YTD performance: **{client["portfolio_performance_pct"]:+.1f}%** (threshold: < -5%)\n\n'
            'Recommend: proactive outreach from support team immediately.'
        )
    elif high_login_flag:
        st.warning(
            f'🟡 **Warning — High Login Activity**\n\n'
            f'- Login count this week: **{int(client["login_count_this_week"])}** (threshold: ≥ 5)\n'
            f'- Performance is within normal range ({client["portfolio_performance_pct"]:+.1f}%).\n\n'
            'Monitor: client may have questions about recent market movements.'
        )
    elif negative_perf_flag:
        st.warning(
            f'🟡 **Warning — Negative Performance Signal**\n\n'
            f'- YTD performance: **{client["portfolio_performance_pct"]:+.1f}%** (threshold: < -5%)\n'
            f'- Login frequency is normal ({int(client["login_count_this_week"])} this week).\n\n'
            'Monitor: no immediate panic signs but performance may prompt client contact.'
        )
    else:
        st.success(
            f'🟢 **All Clear — No Panic Signals**  '
            f'Logins this week: {int(client["login_count_this_week"])} | '
            f'YTD: {client["portfolio_performance_pct"]:+.1f}%'
        )

    st.divider()

    # ── Section 5: Portfolio Drift & Advisor Notes ────────────────────────────
    st.subheader('Portfolio Drift & Advisor Notes')

    with st.expander('📊 Portfolio Drift Details', expanded=True):
        if client_portfolio.empty:
            st.info('No portfolio data available.')
        else:
            for _, row in client_portfolio.iterrows():
                drift = round(row['weight_pct'] - row['target_pct'], 1)
                if drift > 1.0:
                    st.markdown(
                        f'🔺 **{row["etf"]}** is **{drift}% above target** '
                        f'({row["weight_pct"]}% current vs {row["target_pct"]}% target) '
                        f'— may be rebalanced down soon.'
                    )
                elif drift < -1.0:
                    st.markdown(
                        f'🔻 **{row["etf"]}** is **{abs(drift)}% below target** '
                        f'({row["weight_pct"]}% current vs {row["target_pct"]}% target) '
                        f'— may receive additional allocation.'
                    )
                else:
                    st.markdown(f'✅ **{row["etf"]}** is on target ({row["target_pct"]}%).')

    st.markdown('**Advisor Notes**')

    if not client_notes.empty:
        display_notes = client_notes[['date', 'note_text', 'added_by']].copy()
        display_notes['date'] = display_notes['date'].dt.strftime('%d %b %Y')
        display_notes.columns = ['Date', 'Note', 'Added By']
        st.dataframe(display_notes, use_container_width=True, hide_index=True)
    else:
        st.caption('No notes yet.')

    with st.form('add_note_form', clear_on_submit=True):
        st.markdown('**Add New Note**')
        note_author = st.text_input('Your name', placeholder='e.g. Lisa Wagner')
        note_text   = st.text_area('Note', placeholder='Type advisor note here…')
        submitted   = st.form_submit_button('Save Note')

        if submitted:
            if not note_text.strip():
                st.warning('Note text cannot be empty.')
            else:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                        INSERT INTO client_notes (client_id, date, note_text, added_by)
                        VALUES (:cid, NOW(), :note, :author)
                        """),
                        {
                            'cid':    cid,
                            'note':   note_text.strip(),
                            'author': note_author.strip() if note_author.strip() else 'Unknown',
                        }
                    )
                    conn.commit()
                utils.load_notes.clear()
                st.success('Note saved.')
                st.rerun()

    st.divider()

    # ── Section 6: Recent ETF Alerts ─────────────────────────────────────────
    st.subheader('Recent ETF Alerts')

    if client_portfolio.empty:
        st.info('No portfolio data to match alerts against.')
    else:
        cutoff_7 = pd.Timestamp(today) - pd.Timedelta(days=7)
        recent_events = events[
            events['etf_ticker'].isin(client_etfs) & (events['timestamp'] >= cutoff_7)
        ].sort_values('timestamp', ascending=False)

        if recent_events.empty:
            st.success('✅ No recent ETF alerts for this client\'s holdings in the past 7 days.')
        else:
            for _, ev in recent_events.iterrows():
                ts_str  = ev['timestamp'].strftime('%d %b %Y %H:%M')
                content = (
                    f'**{ev["event_type"]}** · {ts_str} · ETF: `{ev["etf_ticker"]}`\n\n'
                    f'{ev["reason"]}'
                )
                if ev['severity'] == 'critical':
                    st.error(content)
                elif ev['severity'] == 'warning':
                    st.warning(content)
                else:
                    st.info(content)

    st.divider()

    # ── Section 7: Best Time to Reach Out ────────────────────────────────────
    st.subheader('Best Time to Reach Out')

    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    login_day  = client['last_login_date'].weekday()
    day_type   = 'weekday' if login_day < 5 else 'weekend'
    day_name   = weekday_names[login_day]

    if not client_contacts.empty:
        last_contact_str = f'Last contacted **{days_since_contact} days ago** ({client_contacts.iloc[0]["contact_type"]}).'
    else:
        last_contact_str = 'No contact history found.'

    urgent = days_since_contact > 60 and churn_risk == 'High'

    if churn_risk == 'High' or days_since_contact > 30:
        recommendation = '📞 **Recommended:** Schedule a call this week — elevated risk or extended time since last contact.'
    else:
        recommendation = '📧 **Recommended:** Send monthly portfolio update — client is engaged and up to date.'

    message = (
        f'🗓️ Client typically active on **{day_type}s** (last seen on a {day_name}).  \n'
        f'{last_contact_str}  \n'
        f'{recommendation}'
    )

    if urgent:
        st.error(message)
    else:
        st.info(message)

    st.divider()

    # ── Section 8: Communication History ─────────────────────────────────────
    st.subheader('Communication History')

    if not client_contacts.empty:
        disp_contacts = client_contacts[[
            'contact_date', 'contact_type', 'agent_name', 'description', 'outcome'
        ]].copy()
        disp_contacts['contact_date'] = disp_contacts['contact_date'].dt.strftime('%d %b %Y')
        disp_contacts.columns = ['Date', 'Type', 'Agent', 'Description', 'Outcome']
        st.dataframe(disp_contacts, use_container_width=True, hide_index=True)
    else:
        st.caption('No contact history yet.')

    with st.form('add_contact_form', clear_on_submit=True):
        st.markdown('**Log New Contact**')

        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            contact_date = st.date_input('Date', value=date.today())
        with fc2:
            contact_type = st.selectbox('Type', ['Phone Call', 'Email', 'Meeting', 'Chat'])
        with fc3:
            agent_name = st.text_input('Agent name', placeholder='Your name')

        description = st.text_area('Description', placeholder='Brief summary of the conversation…')
        outcome     = st.text_input('Outcome', placeholder='e.g. Resolved — no changes')
        submitted   = st.form_submit_button('Log Contact')

        if submitted:
            if not description.strip():
                st.warning('Description cannot be empty.')
            else:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                        INSERT INTO client_contacts
                        (client_id, contact_date, contact_type, agent_name, description, outcome)
                        VALUES (:cid, :dt, :ctype, :agent, :desc, :outcome)
                        """),
                        {
                            'cid':     cid,
                            'dt':      contact_date,
                            'ctype':   contact_type,
                            'agent':   agent_name.strip() if agent_name.strip() else 'Unknown',
                            'desc':    description.strip(),
                            'outcome': outcome.strip(),
                        }
                    )
                    conn.commit()
                utils.load_contacts.clear()
                st.success('Contact logged.')
                st.rerun()
