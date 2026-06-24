import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st
from datetime import datetime, date
import utils
from sqlalchemy import text

st.set_page_config(
    page_title='Quant & Support Feed — froots',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

utils.render_sidebar()

st.title('Quant & Support Feed')
st.caption(f'Last updated: {datetime.now().strftime("%d %b %Y, %H:%M")}')
st.divider()

# ── Data ──────────────────────────────────────────────────────────────────────

events     = utils.load_quant_events()
portfolios = utils.load_portfolios()
clients    = utils.load_clients()
engine     = utils.get_engine()

# Pre-populate search from sidebar global search
default_keyword = st.session_state.pop('search_keyword', '')
default_etf     = st.session_state.pop('search_etf', '')

# ── Draft message templates ───────────────────────────────────────────────────

DRAFT_TEMPLATES = {
    'Risk Alert': (
        "Subject: Update on recent market activity\n\n"
        "Dear [Client Name],\n\n"
        "We wanted to proactively reach out regarding recent market movements "
        "that may affect your portfolio.\n\n"
        "[Paste alert reason here]\n\n"
        "Your investment strategy remains on track for the long term. "
        "Please don't hesitate to contact us with any questions.\n\n"
        "The froots team"
    ),
    'Rebalance Alert': (
        "Subject: Your portfolio has been reviewed\n\n"
        "Dear [Client Name],\n\n"
        "As part of our ongoing portfolio monitoring, we've identified an "
        "opportunity to rebalance your holdings.\n\n"
        "[Paste alert reason here]\n\n"
        "No action is required from you — we'll handle this automatically "
        "to keep your portfolio aligned with your goals.\n\n"
        "The froots team"
    ),
    'Information Update': (
        "Subject: Important update for your froots account\n\n"
        "Dear [Client Name],\n\n"
        "We have an important update we'd like to share with you.\n\n"
        "[Paste alert reason here]\n\n"
        "Please reach out if you have any questions.\n\n"
        "The froots team"
    ),
    '_default': (
        "Subject: Update from froots\n\n"
        "Dear [Client Name],\n\n"
        "[Paste alert reason here]\n\n"
        "The froots team"
    ),
}

# ── Section 1: Filters ────────────────────────────────────────────────────────

st.subheader('Filters')

all_types      = sorted(events['event_type'].unique().tolist())
all_severities = ['All', 'info', 'warning', 'critical']

fcol1, fcol2, fcol3, fcol4 = st.columns(4)
with fcol1:
    selected_types = st.multiselect('Event type', options=all_types, default=all_types)
with fcol2:
    selected_severity = st.selectbox('Severity', all_severities)
with fcol3:
    keyword = st.text_input(
        'Keyword search',
        value=default_keyword or default_etf,
        placeholder='e.g. VWCE, rebalance…'
    )
with fcol4:
    hide_communicated = st.checkbox('Hide communicated', value=True,
                                    help='Hide alerts already marked as communicated')

# Apply filters
filtered = events.copy()
if selected_types:
    filtered = filtered[filtered['event_type'].isin(selected_types)]
if selected_severity != 'All':
    filtered = filtered[filtered['severity'] == selected_severity]
if keyword.strip():
    kw = keyword.strip()
    filtered = filtered[
        filtered['reason'].str.contains(kw, case=False, na=False) |
        filtered['etf_ticker'].str.contains(kw, case=False, na=False) |
        filtered['event_type'].str.contains(kw, case=False, na=False)
    ]
if hide_communicated:
    filtered = filtered[~filtered['communicated']]

filtered = filtered.sort_values('timestamp', ascending=False).reset_index(drop=True)

st.divider()

# ── Section 2: Post New Alert ─────────────────────────────────────────────────

with st.expander('➕ Post New Alert', expanded=False):
    with st.form('new_alert_form', clear_on_submit=True):
        na1, na2 = st.columns(2)
        with na1:
            new_etf    = st.text_input('ETF ticker (optional)', placeholder='e.g. VWCE.DE')
            new_client = st.text_input('Client name (optional — for client-specific alert)')
            new_type   = st.selectbox(
                'Event type',
                ['Risk Alert', 'Rebalance Alert', 'Information Update', 'Team Task', 'Client Alert']
            )
        with na2:
            new_severity = st.selectbox('Severity', ['info', 'warning', 'critical'])
            new_reason   = st.text_area('Reason / description', height=120,
                                        placeholder='Plain English explanation…')

        submitted = st.form_submit_button('Post Alert', type='primary')

        if submitted:
            if not new_reason.strip():
                st.warning('Reason cannot be empty.')
            else:
                affected_count = 0
                etf_clean = new_etf.strip().upper()
                if etf_clean:
                    matches        = portfolios[portfolios['etf'].str.upper() == etf_clean]
                    affected_ids   = matches['client_id'].unique()
                    affected_count = len(affected_ids)

                with engine.connect() as conn:
                    conn.execute(
                        text("""
                        INSERT INTO quant_events
                        (timestamp, event_type, reason, affected_clients,
                         severity, etf_ticker, client_specific_name, communicated)
                        VALUES (NOW(), :etype, :reason, :affected,
                                :severity, :etf, :client, FALSE)
                        """),
                        {
                            'etype':    new_type,
                            'reason':   new_reason.strip(),
                            'affected': affected_count,
                            'severity': new_severity,
                            'etf':      new_etf.strip(),
                            'client':   new_client.strip(),
                        }
                    )
                    conn.commit()

                utils.load_quant_events.clear()
                st.success(
                    f'Alert posted.'
                    + (f' {affected_count} client(s) affected.' if affected_count else '')
                )
                st.rerun()

st.divider()

# ── Section 3: Event Timeline ─────────────────────────────────────────────────

st.subheader(f'Event Timeline — {len(filtered)} event(s)')

SEVERITY_ICONS = {'info': '🔵', 'warning': '🟡', 'critical': '🔴'}

if filtered.empty:
    st.info('No events match the current filters.')
else:
    for _, row in filtered.iterrows():
        severity  = row['severity']
        icon      = SEVERITY_ICONS.get(severity, '⚪')
        ts_str    = row['timestamp'].strftime('%d %b %Y  %H:%M')
        event_id  = int(row['event_id'])
        etf_clean = row['etf_ticker'].strip().upper() if row['etf_ticker'] else ''

        header_parts = [f'**{row["event_type"]}**', ts_str]
        if row['etf_ticker']:
            header_parts.append(f'ETF: `{row["etf_ticker"]}`')
        if row['client_specific_name']:
            header_parts.append(f'Client: {row["client_specific_name"]}')
        if row['communicated']:
            header_parts.append('✓ *communicated*')

        content = ' · '.join(header_parts) + f'\n\n{row["reason"]}'
        if row['affected_clients'] > 0:
            content += f'\n\n*Affected clients: {int(row["affected_clients"])}*'

        time_col, card_col = st.columns([1, 5])

        with time_col:
            st.markdown(f'{icon} `{ts_str}`')

        with card_col:
            if severity == 'critical':
                st.error(content)
            elif severity == 'warning':
                st.warning(content)
            else:
                st.info(content)

            # Action buttons row
            ab1, ab2, ab3 = st.columns(3)

            # Draft message
            with ab1:
                template = DRAFT_TEMPLATES.get(row['event_type'], DRAFT_TEMPLATES['_default'])
                with st.expander('📋 Draft message'):
                    st.code(template, language=None)

            # Mark as communicated
            with ab2:
                if not row['communicated']:
                    if st.button('✓ Mark communicated', key=f'comm_{event_id}'):
                        with engine.begin() as conn:
                            conn.execute(
                                text('UPDATE quant_events SET communicated=TRUE WHERE event_id=:id'),
                                {'id': event_id}
                            )
                        utils.load_quant_events.clear()
                        st.rerun()
                else:
                    st.caption('✓ Communicated')

            # Add affected clients to queue
            with ab3:
                if etf_clean and int(row['affected_clients']) > 0:
                    matches      = portfolios[portfolios['etf'].str.upper() == etf_clean]
                    affected_ids = matches['client_id'].tolist()
                    if st.button(
                        f'➕ Add {len(affected_ids)} to queue',
                        key=f'queue_{event_id}'
                    ):
                        n = utils.add_clients_to_queue_direct(
                            engine,
                            affected_ids,
                            'market_event',
                            f'Affected by alert: {row["reason"][:120]}',
                            'Share market context and reassurance',
                        )
                        utils.load_action_queue.clear()
                        skipped = len(affected_ids) - n
                        msg = f'Added {n} client(s) to queue.'
                        if skipped:
                            msg += f' {skipped} already in queue.'
                        st.success(msg)
                        st.rerun()

            # View affected clients expander
            if etf_clean:
                matches = portfolios[portfolios['etf'].str.upper() == etf_clean]
                if not matches.empty:
                    affected_names = clients[
                        clients['client_id'].isin(matches['client_id'].unique())
                    ][['name', 'risk_profile', 'portfolio_value_eur']].copy()
                    affected_names.columns = ['Client', 'Risk Profile', 'Portfolio (€)']
                    affected_names['Portfolio (€)'] = affected_names['Portfolio (€)'].map('{:,.0f}'.format)
                    with st.expander(f'View {len(affected_names)} affected client(s)'):
                        st.dataframe(affected_names, use_container_width=True, hide_index=True)

        st.divider()
