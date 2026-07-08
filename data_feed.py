"""
Freox — live data feed.

Two free, no-API-key sources:
  * Yahoo Finance chart API  → live FX quotes + intraday/daily OHLC
  * Forex Factory weekly JSON → economic calendar (news events)

Everything returns plain pandas objects so the Streamlit layer stays dumb.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)
_CAL_CACHE = _CACHE_DIR / "ff_calendar_thisweek.json"
_CAL_CACHE_NEXT = _CACHE_DIR / "ff_calendar_nextweek.json"

_UA = {"User-Agent": "Mozilla/5.0 (Freox dashboard)"}
_YF = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={itv}"
_FF = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_FF_NEXT = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

# 8 majors → the 28 conventional pairs built from them.
MAJORS = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
PAIRS_28 = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "NZDJPY", "NZDCHF", "NZDCAD",
    "CADJPY", "CADCHF", "CHFJPY",
]

# (yahoo range, yahoo interval) per timeframe label. H4 is resampled from H1.
TF_SPEC = {
    "M15": ("1mo", "15m"),
    "H1":  ("3mo", "60m"),
    "H4":  ("3mo", "60m"),   # resampled to 4h downstream
    "D1":  ("1y",  "1d"),
}


# Non-FX instruments use their own Yahoo symbols (not the "=X" spot format).
EXTRA_SYMBOLS = {"XAUUSD": "GC=F", "BTCUSD": "BTC-USD"}


def _yahoo_symbol(pair: str) -> str:
    if pair in EXTRA_SYMBOLS:
        return EXTRA_SYMBOLS[pair]
    return f"{pair.upper()}=X"


# Short-lived memo so identical OHLC requests within one refresh cycle hit the
# network once. E.g. H1 & H4 share the same 60m fetch, and a pair's daily bars
# are used by both trend and ATR — this dedupes them. TTL < the app refresh.
_OHLC_CACHE: dict = {}
_OHLC_TTL = 4.0   # < the 5s refresh: dedupes within a cycle, refreshes between cycles


def get_ohlc(pair: str, rng: str = "1mo", interval: str = "15m") -> pd.DataFrame:
    """Return an OHLC DataFrame (tz-aware UTC index) for a pair, or empty on failure.
    Successful results are memoized for a few seconds to avoid duplicate fetches."""
    key = (pair, rng, interval)
    cached = _OHLC_CACHE.get(key)
    if cached is not None and time.monotonic() - cached[0] < _OHLC_TTL:
        return cached[1]

    url = _YF.format(sym=_yahoo_symbol(pair), rng=rng, itv=interval)
    try:
        r = requests.get(url, headers=_UA, timeout=15)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
    except Exception:
        return pd.DataFrame()

    ts = res.get("timestamp")
    if not ts:
        return pd.DataFrame()
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "close": q.get("close"),
        },
        index=pd.to_datetime(ts, unit="s", utc=True),
    ).dropna(how="all").dropna(subset=["close"])
    _OHLC_CACHE[key] = (time.monotonic(), df)
    return df


def get_ohlc_tf(pair: str, tf: str) -> pd.DataFrame:
    """OHLC for a timeframe label (M15/H1/H4/D1). H4 is resampled from H1."""
    rng, itv = TF_SPEC[tf]
    df = get_ohlc(pair, rng, itv)
    if tf == "H4" and not df.empty:
        df = (
            df.resample("4h")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .dropna(subset=["close"])
        )
    return df


def get_quote(pair: str) -> dict:
    """Live price + daily change %.

    Price = Yahoo's `regularMarketPrice` (freshest indicative mid).
    Prev  = the 2nd-to-last DAILY CANDLE close (yesterday's completed close,
    since the last candle is today's still-forming bar) → a true day-over-day
    change.

    ⚠️ Do NOT use `meta.chartPreviousClose` here: it is RANGE-DEPENDENT — on a
    1y request it returns the price ~a year ago, not yesterday's close — so it
    would silently turn "daily change" into a multi-day/annual change. Yahoo's
    `previousClose`/`regularMarketPreviousClose` are null for FX (=X) symbols.
    """
    url = _YF.format(sym=_yahoo_symbol(pair), rng="5d", itv="1d")
    try:
        r = requests.get(url, headers=_UA, timeout=15)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
    except Exception:
        return {"pair": pair, "price": None, "prev": None, "change_pct": None}

    meta = res.get("meta", {})
    closes = [c for c in (res["indicators"]["quote"][0].get("close") or [])
              if c is not None]
    price = meta.get("regularMarketPrice")
    if price is None:
        price = closes[-1] if closes else None
    prev = closes[-2] if len(closes) >= 2 else None
    chg = ((price - prev) / prev * 100) if (price and prev) else None
    return {"pair": pair, "price": price, "prev": prev, "change_pct": chg}


# ---------------------------------------------------------------------------
# Economic calendar (Forex Factory weekly JSON)
# ---------------------------------------------------------------------------
_IMPACT_RANK = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0, "": 0}


def _fetch_calendar_raw(url, cache_path) -> tuple[list | None, bool]:
    """Return (events, stale) for one Forex Factory feed. Tries the network
    (2 attempts, backoff); on any failure — incl. HTTP 429 rate-limit — falls
    back to the last-good disk copy at `cache_path`."""
    for attempt in range(2):
        try:
            r = requests.get(url, headers=_UA, timeout=15)
            # 429 returns an HTML error page, not JSON — guard on both.
            if r.status_code == 200 and r.text.lstrip().startswith("["):
                data = r.json()
                try:
                    cache_path.write_text(json.dumps(data))
                except Exception:
                    pass
                return data, False
        except Exception:
            pass
        if attempt == 0:
            time.sleep(1.5)
    # network failed → serve last-good cache if we have one
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text()), True
        except Exception:
            pass
    return None, False


def get_calendar() -> pd.DataFrame:
    """This week's economic events. Columns: time, currency, impact, title,
    forecast, previous, impact_rank, next_week. Times are tz-aware (UTC). Carries
    df.attrs['stale'] = True when served from the disk fallback.

    NOTE: Forex Factory's free feed only publishes THIS week — the nextweek/
    lastweek/etc. URLs all 404. So `next_week` is always False here; genuine
    next-week data would need a keyed source (e.g. Financial Modeling Prep)."""
    data, stale = _fetch_calendar_raw(_FF, _CAL_CACHE)
    if not data:
        return pd.DataFrame()

    rows = []
    for ev in data:
        rows.append(
            {
                "time": pd.to_datetime(ev.get("date"), utc=True, errors="coerce"),
                "currency": ev.get("country", ""),
                "impact": ev.get("impact", ""),
                "title": ev.get("title", ""),
                "forecast": ev.get("forecast", ""),
                "previous": ev.get("previous", ""),
                "next_week": False,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["impact_rank"] = df["impact"].map(_IMPACT_RANK).fillna(0).astype(int)
    df = df.sort_values("time").reset_index(drop=True)
    df.attrs["stale"] = stale
    return df


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
