import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
import utils

st.set_page_config(
    page_title='Pension Tool — froots',
    layout='wide',
    page_icon='assets/froots_logo.png',
    initial_sidebar_state='expanded'
)

utils.render_sidebar()

st.title('Pension Tool — Vorsorge ohne KeSt')
st.caption('Product information, projections, client fit scoring, and communication aids.')
st.divider()

# ── Shared config ─────────────────────────────────────────────────────────────

cfg = utils.load_pension_config()

FROOTS_FEE       = 0.012  # 1.0% mgmt + 0.17% ETF product costs + 0.03% risk premium (fynup benchmark, age 35)
FROOTS_KEST      = float(cfg['kest_rate_inside_pct'])  / 100 if cfg is not None else 0.0
FROOTS_INS_TAX   = float(cfg['insurance_tax_pct'])     / 100 if cfg is not None else 0.04
CLASSIC_FEE      = float(cfg['classic_flv_fee_pct'])   / 100 if cfg is not None else 0.015  # 1.5% annual mgmt + fund cost (fynup benchmark)
CLASSIC_KEST     = float(cfg['classic_flv_kest_pct'])  / 100 if cfg is not None else 0.275
MIN_LUMP         = float(cfg['min_lump_sum_eur'])              if cfg is not None else 5000
MIN_MONTHLY      = float(cfg['min_monthly_eur'])               if cfg is not None else 100
PARTNERS         = cfg['insurance_partners']                   if cfg is not None else ''

# ETF allocation by risk profile (froots internal weights for the pension wrapper)
ETF_WEIGHTS = {
    'Conservative': {
        'VWCE.DE': 30, 'EIMI.L': 10, 'AGGG.L': 40, 'IUSV.DE': 10, 'WSML.L': 10
    },
    'Balanced': {
        'VWCE.DE': 40, 'EIMI.L': 15, 'AGGG.L': 20, 'IUSV.DE': 15, 'WSML.L': 10
    },
    'Return-oriented': {
        'VWCE.DE': 45, 'EIMI.L': 20, 'AGGG.L':  5, 'IUSV.DE': 20, 'WSML.L': 10
    },
}

# ── Projection helpers ────────────────────────────────────────────────────────

def _project_lumpsum(principal: float, r: float, years: int, fee: float,
                     ins_tax: float, kest: float):
    """Returns (net_final, gross_final, total_fees, tax_paid, series_by_year)."""
    after_tax_premium = principal * (1 - ins_tax)
    yearly = []
    value  = after_tax_premium
    total_fees = 0.0
    for yr in range(1, years + 1):
        growth      = value * r
        fee_paid    = value * fee
        total_fees += fee_paid
        value       = value + growth - fee_paid
        yearly.append(value)
    gross_final = yearly[-1]
    gains       = max(gross_final - principal, 0)
    tax_paid    = gains * kest
    net_final   = gross_final - tax_paid
    return net_final, gross_final, total_fees, tax_paid, yearly


def _project_monthly(monthly: float, r: float, years: int, fee: float,
                     ins_tax: float, kest: float):
    """Returns (net_final, gross_final, total_fees, tax_paid, series_by_year, total_invested)."""
    # VSt is 4% OF total premium (added on top of net amount), so net = monthly / (1 + ins_tax)
    # Gives total Versicherungssteuer = monthly * ins_tax / (1 + ins_tax); at C=300 over 360 mo ≈ €4,154
    monthly_eff   = monthly / (1 + ins_tax)
    net_monthly_r = (r - fee) / 12   # linear fee drag; for froots: (0.07 - 0.012) / 12
    monthly_fee   = fee / 12          # used for fee tracking only

    total_invested = monthly * 12 * years
    series_by_year = []
    value = 0.0
    total_fees = 0.0
    months_total = years * 12

    for m in range(months_total):
        value      = (value + monthly_eff) * (1 + net_monthly_r)
        fee_month  = (value - monthly_eff) * monthly_fee  # approx fee on existing balance
        total_fees+= fee_month
        if (m + 1) % 12 == 0:
            series_by_year.append(value)

    gross_final = value
    gains       = max(gross_final - total_invested, 0)
    tax_paid    = gains * kest
    net_final   = gross_final - tax_paid
    return net_final, gross_final, total_fees, tax_paid, series_by_year, total_invested


