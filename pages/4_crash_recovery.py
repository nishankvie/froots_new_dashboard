import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import date
import utils

st.set_page_config(
    page_title='Crash Context — froots',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

utils.render_sidebar()

st.title('Crash Context')
st.caption('Historical market events, recovery data, and client communication aids.')
st.divider()

# ── Event definitions ─────────────────────────────────────────────────────────

EVENTS = {
    'COVID Crash 2020':    ('2020-01-01', '2021-06-30'),
    '2022 Rate Spike':     ('2021-12-01', '2023-06-30'),
    '2023 Banking Crisis': ('2023-01-01', '2023-12-31'),
    'Custom Date Range':   None,
}

# Plain-language narratives — keys verified against EVENTS dict above
EVENT_NARRATIVES = {
    'COVID Crash 2020': (
        "In early 2020, global markets fell sharply as the COVID-19 pandemic spread worldwide. "
        "The MSCI World Index dropped over 30% in just five weeks — one of the fastest declines in history. "
        "Central banks and governments responded with unprecedented support. "
        "Most diversified portfolios recovered fully within 6–12 months.\n\n"
        "**Key message for clients:** Staying invested through the crash and recovery was the right decision. "
        "Clients who sold during the downturn locked in losses; those who held on recovered everything — and more."
    ),
    '2022 Rate Spike': (
        "Throughout 2022, central banks raised interest rates aggressively to combat post-pandemic inflation. "
        "This caused both equity and bond markets to fall simultaneously — an unusual event that made "
        "traditional diversification less effective than normal. Portfolios with significant bond allocations "
        "were particularly affected.\n\n"
        "**Key message for clients:** This was an unusual environment where bonds and equities fell together. "
        "The long-term case for diversified investing remains intact — most portfolios recovered by end-2023."
    ),
    '2023 Banking Crisis': (
        "In March 2023, several US regional banks failed and Credit Suisse was absorbed by UBS. "
        "Markets fell briefly but recovered quickly as regulators intervened decisively. "
        "The impact on diversified ETF portfolios was limited and short-lived.\n\n"
        "**Key message for clients:** This was a contained crisis, not a repeat of 2008. "
        "Regulatory responses were fast, and ETF investors were not materially affected."
    ),
}

GENERIC_NARRATIVE = (
    "This chart shows how your clients' ETFs performed and recovered during the selected period. "
    "Use the recovery times below to contextualise client conversations."
)

# ── Event selector ────────────────────────────────────────────────────────────

selected_event = st.selectbox('Select market event', list(EVENTS.keys()))

if selected_event == 'Custom Date Range':
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input('Start Date')
    with col2:
        end_date = st.date_input('End Date')
    start_str = str(start_date)
    end_str   = str(end_date)
else:
    start_str, end_str = EVENTS[selected_event]

# ── Plain-language narrative ──────────────────────────────────────────────────

narrative = EVENT_NARRATIVES.get(selected_event, GENERIC_NARRATIVE)
with st.container(border=True):
    st.markdown(f'### Context: {selected_event}')
    st.markdown(narrative)

st.markdown('')

# ── Load ETF data ─────────────────────────────────────────────────────────────

price_data = utils.load_etf_prices()

filtered = {}
for ticker, prices in price_data.items():
    fp = prices.loc[start_str:end_str]
    if not fp.empty:
        filtered[ticker] = fp

if not filtered:
    st.warning('No ETF data available for this time period.')
    st.stop()

normalised = {ticker: (prices / prices.iloc[0]) * 100 for ticker, prices in filtered.items()}
normalised_df = pd.concat(normalised, axis=1).sort_index()

# ── Recovery chart ────────────────────────────────────────────────────────────

fig = px.line(
    normalised_df,
    title=f'Portfolio Recovery — {selected_event}',
    labels={'value': 'Normalised Price (start = 100)', 'index': 'Date', 'variable': 'ETF'}
)
fig.add_hline(y=100, line_dash='dash', line_color='gray', annotation_text='Pre-crash level')
fig.update_layout(hovermode='x unified', margin=dict(t=40, b=20))
st.plotly_chart(fig, use_container_width=True)

# ── Recovery time metrics ─────────────────────────────────────────────────────

st.subheader('Recovery Times')
recovery_data = {}
cols = st.columns(len(normalised_df.columns))

for col, ticker in zip(cols, normalised_df.columns):
    series          = normalised_df[ticker]
    crash_low_date  = series.idxmin()
    recovery_series = series[series.index > crash_low_date]
    recovered       = recovery_series[recovery_series >= 100]

    if recovered.empty:
        recovery_text = 'NOT YET RECOVERED'
        months        = None
    else:
        recovery_date = recovered.index[0]
        months = (
            (recovery_date.year  - pd.Timestamp(start_str).year)  * 12 +
            (recovery_date.month - pd.Timestamp(start_str).month)
        )
        recovery_text = f'{months} months'

    recovery_data[ticker] = recovery_text
    with col:
        st.metric(label=ticker, value=recovery_text)

st.divider()

# ── Clients who experienced this event ───────────────────────────────────────

st.subheader('Clients Who Experienced This Event')

today       = pd.Timestamp(date.today())
event_start = pd.Timestamp(start_str)
months_at_event_start = max(int((today - event_start).days // 30), 0)

clients = utils.load_clients()
clients['health_score'] = clients.apply(utils.compute_health_score, axis=1)

invested_then = clients[clients['months_since_joining'] >= months_at_event_start].copy()

st.markdown(
    f'Clients who were invested during **{selected_event}** '
    f'(joined ≥ {months_at_event_start} months ago): **{len(invested_then)}**'
)

if not invested_then.empty:
    display = invested_then[[
        'name', 'portfolio_value_eur', 'months_since_joining', 'health_score', 'risk_profile'
    ]].copy()
    display.columns = ['Client Name', 'Portfolio Value (€)', 'Months Joined', 'Health Score', 'Risk Profile']
    display['Portfolio Value (€)'] = display['Portfolio Value (€)'].map('{:,.0f}'.format)
    display = display.sort_values('Months Joined', ascending=False)
    st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# ── PDF Report Generator ──────────────────────────────────────────────────────

st.subheader('PDF Report')
st.caption('Branded one-page report ready to share with a worried client.')

if st.button('📄 Generate PDF Report', type='primary'):
    try:
        import weasyprint

        # Build recovery table HTML
        recovery_rows = ''.join(
            f'<tr><td>{t}</td><td>{v}</td></tr>'
            for t, v in recovery_data.items()
        )
        recovery_table = f'''
        <table>
          <thead><tr><th>ETF</th><th>Time to Recovery</th></tr></thead>
          <tbody>{recovery_rows}</tbody>
        </table>'''

        # Build client table HTML (max 20 rows to keep PDF compact)
        if not invested_then.empty:
            client_rows = ''.join(
                f'<tr><td>{row["name"]}</td>'
                f'<td>€{row["portfolio_value_eur"]:,.0f}</td>'
                f'<td>{row["risk_profile"].capitalize()}</td></tr>'
                for _, row in invested_then.head(20).iterrows()
            )
            client_table = f'''
            <table>
              <thead><tr><th>Client</th><th>Portfolio Value</th><th>Risk Profile</th></tr></thead>
              <tbody>{client_rows}</tbody>
            </table>'''
            if len(invested_then) > 20:
                client_table += f'<p><em>… and {len(invested_then) - 20} more clients</em></p>'
        else:
            client_table = '<p>No clients were invested during this period.</p>'

        html_str = f'''
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: sans-serif; color: #1a1a1a; padding: 40px; font-size: 13px; }}
            .header {{ background: #2ecc71; color: white; padding: 20px 30px; margin: -40px -40px 30px; }}
            .header h1 {{ margin: 0; font-size: 22px; }}
            .header p  {{ margin: 4px 0 0; opacity: 0.85; font-size: 13px; }}
            h2 {{ color: #1a7a45; margin-top: 28px; font-size: 16px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
            .narrative {{ background: #f8f9fa; border-left: 4px solid #2ecc71;
                          padding: 12px 16px; margin: 12px 0; border-radius: 0 4px 4px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
            th {{ background: #f0f0f0; padding: 7px 10px; text-align: left; font-size: 12px; }}
            td {{ padding: 6px 10px; border-bottom: 1px solid #eee; font-size: 12px; }}
            .footer {{ color: #999; font-size: 10px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 8px; }}
          </style>
        </head>
        <body>
          <div class="header">
            <h1>froots — Market Recovery Report</h1>
            <p>{selected_event} · Generated {today.strftime("%d %b %Y")} · Internal use only</p>
          </div>

          <h2>What Happened</h2>
          <div class="narrative">{narrative.replace("**", "").replace("\n\n", "<br><br>")}</div>

          <h2>ETF Recovery Times</h2>
          {recovery_table}

          <h2>Clients Invested During This Period</h2>
          <p>{len(invested_then)} client(s) were invested with froots during {selected_event}.</p>
          {client_table}

          <div class="footer">froots GmbH · This report is for internal CE team use only · Not for distribution</div>
        </body>
        </html>'''

        pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
        slug      = selected_event.lower().replace(' ', '_').replace('-', '')

        st.download_button(
            label='⬇️ Download PDF',
            data=pdf_bytes,
            file_name=f'froots_recovery_{slug}.pdf',
            mime='application/pdf',
        )

    except ImportError:
        st.error(
            'WeasyPrint is not installed. Run `pip install weasyprint` and ensure '
            'system dependencies are available (see packages.txt).'
        )
    except Exception as e:
        st.error(f'PDF generation failed: {e}')
