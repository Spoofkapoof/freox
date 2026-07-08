"""
Freox — trend + currency-strength math.

Pure functions over pandas. No I/O here (keeps it testable).
"""
from __future__ import annotations

import concurrent.futures as cf

import pandas as pd

from data_feed import MAJORS, PAIRS_28, get_ohlc, get_ohlc_tf


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def trend_of(df: pd.DataFrame, fast: int = 21, mid: int = 55, slow: int = 89) -> dict:
    """Classify trend from an OHLC frame using a THREE-EMA stack.

    Lengths are Fibonacci numbers (21 / 55 / 89) — a Fibonacci EMA ribbon.
    Returns {score: -2..+2, label, arrow}.
      +2 ▲▲ Strong Up  = full stack aligned: price > EMA21 > EMA55 > EMA89
      +1 ▲  Up         = price > EMA21 > EMA55 (top two aligned, slow not yet)
      -1 ▼  Down       = price < EMA21 < EMA55
      -2 ▼▼ Strong Down= price < EMA21 < EMA55 < EMA89
       0 ·  Flat       = mixed / no clean alignment
    The extra (89) EMA is the added confirmation over the old 2-EMA check —
    a "strong" arrow now means three moving averages agree, not two.
    """
    if df.empty or len(df) < slow:
        return {"score": 0, "label": "n/a", "arrow": "·"}
    close = df["close"]
    ef = ema(close, fast).iloc[-1]
    em = ema(close, mid).iloc[-1]
    es = ema(close, slow).iloc[-1]
    px = float(close.iloc[-1])

    if px > ef > em > es:
        return {"score": 2, "label": "Strong Up", "arrow": "▲▲"}
    if px > ef and ef > em:
        return {"score": 1, "label": "Up", "arrow": "▲"}
    if px < ef < em < es:
        return {"score": -2, "label": "Strong Down", "arrow": "▼▼"}
    if px < ef and ef < em:
        return {"score": -1, "label": "Down", "arrow": "▼"}
    return {"score": 0, "label": "Flat", "arrow": "·"}


def pip_size(pair: str) -> float:
    """One pip in price terms. Gold uses 0.1, BTC uses 1.0 (a point),
    JPY-quoted pairs use 0.01, everything else 0.0001."""
    if pair == "XAUUSD":
        return 0.1
    if pair == "BTCUSD":
        return 1.0
    return 0.01 if pair[3:] == "JPY" else 0.0001


def atr_volatility(pair: str, tf: str = "D1", n: int = 13) -> dict:
    """Average True Range volatility for a pair/instrument.

    Returns {atr, pips, pct, tf, day_range, day_vs_atr}. `atr` = raw price-unit
    range, `pips` = in pips, `pct` = ATR / price (normalized). `day_range` =
    today's high-low; `day_vs_atr` = today's range / ATR (how much of an average
    day's movement has already happened — an FX "activity" proxy, since FX has
    no real volume). Uses Wilder's smoothing (the standard ATR).
    """
    df = get_ohlc_tf(pair, tf)
    if df.empty or len(df) < n + 1:
        return {"atr": None, "pips": None, "pct": None, "tf": tf,
                "day_range": None, "day_vs_atr": None}
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])
    price = float(c.iloc[-1])
    day_range = float(h.iloc[-1] - l.iloc[-1])
    return {
        "atr": atr,
        "pips": atr / pip_size(pair),
        "pct": atr / price * 100 if price else None,
        "tf": tf,
        "day_range": day_range,
        "day_vs_atr": (day_range / atr) if atr else None,
    }


def multi_tf_trend(pair: str, tfs=("M15", "H1", "H4", "D1")) -> dict:
    """Trend per timeframe for one pair. Returns {tf: trend_dict}."""
    out = {}
    for tf in tfs:
        out[tf] = trend_of(get_ohlc_tf(pair, tf))
    return out


def tf_heat(pair: str, tf: str, n: int = 13, recent: int = 3) -> float | None:
    """How 'hot' a timeframe is running right NOW, self-normalised.

    = mean true range of the last `recent` bars ÷ ATR(n) baseline.
    ~1.0 = an average bar, >1 heating up, <1 quiet. Because each cell is
    divided by its own ATR, every timeframe (and every pair) lands on the same
    scale — so an M15 cell and a D1 cell are directly comparable. `n`=13 and
    `recent`=3 are Fibonacci, matching the rest of the indicator settings.
    """
    df = get_ohlc_tf(pair, tf)
    if df.empty or len(df) < n + 1:
        return None
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])
    if not atr:
        return None
    return float(tr.iloc[-recent:].mean()) / atr


def multi_tf_heat(pair: str, tfs=("M15", "H1", "H4", "D1")) -> dict:
    """Heat ratio per timeframe for one pair. Returns {tf: ratio | None}."""
    return {tf: tf_heat(pair, tf) for tf in tfs}


# period → (yahoo range, yahoo interval, bars-back defining the window).
# 1D/1W use 1y/1d so they reuse the SAME cached daily fetch that trend + ATR
# pull (position-based lookback → bit-identical to shorter ranges), saving calls.
_STRENGTH_SPEC = {
    "24H": ("5d", "60m", 24),   # last 24 hourly bars
    "1D":  ("1y", "1d", 1),     # yesterday's close → now
    "1W":  ("1y", "1d", 5),     # last 5 trading days
}


def _pct_over(df: pd.DataFrame, bars: int) -> float | None:
    """% change of close over `bars` positions back (gap-safe on position)."""
    if df.empty or len(df) < 2:
        return None
    n = min(bars, len(df) - 1)
    now = float(df["close"].iloc[-1])
    then = float(df["close"].iloc[-1 - n])
    return (now - then) / then * 100 if then else None


def pair_change(pair: str, period: str = "24H") -> float | None:
    rng, itv, bars = _STRENGTH_SPEC.get(period, _STRENGTH_SPEC["24H"])
    return _pct_over(get_ohlc(pair, rng, itv), bars)


def currency_strength(period: str = "24H",
                      pairs: list[str] | None = None) -> pd.Series:
    """Relative strength per currency over `period`, across the 28 majors.

    For a pair BASE/QUOTE moving +c%: BASE gains +c, QUOTE gains -c.
    Each currency's score = mean contribution. Sorted strongest → weakest.
    """
    pairs = pairs or PAIRS_28

    def one(p):
        return p, pair_change(p, period)

    changes: dict[str, float | None] = {}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for p, c in ex.map(one, pairs):
            changes[p] = c

    contrib: dict[str, list[float]] = {c: [] for c in MAJORS}
    for pair, c in changes.items():
        if c is None or pd.isna(c):
            continue
        base, quote = pair[:3], pair[3:]
        if base in contrib:
            contrib[base].append(c)
        if quote in contrib:
            contrib[quote].append(-c)
    scores = {c: (sum(v) / len(v) if v else 0.0) for c, v in contrib.items()}
    return pd.Series(scores).sort_values(ascending=False)
