"""
Freox — all-in-one live FX cockpit.

Single-screen command center (no tabs), trading-terminal styling:
  • KPI strip      — strongest/weakest ccy, next high-impact event, breadth
  • Strength bar   — 8-currency relative strength
  • Pair Monitor   — live price, daily Δ, multi-timeframe trend arrows
  • Vol Heatmap    — pairs × timeframes, how hot each is running right now
  • News feed      — this week's economic calendar w/ live countdown

Data: Yahoo Finance (prices) + Forex Factory (calendar). No API keys.
Run:  bash phone.sh   (or: streamlit run app.py)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import data_feed as d
import indicators as ind
import sessions as sess

# ---------------------------------------------------------------------------
# Cached data wrappers
# ---------------------------------------------------------------------------
import concurrent.futures as _cf


@st.cache_data(ttl=5, show_spinner=False)   # 5s so numbers stay live-market fresh
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
            "heat": ind.multi_tf_heat(p, tfs),   # per-TF activity for the vol heatmap
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


CORR_WINDOW = 34   # daily returns (Fibonacci ~7 weeks) — recent correlation
CORR_MAX = 12      # cap displayed pairs so the matrix stays readable


@st.cache_data(ttl=300, show_spinner=False)
def c_correlation(watch, window=CORR_WINDOW):
    """Pairwise correlation of the last `window` DAILY returns across `watch`.
    Slow-moving, so cached 5 min. Returns a pairs×pairs DataFrame, or None."""
    closes = {}
    for p in watch:
        df = d.get_ohlc_tf(p, "D1")
        if not df.empty and len(df) > 2:
            closes[p] = df["close"]
    if len(closes) < 2:
        return None
    rets = pd.DataFrame(closes).pct_change().tail(window)
    return rets.corr()


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

VERSION = "0.5"   # beta — bump on each release
GITHUB_URL = "https://github.com/Spoofkapoof/freox"
GITHUB_HTML = (
    f'<a class="ghlink" href="{GITHUB_URL}" target="_blank" rel="noopener"'
    ' title="View Freox on GitHub" aria-label="Freox on GitHub">'
    '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" '
    'd="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19'
    '-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15'
    '-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87'
    '.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08'
    '-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 '
    '2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75'
    '-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 '
    '8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg></a>'
)

# ── display time zone (⚙ setting) ──────────────────────────────────────────
# Purely a DISPLAY conversion: the session clock/now-line + calendar times are
# shown in the chosen zone. All the underlying logic (which session is open,
# countdowns) stays UTC-correct. "Local" = the machine running the server.
TZ_OPTIONS = {
    "Local":    None,                 # this device's own zone
    "UTC":      "UTC",
    "New York": "America/New_York",   # US session / FX-day rollover
    "London":   "Europe/London",      # biggest FX session (GMT/BST)
    "Beijing":  "Asia/Shanghai",      # China Standard Time (UTC+8)
}


def _resolve_tz(name):
    """tzinfo for a TZ_OPTIONS label ('Local' → the machine's own zone)."""
    iana = TZ_OPTIONS.get(name)
    if iana is None:
        return datetime.now().astimezone().tzinfo
    return ZoneInfo(iana)


def _tz_label(name, tz):
    """Short label like 'New York (UTC-4)' for the data footer."""
    off = datetime.now(tz).utcoffset() or timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    hh, mm = divmod(abs(mins), 60)
    tag = f"UTC{sign}{hh}" + (f":{mm:02d}" if mm else "")
    return f"{name} · {tag}"

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

  /* soften the 30s auto-refresh: fade each window in from ~55% opacity instead
     of a hard flicker when the fragment repaints. One keyframe, no JS. Charts
     live inside these containers, so the whole window fades as one block. */
  @keyframes freoxFade{{from{{opacity:.55;}}to{{opacity:1;}}}}
  div[data-testid="stVerticalBlockBorderWrapper"],.kpis{{
     animation:freoxFade .35s ease-out;}}
  @media (prefers-reduced-motion:reduce){{
     div[data-testid="stVerticalBlockBorderWrapper"],.kpis{{animation:none;}}}}

  /* panels */
  .panel{{background:{PANEL};border:1px solid {BORDER};border-radius:8px;
          padding:.5rem .65rem;margin-bottom:.55rem;}}
  .panel h4{{margin:0 0 .4rem 0;color:{MUT};font:600 11px/1 'JetBrains Mono',monospace;
             letter-spacing:.16em;text-transform:uppercase;}}

  /* window box: a Streamlit bordered container styled as a terminal panel —
     lets widgets (sort controls) live in the SAME box as the title + table */
  div[data-testid="stVerticalBlockBorderWrapper"]{{background:{PANEL};
      border:1px solid {BORDER}!important;border-radius:8px;margin-bottom:.55rem;}}
  .wtitle{{margin:.1rem 0 .5rem 0;color:{MUT};font:600 11px/1 'JetBrains Mono',monospace;
           letter-spacing:.16em;text-transform:uppercase;text-align:center;}}

  /* header */
  .hdr{{display:flex;align-items:center;gap:.7rem;padding:.15rem .1rem;}}
  .logo{{font:800 20px/1.3 'JetBrains Mono',monospace;color:{INK};letter-spacing:.28em;}}
  .logo b{{color:{UP};}}
  .live{{display:inline-flex;align-items:center;gap:.4rem;color:{UP};
         font:700 11px/1 'JetBrains Mono',monospace;letter-spacing:.14em;}}
  .beta{{color:#ff8c00;border:1px solid #ff8c00;border-radius:4px;padding:.12rem .35rem;
         font:700 9px/1 'JetBrains Mono',monospace;letter-spacing:.12em;}}
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

  /* volatility heatmap (HTML cells → no canvas repaint, no flicker) */
  table.heat{{width:100%;border-collapse:separate;border-spacing:3px;
              margin-top:.35rem;font:700 12px/1 'JetBrains Mono',monospace;}}
  table.heat th{{color:{MUT};font:600 10px/1 'JetBrains Mono',monospace;
                 letter-spacing:.1em;padding:.15rem 0 .3rem;text-align:center;}}
  table.heat td{{text-align:center;padding:.55rem .2rem;border-radius:4px;
                 color:#eef2f8;text-shadow:0 1px 2px rgba(0,0,0,.55);
                 transition:background .3s ease;}}
  table.heat td.pl{{text-align:left;background:transparent!important;color:{INK};
                    font-weight:700;letter-spacing:.04em;text-shadow:none;
                    width:76px;padding-left:.1rem;}}
  /* correlation matrix: many narrow columns → smaller, tighter cells */
  table.corr{{font-size:11px;}}
  table.corr th{{font-size:9px;letter-spacing:.02em;}}
  table.corr td{{padding:.42rem .1rem;}}
  table.corr td.pl{{width:60px;font-size:11px;}}

  /* news feed */
  .feed{{overflow:visible;}}  /* no inner scroll — the 10 rows size the panel */
  /* whole row is one clickable link */
  a.nrow{{display:grid;grid-template-columns:52px 40px 1fr auto;gap:.5rem;
         align-items:center;padding:.4rem .3rem;border-bottom:1px solid #12171f;
         font:600 12px/1.25 'JetBrains Mono',monospace;
         text-decoration:none;color:inherit;cursor:pointer;
         border-radius:4px;transition:background .1s;}}
  a.nrow:hover{{background:#141b26;}}
  a.nrow:hover .ev{{color:{UP};}}
  .nrow .t{{color:{MUT};}}
  .badge{{display:inline-block;padding:.1rem .3rem;border-radius:4px;font-size:10px;
          font-weight:800;text-align:center;letter-spacing:.05em;
          background:#14202e;color:{INK};border:1px solid {BORDER};}}
  .nrow .ev{{color:{INK};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
  .nrow .cd{{color:{MUT};font-size:11px;text-align:right;}}
  .nrow.next{{background:linear-gradient(90deg,#10261c,transparent);
              border-left:2px solid {UP};}}
  .feed::-webkit-scrollbar{{width:7px;}} .feed::-webkit-scrollbar-track{{background:{PANEL};}}
  .feed::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:4px;}}

  /* Watchlist popover trigger — match the terminal look */
  [data-testid="stPopover"] button{{background:{PANEL}!important;border:1px solid {BORDER}!important;
    color:{INK}!important;font:700 12px/1 'JetBrains Mono',monospace!important;
    letter-spacing:.1em;}}
  [data-testid="stPopover"] button:hover{{border-color:{UP}!important;color:{UP}!important;}}
  /* FX session bar */
  .sessbar{{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap;
            background:{PANEL};border:1px solid {BORDER};border-radius:8px;
            padding:.34rem .6rem;margin-bottom:.55rem;
            font:600 11px/1 'JetBrains Mono',monospace;}}
  .sess{{padding:.28rem .55rem;border-radius:5px;letter-spacing:.09em;
         border:1px solid {BORDER};color:{MUT};text-transform:uppercase;}}
  .sess.on{{color:{BG};background:{UP};border-color:{UP};font-weight:800;
            box-shadow:0 0 8px rgba(0,226,138,.35);}}
  .sess-note{{margin-left:.35rem;letter-spacing:.04em;}}
  .sess-next{{margin-left:auto;color:{MUT};letter-spacing:.04em;}}

  /* GitHub repo link — styled to match the popover buttons, sits next to ⚙ */
  .ghlink{{display:flex;align-items:center;justify-content:center;height:38px;width:100%;
           color:{MUT};background:{PANEL};border:1px solid {BORDER};border-radius:8px;
           text-decoration:none;transition:border-color .12s,color .12s;}}
  .ghlink:hover{{color:{UP};border-color:{UP};}}
  .ghlink svg{{width:18px;height:18px;display:block;}}
  /* keep the header GitHub / ⚙ / Watchlist row in ONE line — don't let it
     stack vertically on narrow (phone) screens like Streamlit columns do. */
  .st-key-hdrbtns [data-testid="stHorizontalBlock"]{{flex-wrap:nowrap!important;gap:.5rem!important;}}
  .st-key-hdrbtns [data-testid="stColumn"]{{min-width:0!important;flex:1 1 auto!important;}}

  /* ── phone single scroll pane (?view=phone): the windows scroll under the
     locked top; the full-height flex wiring is injected only in phone view ── */
  .st-key-pscroll{{overflow-y:auto;-webkit-overflow-scrolling:touch;}}
  .st-key-pscroll::-webkit-scrollbar{{width:5px;}}
  .st-key-pscroll::-webkit-scrollbar-thumb{{background:{BORDER};border-radius:3px;}}

  /* ── FX session timeline (phone locked-top): bars on a 0–24 UTC axis ── */
  .stl{{background:{PANEL};border:1px solid {BORDER};border-radius:8px;
        padding:.4rem .6rem .45rem;margin-bottom:.4rem;
        font:600 10px/1 'JetBrains Mono',monospace;}}
  /* label(78) == axis margin == now-line base → everything lines up exactly */
  .stl-axis{{position:relative;height:11px;margin-left:78px;color:{MUT};font-size:9px;}}
  .stl-axis span{{position:absolute;transform:translateX(-50%);}}
  .stl-body{{position:relative;}}
  .srow{{display:flex;align-items:center;gap:0;height:15px;margin:2.5px 0;}}
  .slbl{{flex:0 0 78px;color:{INK};font-size:9px;white-space:nowrap;overflow:hidden;
         letter-spacing:.01em;padding-right:4px;}}
  .strack{{position:relative;flex:1;height:11px;background:#0a0d12;
           border:1px solid #12171f;border-radius:3px;}}
  .sbar{{position:absolute;top:0;bottom:0;border-radius:2px;}}
  .sbar.on{{background:{UP};box-shadow:0 0 6px rgba(0,226,138,.45);}}
  .sbar.off{{background:#2a3547;}}
  /* single continuous 'now' line spanning ONLY the session rows */
  .stl-nowline{{position:absolute;top:0;bottom:0;width:2px;background:{AMBER};
         box-shadow:0 0 5px {AMBER};z-index:4;pointer-events:none;border-radius:1px;}}
  .stl-status{{margin:0 0 .4rem;font-size:11px;letter-spacing:.02em;font-weight:700;}}
  /* labels inside the merged top box (news/movers/market) — uppercase like before */
  .stl .lab{{color:{MUT};font:600 9px/1.3 'JetBrains Mono',monospace;
             letter-spacing:.1em;text-transform:uppercase;}}
  /* Market Activity — one compact line */
  .stl-mkt{{margin-top:.4rem;padding-top:.35rem;border-top:1px solid {BORDER};
            font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
  /* News + Movers sub-section, divided from Market Activity */
  .stl-nm{{margin-top:.4rem;padding-top:.4rem;border-top:1px solid {BORDER};}}
  /* Centre the Watchlist dropdown on screen. The button is already page-centred,
     so centring the panel on the viewport aligns it under the button — no width
     math, no per-pixel guessing. Full-override of floating-ui's positioning. */
  [data-testid="stPopoverBody"]{{
    position:fixed!important;
    left:50%!important; right:auto!important; top:64px!important;
    transform:translateX(-50%)!important;
    max-height:80vh;overflow-y:auto;
  }}

  /* ── stop the auto-refresh dim/flicker ── */
  [data-stale="true"]{{opacity:1!important;transition:none!important;filter:none!important;}}
  .element-container,.stPlotlyChart{{transition:none!important;}}
  div[data-testid="stStatusWidget"]{{display:none!important;}}
  div[data-testid="stSpinner"]{{display:none!important;}}
  .stApp [data-testid="stAppViewBlockContainer"]{{opacity:1!important;}}

  /* ── phone-cockpit sizing — the ONE layout, applied on every screen so the
     PC (centred phone-width column) looks exactly like the phone ── */
  .block-container{{padding:.4rem .5rem 0!important;}}
  .kpis{{grid-template-columns:1fr!important;gap:.4rem;}}   /* stack KPI tiles */
  .kpi .val{{font-size:18px;}}
  .logo{{font-size:16px;letter-spacing:.16em;}}
  .clock{{font-size:11px;}}
  .sessbar{{font-size:10px;}}
  /* wide tables scroll sideways inside their box instead of squishing */
  .scrollx{{overflow-x:auto;-webkit-overflow-scrolling:touch;}}
  table.term{{font-size:12px;}} table.term th,table.term td{{padding:.4rem .35rem;}}
  table.corr{{min-width:520px;}}       /* force horizontal scroll */
</style>""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Number "roll" animation. Streamlit strips <script> from st.markdown, and a
# components.html iframe is torn down on every rerun — so we inject a script
# ONCE into the PARENT document (guarded by an id). Living in the parent realm,
# it survives the 5s fragment refreshes. It watches every element with class
# `roll` + data-k (stable id) + data-v (target value); when a cell's value
# changes it briefly scrambles the digits, then lands on the real number.
# First sighting of a cell is seeded silently — only genuine CHANGES animate.
# ---------------------------------------------------------------------------
_ROLL_INJECTED_JS = """
(function(){
  if (window.__rollReady) return;      // parent-realm singleton
  window.__rollReady = true;
  var store = {};
  function randLike(t){ return t.replace(/[0-9]/g, function(){ return Math.floor(Math.random()*10); }); }
  function scramble(el, target){
    if (el.__t){ clearInterval(el.__t); }
    var n = 6;                                     // ~6 quick frames (~270ms)
    el.__t = setInterval(function(){
      if (n-- <= 0){ clearInterval(el.__t); el.__t = null; el.textContent = target; return; }
      el.textContent = randLike(target);
    }, 45);
  }
  function tick(){
    var els = document.querySelectorAll('.roll[data-k]');
    for (var i=0;i<els.length;i++){
      var el = els[i], k = el.getAttribute('data-k'), v = el.getAttribute('data-v');
      if (v === null || v === '') { store[k] = v; continue; }
      if (!(k in store)) { store[k] = v; continue; }   // first sight → no anim
      if (store[k] !== v) { store[k] = v; scramble(el, v); }
    }
  }
  var pending = false;
  function schedule(){ if (pending) return; pending = true; setTimeout(function(){ pending=false; tick(); }, 30); }
  new MutationObserver(schedule).observe(document.body, {childList:true, subtree:true});
  setInterval(tick, 2000);   // safety sweep
  tick();
})();
"""
components.html(
    "<script>(function(){var d=window.parent.document;"
    "if(d.getElementById('rollInjector'))return;"
    "var s=d.createElement('script');s.id='rollInjector';"
    "s.textContent=" + json.dumps(_ROLL_INJECTED_JS) + ";"
    "d.head.appendChild(s);})();</script>",
    height=0,
)

TF_ALL = ["M15", "H1", "H4", "D1"]
EXTRA = ["XAUUSD", "BTCUSD"]
MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
# Minor crosses split by liquidity/popularity:
# Minors 1 = the most-traded crosses; Minors 2 = the thinner, less-popular ones.
MINORS_1 = ["EURJPY", "GBPJPY", "EURGBP", "EURCHF", "AUDJPY", "EURAUD",
            "GBPCHF", "CADJPY", "NZDJPY", "EURCAD", "GBPAUD", "CHFJPY"]
MINORS_2 = ["EURNZD", "GBPCAD", "GBPNZD", "AUDCHF", "AUDCAD", "AUDNZD",
            "NZDCHF", "NZDCAD", "CADCHF"]
MINOR_PAIRS = MINORS_1 + MINORS_2
ALL_SYMBOLS = MAJOR_PAIRS + MINOR_PAIRS + EXTRA
# Default watchlist = the 7 majors only (everything else is opt-in via the picker).
DEFAULT_WATCH = MAJOR_PAIRS
IMPACT_DOT = {"High": DOWN, "Medium": AMBER, "Low": "#4a90d9", "Holiday": MUT}
ARROW_COL = {"▲▲": UP, "▲": UP_DIM, "▼": DOWN_DIM, "▼▼": DOWN, "·": MUT}
NEWS_LEVELS = ["High", "Medium", "Low", "Holiday"]

# Toggleable windows (⚙ Settings → Panels). Order = display order in settings.
PANELS = [
    ("sessions",    "Session clock"),
    ("kpi",         "KPI strip"),
    ("monitor",     "Pair Monitor"),
    ("setups",      "Top Setups"),
    ("heatmap",     "Volatility Heatmap"),
    ("calendar",    "Economic Calendar"),
    ("strength",    "Currency Strength"),
    ("correlation", "Correlation Matrix"),
]
PANEL_KEYS = [k for k, _ in PANELS]

# ---------------------------------------------------------------------------
# Restore every setting from the URL query params on a fresh page load, so
# filters/watchlist survive a HARD browser refresh (session_state alone resets
# on reload). Runs once per session; widgets then read from session_state, and
# the cockpit writes the current settings back to the URL each render.
# ---------------------------------------------------------------------------
if not st.session_state.get("_settings_restored"):
    _qp = st.query_params

    def _csv(key, valid, default):
        raw = _qp.get(key)
        if raw is None:
            return list(default)
        picked = [x for x in raw.split(",") if x in valid]
        return picked or list(default)

    st.session_state["tfs_sel"] = _csv("tfs", TF_ALL, TF_ALL)
    st.session_state["news_impacts"] = _csv("ni", NEWS_LEVELS, ["High", "Medium"])
    _sp = _qp.get("sp"); st.session_state["strength_period"] = _sp if _sp in ("24H", "1D", "1W") else "24H"
    _rf = _qp.get("rf"); st.session_state["refresh_lbl"] = _rf if _rf in ("Off", "5s", "15s", "30s", "60s") else "5s"
    _tz = _qp.get("tz"); st.session_state["tz_sel"] = _tz if _tz in TZ_OPTIONS else "Local"
    _so = _qp.get("so"); st.session_state["sort_order"] = _so if _so in ("High→Low", "Low→High") else "High→Low"
    st.session_state["sort_by"] = _qp.get("sb") or "Default"
    _wl = _qp.get("wl")
    _watched = ({x for x in _wl.split(",") if x in ALL_SYMBOLS} if _wl is not None
                else set(DEFAULT_WATCH))
    for _p in ALL_SYMBOLS:
        st.session_state[f"w_{_p}"] = _p in _watched
    _pn = _qp.get("pn")                       # panels: store the HIDDEN ones
    _hidden = set(_pn.split(",")) if _pn else set()
    for _k in PANEL_KEYS:
        st.session_state[f"pan_{_k}"] = _k not in _hidden
    st.session_state["_settings_restored"] = True


def persist_settings():
    """Write current settings to the URL so a page refresh restores them."""
    st.query_params.update({
        "tfs": ",".join(st.session_state.get("tfs_sel", TF_ALL)),
        "ni": ",".join(st.session_state.get("news_impacts", [])),
        "sp": st.session_state.get("strength_period", "24H"),
        "rf": st.session_state.get("refresh_lbl", "5s"),
        "tz": st.session_state.get("tz_sel", "Local"),
        "sb": st.session_state.get("sort_by", "Default"),
        "so": st.session_state.get("sort_order", "High→Low"),
        "wl": ",".join(p for p in ALL_SYMBOLS if st.session_state.get(f"w_{p}")),
        "pn": ",".join(k for k in PANEL_KEYS if not st.session_state.get(f"pan_{k}", True)),
    })


# ---------------------------------------------------------------------------
# Settings live in the header ⚙ popover (settings_panel, rendered in cockpit).
# Here we only DERIVE the current values from session_state — seeded by the URL
# restore above and written by those widgets — so the run_every fragment
# decorator and the render helpers have them. cockpit() re-reads them each run
# so a change made in the popover takes effect on the next (fragment) rerun.
# ---------------------------------------------------------------------------
_REFRESH_MAP = {"Off": None, "5s": 5, "15s": 15, "30s": 30, "60s": 60}


def _read_settings():
    """Refresh the module-level setting globals from session_state."""
    global tfs, strength_period, news_impacts, refresh_lbl, display_tz, tz_label
    tfs = [t for t in TF_ALL if t in st.session_state.get("tfs_sel", TF_ALL)] or TF_ALL
    strength_period = st.session_state.get("strength_period", "24H")
    news_impacts = st.session_state.get("news_impacts", ["High", "Medium"])
    refresh_lbl = st.session_state.get("refresh_lbl", "5s")
    _tzname = st.session_state.get("tz_sel", "Local")
    display_tz = _resolve_tz(_tzname)
    tz_label = _tz_label(_tzname, display_tz)


_read_settings()
_REFRESH = _REFRESH_MAP[refresh_lbl]
_REFRESH_LABEL = refresh_lbl   # what run_every was built with (this full run)


def settings_panel():
    """All customizable settings — rendered inside the header ⚙ popover."""
    st.markdown('<div class="wtitle" style="margin-top:0">⚙ Settings</div>',
                unsafe_allow_html=True)
    st.multiselect("Timeframes", TF_ALL, key="tfs_sel",
                   help="Which timeframes to show across the Pair Monitor & heatmap.")
    st.selectbox("Strength window", ["24H", "1D", "1W"], key="strength_period",
                 help="Lookback for the currency-strength bar.")
    st.selectbox("Auto-refresh", ["Off", "5s", "15s", "30s", "60s"], key="refresh_lbl",
                 help="How often the dashboard pulls fresh prices.")
    st.selectbox("Time zone", list(TZ_OPTIONS), key="tz_sel",
                 help="Show the session clock, now-line and calendar times in this "
                      "zone. 'Local' = your device's timezone.")
    st.multiselect("News impact", NEWS_LEVELS, key="news_impacts",
                   help="Impact levels to show in the Economic Calendar.")

    st.markdown('<div class="wtitle" style="margin:.5rem 0 .1rem">Panels — show / hide</div>',
                unsafe_allow_html=True)
    pcols = st.columns(2)
    for i, (k, label) in enumerate(PANELS):
        pcols[i % 2].checkbox(label, key=f"pan_{k}")

    if st.button("Force refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()


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
    if pct >= 0.618:
        return AMBER         # elevated (Fib 0.618)
    if pct >= 0.382:
        return INK           # normal (Fib 0.382)
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


def _activity_dot(vol):
    """Colour a live-activity dot by today's range vs the pair's average range
    (ATR): bright = running hot right now, dim = quiet so far."""
    r = vol.get("day_vs_atr")
    if r is None:
        return MUT
    if r >= 1.0:
        return UP            # today already ≥ a full average day → hot
    if r >= 0.618:
        return AMBER         # active (Fib 0.618)
    return "#3a4150"         # quiet so far (dim)


def _wl_set_only(group):
    """Set exactly `group` on, everything else off (used by Select all / Clear)."""
    for p in ALL_SYMBOLS:
        st.session_state[f"w_{p}"] = p in group


def _wl_toggle(group):
    """Toggle a group: if all are already on, turn them all off; otherwise turn
    them all on. Leaves other groups untouched."""
    all_on = all(st.session_state.get(f"w_{p}") for p in group)
    for p in group:
        st.session_state[f"w_{p}"] = not all_on


def watchlist_picker():
    """The instrument picker (rendered inside the Watchlist popover). Toggle
    buttons set state BEFORE the checkboxes render below, so no st.rerun() is
    needed. Returns the selected list."""
    st.markdown("**Select instruments to monitor**")
    # per-tab toggle buttons: tick/untick a whole group without touching others.
    # Metal/Crypto is just 2 items, so no button for it — tick them directly.
    qa = st.columns(3)
    if qa[0].button("Majors", key="wl_maj", width="stretch"):
        _wl_toggle(MAJOR_PAIRS)
    if qa[1].button("Minors 1", key="wl_min1", width="stretch"):
        _wl_toggle(MINORS_1)
    if qa[2].button("Minors 2", key="wl_min2", width="stretch"):
        _wl_toggle(MINORS_2)
    qb = st.columns(2)
    if qb[0].button("Select all", key="wl_all", width="stretch"):
        _wl_set_only(ALL_SYMBOLS)
    if qb[1].button("Clear", key="wl_clr", width="stretch"):
        _wl_set_only([])

    groups = [("Majors", MAJOR_PAIRS), ("Minors 1", MINORS_1),
              ("Minors 2", MINORS_2), ("Metal / Crypto", EXTRA)]
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
        return v

    vals = {p: metric(p) for p in pairs}
    have = sorted((p for p in pairs if vals[p] is not None),
                  key=lambda p: vals[p], reverse=desc)
    missing = [p for p in pairs if vals[p] is None]
    return have + missing   # no-data rows always sink to the bottom, either way


def monitor_table(pairs, quotes, trends, atrs):
    head = "".join(f"<th>{t}</th>" for t in tfs)
    body = ""
    for p in pairs:
        q, tr, vol = quotes[p], trends[p], atrs[p]
        chg = q["change_pct"]
        cc = UP if (chg or 0) >= 0 else DOWN
        chg_txt = "—" if chg is None else f"{chg:+.2f}%"
        vcol = _vol_color(vol["pct"])
        acol = _activity_dot(vol)
        cells = ""
        for t in tfs:
            a = tr[t]["arrow"]
            cells += f'<td style="color:{ARROW_COL.get(a,MUT)};font-size:15px">{a}</td>'
        body += (f'<tr><td>{p} <span style="color:{acol};font-size:9px" '
                 f'title="live activity: today\'s range vs average">&#9679;</span></td>'
                 f'<td style="color:{cc}">{chg_txt}</td>'
                 f'<td style="color:{vcol}" title="Avg daily range (ATR-13)">'
                 f'{_vol_fmt(p, vol)}</td>{cells}</tr>')
    return (f'<div class="scrollx"><table class="term"><thead><tr><th>Pair</th>'
            f'<th>Δ Day</th><th>Vol/D</th>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def top_setups_html(pairs, trends):
    """Shortlist the pairs whose timeframes lean the same way — the aligned-trend
    setups. Ranks by total trend score; a fully-aligned pair (all TFs same
    direction) is bold. Two columns: LONGS (net-up) and SHORTS (net-down)."""
    rows = []
    for p in pairs:
        scores = [trends[p][t]["score"] for t in tfs]
        total = sum(scores)
        aligned = all(s > 0 for s in scores) or all(s < 0 for s in scores)
        arrows = "".join("▲" if s > 0 else ("▼" if s < 0 else "·") for s in scores)
        rows.append((p, total, aligned, arrows))
    longs = sorted([r for r in rows if r[1] > 0], key=lambda x: -x[1])[:5]
    shorts = sorted([r for r in rows if r[1] < 0], key=lambda x: x[1])[:5]

    def col(items, color, head):
        h = (f'<div class="sub" style="color:{color};text-align:center;'
             f'font-weight:700;margin-bottom:.25rem">{head}</div>')
        if not items:
            return h + f'<div class="sub" style="color:{MUT};text-align:center">—</div>'
        body = ""
        for p, total, aligned, arrows in items:
            weight = 800 if aligned else 600
            star = "★ " if aligned else ""
            body += (f'<div style="display:flex;justify-content:space-between;'
                     f'font:{weight} 12px/1.6 \'JetBrains Mono\',monospace;color:{color}">'
                     f'<span>{star}{p}</span>'
                     f'<span style="letter-spacing:1px">{arrows}</span></div>')
        return h + body

    return (f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:.7rem;margin-top:.2rem">'
            f'<div>{col(longs, UP, "LONGS ▲")}</div>'
            f'<div>{col(shorts, DOWN, "SHORTS ▼")}</div></div>'
            f'<div class="sub phelp" style="color:{MUT};text-align:center;margin-top:.3rem">'
            f'★ = all timeframes aligned · arrows = M15·H1·H4·D1</div>')


def news_feed(cal, now):
    if cal.empty:
        return (f'<div style="color:{AMBER};font:600 12px/1.5 monospace;padding:.4rem">'
                f'⚠ Calendar temporarily unavailable<br>'
                f'<span style="color:{MUT};font-weight:500">source rate-limited — '
                f'auto-retries on the next refresh</span></div>')
    stale = cal.attrs.get("stale", False)
    total = len(cal)
    # keep from 2h ago onward so "just happened" stays visible
    upc = cal[cal["time"] >= now - pd.Timedelta(hours=2)]
    sel = upc[upc["impact"].isin(news_impacts)]
    # keep the panel FULL: show the selected-impact events, and if fewer than 10,
    # top up with the earliest remaining events so it never looks empty.
    LIMIT = 10
    if len(sel) >= LIMIT:
        cal = sel.head(LIMIT)
    else:
        fill = upc[~upc["impact"].isin(news_impacts)].head(LIMIT - len(sel))
        cal = pd.concat([sel, fill]).sort_values("time")
    if cal.empty:
        return (f'<div style="color:{MUT};font:600 12px/1.5 monospace;padding:.4rem">'
                f'No events upcoming ({total} total loaded).</div>')
    upcoming = cal[cal["time"] >= now]
    next_idx = upcoming.index[0] if not upcoming.empty else None
    banner = ""
    if stale:
        banner = (f'<div style="color:{MUT};font:500 10px/1.3 monospace;'
                  f'padding:0 .3rem .3rem">cached copy (live source rate-limited)</div>')
    rows = ""
    for i, ev in cal.iterrows():
        dot = IMPACT_DOT.get(ev["impact"], MUT)
        # this-week events → live hrs/mins countdown; next-week → "next week"
        cd = "next week" if ev.get("next_week") else _countdown(ev["time"], now)
        nxt = " next" if i == next_idx else ""
        link = ("https://www.google.com/search?tbm=nws&q=" +
                quote_plus(f'{ev["currency"]} {ev["title"]}'))
        rows += (
            f'<a class="nrow{nxt}" href="{link}" target="_blank" rel="noopener">'
            f'<span class="t">{ev["time"].astimezone(display_tz):%a %H:%M}</span>'
            f'<span class="badge">{_esc(ev["currency"])}</span>'
            f'<span class="ev"><span style="color:{dot}">&#9679;</span> '
            f'{_esc(ev["title"])} ↗</span>'
            f'<span class="cd">{cd}</span></a>')
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
    # headroom so the "outside" value labels never clip at the box edge
    m = max(abs(float(s.min())), abs(float(s.max())), 0.1)
    pad = m * 0.6 + 0.05
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h", marker_color=colors,
        text=[f"{v:+.2f}" for v in s.values], textposition="outside",
        textfont=dict(family="JetBrains Mono", size=11, color=INK),
        cliponaxis=False))
    fig.update_layout(
        height=250, template="plotly_dark", dragmode=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=6, r=12, t=6, b=6),
        yaxis=dict(autorange="reversed", fixedrange=True),
        font=dict(family="JetBrains Mono", color=MUT, size=11),
        xaxis=dict(gridcolor=BORDER, zerolinecolor=MUT, fixedrange=True,
                   range=[-(m + pad), m + pad]))
    return fig


def _mean_heat(hmap):
    """Average heat across a pair's timeframes (skips missing cells)."""
    vs = [v for v in hmap.values() if v is not None]
    return sum(vs) / len(vs) if vs else 0.0


# Thermal ramp stops (heat 0→2 mapped to 0→1): quiet-dark → cool → teal(normal)
# → amber → hot orange-red. Same colours the old Plotly heatmap used.
_HEAT_STOPS = [(0.00, (0x16, 0x1b, 0x24)), (0.30, (0x1f, 0x33, 0x46)),
               (0.50, (0x2f, 0x6f, 0x6a)), (0.72, (0xc1, 0x85, 0x2b)),
               (1.00, (0xff, 0x5a, 0x36))]


def _heat_color(v):
    """Interpolate a heat ratio (~0..2, 1.0 = normal) to a thermal hex colour."""
    if v is None:
        return "#12161d"                      # no data
    t = max(0.0, min(1.0, v / 2.0))
    for (p0, c0), (p1, c1) in zip(_HEAT_STOPS, _HEAT_STOPS[1:]):
        if t <= p1:
            f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            r, g, b = (round(a + (b_ - a) * f) for a, b_ in zip(c0, c1))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#ff5a36"


def vol_heatmap_html(pairs, heats):
    """Volatility heatmap as an HTML table (pairs × timeframe), each cell coloured
    by how hot it is running right now (recent range ÷ ATR, 1.0 = an average bar).

    Rendered as HTML — not Plotly — on purpose: the DOM diffs cell colours in
    place on each 30s refresh, so nothing repaints/strobes the way a Plotly
    heatmap canvas does. Deliberately a thermal ramp, NOT green/red (those mean
    trend up/down elsewhere)."""
    head = '<tr><th></th>' + ''.join(f'<th>{t}</th>' for t in tfs) + '</tr>'
    rows = []
    for p in pairs:
        cells = [f'<td class="pl">{p}</td>']
        for t in tfs:
            v = heats[p].get(t)
            lbl = '' if v is None else f'{v:.1f}'
            # class "roll" + data-k (stable id) + data-v (target) let the injected
            # JS scramble ONLY the cells whose value actually changed on refresh.
            cells.append(f'<td class="roll" data-k="{p}|{t}" data-v="{lbl}" '
                         f'style="background:{_heat_color(v)}">{lbl}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    return (f'<table class="heat"><thead>{head}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _corr_color(c):
    """Diverging colour for a correlation (-1..1). Warm amber = move together,
    cool blue = move opposite, dark neutral near 0. Deliberately NOT green/red
    (those mean trend up/down); negative correlation isn't 'bad'."""
    if c is None or pd.isna(c):
        return "#12161d"
    c = max(-1.0, min(1.0, float(c)))
    dark = (0x1c, 0x22, 0x2e)
    end = (0xe8, 0x87, 0x3a) if c >= 0 else (0x3d, 0x7d, 0xd6)   # warm / cool
    t = abs(c)
    r, g, b = (round(dark[i] + (end[i] - dark[i]) * t) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"


# Currency priority for grouping the matrix — USD first, then the rest of the
# majors (data_feed.MAJORS already starts USD, EUR, GBP, …).
_CCY_ORDER = {c: i for i, c in enumerate(d.MAJORS)}


def _ccy_rank(c):
    return _CCY_ORDER.get(c, len(d.MAJORS))   # non-majors (XAU/BTC) sort last


def group_pairs_by_currency(pairs):
    """Stack pairs sharing a currency together so correlation blocks are obvious:
    grouped by each pair's highest-priority currency (USD first, then EUR, …),
    and within a group the base-side pairs (USDxxx) are kept apart from the
    quote-side ones (xxxUSD) — which is exactly where correlation flips sign."""
    def key(p):
        a, b = p[:3], p[3:]
        ra, rb = _ccy_rank(a), _ccy_rank(b)
        if ra <= rb:                 # primary currency is the base
            return (ra, 0, rb, p)
        return (rb, 1, ra, p)        # primary currency is the quote
    return sorted(pairs, key=key)


def corr_matrix_html(corr):
    """Correlation heatmap as an HTML table (pairs × pairs). Diagonal is muted.
    Pairs are grouped by shared currency; capped at CORR_MAX (caller flags it)."""
    pairs = group_pairs_by_currency(list(corr.columns))[:CORR_MAX]
    head = '<tr><th></th>' + ''.join(f'<th>{p}</th>' for p in pairs) + '</tr>'
    rows = []
    for r in pairs:
        cells = [f'<td class="pl">{r}</td>']
        for c in pairs:
            v = corr.loc[r, c]
            if r == c:
                cells.append('<td style="background:#161b24;color:#39424f">·</td>')
            else:
                lbl = '' if pd.isna(v) else f'{v:.1f}'
                cells.append(f'<td style="background:{_corr_color(v)}">{lbl}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    return (f'<div class="scrollx"><table class="heat corr"><thead>{head}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def sessions_strip(now):
    """Horizontal FX session clock: which centres are live, the London–NY
    overlap (peak liquidity), and a countdown to the next session change.
    Pure time math — no data feed, on-thesis with the volatility-first view."""
    s = sess.market_sessions(now)
    pills = "".join(
        f'<span class="sess {"on" if is_open else "off"}">{name}</span>'
        for name, is_open in s["sessions"])

    if s["weekend"]:
        note = f'<span class="sess-note" style="color:{MUT}">✖ FX market closed — weekend</span>'
    elif s["overlap"]:
        note = f'<span class="sess-note" style="color:{AMBER}">⚡ London–New York overlap · peak liquidity</span>'
    elif s["any_open"]:
        live = " + ".join(n for n, o in s["sessions"] if o)
        note = f'<span class="sess-note" style="color:{UP}">● {live} open</span>'
    else:
        note = f'<span class="sess-note" style="color:{MUT}">○ between sessions · thin liquidity</span>'

    nxt = s["next"]
    nxt_html = ""
    if nxt:
        verb = "opens" if nxt["kind"] == "open" else "closes"
        nxt_html = (f'<span class="sess-next">next: {nxt["name"]} {verb} in '
                    f'{sess.fmt_countdown(nxt["seconds"])}</span>')
    return f'<div class="sessbar">{pills}{note}{nxt_html}</div>'


def _market_activity(pairs, atrs):
    """(value, phrase, colour) for the Market Activity gauge — shared by phone."""
    acts = [atrs[p]["day_vs_atr"] for p in pairs if atrs[p].get("day_vs_atr") is not None]
    ma = (sum(acts) / len(acts)) if acts else 0.0
    if ma >= 0.786:
        return ma, "High volatility — active market", UP
    if ma >= 0.382:
        return ma, "Normal activity — average day", AMBER
    return ma, "Low volatility — quiet market", DOWN


def phone_top_html(now, pairs, atrs, cal, quotes, strength):
    """The ENTIRE locked top as ONE compact box: session timeline + a one-line
    Market Activity + Upcoming News (left) with Top Movers (right)."""
    # ── session timeline (axis + bars + now-line all in the chosen display tz) ──
    bars = sess.session_bars(now, display_tz)
    now_l = now.astimezone(display_tz)
    now_frac = (now_l.hour + now_l.minute / 60) / 24
    s = sess.market_sessions(now)
    rows = ""
    for b in bars:
        segs = "".join(
            f'<i class="sbar {"on" if b["open"] else "off"}" '
            f'style="left:{st_h/24*100:.2f}%;width:{(en_h-st_h)/24*100:.2f}%"></i>'
            for st_h, en_h in b["segs"])
        dot = UP if b["open"] else MUT
        rows += (f'<div class="srow"><span class="slbl"><b style="color:{dot}">●</b> '
                 f'{b["flag"]} {b["name"]}</span><span class="strack">{segs}</span></div>')
    axis = "".join(f'<span style="left:{h/24*100:.2f}%">{h:02d}</span>'
                   for h in (0, 3, 6, 9, 12, 15, 18, 21, 24))
    if s["weekend"]:
        status = f'<span style="color:{MUT}">✖ market closed — weekend</span>'
    elif s["overlap"]:
        status = f'<span style="color:{AMBER}">⚡ London–NY overlap · peak liquidity</span>'
    elif s["any_open"]:
        live = " + ".join(n for n, o in s["sessions"] if o)
        status = f'<span style="color:{UP}">● {live} session open</span>'
    else:
        status = f'<span style="color:{MUT}">○ between sessions · thin liquidity</span>'

    # ── market activity — ONE line, short phrase only (before the "—") ──
    ma, phrase, mcol = _market_activity(pairs, atrs)
    short = phrase.split(" — ")[0]
    market = (f'<div class="stl-mkt"><span class="lab">Market Activity</span> '
              f'<span style="color:{mcol};font-weight:700">{short}</span>'
              f'<span style="color:{MUT}"> · {ma*100:.0f}% of avg range</span></div>')

    # ── news (left): next 3, High preferred, filled with Medium ──
    events = []
    if not cal.empty:
        upc = cal[cal["time"] >= now]
        events = list(upc[upc["impact"] == "High"].head(3).iterrows())
        if len(events) < 3:
            fill = upc[upc["impact"] == "Medium"].head(3 - len(events))
            events += list(fill.iterrows())
            events.sort(key=lambda t: t[1]["time"])
    news_rows = ""
    for _, ev in events:
        col = DOWN if ev["impact"] == "High" else AMBER
        title = _esc(ev["title"])
        title = (title[:19] + "…") if len(title) > 19 else title
        news_rows += (f'<div style="display:flex;align-items:baseline;gap:.4rem;margin-top:.26rem;'
                      f'font:600 12px/1.2 \'JetBrains Mono\',monospace">'
                      f'<span style="color:{col};flex:0 0 28px;font-weight:800">{_esc(ev["currency"])}</span>'
                      f'<span style="color:{INK};flex:0 0 50px">{_countdown(ev["time"], now)}</span>'
                      f'<span style="color:{MUT};overflow:hidden;text-overflow:ellipsis;'
                      f'white-space:nowrap">{title}</span></div>')
    if len(events) < 3:
        msg = ("· nothing else this week — updates next week" if events
               else "· no high-impact news left — updates next week")
        news_rows += (f'<div style="margin-top:.26rem;font:italic 600 11px/1.2 '
                      f'\'JetBrains Mono\',monospace;color:{MUT}">{msg}</div>')

    # ── top movers (right) ──
    strong, weak = strength.index[0], strength.index[-1]
    movers = [(p, quotes[p]["change_pct"]) for p in pairs
              if quotes[p].get("change_pct") is not None]
    if movers:
        mp, mc = max(movers, key=lambda x: abs(x[1]))
        m_pair, m_sub, m_col = mp, f"{mc:+.2f}%", (UP if mc >= 0 else DOWN)
    else:
        m_pair, m_sub, m_col = "—", "", MUT

    def mv(lab, val, sub, col):
        return (f'<div style="margin-top:.2rem;white-space:nowrap">'
                f'<div class="lab" style="font-size:8px">{lab}</div>'
                f'<div style="color:{col};font:800 12px/1.15 \'JetBrains Mono\',monospace">'
                f'{_esc(val)} <span style="font-weight:600;font-size:10px">{_esc(sub)}</span></div></div>')
    movers_col = (
        f'<div style="flex:0 0 96px;border-left:1px solid {BORDER};padding-left:.5rem">'
        + mv("Strongest", strong, f"{strength.iloc[0]:+.2f}", UP)
        + mv("Top Mover", m_pair, m_sub, m_col)
        + mv("Weakest", weak, f"{strength.iloc[-1]:+.2f}", DOWN)
        + '</div>')
    newsmovers = (f'<div class="stl-nm"><div style="display:flex;gap:.5rem">'
                  f'<div style="flex:1;min-width:0"><div class="lab">📰 Upcoming News · high · med</div>'
                  f'{news_rows}</div>{movers_col}</div></div>')

    return (f'<div class="stl">'
            f'<div class="stl-status">{status}</div>'
            f'<div class="stl-axis">{axis}</div>'
            f'<div class="stl-body">{rows}'
            f'<i class="stl-nowline" style="left:calc(78px + (100% - 78px) * {now_frac:.4f})"></i>'
            f'</div>{market}{newsmovers}</div>')


def kpi_strip(pairs, quotes, atrs, strength, trends, cal, now, include_news=True):
    strong, weak = strength.index[0], strength.index[-1]
    # biggest daily mover among the watched pairs
    movers = [(p, quotes[p]["change_pct"]) for p in pairs
              if quotes[p].get("change_pct") is not None]
    if movers:
        mp, mc = max(movers, key=lambda x: abs(x[1]))
        m_pair, m_sub, m_col = mp, f"{mc:+.2f}%", (UP if mc >= 0 else DOWN)
    else:
        m_pair, m_sub, m_col = "—", "", MUT
    # market ACTIVITY (not trend direction — direction is irrelevant in FX, you
    # trade both ways). Measures how much has actually moved today: today's range
    # vs the average daily range (ATR), averaged across pairs. FX has no real
    # volume, so realized range is the standard activity/volume proxy.
    acts = [atrs[p]["day_vs_atr"] for p in pairs
            if atrs[p].get("day_vs_atr") is not None]
    market_act = (sum(acts) / len(acts)) if acts else 0.0
    if market_act >= 0.786:
        mkt_phrase, mkt_col = "High volatility — active market", UP
    elif market_act >= 0.382:
        mkt_phrase, mkt_col = "Normal activity — average day", AMBER
    else:
        mkt_phrase, mkt_col = "Low volatility — quiet market", DOWN
    mkt_tile = (
        f'<div class="kpi"><div class="lab">Market Activity</div>'
        f'<div style="color:{mkt_col};font:700 13px/1.35 \'JetBrains Mono\',monospace;'
        f'margin:.2rem 0">{mkt_phrase}</div>'
        f'<div class="sub">{market_act*100:.0f}% of avg daily range</div></div>')
    # next up-to-3 high-impact events (ccy + countdown; title on the first)
    hi = (cal[(cal["impact"] == "High") & (cal["time"] >= now)].head(3)
          if not cal.empty else pd.DataFrame())
    if hi.empty:
        hi_body = (f'<div class="val" style="color:{MUT}">—</div>'
                   f'<div class="sub">no high-impact ahead</div>')
    else:
        events = list(hi.iterrows())
        aligns = ["left", "center", "right"]
        cells = []
        for i in range(3):
            al = aligns[i]
            if i < len(events):
                _, ev = events[i]
                ccy, cd = _esc(ev["currency"]), _countdown(ev["time"], now)
                title = _esc(ev["title"])
                title = (title[:13] + "…") if len(title) > 13 else title
                cells.append(
                    f'<div style="text-align:{al};min-width:0;flex:1">'
                    f'<div style="font:700 15px/1.25 \'JetBrains Mono\',monospace;white-space:nowrap">'
                    f'<span style="color:{DOWN}">{ccy}</span> '
                    f'<span style="color:{INK}">{cd}</span></div>'
                    f'<div class="sub" style="color:{MUT};white-space:nowrap;'
                    f'overflow:hidden;text-overflow:ellipsis">{title}</div></div>')
            else:
                cells.append(f'<div style="text-align:{al};flex:1">'
                             f'<div class="val" style="color:{MUT};font-size:15px">—</div></div>')
        hi_body = ('<div style="display:flex;justify-content:space-between;'
                   'align-items:flex-start;gap:.5rem;margin-top:.15rem">'
                   + "".join(cells) + '</div>')
    hi_tile = f'<div class="kpi"><div class="lab">Next High-Impact</div>{hi_body}</div>'

    def tile(lab, val, sub, col):
        return (f'<div class="kpi"><div class="lab">{lab}</div>'
                f'<div class="val" style="color:{col}">{_esc(val)}</div>'
                f'<div class="sub">{_esc(sub)}</div></div>')

    # strongest | top mover | weakest — labels aligned over their values
    combined = (
        f'<div class="kpi">'
        f'<div class="lab" style="display:flex;justify-content:space-between">'
        f'<span>Strongest</span><span>Top Mover</span><span>Weakest</span></div>'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'gap:.4rem;margin-top:.1rem">'
        f'<div><div class="val" style="color:{UP};font-size:20px">{strong}</div>'
        f'<div class="sub" style="color:{UP}">{strength.iloc[0]:+.2f}</div></div>'
        f'<div style="text-align:center"><div class="val" style="color:{m_col};font-size:16px">{_esc(m_pair)}</div>'
        f'<div class="sub" style="color:{m_col}">{m_sub}</div></div>'
        f'<div style="text-align:right"><div class="val" style="color:{DOWN};font-size:20px">{weak}</div>'
        f'<div class="sub" style="color:{DOWN}">{strength.iloc[-1]:+.2f}</div></div>'
        f'</div></div>')

    # phone merges Next High-Impact into the session timeline, so it can drop the
    # news tile here (include_news=False) and show a tighter 2-tile strip.
    cols = "1.4fr 1fr 1.5fr" if include_news else "1.3fr 1fr"
    tiles = combined + mkt_tile + (hi_tile if include_news else "")
    return f'<div class="kpis" style="grid-template-columns:{cols}">{tiles}</div>'


# ---------------------------------------------------------------------------
# The cockpit (one fragment → all panels refresh together)
# ---------------------------------------------------------------------------
@st.fragment(run_every=_REFRESH)
def cockpit():
    # Pick up any settings changed in the ⚙ popover on the previous rerun.
    _read_settings()
    now = d.now_utc()
    rlabel = "auto-refresh off" if _REFRESH is None else f"every {refresh_lbl}"

    # header (single-column cockpit): logo/live row, then the buttons row.
    # Rendered as two stacked rows rather than responsive [5,4,5] columns so it
    # looks identical at any width (Streamlit only stacks columns on a narrow
    # viewport, which would cram the buttons on a wide screen).
    st.markdown(
        f'<div class="hdr"><span class="logo">FRE<b>O</b>X</span>'
        f'<span class="beta">v{VERSION} BETA</span>'
        f'<span class="live"><span class="dot"></span>{rlabel.upper()}</span></div>',
        unsafe_allow_html=True)
    # keyed container → .st-key-hdrbtns, so CSS can force this row to stay
    # horizontal (Streamlit otherwise stacks columns when the viewport is narrow).
    with st.container(key="hdrbtns"):
        ghcol, gcol, wcol = st.columns([1, 1, 3], gap="small")
        with ghcol:
            st.markdown(GITHUB_HTML, unsafe_allow_html=True)
        with gcol:
            with st.popover("⚙", width="stretch"):
                settings_panel()
        with wcol:
            with st.popover("☰ Watchlist", width="stretch"):
                watch = watchlist_picker()

    # which windows are visible (⚙ Settings → Panels; persisted in the URL)
    show = {k: st.session_state.get(f"pan_{k}", True) for k in PANEL_KEYS}

    # The phone cockpit is the ONE layout now, everywhere. The old wide multi-column
    # grid was retired in favour of the (cleaner) single-column phone cockpit; on a
    # big screen it's centred at phone width (dark margins on the sides) so the PC
    # looks exactly like the phone. ?view=phone is still accepted (the desktop-app
    # window passes it) but no longer changes anything.
    phone_view = True

    if phone_view:
        # full-height layout: the page becomes a fixed-viewport flex column so the
        # top info bars stay pinned and the two split panes fill + scroll the rest.
        # (Injected only in phone view → never affects the PC layout.)
        st.markdown(
            "<style>"
            "[data-testid='stMainBlockContainer']{height:100dvh!important;"
            "overflow:hidden!important;padding:.3rem .5rem .2rem!important;"
            "display:flex!important;flex-direction:column!important;}"
            # centre the cockpit at phone width on big screens → PC == phone,
            # with the dark page background showing on either side
            "[data-testid='stMainBlockContainer']{max-width:480px!important;"
            "margin-left:auto!important;margin-right:auto!important;}"
            "[data-testid='stMainBlockContainer'] [data-testid='stVerticalBlock']"
            "{gap:.25rem!important;}"
            # the layout wrapper that holds the scroll pane grows to fill the
            # space left by the pinned (locked) top info boxes; margin-top gives a
            # little breathing room between the locked top and the scroll region
            "[data-testid='stLayoutWrapper']:has(.st-key-pscroll)"
            "{flex:1 1 0!important;min-height:0!important;align-self:stretch;margin-top:.55rem!important;}"
            ".st-key-pscroll{height:100%!important;min-height:0!important;"
            "border-top:1px solid #1b2230;padding-top:.4rem;}"
            # remove the LAST UPDATED clock on phone (it crowded the timeline)
            ".clock{display:none!important;}"
            # compact header: shorter GitHub / gear / watchlist buttons
            # GitHub / ⚙ / Watchlist buttons all the SAME height so the row is
            # symmetrical (was 30px vs 26px), a touch taller, not cramped
            ".ghlink{height:34px!important;}"
            "[data-testid='stPopover'] button{padding-top:.25rem!important;"
            "padding-bottom:.25rem!important;min-height:34px!important;"
            "display:flex!important;align-items:center!important;justify-content:center!important;}"
            ".hdr{padding:.1rem!important;}"
            # tighten every panel's help-text on phone so the verbose ones
            # (heatmap, correlation) collapse to fewer lines and the Pair Monitor
            # blurb fits one line — desktop keeps its full-size help text
            ".phelp{font-size:9px!important;line-height:1.32!important;"
            "margin-bottom:.3rem!important;}"
            # tight top, but leave the logo room to breathe and a clear gap
            # between the logo row and the buttons row (they were overlapping)
            "[data-testid='stMainBlockContainer']{padding-top:.4rem!important;}"
            ".hdr{margin-bottom:.5rem!important;}"
            ".st-key-hdrbtns{margin-top:.5rem!important;}"
            # space between the info-bar (locked top) and the divider line above
            # the scroll area, so the separator isn't pressed against the box
            "[data-testid='stLayoutWrapper']:has(.st-key-pscroll)"
            "{margin-top:.75rem!important;}"
            # a bit more breathing room below the divider so the first panel
            # (Pair Monitor) isn't pressed right up against the separator line
            ".st-key-pscroll{padding-top:.7rem!important;}"
            # Pair Monitor sort/order filter → compact: keep Sort + Order on ONE
            # row (Streamlit stacks them when narrow), tiny uppercase labels,
            # shorter dropdown, tighter rows (phone only; PC layout untouched)
            ".st-key-sortrow [data-testid='stHorizontalBlock']"
            "{flex-wrap:nowrap!important;gap:.5rem!important;}"
            ".st-key-sortrow [data-testid='stColumn']"
            "{min-width:0!important;flex:1 1 auto!important;}"
            ".st-key-sortrow [data-testid='stVerticalBlock']{gap:.1rem!important;}"
            ".st-key-sortrow [data-testid='stWidgetLabel']{margin-bottom:.02rem!important;}"
            ".st-key-sortrow [data-testid='stWidgetLabel'] p"
            "{font-size:9px!important;letter-spacing:.06em;text-transform:uppercase;}"
            ".st-key-sortrow [data-baseweb='select']>div"
            "{min-height:32px!important;padding-top:0!important;padding-bottom:0!important;}"
            ".st-key-sortrow [role='radiogroup']{gap:.5rem!important;flex-wrap:nowrap!important;}"
            ".st-key-sortrow [role='radiogroup'] label{white-space:nowrap!important;}"
            ".st-key-sortrow [role='radiogroup'] p{font-size:10px!important;white-space:nowrap!important;}"
            "</style>",
            unsafe_allow_html=True)

    # FX session clock — desktop shows the strip here; phone shows the timeline
    # (with news merged) in its locked top after data is fetched.
    if show["sessions"] and not phone_view:
        st.markdown(sessions_strip(now), unsafe_allow_html=True)

    if not watch:
        st.warning("No instruments selected — open **☰ Watchlist** and pick some.")
        return

    data = gather_pairs(tuple(watch), tuple(tfs))
    quotes = {p: data[p]["quote"] for p in watch}
    trends = {p: data[p]["trend"] for p in watch}
    heats = {p: data[p]["heat"] for p in watch}
    atrs = {p: data[p]["atr"] for p in watch}

    # only fetch what a visible panel needs (KPI uses strength + calendar)
    strength = c_strength(strength_period) if (show["strength"] or show["kpi"]) else None
    cal = c_calendar() if (show["calendar"] or show["kpi"]) else None

    _STATIC = {"displayModeBar": False, "staticPlot": True, "scrollZoom": False}

    # pair order — read sort from session_state so it still works when the
    # Pair Monitor (which hosts the sort widgets) is hidden.
    _sopts = ["Default", "Day %", "Vol"] + tfs
    if st.session_state.get("sort_by") not in _sopts:
        st.session_state["sort_by"] = "Default"
    ordered = order_pairs(
        watch, quotes, trends, atrs,
        st.session_state.get("sort_by", "Default"),
        st.session_state.get("sort_order", "High→Low") == "High→Low")

    if show["kpi"] and not phone_view:   # desktop KPI strip (phone renders its own)
        st.markdown(kpi_strip(watch, quotes, atrs, strength, trends, cal, now),
                    unsafe_allow_html=True)

    # ── panel renderers (invoked by the reflow grid / phone carousel below) ──
    def _panel_monitor():
        with st.container(border=True):
            st.markdown(
                f'<div class="wtitle">Pair Monitor</div>'
                f'<div class="phelp" style="color:{MUT};font:500 10px/1.35 monospace;'
                f'text-align:center;margin-bottom:.35rem">'
                f'Vol/D = avg daily range (ATR-13) &nbsp;·&nbsp; '
                f'<span style="color:{UP}">&#9679;</span> '
                f'<span style="color:{UP}">hot</span> / '
                f'<span style="color:{AMBER}">active</span> / '
                f'<span style="color:#3a4150">quiet</span></div>',
                unsafe_allow_html=True)
            with st.container(key="sortrow"):
                sc1, sc2 = st.columns([1, 1], gap="small")
                sc1.selectbox("Sort by", _sopts, key="sort_by")
                sc2.radio("Order", ["High→Low", "Low→High"], horizontal=True,
                          key="sort_order")
            st.markdown(monitor_table(ordered, quotes, trends, atrs), unsafe_allow_html=True)

    def _panel_setups():
        with st.container(border=True):
            st.markdown('<div class="wtitle">Top Setups · aligned trends</div>' +
                        top_setups_html(watch, trends), unsafe_allow_html=True)

    def _panel_heatmap():
        with st.container(border=True):
            hot = max(ordered, key=lambda p: _mean_heat(heats[p])) if ordered else None
            hv = _mean_heat(heats[hot]) if hot else 0.0
            hcol = UP if hv >= 1.0 else (AMBER if hv >= 0.618 else MUT)
            st.markdown(
                f'<div class="wtitle">Volatility Heatmap · pair × TF</div>'
                f'<div class="phelp" style="color:{INK};font:600 12px/1.5 monospace;text-align:center">'
                f'▸ Hottest now: <span style="color:{hcol}">{hot} {hv:.1f}×</span> '
                f'<span style="color:{MUT}">vs its normal range</span><br>'
                f'<span style="color:{MUT}">bright = running hot right now · '
                f'dark = quiet · 1.0 = an average bar</span></div>'
                + vol_heatmap_html(ordered, heats),
                unsafe_allow_html=True)

    def _panel_calendar():
        with st.container(border=True):
            st.markdown('<div class="wtitle">📰 Economic Calendar</div>' +
                        news_feed(cal, now), unsafe_allow_html=True)

    def _panel_strength():
        with st.container(border=True):
            st.markdown(f'<div class="wtitle">Currency Strength · {strength_period}</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(strength_fig(strength), width="stretch",
                            config=_STATIC, key="strength_bar")

    def _panel_correlation():
        corr = c_correlation(tuple(watch))
        if corr is None or len(corr.columns) < 2:
            return
        with st.container(border=True):
            n = len(corr.columns)
            more = (f' · showing first {CORR_MAX} of {n} — narrow your watchlist '
                    f'for the rest') if n > CORR_MAX else ''
            st.markdown(
                f'<div class="wtitle">Correlation · {CORR_WINDOW}-day returns{more}</div>'
                f'<div class="phelp" style="color:{MUT};font:500 10px/1.4 monospace;'
                f'text-align:center;margin-bottom:.35rem">'
                f'<span style="color:#e8873a">amber = move together</span> · '
                f'<span style="color:#3d7dd6">blue = move opposite</span> · '
                f'stacking correlated pairs = the same bet twice (double risk)</div>'
                + corr_matrix_html(corr),
                unsafe_allow_html=True)

    if phone_view:
        # ── PHONE: locked top (compact) + one scrollable page of all windows ──
        # locked top = session TIMELINE (with Next High-Impact merged in) + a
        # tighter 2-tile KPI. These stay pinned; the windows scroll beneath.
        # locked top — ONE merged box: session timeline + one-line Market Activity
        # + Upcoming News (left) with Top Movers (right).
        if show["sessions"] or show["kpi"]:
            st.markdown(phone_top_html(now, watch, atrs, cal, quotes, strength),
                        unsafe_allow_html=True)
        with st.container(key="pscroll"):
            if show["monitor"]:
                _panel_monitor()
            if show["setups"]:
                _panel_setups()
            if show["heatmap"]:
                _panel_heatmap()
            if show["calendar"]:
                _panel_calendar()
            if show["strength"]:
                _panel_strength()
            if show["correlation"]:
                _panel_correlation()
    else:
        # ── PC: reflow column grid (the desktop layout — untouched) ──
        cols_spec = []
        left = [f for k, f in (("monitor", _panel_monitor), ("setups", _panel_setups)) if show[k]]
        mid = [_panel_heatmap] if show["heatmap"] else []
        right = [f for k, f in (("calendar", _panel_calendar), ("strength", _panel_strength)) if show[k]]
        if left:
            cols_spec.append((5, left))
        if mid:
            cols_spec.append((4, mid))
        if right:
            cols_spec.append((3, right))
        if cols_spec:
            cols = st.columns([w for w, _ in cols_spec], gap="small")
            for col, (_, panels) in zip(cols, cols_spec):
                with col:
                    for render in panels:
                        render()
        if show["correlation"]:
            _panel_correlation()

    if not any(show.values()):
        st.caption("All panels hidden — turn some back on in ⚙ Settings → Panels.")

    # data-source disclaimer (accuracy honesty)
    st.markdown(
        f'<div style="color:{MUT};font:500 10px/1.5 monospace;'
        f'border-top:1px solid {BORDER};padding-top:.4rem;margin-top:.2rem">'
        f'DATA · Prices: Yahoo Finance indicative mid quotes — near-real-time, '
        f'may differ from your broker, not for execution. '
        f'Calendar: Forex Factory. Strength/trend/vol computed locally. '
        f'All times {tz_label}.</div>', unsafe_allow_html=True)

    # persist all current settings to the URL so a page refresh restores them
    persist_settings()

    # Re-apply run_every when the refresh RATE changed in the ⚙ popover. This is
    # done LAST — after every widget (incl. the Watchlist checkboxes) has already
    # rendered this run — so the forced app rerun can't garbage-collect unrendered
    # widget state (which would silently clear the watchlist). run_every is fixed
    # on the fragment decorator at module-run time, so a full app rerun is needed.
    if refresh_lbl != _REFRESH_LABEL:
        st.rerun(scope="app")


cockpit()
