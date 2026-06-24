import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from datetime import date
import utils

st.set_page_config(
    page_title='Market Pulse — froots',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

utils.render_sidebar()

st.title('Market Pulse')
st.caption('Live market signals, ETF risk overview, and client exposure.')
st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────

price_data = utils.load_etf_prices()
tickers    = list(price_data.keys())
portfolios = utils.load_portfolios()
clients    = utils.load_clients()
engine     = utils.get_engine()

clients['churn_risk']  = clients.apply(utils.compute_churn_risk,  axis=1)
clients['health_score']= clients.apply(utils.compute_health_score, axis=1)

# Build daily returns for all tickers
returns_df = pd.DataFrame({t: price_data[t].pct_change() for t in tickers})

# ── Section 1 — Market Signal Cards ──────────────────────────────────────────

st.subheader('Market Signals — Today')

DRAFT_TEMPLATE = """Subject: Update on recent market activity

Dear [Client Name],

We're reaching out proactively about recent movements in your portfolio.

{etf} moved {direction} {pct:.1f}% today, which is outside its normal daily range \
(typical swing: ±{normal:.1f}%).

This kind of short-term volatility is a normal part of long-term investing. \
Your portfolio is built to weather these periods, and our strategy remains unchanged.

Please don't hesitate to reach out if you have any questions.

The froots team"""

notable_signals = []
for ticker in tickers:
    series    = returns_df[ticker].dropna()
    if len(series) < 31:
        continue
    today_ret = series.iloc[-1]
    std_30    = series.iloc[-31:-1].std()
    if std_30 == 0:
        continue
    daily_normal = std_30   # 1 stddev = "normal daily range"
    if abs(today_ret) > 1.5 * std_30:
        # Count clients holding this ETF
        holders = portfolios[portfolios['etf'] == ticker]['client_id'].unique()
        holder_clients = clients[clients['client_id'].isin(holders)]
        panic_count = int(
            ((holder_clients['login_count_this_week'] >= 5) &
             (holder_clients['churn_risk'] == 'High')).sum()
        )
        notable_signals.append({
            'ticker':        ticker,
            'today_ret':     today_ret,
            'std_30':        std_30,
            'daily_normal':  daily_normal,
            'holder_ids':    list(holders),
            'n_holders':     len(holders),
            'panic_count':   panic_count,
        })

if not notable_signals:
    st.success('✅ No unusual market signals today. All ETFs are moving within normal ranges.')
else:
    for sig in notable_signals:
        direction = 'down' if sig['today_ret'] < 0 else 'up'
        pct       = abs(sig['today_ret']) * 100
        normal_pct= sig['daily_normal'] * 100

        card_color = 'error' if sig['today_ret'] < 0 else 'warning'
        card_fn    = st.error if card_color == 'error' else st.warning

        card_fn(
            f"**{sig['ticker']} {direction} {pct:.1f}% today** "
            f"(above normal range — typical: ±{normal_pct:.1f}%)\n\n"
            f"**{sig['n_holders']}** clients hold this ETF · "
            f"**{sig['panic_count']}** have both high login activity and High churn risk"
        )

        btn1, btn2 = st.columns(2)
        with btn1:
            draft_text = DRAFT_TEMPLATE.format(
                etf=sig['ticker'],
                direction=direction,
                pct=pct,
                normal=normal_pct,
            )
            with st.expander(f'📋 Draft message — {sig["ticker"]}'):
                st.code(draft_text, language=None)

        with btn2:
            if st.button(
                f'➕ Add {sig["n_holders"]} affected clients to queue',
                key=f'mkt_queue_{sig["ticker"]}'
            ):
                n = utils.add_clients_to_queue_direct(
                    engine,
                    sig['holder_ids'],
                    'market_event',
                    f'Portfolio affected by {sig["ticker"]} {direction} {pct:.1f}% today '
                    f'(outside normal range ±{normal_pct:.1f}%)',
                    'Share market context and reassurance',
                )
                utils.load_action_queue.clear()
                skipped = sig['n_holders'] - n
                msg = f'Added {n} client(s) to queue.'
                if skipped:
                    msg += f' {skipped} already in queue (skipped).'
                st.success(msg)
                st.rerun()

        st.markdown('')

st.divider()

# ── Section 2 — ETF Volatility & Drawdown (plain-English) ────────────────────

st.subheader('ETF Risk Overview')
st.caption('Every metric is followed by a plain-English interpretation for non-finance staff.')

# Rolling 30-day annualised volatility
vol_df = returns_df.rolling(30).std() * np.sqrt(252)
latest_vol = vol_df.dropna().iloc[-1]

# Drawdown
price_idx   = (1 + returns_df).cumprod()
running_max = price_idx.cummax()
drawdown_df = (price_idx - running_max) / running_max
max_dd      = drawdown_df.min()

fig_vol = px.line(
    vol_df.dropna(),
    title='30-Day Rolling Volatility (annualised)',
    labels={'value': 'Annualised Volatility', 'index': 'Date', 'variable': 'ETF'}
)
fig_vol.update_layout(hovermode='x unified', margin=dict(t=40, b=20))
st.plotly_chart(fig_vol, use_container_width=True)

st.markdown('**Current readings by ETF:**')
cols = st.columns(len(tickers))
for col, ticker in zip(cols, tickers):
    with col:
        ann_vol   = latest_vol[ticker]
        daily_sw  = ann_vol / np.sqrt(252)          # daily swing = annualised_vol / √252
        dd        = max_dd[ticker]

        st.markdown(f'**{ticker}**')
        st.metric('Volatility', f'{ann_vol:.1%}')
        st.caption(
            f'Daily swings of ±{daily_sw:.1%} are normal for this ETF. '
            f'Higher = more day-to-day price movement.'
        )
        st.metric('Max Drawdown', f'{dd:.1%}')
        st.caption(
            f'The worst historical loss from a peak was {dd:.1%}. '
            f'{"The ETF has since recovered." if price_idx[ticker].iloc[-1] >= 1.0 else "Still below that peak."}'
        )

st.divider()

# ── Section 3 — Clients Most Exposed ─────────────────────────────────────────

st.subheader('Clients Most Exposed')

highest_vol_ticker = latest_vol.idxmax()
highest_vol_value  = latest_vol.max()

st.markdown(
    f'Highest current volatility ETF: **{highest_vol_ticker}** '
    f'({highest_vol_value:.1%} annualised) — showing clients with >30% allocation.'
)

exposed = portfolios[
    (portfolios['etf'] == highest_vol_ticker) & (portfolios['weight_pct'] > 30)
].merge(
    clients[['client_id', 'name', 'portfolio_value_eur', 'churn_risk', 'health_score']],
    on='client_id'
)[['client_id', 'name', 'portfolio_value_eur', 'weight_pct', 'churn_risk', 'health_score']].copy()

if exposed.empty:
    st.info(f'No clients hold more than 30% in {highest_vol_ticker}.')
else:
    display = exposed[['name', 'portfolio_value_eur', 'weight_pct', 'churn_risk', 'health_score']].copy()
    display.columns = ['Client', 'Portfolio (€)', f'{highest_vol_ticker} Weight (%)', 'Churn Risk', 'Health']
    display['Portfolio (€)'] = display['Portfolio (€)'].map('{:,.0f}'.format)
    display = display.sort_values(f'{highest_vol_ticker} Weight (%)', ascending=False)
    st.dataframe(display, use_container_width=True, hide_index=True)

    if st.button(f'➕ Add all {len(exposed)} exposed clients to Today\'s Queue'):
        n = utils.add_clients_to_queue_direct(
            engine,
            exposed['client_id'].tolist(),
            'market_event',
            f'High exposure to {highest_vol_ticker} ({highest_vol_value:.1%} annualised volatility)',
            'Review portfolio exposure and contact client if needed',
        )
        utils.load_action_queue.clear()
        skipped = len(exposed) - n
        msg = f'Added {n} client(s) to queue.'
        if skipped:
            msg += f' {skipped} already in queue (skipped).'
        st.success(msg)
