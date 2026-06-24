import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import date
import utils

st.set_page_config(
    page_title='Client Hub — froots',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

utils.render_sidebar()

# ── Data prep ─────────────────────────────────────────────────────────────────

clients   = utils.load_clients()
contacts  = utils.load_contacts()
aum_hist  = utils.load_aum_history()
engine    = utils.get_engine()
today     = pd.Timestamp(date.today())

clients['health_score']      = clients.apply(utils.compute_health_score, axis=1)
clients['churn_risk']        = clients.apply(utils.compute_churn_risk, axis=1)
clients['pension_fit_score'] = clients.apply(utils.compute_pension_fit_score, axis=1)
clients['days_since_login']  = (today - clients['last_login_date']).dt.days

last_contact_days = utils.compute_last_contact_days(contacts)
clients['days_since_contact'] = clients['client_id'].map(last_contact_days).fillna(999).astype(int)

last_contact_date = contacts.groupby('client_id')['contact_date'].max()
clients['last_contact_date'] = clients['client_id'].map(last_contact_date)

def _suggested_action(row):
    if row['churn_risk'] == 'High':    return '📞 Call'
    if row['health_score'] < 40:       return '📧 Reassure'
    if row['days_since_contact'] > 60: return '📅 Check-in'
    return '✅ Engaged'

clients['next_action'] = clients.apply(_suggested_action, axis=1)

# ── Segment definitions ────────────────────────────────────────────────────────

hv_threshold = clients['portfolio_value_eur'].quantile(0.80)

SEGMENTS = {
    'All Clients':         {'mask': pd.Series([True] * len(clients), index=clients.index), 'stream': None},
    'At Risk':             {'mask': (clients['health_score'] < 40) | (clients['churn_risk'] == 'High'),   'stream': 'at_risk'},
    'High Value':          {'mask': clients['portfolio_value_eur'] >= hv_threshold,                        'stream': 'milestone'},
    'New This Month':      {'mask': clients['months_since_joining'] <= 1,                                  'stream': 'onboarding'},
    'Pension Candidates':  {'mask': clients['pension_fit_score'] >= 70,                                    'stream': 'pension'},
    'Dormant':             {'mask': clients['days_since_login'] > 60,                                      'stream': 'at_risk'},
    'Recently Contacted':  {'mask': clients['days_since_contact'] <= 7,                                    'stream': None},
}

st.title('Client Hub')

with st.expander('📐 Score formulas', expanded=False):
    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        st.markdown('**Health Score (0–100)**')
        st.markdown(
            '- Login activity this week · max 5 logins = **25 pts**\n'
            '- Monthly deposit > €0 → **25 pts**\n'
            '- Portfolio value up to €50 k → up to **25 pts** (linear)\n'
            '- Last login within 30 days → **25 pts**\n\n'
            '🟢 ≥70 Healthy · 🟡 40–69 Moderate · 🔴 <40 At Risk'
        )
    with scol2:
        st.markdown('**Churn Risk**')
        st.markdown(
            'Three binary signals — **all three** = High, **any one** = Medium, **none** = Low:\n\n'
            '- ≥2 missed deposits in last 3 months\n'
            '- ≤1 login this week\n'
            '- Portfolio performance < −3% YTD'
        )
    with scol3:
        st.markdown('**Pension Fit Score (0–100)**')
        st.markdown(
            '- Age 25–50 → **30 pts**\n'
            '- 0 missed deposits (3 mo) → **25 pts**\n'
            '- Portfolio > €10 k → **20 pts**\n'
            '- Balanced/Growth risk profile → **15 pts**\n'
            '- Pension/retirement/long-term goal → **10 pts**\n\n'
            '✅ Strong ≥70 · ⚠️ Moderate 40–69 · — Below 40'
        )

# ── Business Health (collapsed) ───────────────────────────────────────────────

with st.expander('📊 Business Health', expanded=False):
    total_clients  = len(clients)
    clients_at_risk = int(((clients['health_score'] < 40) | (clients['churn_risk'] == 'High')).sum())
    high_login     = int((clients['login_count_this_week'] >= 5).sum())
    inactive       = int((clients['days_since_login'] > 30).sum())
    total_aum      = clients['portfolio_value_eur'].sum()
    annual_fee_rev = total_aum * 0.01

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric('Total Clients',      total_clients)
    c2.metric('Clients At Risk',    clients_at_risk, help='Health < 40 or churn High')
    c3.metric('High Login Activity',high_login,      help='≥5 logins this week')
    c4.metric('Inactive (30+ days)',inactive,         help='Last login >30 days ago')
    c5.metric('Total AUM',          f'€{total_aum:,.0f}')
    c6.metric('Annual Fee Revenue', f'€{annual_fee_rev:,.0f}', help='AUM × 1%')

    st.markdown('')
    fig_aum = px.line(
        aum_hist, x='date', y='total_aum_eur',
        labels={'total_aum_eur': 'AUM (€)', 'date': 'Month'},
        markers=True, title='AUM — 24 Month Growth'
    )
    fig_aum.update_traces(line_color='#2ecc71', line_width=2.5)
    fig_aum.update_layout(yaxis_tickformat='€,.0f', hovermode='x unified', margin=dict(t=30, b=20))
    st.plotly_chart(fig_aum, use_container_width=True)

# ── Filters row ───────────────────────────────────────────────────────────────

f1, f2, f3 = st.columns(3)
with f1:
    profile_opts = sorted(clients['risk_profile'].dropna().unique().tolist())
    selected_profiles = st.multiselect('Risk profile', profile_opts, default=profile_opts)
with f2:
    pv_min = int(clients['portfolio_value_eur'].min())
    pv_max = int(clients['portfolio_value_eur'].max())
    pv_range = st.slider('Portfolio value (€)', pv_min, pv_max, (pv_min, pv_max), step=1000)
with f3:
    dep_min = int(clients['monthly_deposit'].min())
    dep_max = int(clients['monthly_deposit'].max())
    dep_range = st.slider('Monthly deposit (€)', dep_min, dep_max, (dep_min, dep_max), step=50)

# Apply cross-segment filters
filter_mask = (
    clients['risk_profile'].isin(selected_profiles) &
    clients['portfolio_value_eur'].between(pv_range[0], pv_range[1]) &
    clients['monthly_deposit'].between(dep_range[0], dep_range[1])
)

# ── Display table helper ──────────────────────────────────────────────────────

def _color_health(val):
    if val >= 70: return 'background-color:#d4edda;color:#155724'
    if val >= 40: return 'background-color:#fff3cd;color:#856404'
    return 'background-color:#f8d7da;color:#721c24'

def _color_churn(val):
    return {
        'High':   'background-color:#f8d7da;color:#721c24',
        'Medium': 'background-color:#fff3cd;color:#856404',
        'Low':    'background-color:#d4edda;color:#155724',
    }.get(val, '')

def render_segment_table(tab_key: str, segment_clients: pd.DataFrame, stream: str | None):
    """Renders the filtered table + bulk action buttons for one segment tab."""

    if segment_clients.empty:
        st.caption('No clients in this segment.')
        return

    # Build display frame
    disp = segment_clients[[
        'client_id', 'name', 'portfolio_value_eur', 'risk_profile',
        'health_score', 'churn_risk', 'days_since_contact',
        'days_since_login', 'next_action'
    ]].copy()

    disp['last_contact'] = disp['days_since_contact'].apply(
        lambda d: 'Never' if d >= 999 else (f'{d}d ago' if d > 0 else 'Today')
    )
    disp['last_login']   = disp['days_since_login'].apply(
        lambda d: f'{d}d ago' if d > 0 else 'Today'
    )
    disp['portfolio_value_eur'] = disp['portfolio_value_eur'].map('€{:,.0f}'.format)
    disp['risk_profile']        = disp['risk_profile'].str.capitalize()

    display_df = disp.rename(columns={
        'name':               'Name',
        'portfolio_value_eur':'Portfolio Value',
        'risk_profile':       'Risk Profile',
        'health_score':       'Health',
        'churn_risk':         'Churn Risk',
        'last_contact':       'Last Contact',
        'last_login':         'Last Login',
        'next_action':        'Next Action',
    })[[
        'Name', 'Portfolio Value', 'Risk Profile', 'Health',
        'Churn Risk', 'Last Contact', 'Last Login', 'Next Action'
    ]]

    styled = (
        display_df.style
        .map(_color_health, subset=['Health'])
        .map(_color_churn,  subset=['Churn Risk'])
    )

    event = st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        selection_mode='multi-row',
        on_select='rerun',
        key=f'table_{tab_key}',
    )

    selected_indices = event.selection.rows
    n_selected       = len(selected_indices)

    if n_selected == 0:
        return

    selected_clients = segment_clients.iloc[selected_indices]
    selected_ids     = selected_clients['client_id'].tolist()
    selected_names   = selected_clients['name'].tolist()

    btn_cols = st.columns(4)

    # Open Profile — only for single selection
    if n_selected == 1:
        with btn_cols[0]:
            if st.button('Open Profile →', key=f'open_{tab_key}', type='primary'):
                st.session_state['selected_client_id'] = int(selected_ids[0])
                st.switch_page('pages/2_client_portfolio.py')

    # Add to Queue — disabled for segments with no defined stream
    if stream is not None:
        queue_label = f'Add to Queue ({n_selected})'
        with btn_cols[1] if n_selected == 1 else btn_cols[0]:
            if st.button(queue_label, key=f'queue_{tab_key}'):
                segment_reason = {
                    'at_risk':   'Manually added from Client Hub — At Risk or Dormant segment',
                    'milestone': 'Manually added from Client Hub — High Value segment',
                    'onboarding':'Manually added from Client Hub — New This Month segment',
                    'pension':   'Manually added from Client Hub — Pension Candidates segment',
                }.get(stream, 'Manually added from Client Hub')

                segment_action = {
                    'at_risk':   'Review client status and make contact',
                    'milestone': 'Relationship check-in',
                    'onboarding':'Onboarding check-in call',
                    'pension':   'Book pension product introduction',
                }.get(stream, 'Contact client')

                n_added = utils.add_clients_to_queue_direct(
                    engine, selected_ids, stream, segment_reason, segment_action
                )
                utils.load_action_queue.clear()
                skipped = n_selected - n_added
                msg = f'Added {n_added} of {n_selected} client(s) to queue.'
                if skipped:
                    msg += f' {skipped} already in queue (skipped).'
                st.success(msg)
    else:
        # Visually show why the button is absent
        if stream is None and tab_key in ('All Clients', 'Recently Contacted'):
            with btn_cols[1] if n_selected == 1 else btn_cols[0]:
                st.button('Add to Queue', disabled=True, key=f'queue_{tab_key}',
                          help='Select a specific segment tab to add clients to the queue.')

    # Export CSV — always available
    export_col = btn_cols[2] if n_selected == 1 else btn_cols[1]
    with export_col:
        csv_data = selected_clients[[
            'name', 'portfolio_value_eur', 'risk_profile', 'health_score',
            'churn_risk', 'days_since_contact', 'days_since_login', 'next_action'
        ]].to_csv(index=False)
        st.download_button(
            label=f'Export CSV ({n_selected})',
            data=csv_data,
            file_name=f'froots_{tab_key.lower().replace(" ","_")}.csv',
            mime='text/csv',
            key=f'csv_{tab_key}',
        )

# ── Segment tabs ──────────────────────────────────────────────────────────────

tab_labels = list(SEGMENTS.keys())
tabs       = st.tabs(tab_labels)

for tab, (tab_name, seg_meta) in zip(tabs, SEGMENTS.items()):
    with tab:
        # Apply segment mask + cross-segment filters
        seg_mask = seg_meta['mask'] & filter_mask
        seg_df   = clients[seg_mask].reset_index(drop=True)

        st.caption(f'{len(seg_df)} client{"s" if len(seg_df) != 1 else ""}')
        render_segment_table(tab_name, seg_df, seg_meta['stream'])
