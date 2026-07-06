"""
Freox — all-in-one live FX cockpit.

Single-screen command center (no tabs), trading-terminal styling:
  • KPI strip      — strongest/weakest ccy, next high-impact event, breadth
  • Strength bar   — 8-currency relative strength
  • Pair Monitor   — live price, daily Δ, multi-timeframe trend arrows
  • Trend Heatmap  — pairs × timeframes grid
  • News feed      — this week's economic calendar w/ live countdown

Data: Yahoo Finance (prices) + Forex Factory (calendar). No API keys.
Run:  bash launch.sh   (or: streamlit run app.py)
"""
from __future__ import annotations

from urllib.parse import quote_plus

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_feed as d
import indicators as ind

# ---------------------------------------------------------------------------
# Cached data wrappers
# ---------------------------------------------------------------------------
import concurrent.futures as _cf


@st.cache_data(ttl=45, show_spinner=False)
def gather_pairs(watch, tfs):
    """Fetch quote + multi-TF trend + ATR for every pair IN PARALLEL.

    One cache entry for the whole watchlist, so 30+ pairs load in a few
    seconds instead of tens. Threads call the plain (non-Streamlit) data
    functions, which is thread-safe.
    """
    def one(p):
        return p, {
            "quote": d.get_quote(p),
            "trend": ind.multi_tf_trend(p, tfs),
            "atr": ind.atr_volatility(p, "D1"),
        }

    out = {}
    with _cf.ThreadPoolExecutor(max_workers=12) as ex:
        for p, data in ex.map(one, watch):
            out[p] = data
    return out


@st.cache_data(ttl=30, show_spinner=False)
def c_strength(period):
    return ind.currency_strength(period)


@st.cache_data(ttl=1800, show_spinner=False)
def c_calendar():
    return d.get_calendar()


# ---------------------------------------------------------------------------
# Palette (trading terminal)
# ---------------------------------------------------------------------------
BG      = "#07090d"
PANEL   = "#0d1017"
BORDER  = "#1b2230"
UP      = "#00e28a"   # neon green
UP_DIM  = "#0a7d52"
DOWN    = "#ff3b5c"   # neon red
DOWN_DIM= "#a01730"
AMBER   = "#ffb020"
INK     = "#d7dde8"
MUT     = "#6b7688"

