import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import text
import utils

st.set_page_config(
    page_title="Today's Work — froots",
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

utils.render_sidebar()

# ── Stream metadata ────────────────────────────────────────────────────────────

STREAMS = {
    'at_risk':      {'label': 'At-Risk Outreach',        'icon': '🔴'},
    'market_event': {'label': 'Market Event Response',   'icon': '📉'},
    'onboarding':   {'label': 'New Client Onboarding',   'icon': '🌱'},
    'pension':      {'label': 'Pension Conversions',     'icon': '🏦'},
    'milestone':    {'label': 'Milestone & Relationship','icon': '⭐'},
}

def _urgency_label(stream: str, urgency_score: float) -> str:
    if stream == 'at_risk':
        return 'High'
    if stream == 'market_event':
        return 'High' if urgency_score > 200 else 'Medium'
    if stream == 'onboarding':
        return 'High' if urgency_score >= 30 else ('Medium' if urgency_score >= 10 else 'Low')
    if stream == 'pension':
        return 'High' if urgency_score >= 90 else ('Medium' if urgency_score >= 80 else 'Low')
    # milestone
    return 'Medium' if urgency_score > 30 else 'Low'

URGENCY_ICON = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}

# ── Queue regeneration (once per browser session, then only on button click) ──

engine = utils.get_engine()

if 'last_regenerated_at' not in st.session_state:
    with st.spinner('Building your work queue…'):
        utils.generate_action_queue(engine)
        utils.load_action_queue.clear()
    st.session_state['last_regenerated_at'] = datetime.now()

# ── Top strip ──────────────────────────────────────────────────────────────────

contacts_df = utils.load_contacts()
contacts_df['contact_date'] = pd.to_datetime(contacts_df['contact_date'])
week_ago = pd.Timestamp(date.today()) - pd.Timedelta(days=7)
contacted_this_week = contacts_df[contacts_df['contact_date'] >= week_ago]['client_id'].nunique()

done_today_count = 0
try:
    done_today_df = pd.read_sql("""
        SELECT COUNT(*) AS cnt FROM action_queue
        WHERE status = 'done' AND resolved_at >= CURRENT_DATE
    """, engine)
    done_today_count = int(done_today_df['cnt'].iloc[0])
except Exception:
    pass

hours_saved = done_today_count * 0.25

open_queue_count = 0
try:
    open_q_df = pd.read_sql(
        "SELECT COUNT(*) AS cnt FROM action_queue WHERE status = 'open'", engine
    )
    open_queue_count = int(open_q_df['cnt'].iloc[0])
except Exception:
    pass
last_regen  = st.session_state['last_regenerated_at']
mins_ago    = int((datetime.now() - last_regen).total_seconds() / 60)

# Header row
head_col, regen_col = st.columns([4, 1])
with head_col:
    st.title("Today's Work")
with regen_col:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button('🔄 Refresh Queue', use_container_width=True):
        with st.spinner('Refreshing…'):
            utils.generate_action_queue(engine)
            utils.load_action_queue.clear()
        st.session_state['last_regenerated_at'] = datetime.now()
        st.rerun()
    st.caption(f'Last refreshed: {mins_ago}m ago')

# KPI strip
k1, k2, k3 = st.columns(3)
k1.metric('Clients contacted this week', contacted_this_week)
k2.metric('Est. time saved today', f'{hours_saved:.1f} h', help='Completed queue items × 15 min each')
k3.metric('Open queue items', open_queue_count, help='Total open items across all streams right now')

st.divider()

# ── Stream filter ──────────────────────────────────────────────────────────────

stream_options = ['All Streams'] + [v['label'] for v in STREAMS.values()]
selected_label = st.selectbox(
    'Show stream:',
    stream_options,
    label_visibility='collapsed',
    key='stream_filter'
)
selected_stream = None
if selected_label != 'All Streams':
    selected_stream = next(k for k, v in STREAMS.items() if v['label'] == selected_label)

st.markdown('')

# ── Load queue ─────────────────────────────────────────────────────────────────

queue_df = utils.load_action_queue()

# ── DB action helpers ──────────────────────────────────────────────────────────

def _mark_done(row_id: int):
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE action_queue SET status='done', resolved_at=NOW() WHERE id=:id"
        ), {'id': row_id})
    utils.load_action_queue.clear()

def _snooze(row_id: int):
    snooze_until = datetime.now() + timedelta(days=7)
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE action_queue SET status='snoozed', snooze_until=:su WHERE id=:id"
        ), {'id': row_id, 'su': snooze_until})
    utils.load_action_queue.clear()

def _skip(row_id: int):
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE action_queue SET status='skipped', resolved_at=NOW() WHERE id=:id"
        ), {'id': row_id})
    utils.load_action_queue.clear()

# ── Card renderer ──────────────────────────────────────────────────────────────

def render_card(row: pd.Series):
    row_id   = int(row['id'])
    ulabel   = _urgency_label(row['stream'], float(row['urgency_score']))
    uicon    = URGENCY_ICON[ulabel]
    est_mins = int(row['estimated_minutes'])

    with st.container(border=True):
        st.markdown(f"**{row['client_name']}**")
        st.caption(row['reason'])
        st.markdown(f"*{row['suggested_action']}*")
        st.markdown(f"{uicon} {ulabel} &nbsp;·&nbsp; ~{est_mins} min", unsafe_allow_html=True)

        b1, b2 = st.columns(2)
        with b1:
            if st.button('Open Profile', key=f'open_{row_id}', use_container_width=True):
                st.session_state['selected_client_id'] = int(row['client_id'])
                st.switch_page('pages/2_client_portfolio.py')
            if st.button('Mark Done ✓', key=f'done_{row_id}', use_container_width=True):
                _mark_done(row_id)
                st.rerun()
        with b2:
            if st.button('Snooze 7d 💤', key=f'snooze_{row_id}', use_container_width=True):
                _snooze(row_id)
                st.rerun()
            if st.button('Skip →', key=f'skip_{row_id}', use_container_width=True):
                _skip(row_id)
                st.rerun()

# ── Render streams ─────────────────────────────────────────────────────────────

stream_keys = [selected_stream] if selected_stream else list(STREAMS.keys())

if queue_df.empty:
    st.info('Queue is empty — all clients are accounted for. Click **Refresh Queue** to re-evaluate.')
else:
    if selected_stream:
        # Single stream: full-width column
        meta   = STREAMS[selected_stream]
        subset = queue_df[queue_df['stream'] == selected_stream]
        st.subheader(f"{meta['icon']} {meta['label']} ({len(subset)})")
        if subset.empty:
            st.caption('Nothing in this stream right now.')
        else:
            for _, row in subset.iterrows():
                render_card(row)
    else:
        # All streams: 5-column layout
        cols = st.columns(5)
        for col, stream_key in zip(cols, stream_keys):
            meta   = STREAMS[stream_key]
            subset = queue_df[queue_df['stream'] == stream_key]
            with col:
                st.markdown(f"**{meta['icon']} {meta['label']}**")
                st.caption(f"{len(subset)} item{'s' if len(subset) != 1 else ''}")
                st.markdown('---')
                if subset.empty:
                    st.caption('All clear')
                else:
                    for _, row in subset.iterrows():
                        render_card(row)