def _build_projection_pdf(
    mode: str, scenario_label: str,
    principal_or_monthly: float, r: float, years: int,
    froots_net: float, froots_fees: float, froots_tax: float,
    classic_net: float, classic_fees: float, classic_tax: float,
    total_invested: float, narrative: str = '',
    extra_sections: str = '',
) -> bytes:
    today_str = date.today().strftime('%d %b %Y')
    saving    = froots_net - classic_net

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; color: #1a1a1a; padding: 40px; font-size: 13px; }}
  .header {{ background:#2ecc71; color:white; padding:20px 30px; margin:-40px -40px 30px; }}
  .header h1 {{ margin:0; font-size:20px; }}
  .header p  {{ margin:4px 0 0; opacity:.85; font-size:12px; }}
  h2 {{ color:#1a7a45; font-size:15px; border-bottom:1px solid #ddd;
        padding-bottom:4px; margin-top:24px; }}
  table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
  th {{ background:#f0f0f0; padding:7px 10px; text-align:left; font-size:12px; }}
  td {{ padding:6px 10px; border-bottom:1px solid #eee; font-size:12px; }}
  .highlight {{ background:#eafaf1; border-left:4px solid #2ecc71;
                padding:10px 14px; border-radius:0 4px 4px 0; margin:12px 0; }}
  .footer {{ color:#999; font-size:10px; margin-top:36px;
             border-top:1px solid #eee; padding-top:8px; }}
</style>
</head>
<body>
<div class="header">
  <h1>froots — Pension Projection</h1>
  <p>{scenario_label} · {today_str} · Internal use only</p>
</div>

<h2>Inputs</h2>
<table>
  <tr><th>Parameter</th><th>Value</th></tr>
  <tr><td>Mode</td><td>{mode}</td></tr>
  <tr><td>{"Lump sum" if "Lump" in mode else "Monthly contribution"}</td>
      <td>€{principal_or_monthly:,.0f}</td></tr>
  <tr><td>Horizon</td><td>{years} years</td></tr>
  <tr><td>Expected annual return</td><td>{r*100:.1f}%</td></tr>
  <tr><td>Total invested</td><td>€{total_invested:,.0f}</td></tr>
</table>

<h2>Results</h2>
<table>
  <tr><th></th><th>froots Vorsorge (KeSt-free)</th><th>Classic FLV</th></tr>
  <tr><td>Net final value</td>
      <td><strong>€{froots_net:,.0f}</strong></td>
      <td>€{classic_net:,.0f}</td></tr>
  <tr><td>Total fees paid</td>
      <td>€{froots_fees:,.0f}</td>
      <td>€{classic_fees:,.0f}</td></tr>
  <tr><td>Tax paid at exit</td>
      <td>€{froots_tax:,.0f}</td>
      <td>€{classic_tax:,.0f}</td></tr>
</table>

<div class="highlight">
  <strong>Net advantage of froots Vorsorge: €{saving:,.0f}</strong><br>
  Over {years} years, the KeSt-free structure and lower fee save an estimated
  €{saving:,.0f} compared to a classic FLV.
</div>

{f'<h2>Notes</h2><p>{narrative}</p>' if narrative else ''}
{extra_sections}

<div class="footer">
  froots GmbH · Projection assumes constant annual return of {r*100:.1f}%.
  Past performance does not guarantee future results. For internal CE use only.
</div>
</body></html>'''

    try:
        import weasyprint
        return weasyprint.HTML(string=html).write_pdf()
    except ImportError:
        return None


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    '7.1 Product Snapshot',
    '7.2 Custom Projection',
    '7.3 Client Fit Finder',
    '7.4 Back-Calculation',
    '7.5 Question Library',
    '7.6 Report Export',
])

# ─────────────────────────────────────────────────────────────────────────────
# 7.1  PRODUCT SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader('Vorsorge ohne KeSt — What it is')

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown('#### How it works')
        st.markdown(
            f'froots wraps your ETF portfolio inside a **fondsgebundene Lebensversicherung** '
            f'(unit-linked life insurance). Inside the wrapper:\n\n'
            f'- **{FROOTS_KEST:.0%} KeSt** on investment gains (vs 27.5% in a classic depot)\n'
            f'- **{FROOTS_FEE:.1%} annual all-in fee** — no acquisition fee, no Zillmerung, no kickbacks\n'
            f'- **{FROOTS_INS_TAX:.0%} Versicherungssteuer** deducted from each premium going in\n'
            f'- **Minimum lump sum:** €{MIN_LUMP:,.0f}  ·  '
            f'**Minimum monthly:** €{MIN_MONTHLY:,.0f}/month\n'
            f'- **Target horizon:** 15+ years (Altersvorsorge)'
        )

        st.markdown('#### Insurance partners')
        for p in PARTNERS.split(','):
            st.markdown(f'- {p.strip()}')

    with col_b:
        st.markdown('#### Tax advantage — concrete example')
        example_principal = 50_000
        example_r         = 0.06
        example_years     = 20

        f_net, f_gross, f_fees, f_tax, _ = _project_lumpsum(
            example_principal, example_r, example_years,
            FROOTS_FEE, FROOTS_INS_TAX, FROOTS_KEST
        )
        c_net, c_gross, c_fees, c_tax, _ = _project_lumpsum(
            example_principal, example_r, example_years,
            CLASSIC_FEE, 0.0, CLASSIC_KEST
        )

        st.markdown(
            f'*€{example_principal:,.0f} invested for {example_years} years at '
            f'{example_r*100:.0f}%/year*'
        )
        comp_df = pd.DataFrame({
            '': ['Net final value', 'Total fees paid', 'Tax paid at exit'],
            'froots Vorsorge': [f'€{f_net:,.0f}', f'€{f_fees:,.0f}', f'€{f_tax:,.0f}'],
            'Classic FLV':     [f'€{c_net:,.0f}', f'€{c_fees:,.0f}', f'€{c_tax:,.0f}'],
        })
        st.dataframe(comp_df, use_container_width=True, hide_index=True)
        st.success(f'**Advantage: €{f_net - c_net:,.0f}** over {example_years} years')

    st.divider()
    st.markdown('#### ETF allocation by risk profile (in the pension wrapper)')

    alloc_rows = []
    for profile, weights in ETF_WEIGHTS.items():
        row = {'Risk Profile': profile}
        row.update({etf: f'{w}%' for etf, w in weights.items()})
        alloc_rows.append(row)

    st.dataframe(pd.DataFrame(alloc_rows), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# 7.2  CUSTOM PROJECTION
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader('Custom Projection')

    clients_df = utils.load_clients()
    mode = st.radio('Mode', ['New Prospect', 'Existing Client'], horizontal=True)

    if mode == 'Existing Client':
        client_names = sorted(clients_df['name'].tolist())
        selected_name = st.selectbox('Select client', client_names)
        sel_client = clients_df[clients_df['name'] == selected_name].iloc[0]
        default_lump    = float(sel_client['portfolio_value_eur'])
        default_monthly = float(sel_client['monthly_deposit'])
        default_horizon = max(int((65 - sel_client['age']) * 1), 10)
    else:
        default_lump    = 10_000.0
        default_monthly = 200.0
        default_horizon = 20

    p1, p2, p3 = st.columns(3)
    with p1:
        contribution_type = st.radio('Contribution type', ['Lump Sum', 'Monthly'], horizontal=True)
    with p2:
        if contribution_type == 'Lump Sum':
            principal = st.number_input('Lump sum (€)', min_value=MIN_LUMP,
                                        value=default_lump, step=1000.0)
        else:
            principal = st.number_input('Monthly contribution (€)', min_value=MIN_MONTHLY,
                                        value=default_monthly, step=50.0)
    with p3:
        years = st.slider('Investment horizon (years)', 5, 40, default_horizon)

    expected_return = st.slider('Expected annual return (%)', 2.0, 10.0, 5.0, 0.5) / 100

    st.markdown('---')

    # Calculate
    if contribution_type == 'Lump Sum':
        f_net, f_gross, f_fees, f_tax, f_series = _project_lumpsum(
            principal, expected_return, years, FROOTS_FEE, FROOTS_INS_TAX, FROOTS_KEST
        )
        c_net, c_gross, c_fees, c_tax, c_series = _project_lumpsum(
            principal, expected_return, years, CLASSIC_FEE, 0.0, CLASSIC_KEST
        )
        total_invested = principal
    else:
        f_net, f_gross, f_fees, f_tax, f_series, total_invested = _project_monthly(
            principal, expected_return, years, FROOTS_FEE, FROOTS_INS_TAX, FROOTS_KEST
        )
        c_net, c_gross, c_fees, c_tax, c_series, _ = _project_monthly(
            principal, expected_return, years, CLASSIC_FEE, 0.0, CLASSIC_KEST
        )

    saving = f_net - c_net

    # Results side-by-side
    r1, r2, r3 = st.columns(3)
    with r1:
        st.metric('Total invested', f'€{total_invested:,.0f}')
    with r2:
        st.metric('froots net value', f'€{f_net:,.0f}')
    with r3:
        st.metric('Classic FLV net value', f'€{c_net:,.0f}',
                  delta=f'-€{saving:,.0f} vs froots', delta_color='inverse')

    d1, d2, d3 = st.columns(3)
    with d1:
        st.metric('froots fees paid', f'€{f_fees:,.0f}')
        st.metric('Classic FLV fees', f'€{c_fees:,.0f}')
    with d2:
        st.metric('froots KeSt at exit', f'€{f_tax:,.0f}')
        st.metric('Classic FLV KeSt',    f'€{c_tax:,.0f}')
    with d3:
        st.metric('Net advantage (froots)', f'€{saving:,.0f}',
                  help='froots net value minus classic FLV net value')

    # Cumulative value chart
    year_labels = list(range(1, years + 1))
    chart_df = pd.DataFrame({
        'Year': year_labels,
        'froots Vorsorge': f_series,
        'Classic FLV':     c_series,
    })
    fig_proj = px.line(
        chart_df, x='Year', y=['froots Vorsorge', 'Classic FLV'],
        title='Portfolio Value Over Time',
        labels={'value': 'Value (€)', 'variable': 'Product'},
        color_discrete_map={'froots Vorsorge': '#2ecc71', 'Classic FLV': '#95a5a6'}
    )
    fig_proj.update_layout(hovermode='x unified', margin=dict(t=40, b=20))
    st.plotly_chart(fig_proj, use_container_width=True)

    # Fee drag + tax savings bars
    bar_df = pd.DataFrame({
        'Category': ['Fees', 'KeSt (tax)', 'Net value'],
        'froots Vorsorge': [f_fees, f_tax, f_net],
        'Classic FLV':     [c_fees, c_tax, c_net],
    })
    fig_bar = px.bar(
        bar_df, x='Category', y=['froots Vorsorge', 'Classic FLV'],
        barmode='group', title='Fee Drag & Tax Comparison',
        labels={'value': '€', 'variable': 'Product'},
        color_discrete_map={'froots Vorsorge': '#2ecc71', 'Classic FLV': '#95a5a6'}
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # Save + Export
    sc1, sc2 = st.columns(2)
    with sc1:
        if st.button('💾 Save Scenario', key='save_scenario'):
            st.session_state['saved_projection'] = {
                'label':          f'{contribution_type} — {years}yr @ {expected_return*100:.1f}%',
                'mode':           mode,
                'contribution_type': contribution_type,
                'principal':      principal,
                'years':          years,
                'r':              expected_return,
                'total_invested': total_invested,
                'f_net': f_net, 'f_fees': f_fees, 'f_tax': f_tax,
                'c_net': c_net, 'c_fees': c_fees, 'c_tax': c_tax,
                'f_series': f_series, 'c_series': c_series,
            }
            st.success('Scenario saved — see tab 7.6 for PDF export.')

    with sc2:
        if st.button('📄 Export PDF', key='proj_pdf'):
            pdf = _build_projection_pdf(
                mode=f'{mode} — {contribution_type}',
                scenario_label=f'{contribution_type} projection',
                principal_or_monthly=principal,
                r=expected_return, years=years,
                froots_net=f_net, froots_fees=f_fees, froots_tax=f_tax,
                classic_net=c_net, classic_fees=c_fees, classic_tax=c_tax,
                total_invested=total_invested,
            )
            if pdf:
                st.download_button('⬇️ Download PDF', data=pdf,
                                   file_name='froots_pension_projection.pdf',
                                   mime='application/pdf', key='dl_proj_pdf')
            else:
                st.error('WeasyPrint not available — install it and system dependencies (see packages.txt).')


# ─────────────────────────────────────────────────────────────────────────────
# 7.3  CLIENT FIT FINDER
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader('Client Fit Finder')
    st.caption('All clients ranked by pension product fit. Score ≥70 = Strong Fit.')

    with st.container(border=True):
        st.markdown('**How the score is calculated — 100 pts total**')
        f1, f2, f3, f4, f5 = st.columns(5)
        with f1:
            st.metric('Age 25–50', '30 pts')
            st.caption('Prime savings window. Too young = low capital; too old = short horizon.')
        with f2:
            st.metric('Consistent deposits', '25 pts')
            st.caption('0 missed deposits in the last 3 months — shows financial discipline.')
        with f3:
            st.metric('Portfolio > €10 k', '20 pts')
            st.caption('Has investable capital to seed the pension wrapper (min €5,000 lump sum).')
        with f4:
            st.metric('Balanced / Growth profile', '15 pts')
            st.caption('Risk appetite suits long-horizon ETF investing inside the wrapper.')
        with f5:
            st.metric('Pension / retirement goal', '10 pts')
            st.caption('Investment goal mentions pension, retirement, long-term, or similar.')
        st.caption('✅ Strong Fit ≥ 70 pts · ⚠️ Moderate 40–69 pts · — Below 40 pts')

    clients_df = utils.load_clients()

    def _fit_breakdown(row):
        age_pts       = 30 if 25 <= int(row['age']) <= 50 else 0
        deposit_pts   = 25 if row['missed_deposits_last_3_months'] == 0 else 0
        portfolio_pts = 20 if row['portfolio_value_eur'] > 10_000 else 0
        profile_pts   = 15 if row['risk_profile'].lower() in ('balanced', 'growth') else 0
        goal_pts      = 10 if any(w in str(row['investment_goal']).lower()
                                   for w in ('pension', 'retirement', 'long-term', 'long term')) else 0
        total = age_pts + deposit_pts + portfolio_pts + profile_pts + goal_pts
        return total, age_pts, deposit_pts, portfolio_pts, profile_pts, goal_pts

    rows = []
    for _, r in clients_df.iterrows():
        total, a, d, p, pr, g = _fit_breakdown(r)
        rows.append({
            'client_id':     int(r['client_id']),
            'Name':          r['name'],
            'Fit Score':     total,
            'Fit':           '✅ Strong' if total >= 70 else ('⚠️ Moderate' if total >= 40 else '—'),
            'Age (30)':      f'✓ {a}' if a else f'— {a}',
            'Deposits (25)': f'✓ {d}' if d else f'— {d}',
            'Portfolio (20)':f'✓ {p}' if p else f'— {p}',
            'Profile (15)':  f'✓ {pr}' if pr else f'— {pr}',
            'Goal (10)':     f'✓ {g}' if g else f'— {g}',
        })

    fit_df = pd.DataFrame(rows).sort_values('Fit Score', ascending=False).reset_index(drop=True)

    st.dataframe(
        fit_df.drop(columns=['client_id']),
        use_container_width=True, hide_index=True
    )

    st.markdown('---')
    st.markdown('**Bulk add top candidates to Pension Conversions queue**')
    top_n = st.number_input('Add top N clients (score ≥70)', min_value=1, max_value=50, value=5)
    strong_fit = fit_df[fit_df['Fit Score'] >= 70].head(int(top_n))

    if strong_fit.empty:
        st.caption('No clients currently score ≥70.')
    else:
        st.caption(f'{len(strong_fit)} client(s) selected (score ≥70, top {int(top_n)})')
        if st.button(f'➕ Add {len(strong_fit)} to Pension Conversions queue'):
            engine = utils.get_engine()
            n = utils.add_clients_to_queue_direct(
                engine,
                strong_fit['client_id'].tolist(),
                'pension',
                'High pension product fit score (≥70/100) — strong candidate for Vorsorge ohne KeSt',
                'Book pension product introduction',
                estimated_minutes=15,
            )
            utils.load_action_queue.clear()
            skipped = len(strong_fit) - n
            msg = f'Added {n} client(s) to queue.'
            if skipped:
                msg += f' {skipped} already in queue (skipped).'
            st.success(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 7.4  BACK-CALCULATION
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader('Back-Calculation')
    st.caption(
        'For an existing client: if they had been in the froots wrapper for the past N years, '
        'what would the difference be in concrete euros?'
    )

    clients_df  = utils.load_clients()
    price_data  = utils.load_etf_prices()

    bc_name = st.selectbox('Select client', sorted(clients_df['name'].tolist()), key='bc_client')
    bc_client = clients_df[clients_df['name'] == bc_name].iloc[0]

    bc_years = st.slider('Look-back period (years)', 1, 20, 10, key='bc_years')

    # Use VWCE.DE as the primary ETF for back-calculation (largest allocation in all profiles)
    vwce = price_data.get('VWCE.DE')
    today_ts = pd.Timestamp(date.today())
    start_ts = today_ts - pd.DateOffset(years=bc_years)

    if vwce is not None:
        period = vwce.loc[str(start_ts.date()):]
        if len(period) < 2:
            st.warning(f'Not enough VWCE.DE data for a {bc_years}-year look-back. '
                       f'Try a shorter period.')
            actual_return = 0.05
        else:
            total_period_return = (period.iloc[-1] / period.iloc[0]) - 1
            actual_return = (1 + total_period_return) ** (1 / bc_years) - 1
    else:
        actual_return = 0.05

    principal   = float(bc_client['portfolio_value_eur'])
    monthly_dep = float(bc_client['monthly_deposit'])

    st.markdown(
        f'**{bc_name}** · Portfolio value: **€{principal:,.0f}** · '
        f'Monthly deposit: **€{monthly_dep:,.0f}** · '
        f'VWCE.DE annualised return over {bc_years}yr: **{actual_return*100:.1f}%**'
    )
    st.divider()

    # Compute both scenarios using monthly contributions
    f_net, f_gross, f_fees, f_tax, f_series, f_invested = _project_monthly(
        monthly_dep, actual_return, bc_years, FROOTS_FEE, FROOTS_INS_TAX, FROOTS_KEST
    )
    c_net, c_gross, c_fees, c_tax, c_series, _ = _project_monthly(
        monthly_dep, actual_return, bc_years, CLASSIC_FEE, 0.0, CLASSIC_KEST
    )
    saving = f_net - c_net

    col1, col2, col3 = st.columns(3)
    col1.metric('Total invested (monthly dep)', f'€{f_invested:,.0f}')
    col2.metric('froots wrapper — net value', f'€{f_net:,.0f}')
    col3.metric('Classic FLV — net value', f'€{c_net:,.0f}',
                delta=f'-€{saving:,.0f} vs froots', delta_color='inverse')

    d1, d2 = st.columns(2)
    with d1:
        st.metric('Fees saved vs classic', f'€{c_fees - f_fees:,.0f}')
    with d2:
        st.metric('Tax saved vs classic', f'€{c_tax - f_tax:,.0f}')

    year_labels = list(range(1, bc_years + 1))
    bc_chart = pd.DataFrame({
        'Year': year_labels,
        'froots Vorsorge (if had joined)': f_series,
        'Classic FLV (estimated)':         c_series,
    })
    fig_bc = px.line(
        bc_chart, x='Year', y=['froots Vorsorge (if had joined)', 'Classic FLV (estimated)'],
        title=f'Back-Calculation — {bc_name} over {bc_years} years',
        labels={'value': '€', 'variable': 'Scenario'},
        color_discrete_map={
            'froots Vorsorge (if had joined)': '#2ecc71',
            'Classic FLV (estimated)': '#95a5a6'
        }
    )
    fig_bc.update_layout(hovermode='x unified', margin=dict(t=40, b=20))
    st.plotly_chart(fig_bc, use_container_width=True)

    st.caption(
        f'Note: uses {bc_years}-year actual VWCE.DE return ({actual_return*100:.1f}%/yr) '
        f'and {bc_name}\'s current monthly deposit (€{monthly_dep:,.0f}) '
        f'as a constant contribution. Does not account for historical deposit changes.'
    )

    if st.button('📄 Export Back-Calculation PDF', key='bc_pdf'):
        pdf = _build_projection_pdf(
            mode='Back-Calculation — Monthly',
            scenario_label=f'{bc_name} — {bc_years}-year look-back',
            principal_or_monthly=monthly_dep,
            r=actual_return, years=bc_years,
            froots_net=f_net, froots_fees=f_fees, froots_tax=f_tax,
            classic_net=c_net, classic_fees=c_fees, classic_tax=c_tax,
            total_invested=f_invested,
            narrative=(
                f'Based on {bc_years} years of actual VWCE.DE performance '
                f'(annualised: {actual_return*100:.1f}%), '
                f'using {bc_name}\'s current monthly deposit of €{monthly_dep:,.0f}.'
            )
        )
        if pdf:
            st.download_button('⬇️ Download PDF', data=pdf,
                               file_name=f'froots_backcalc_{bc_name.lower().replace(" ","_")}.pdf',
                               mime='application/pdf', key='dl_bc_pdf')
        else:
            st.error('WeasyPrint not available — install it and system dependencies (see packages.txt).')


# ─────────────────────────────────────────────────────────────────────────────
# 7.5  QUESTION LIBRARY
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.subheader('Question Library')
    st.caption('All answers are pre-written. No AI involved. Copy and paste directly.')

    QA = [
        # ── Risk ──────────────────────────────────────────────────────────────
        {
            'category': 'Risk',
            'question': 'Can I lose money in the froots pension wrapper?',
            'short': 'Yes — it is invested in ETFs, so market risk applies. '
                     'The wrapper does not guarantee capital.',
            'detail': (
                'The fondsgebundene Lebensversicherung is an investment product, not a savings account. '
                'Your contributions are invested in ETFs (VWCE.DE, EIMI.L, AGGG.L, IUSV.DE, WSML.L) '
                'and the value fluctuates with the market. '
                'Over horizons of 15+ years, diversified equity ETFs have historically recovered '
                'from all major downturns, but past performance does not guarantee future returns. '
                'froots does not offer capital protection.'
            ),
        },
        {
            'category': 'Risk',
            'question': 'What happens to my money if froots goes bankrupt?',
            'short': 'Your assets are held by the insurance partner (e.g. Zurich), not froots. '
                     'They are legally separated from froots\'s balance sheet.',
            'detail': (
                'froots acts as the distribution partner. The actual insurance contract is '
                'held with one of the licensed Austrian insurance partners '
                '(Zurich, Donau, Helvetia, Österreichische Beamtenversicherung, Standard Life). '
                'Your assets are legally separated from froots\'s business assets and '
                'are protected under Austrian insurance regulation (VAG). '
                'If froots were to cease operations, the insurance contract would remain valid '
                'and could be continued or transferred.'
            ),
        },
        # ── Returns ───────────────────────────────────────────────────────────
        {
            'category': 'Returns',
            'question': 'What returns can I expect?',
            'short': 'We cannot guarantee returns. Historically, global equity ETFs have returned '
                     '6–8%/year over long periods, but this is not guaranteed.',
            'detail': (
                'The froots portfolio uses globally diversified ETFs. '
                'Historical long-term equity returns (20+ years) have been roughly 6–8% per year '
                'in nominal terms. Our projections typically use 5–6% as a conservative assumption. '
                'Returns depend on global market performance, ETF TERs (0.1–0.3%), '
                'and the 1% froots annual fee. We do not provide return guarantees, '
                'and all projections are illustrative only.'
            ),
        },
        # ── Fees ──────────────────────────────────────────────────────────────
        {
            'category': 'Fees',
            'question': 'What does the 1% annual fee cover?',
            'short': 'Everything: platform, rebalancing, advice, and the insurance wrapper. '
                     'There are no additional transaction fees or exit fees.',
            'detail': (
                'The 1% annual all-in fee (charged on assets under management) covers: '
                'the froots platform and reporting, portfolio rebalancing, ongoing advisory, '
                'and the cost of the insurance wrapper administration. '
                'There is no acquisition fee (Ausgabeaufschlag), no Zillmerung, '
                'no performance fee, no kickbacks from ETF providers, and no exit fee. '
                'The only additional cost is the 4% Versicherungssteuer on premiums, '
                'which is a statutory Austrian tax, not a froots fee.'
            ),
        },
        {
            'category': 'Fees',
            'question': 'What is the Versicherungssteuer and why do I pay it?',
            'short': 'It is a 4% Austrian statutory tax on life insurance premiums. '
                     'It applies to all Austrian life insurance products, including froots.',
            'detail': (
                'The Versicherungssteuer (insurance premium tax) of 4% is levied by the Austrian '
                'government on premiums paid into all fondsgebundene Lebensversicherungen. '
                'It is not specific to froots — any competing FLV product in Austria is subject '
                'to the same tax. For a €500/month contribution, €20 goes to the tax authority '
                'and €480 is invested. The tax is applied to each premium as it is paid in.'
            ),
        },
        # ── Taxes ─────────────────────────────────────────────────────────────
        {
            'category': 'Taxes',
            'question': 'Why is there 0% KeSt inside the wrapper?',
            'short': 'Austrian tax law exempts gains inside life insurance wrappers from the '
                     '27.5% capital gains tax (KeSt), as long as the product qualifies.',
            'detail': (
                'Under §27 EStG (Austrian Income Tax Act), investment gains within a '
                'qualifying fondsgebundene Lebensversicherung are not subject to '
                'Kapitalertragsteuer (KeSt) during the accumulation phase. '
                'At payout, the insurance benefit is taxed differently '
                '(typically as a lump sum with reduced effective rate or not at all '
                'for pension-qualified products held to maturity). '
                'This is the key tax advantage compared to holding ETFs directly in a '
                'Wertpapierdepot, where every dividend and realised gain is taxed at 27.5%.'
            ),
        },
        {
            'category': 'Taxes',
            'question': 'What tax do I pay when I take the money out?',
            'short': 'For pension-qualified payouts, the benefit is often tax-free or '
                     'taxed at a favourable flat rate. This depends on how you take the payout.',
            'detail': (
                'If you take the benefit as a pension (regular payments), it is taxed as '
                'ordinary income at your marginal tax rate. '
                'If you take a lump sum payout, Austrian law may apply a reduced flat tax rate '
                'depending on the product structure and duration. '
                'froots recommends clients consult a tax advisor for their specific situation. '
                'The key point is that during accumulation, 0% KeSt applies, '
                'which is the main advantage for long-term wealth building.'
            ),
        },
        # ── Withdrawal ────────────────────────────────────────────────────────
        {
            'category': 'Withdrawal',
            'question': 'Can I access my money before retirement?',
            'short': 'Yes, but early termination typically incurs costs and loses the tax benefit.',
            'detail': (
                'The froots pension wrapper can be terminated early. '
                'However, early termination may result in: '
                '(1) surrender charges in the early years of the contract (if applicable), '
                '(2) loss of the KeSt exemption on accumulated gains (gains may become subject '
                'to KeSt retrospectively in some structures), and '
                '(3) the 4% Versicherungssteuer already paid on premiums is not refunded. '
                'froots strongly recommends treating this as a long-term product (15+ years). '
                'For short-term capital needs, a regular ETF depot is more suitable.'
            ),
        },
        # ── Lock-in ───────────────────────────────────────────────────────────
        {
            'category': 'Lock-in',
            'question': 'Is there a mandatory lock-in period?',
            'short': 'No mandatory lock-in, but the product is designed for 15+ years. '
                     'Exiting early reduces the tax advantage.',
            'detail': (
                'There is no contractual lock-in that prevents withdrawal. '
                'However, the economic benefit of the KeSt exemption compounds over time — '
                'the longer you hold, the larger the advantage over a classic depot. '
                'froots models show the break-even on the 4% insurance tax '
                'typically occurs within 3–5 years. Beyond that, the tax saving accelerates. '
                'The product is therefore best suited for clients with a 15-year+ horizon.'
            ),
        },
        # ── Death / inheritance ───────────────────────────────────────────────
        {
            'category': 'Death & Inheritance',
            'question': 'What happens to the policy if the policyholder dies?',
            'short': 'The death benefit (current policy value) is paid to the named beneficiary, '
                     'outside the estate.',
            'detail': (
                'As a life insurance product, the froots pension wrapper allows '
                'the policyholder to name a beneficiary. '
                'On death, the current policy value (Rückkaufswert) is paid directly '
                'to the named beneficiary and does not form part of the estate '
                '(Nachlassmasse). This can simplify inheritance in some cases, '
                'though Austrian inheritance tax rules (Erbschaftssteuer — currently not levied '
                'at federal level but applicable via Schenkungssteuer in some cantons) '
                'may still apply depending on the beneficiary relationship. '
                'Clients should consult a notary or estate planner for their situation.'
            ),
        },
        # ── Stopping contributions ────────────────────────────────────────────
        {
            'category': 'Stopping Contributions',
            'question': 'What happens if I stop making contributions?',
            'short': 'The policy becomes "beitragsfrei" — it stays invested but you stop paying in. '
                     'No penalty for this.',
            'detail': (
                'If you stop making regular contributions, the policy is converted to '
                '"beitragsfrei" (paid-up) status. The existing value continues to grow '
                '(or fluctuate) based on ETF performance, minus the 1% annual fee. '
                'There is no penalty for stopping contributions. '
                'You can resume contributions at any time. '
                'If you want to fully exit, you can surrender the policy (Rückkauf) '
                'and receive the current value, subject to any applicable charges.'
            ),
        },
        # ── Comparison to alternatives ────────────────────────────────────────
        {
            'category': 'Comparison',
            'question': 'How does this compare to a regular ETF depot?',
            'short': 'The wrapper saves 27.5% KeSt on gains. In return, you pay 4% insurance tax '
                     'on contributions and 1% annual fee vs potentially lower depot fees.',
            'detail': (
                'A regular ETF depot (Wertpapierdepot) is more flexible and may have lower fees '
                '(some brokers offer 0.2–0.5%/year). However, every dividend and realised gain '
                'is taxed at 27.5% KeSt as it occurs. '
                'The froots wrapper defers and eliminates this tax. '
                'For long horizons (15+ years) and higher returns, the KeSt saving typically '
                'outweighs the 4% insurance tax and the fee differential. '
                'For shorter horizons or lower return expectations, a depot may be preferable.'
            ),
        },
        {
            'category': 'Comparison',
            'question': 'How does this compare to a Prämienpension or state pension?',
            'short': 'The froots wrapper is a private supplement to the state pension — it does not '
                     'replace ASVG entitlements.',
            'detail': (
                'The Austrian state pension (ASVG) provides a base level of pension income '
                'linked to employment contributions. The froots wrapper is a private '
                'supplementary pension product. It does not interact with state pension '
                'calculations and is not a Zulagenprodukt (no government top-up subsidy like '
                'the Zukunftsvorsorge). It is purely market-linked and tax-advantaged. '
                'Clients with high state pension exposure should model their total retirement '
                'income including both sources.'
            ),
        },
        # ── Minimum amounts ───────────────────────────────────────────────────
        {
            'category': 'Minimum Amounts',
            'question': f'What is the minimum investment?',
            'short': f'€{MIN_LUMP:,.0f} lump sum or €{MIN_MONTHLY:,.0f}/month recurring contribution.',
            'detail': (
                f'froots accepts a minimum lump sum of €{MIN_LUMP:,.0f} or a minimum monthly '
                f'standing order of €{MIN_MONTHLY:,.0f}. '
                f'Clients can combine both — e.g. an initial lump sum plus ongoing monthly contributions. '
                f'There is no maximum contribution limit imposed by froots '
                f'(insurance regulatory limits may apply at very high amounts).'
            ),
        },
        # ── Insurance partner details ─────────────────────────────────────────
        {
            'category': 'Insurance Partners',
            'question': 'Which insurance company actually holds my policy?',
            'short': 'froots works with Zurich, Donau, Helvetia, Österreichische Beamtenversicherung, '
                     'and Standard Life. The specific partner depends on your profile.',
            'detail': (
                f'The froots pension wrapper is underwritten by one of the following licensed '
                f'Austrian or EU-passported insurers: {PARTNERS}. '
                f'The specific partner is selected based on the client\'s profile and product fit. '
                f'All partners are regulated by the FMA (Finanzmarktaufsicht) and/or '
                f'equivalent EU regulators. Client assets are held separately from froots\'s '
                f'own business assets and are protected under applicable insurance regulation.'
            ),
        },
    ]

    # Search + filter
    search_q = st.text_input('🔍 Search questions', placeholder='e.g. fee, tax, withdraw…')
    all_cats  = sorted(set(q['category'] for q in QA))
    sel_cats  = st.multiselect('Filter by category', all_cats, default=all_cats)

    filtered_qa = [
        q for q in QA
        if q['category'] in sel_cats and (
            not search_q.strip() or
            search_q.lower() in q['question'].lower() or
            search_q.lower() in q['short'].lower() or
            search_q.lower() in q['detail'].lower()
        )
    ]

    st.caption(f'{len(filtered_qa)} of {len(QA)} questions shown')

    for i, q in enumerate(filtered_qa):
        with st.expander(f'**[{q["category"]}]** {q["question"]}'):
            st.markdown(f'**Short answer:** {q["short"]}')
            st.markdown('---')
            st.markdown(f'**Detailed answer:** {q["detail"]}')
            c1, c2 = st.columns(2)
            with c1:
                st.code(q['short'],  language=None)
                st.caption('← Short answer (copy above)')
            with c2:
                st.code(q['detail'], language=None)
                st.caption('← Detailed answer (copy above)')


# ─────────────────────────────────────────────────────────────────────────────
# 7.6  REPORT EXPORT
# ─────────────────────────────────────────────────────────────────────────────
with tab6:
    st.subheader('Report Export')
    st.caption(
        'PDF reports can be generated directly from the **Custom Projection** (tab 7.2) '
        'or **Back-Calculation** (tab 7.4) tabs using the Export PDF button there.\n\n'
        'Use "Save Scenario" in tab 7.2 to store a projection, then export a consolidated '
        'PDF here with optional Q&A appended.'
    )

    saved = st.session_state.get('saved_projection')

    if not saved:
        st.info('No scenario saved yet. Go to **7.2 Custom Projection**, run a calculation, '
                'and click **Save Scenario**.')
    else:
        st.success(f'Saved scenario: **{saved["label"]}**')

        st.markdown('#### Include in report:')
        inc_breakdown = st.checkbox('Fee & tax breakdown', value=True)
        inc_alloc     = st.checkbox('ETF allocation table', value=True)
        inc_qa        = st.checkbox('Append selected Q&A', value=False)

        selected_qa_items = []
        if inc_qa:
            qa_options = [f'[{q["category"]}] {q["question"]}' for q in QA]
            chosen     = st.multiselect('Select Q&A to include', qa_options)
            selected_qa_items = [QA[qa_options.index(c)] for c in chosen]

        if st.button('📄 Generate Consolidated PDF', type='primary'):
            # Build optional sections
            alloc_html = ''
            if inc_alloc:
                rows_html = ''.join(
                    f'<tr><td>{prof}</td>' +
                    ''.join(f'<td>{w}%</td>' for w in weights.values()) +
                    '</tr>'
                    for prof, weights in ETF_WEIGHTS.items()
                )
                etf_headers = ''.join(f'<th>{etf}</th>' for etf in list(ETF_WEIGHTS['Balanced'].keys()))
                alloc_html = f'''
                <h2>ETF Allocation by Risk Profile</h2>
                <table>
                  <thead><tr><th>Profile</th>{etf_headers}</tr></thead>
                  <tbody>{rows_html}</tbody>
                </table>'''

            qa_html = ''
            if selected_qa_items:
                qa_rows = ''.join(
                    f'<h3>[{q["category"]}] {q["question"]}</h3>'
                    f'<p><strong>Short:</strong> {q["short"]}</p>'
                    f'<p>{q["detail"]}</p>'
                    for q in selected_qa_items
                )
                qa_html = f'<h2>Client Q&A</h2>{qa_rows}'

            pdf = _build_projection_pdf(
                mode=saved['mode'],
                scenario_label=saved['label'],
                principal_or_monthly=saved['principal'],
                r=saved['r'], years=saved['years'],
                froots_net=saved['f_net'], froots_fees=saved['f_fees'],
                froots_tax=saved['f_tax'],
                classic_net=saved['c_net'], classic_fees=saved['c_fees'],
                classic_tax=saved['c_tax'],
                total_invested=saved['total_invested'],
                extra_sections=alloc_html + qa_html,
            )

            if pdf:
                st.download_button(
                    '⬇️ Download Consolidated PDF',
                    data=pdf,
                    file_name='froots_pension_report.pdf',
                    mime='application/pdf',
                    key='dl_consolidated_pdf',
                )
            else:
                st.error('WeasyPrint not available — install it and system dependencies.')