st.set_page_config(page_title="FREOX ▮ FX Cockpit", page_icon="💹",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""<style>
  header[data-testid="stHeader"]{{display:none!important;}}
  #MainMenu,footer{{visibility:hidden;height:0;}}
  .stApp{{background:{BG};}}
  .block-container{{padding:.6rem .9rem 0 .9rem!important;max-width:100%!important;}}
  section[data-testid="stSidebar"]{{background:{PANEL};border-right:1px solid {BORDER};}}
  * {{font-variant-numeric:tabular-nums;}}
  code,.mono{{font-family:'JetBrains Mono','SFMono-Regular',Consolas,monospace;}}

  /* panels */
  .panel{{background:{PANEL};border:1px solid {BORDER};border-radius:8px;
          padding:.5rem .65rem;margin-bottom:.55rem;}}
  .panel h4{{margin:0 0 .4rem 0;color:{MUT};font:600 11px/1 'JetBrains Mono',monospace;
             letter-spacing:.16em;text-transform:uppercase;}}

  /* header */
  .hdr{{display:flex;align-items:center;gap:.8rem;padding:.15rem .1rem .5rem;}}
  .logo{{font:800 20px/1 'JetBrains Mono',monospace;color:{INK};letter-spacing:.28em;}}
  .logo b{{color:{UP};}}
  .live{{display:inline-flex;align-items:center;gap:.4rem;color:{UP};
         font:700 11px/1 'JetBrains Mono',monospace;letter-spacing:.14em;}}
  .dot{{width:8px;height:8px;border-radius:50%;background:{UP};
        box-shadow:0 0 8px {UP};animation:pulse 1.6s infinite;}}
  @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:.35;}}}}
  .clock{{margin-left:auto;color:{MUT};font:600 12px/1 'JetBrains Mono',monospace;
          letter-spacing:.1em;}}

  /* KPI tiles */
  .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:.55rem;margin-bottom:.55rem;}}
  .kpi{{background:{PANEL};border:1px solid {BORDER};border-radius:8px;padding:.5rem .7rem;}}
  .kpi .lab{{color:{MUT};font:600 10px/1.2 'JetBrains Mono',monospace;
             letter-spacing:.14em;text-transform:uppercase;}}
  .kpi .val{{font:800 22px/1.25 'JetBrains Mono',monospace;margin-top:.15rem;}}
  .kpi .sub{{color:{MUT};font:500 11px/1.2 'JetBrains Mono',monospace;}}

  /* monitor table */
  table.term{{width:100%;border-collapse:collapse;
              font:600 13px/1 'JetBrains Mono',monospace;}}
  table.term th{{color:{MUT};font:600 10px/1 'JetBrains Mono',monospace;
                 letter-spacing:.12em;text-align:right;padding:.35rem .5rem;
                 border-bottom:1px solid {BORDER};text-transform:uppercase;}}
  table.term th:first-child{{text-align:left;}}
  table.term td{{padding:.42rem .5rem;text-align:right;border-bottom:1px solid #12171f;
                 color:{INK};}}
  table.term td:first-child{{text-align:left;color:{INK};font-weight:700;letter-spacing:.05em;}}
  table.term tr:hover td{{background:#111722;}}

  /* news feed */
  .feed{{max-height:520px;overflow-y:auto;}}
  .nrow{{display:grid;grid-template-columns:52px 40px 1fr auto;gap:.5rem;
         align-items:center;padding:.4rem .3rem;border-bottom:1px solid #12171f;
         font:600 12px/1.25 'JetBrains Mono',monospace;}}
  .nrow .t{{color:{MUT};}}
  .badge{{display:inline-block;padding:.1rem .3rem;border-radius:4px;font-size:10px;
          font-weight:800;text-align:center;letter-spacing:.05em;
          background:#14202e;color:{INK};border:1px solid {BORDER};}}
  .nrow .ev{{color:{INK};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .nrow .ev a{{color:{INK};text-decoration:none;}}
  .nrow .ev a:hover{{color:{UP};text-decoration:underline;}}
  .nrow .cd{{color:{MUT};font-size:11px;text-align:right;}}
  .nrow.next{{background:linear-gradient(90deg,#10261c,transparent);
              border-left:2px solid {UP};}}
  .feed::-webkit-scrollbar{{width:7px;}} .feed::-webkit-scrollbar-track{{background:{PANEL};}}
  .feed::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:4px;}}

  /* watchlist popover trigger — match the terminal look */
  [data-testid="stPopover"] button{{background:{PANEL}!important;border:1px solid {BORDER}!important;
    color:{INK}!important;font:700 12px/1 'JetBrains Mono',monospace!important;
    letter-spacing:.1em;}}
  [data-testid="stPopover"] button:hover{{border-color:{UP}!important;color:{UP}!important;}}

  /* ── stop the auto-refresh dim/flicker ── */
  [data-stale="true"]{{opacity:1!important;transition:none!important;filter:none!important;}}
  .element-container,.stPlotlyChart{{transition:none!important;}}
  div[data-testid="stStatusWidget"]{{display:none!important;}}
  div[data-testid="stSpinner"]{{display:none!important;}}
  .stApp [data-testid="stAppViewBlockContainer"]{{opacity:1!important;}}
</style>""", unsafe_allow_html=True)

TF_ALL = ["M15", "H1", "H4", "D1"]
EXTRA = ["XAUUSD", "BTCUSD"]
MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
# Minor pairs = the major crosses (no USD leg).
MINOR_PAIRS = [p for p in d.PAIRS_28 if p not in MAJOR_PAIRS]
ALL_SYMBOLS = d.PAIRS_28 + EXTRA
# Default: majors, then minors, then gold + BTC pinned to the bottom.
DEFAULT_WATCH = MAJOR_PAIRS + MINOR_PAIRS + EXTRA
IMPACT_DOT = {"High": DOWN, "Medium": AMBER, "Low": "#4a90d9", "Holiday": MUT}
ARROW_COL = {"▲▲": UP, "▲": UP_DIM, "▼": DOWN_DIM, "▼▼": DOWN, "·": MUT}

# ---------------------------------------------------------------------------
# Sidebar (controls only — cockpit stays clean)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### CONTROLS")
    st.caption("Pairs are chosen from the **Watchlist** button up top.")
    tfs = st.multiselect("Timeframes", TF_ALL, default=TF_ALL, key="tfs_sel")
    tfs = [t for t in TF_ALL if t in tfs] or TF_ALL

    strength_period = st.selectbox("Strength window", ["24H", "1D", "1W"],
                                   index=0, key="strength_period")
    refresh_lbl = st.selectbox("Auto-refresh", ["Off", "15s", "30s", "60s"],
                               index=2, key="refresh_lbl")
    news_impacts = st.multiselect("News impact", ["High", "Medium", "Low", "Holiday"],
                                  default=["High", "Medium"], key="news_impacts")
    if st.button("Force refresh", width="stretch"):
        st.cache_data.clear(); st.rerun()

_REFRESH = {"Off": None, "15s": 15, "30s": 30, "60s": 60}[refresh_lbl]

# Persist watchlist checkbox state once; survives every auto-refresh rerun.
for _p in ALL_SYMBOLS:
    st.session_state.setdefault(f"w_{_p}", _p in DEFAULT_WATCH)


def _fmt_price(p):
    return "—" if p is None else (f"{p:,.3f}" if p >= 20 else f"{p:.5f}")


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Renderers (return HTML)
# ---------------------------------------------------------------------------
def _vol_color(pct):
    """Color the ATR% by how hot the instrument is running."""
    if pct is None:
        return MUT
    if pct >= 1.0:
        return DOWN          # very volatile
    if pct >= 0.7:
        return AMBER         # elevated
    if pct >= 0.4:
        return INK           # normal
    return MUT               # quiet


def _vol_fmt(pair, vol):
    """Volatility in the instrument's natural unit: pips (FX), points (gold),
    dollars (BTC)."""
    a = vol.get("atr")
    if a is None:
        return "—"
    if pair == "BTCUSD":
        return f"{a/1000:.1f}k" if a >= 1000 else f"{a:.0f}"
    if pair == "XAUUSD":
        return f"{a:.0f}pt"
    return f'{vol["pips"]:.0f}p'


def watchlist_picker():
    """Grouped checkboxes to add/remove instruments. Returns the selected list
    (in ALL_SYMBOLS order). State lives in session_state, so it survives refreshes."""
    st.markdown("**Select instruments to monitor**")
    qa = st.columns(3)
    if qa[0].button("Select all", key="wl_all", width="stretch"):
        for p in ALL_SYMBOLS:
            st.session_state[f"w_{p}"] = True
        st.rerun()
    if qa[1].button("Majors + XAU/BTC", key="wl_maj", width="stretch"):
        for p in ALL_SYMBOLS:
            st.session_state[f"w_{p}"] = p in MAJOR_PAIRS + EXTRA
        st.rerun()
    if qa[2].button("Clear", key="wl_clr", width="stretch"):
        for p in ALL_SYMBOLS:
            st.session_state[f"w_{p}"] = False
        st.rerun()

    groups = [("Majors", MAJOR_PAIRS), ("Minors", MINOR_PAIRS[:11]),
              ("Minors", MINOR_PAIRS[11:]), ("Metal / Crypto", EXTRA)]
    cols = st.columns(4)
    for col, (name, plist) in zip(cols, groups):
        with col:
            st.caption(name)
            for p in plist:
                st.checkbox(p, key=f"w_{p}")
    return [p for p in ALL_SYMBOLS if st.session_state.get(f"w_{p}")]


def order_pairs(pairs, quotes, trends, atrs, sort_by, desc):
    """Return `pairs` sorted per the monitor sort control (None sinks to bottom)."""
    if sort_by == "Default":
        return pairs

    def metric(p):
        if sort_by == "Day %":
            v = quotes[p]["change_pct"]
        elif sort_by == "Vol":
            v = atrs[p]["pct"]
        else:  # a timeframe → trend score
            v = trends[p].get(sort_by, {}).get("score")
        return float("-inf") if v is None else v

    return sorted(pairs, key=metric, reverse=desc)


def monitor_table(pairs, quotes, trends, atrs):
    head = "".join(f"<th>{t}</th>" for t in tfs)
    body = ""
    for p in pairs:
        q, tr, vol = quotes[p], trends[p], atrs[p]
        chg = q["change_pct"]
        cc = UP if (chg or 0) >= 0 else DOWN
        chg_txt = "—" if chg is None else f"{chg:+.2f}%"
        vcol = _vol_color(vol["pct"])
        cells = ""
        for t in tfs:
            a = tr[t]["arrow"]
            cells += f'<td style="color:{ARROW_COL.get(a,MUT)};font-size:15px">{a}</td>'
        body += (f'<tr><td>{p}</td>'
                 f'<td style="color:{cc}">{chg_txt}</td>'
                 f'<td style="color:{vcol}" title="Avg daily range (ATR-14)">'
                 f'{_vol_fmt(p, vol)}</td>{cells}</tr>')
    return (f'<table class="term"><thead><tr><th>Pair</th>'
            f'<th>Δ Day</th><th>Vol/D</th>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table>')


def news_feed(cal, now):
    if cal.empty:
        return (f'<div style="color:{AMBER};font:600 12px/1.5 monospace;padding:.4rem">'
                f'⚠ Calendar temporarily unavailable<br>'
                f'<span style="color:{MUT};font-weight:500">source rate-limited — '
                f'auto-retries on the next refresh</span></div>')
    stale = cal.attrs.get("stale", False)
    total = len(cal)
    cal = cal[cal["impact"].isin(news_impacts)].copy()
    # keep from 2h ago onward so "just happened" stays visible
    cal = cal[cal["time"] >= now - pd.Timedelta(hours=2)]
    if cal.empty:
        return (f'<div style="color:{MUT};font:600 12px/1.5 monospace;padding:.4rem">'
                f'No {"/".join(news_impacts)} events left this week '
                f'({total} total loaded).<br>Add "Low" in the sidebar to see more.</div>')
    upcoming = cal[cal["time"] >= now]
    next_idx = upcoming.index[0] if not upcoming.empty else None
    banner = ""
    if stale:
        banner = (f'<div style="color:{MUT};font:500 10px/1.3 monospace;'
                  f'padding:0 .3rem .3rem">cached copy (live source rate-limited)</div>')
    rows = ""
    for i, ev in cal.iterrows():
        dot = IMPACT_DOT.get(ev["impact"], MUT)
        cd = _countdown(ev["time"], now)
        nxt = " next" if i == next_idx else ""
        link = ("https://www.google.com/search?tbm=nws&q=" +
                quote_plus(f'{ev["currency"]} {ev["title"]}'))
        rows += (
            f'<div class="nrow{nxt}">'
            f'<span class="t">{ev["time"]:%a %H:%M}</span>'
            f'<span class="badge">{_esc(ev["currency"])}</span>'
            f'<span class="ev"><span style="color:{dot}">&#9679;</span> '
            f'<a href="{link}" target="_blank" rel="noopener">'
            f'{_esc(ev["title"])} ↗</a></span>'
            f'<span class="cd">{cd}</span></div>')
    return f'{banner}<div class="feed">{rows}</div>'


def _countdown(t, now):
    s = (t - now).total_seconds()
    if s < -3600:
        return "done"
    if s < 0:
        return "now"
    h, m = int(s // 3600), int((s % 3600) // 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def strength_fig(s):
    colors = [UP if v >= 0 else DOWN for v in s.values]
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h", marker_color=colors,
        text=[f"{v:+.2f}" for v in s.values], textposition="outside",
        textfont=dict(family="JetBrains Mono", size=11, color=INK)))
    fig.update_layout(
        height=250, template="plotly_dark", dragmode=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=6, r=30, t=6, b=6),
        yaxis=dict(autorange="reversed", fixedrange=True),
        font=dict(family="JetBrains Mono", color=MUT, size=11),
        xaxis=dict(gridcolor=BORDER, zerolinecolor=MUT, fixedrange=True))
    return fig


def heatmap_fig(pairs, trends):
    z = [[trends[p][t]["score"] for t in tfs] for p in pairs]
    txt = [[trends[p][t]["arrow"] for t in tfs] for p in pairs]
    fig = go.Figure(go.Heatmap(
        z=z, x=tfs, y=pairs, text=txt, texttemplate="%{text}",
        textfont={"size": 15, "family": "JetBrains Mono"},
        zmid=0, zmin=-2, zmax=2, showscale=False, xgap=4, ygap=4,
        colorscale=[[0, DOWN], [0.25, DOWN_DIM], [0.5, "#202632"],
                    [0.75, UP_DIM], [1, UP]]))
    fig.update_layout(
        height=max(250, 34 * len(pairs) + 40), template="plotly_dark", dragmode=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=6, r=6, t=22, b=6),
        yaxis=dict(autorange="reversed", fixedrange=True),
        xaxis=dict(fixedrange=True, side="top"),
        font=dict(family="JetBrains Mono", color=MUT, size=11))
    return fig


def kpi_strip(pairs, strength, trends, cal, now):
    strong, weak = strength.index[0], strength.index[-1]
    # breadth: share of (pair,tf) cells trending up
    cells = [trends[p][t]["score"] for p in pairs for t in tfs]
    up = sum(1 for c in cells if c > 0)
    breadth = f"{up}/{len(cells)}"
    bcol = UP if up * 2 >= len(cells) else DOWN
    # next high-impact
    hi = cal[(cal["impact"] == "High") & (cal["time"] >= now)] if not cal.empty else pd.DataFrame()
    if not hi.empty:
        nh = hi.iloc[0]
        nh_val = f'{nh["currency"]} {_countdown(nh["time"], now)}'
        nh_sub = _esc(nh["title"])[:26]
    else:
        nh_val, nh_sub = "—", "no high-impact ahead"
    tiles = [
        ("Strongest", strong, f'{strength.iloc[0]:+.2f}', UP),
        ("Weakest", weak, f'{strength.iloc[-1]:+.2f}', DOWN),
        ("Trend breadth", breadth, "cells up", bcol),
        ("Next high-impact", nh_val, nh_sub, AMBER),
    ]
    html = '<div class="kpis">'
    for lab, val, sub, col in tiles:
        html += (f'<div class="kpi"><div class="lab">{lab}</div>'
                 f'<div class="val" style="color:{col}">{_esc(val)}</div>'
                 f'<div class="sub">{_esc(sub)}</div></div>')
    return html + "</div>"


# ---------------------------------------------------------------------------
# The cockpit (one fragment → all panels refresh together)
# ---------------------------------------------------------------------------
@st.fragment(run_every=_REFRESH)
def cockpit():
    now = d.now_utc()
    rlabel = "auto-refresh off" if _REFRESH is None else f"every {refresh_lbl}"

    # top bar: logo/live | Watchlist popover | LAST UPDATED time
    hL, hMid, hR = st.columns([5, 2, 5], gap="small", vertical_alignment="center")
    with hL:
        st.markdown(
            f'<div class="hdr"><span class="logo">FRE<b>O</b>X</span>'
            f'<span class="live"><span class="dot"></span>{rlabel.upper()}</span></div>',
            unsafe_allow_html=True)
    with hMid:
        with st.popover("☰ Watchlist", width="stretch"):
            watch = watchlist_picker()
    with hR:
        st.markdown(
            f'<div class="clock" style="text-align:right;padding-top:.4rem">'
            f'LAST UPDATED&nbsp; {now:%Y-%m-%d %H:%M:%S} UTC</div>',
            unsafe_allow_html=True)

    if not watch:
        st.warning("No instruments selected — open **☰ Watchlist** and pick some.")
        return

    data = gather_pairs(tuple(watch), tuple(tfs))
    quotes = {p: data[p]["quote"] for p in watch}
    trends = {p: data[p]["trend"] for p in watch}
    atrs = {p: data[p]["atr"] for p in watch}
    strength = c_strength(strength_period)
    cal = c_calendar()

    # KPI strip
    st.markdown(kpi_strip(watch, strength, trends, cal, now), unsafe_allow_html=True)

    # main grid: [monitor+strength] | [heatmap] | [news]
    left, mid, right = st.columns([5, 4, 3], gap="small")

    _STATIC = {"displayModeBar": False, "staticPlot": True, "scrollZoom": False}

    with left:
        # title box — centered title + the Vol/D legend inside it
        st.markdown(
            f'<div class="panel" style="margin-bottom:.3rem">'
            f'<h4 style="text-align:center">Pair Monitor</h4>'
            f'<div style="color:{MUT};font:500 10px/1.4 monospace;text-align:center">'
            f'Vol/D = avg daily range (ATR-14): pips · pt gold · $ btc · '
            f'<span style="color:{DOWN}">■</span> wild '
            f'<span style="color:{AMBER}">■</span> elevated '
            f'<span style="color:{INK}">■</span> normal '
            f'<span style="color:{MUT}">■</span> quiet</div></div>',
            unsafe_allow_html=True)
        sc1, sc2 = st.columns([3, 2], gap="small")
        sort_by = sc1.selectbox("Sort by", ["Default", "Day %", "Vol"] + tfs,
                                index=0, key="sort_by")
        sort_desc = sc2.radio("Order", ["High→Low", "Low→High"], index=0,
                              horizontal=True, key="sort_order") == "High→Low"
        ordered = order_pairs(watch, quotes, trends, atrs, sort_by, sort_desc)

        st.markdown('<div class="panel">' +
                    monitor_table(ordered, quotes, trends, atrs) + '</div>',
                    unsafe_allow_html=True)

    with mid:
        strong, weak = strength.index[0], strength.index[-1]
        st.markdown(
            f'<div class="panel"><h4 style="text-align:center">Trend Heatmap · pair × TF</h4>'
            f'<div style="color:{INK};font:600 12px/1.5 monospace;text-align:center">'
            f'▸ Cleanest bias: <span style="color:{UP}">LONG {strong}</span> / '
            f'<span style="color:{DOWN}">SHORT {weak}</span><br>'
            f'<span style="color:{MUT}">strongest vs weakest currency — '
            f'look for the pair that is {strong}{weak} or {weak}{strong}</span></div></div>',
            unsafe_allow_html=True)
        st.plotly_chart(heatmap_fig(ordered, trends), width="stretch", config=_STATIC)

    with right:
        st.markdown('<div class="panel"><h4>📰 Economic Calendar</h4>' +
                    news_feed(cal, now) + '</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="panel"><h4>Currency Strength · {strength_period}</h4></div>',
                    unsafe_allow_html=True)
        st.plotly_chart(strength_fig(strength), width="stretch", config=_STATIC)

    # data-source disclaimer (accuracy honesty)
    st.markdown(
        f'<div style="color:{MUT};font:500 10px/1.5 monospace;'
        f'border-top:1px solid {BORDER};padding-top:.4rem;margin-top:.2rem">'
        f'DATA · Prices: Yahoo Finance indicative mid quotes — near-real-time, '
        f'may differ from your broker, not for execution. '
        f'Calendar: Forex Factory. Strength/trend/vol computed locally. '
        f'All times UTC.</div>', unsafe_allow_html=True)


cockpit()
