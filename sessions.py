"""
Freox — FX market session clock (pure time logic, no I/O).

Which trading sessions are open right now, whether the high-liquidity
London–New York overlap is live, and a countdown to the next session change.
Uses `zoneinfo` so each centre's open/close respects its own DST. FX trades
~24h on weekdays; sessions are Mon–Fri in each local centre, which naturally
models the Sunday-evening reopen and Friday-evening close.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

_UTC = ZoneInfo("UTC")

# (name, IANA tz, local open hour, local close hour) — conventional FX session
# hours in each financial centre's own local time (DST handled by zoneinfo).
SESSIONS = [
    ("Sydney",   "Australia/Sydney", 7, 16),
    ("Tokyo",    "Asia/Tokyo",       9, 18),
    ("London",   "Europe/London",    8, 16),
    ("New York", "America/New_York", 8, 17),
]


def _is_open(now_utc: datetime, tz: str, oh: int, ch: int) -> bool:
    """Is this centre in session right now (weekday + within local hours)?"""
    local = now_utc.astimezone(ZoneInfo(tz))
    if local.weekday() >= 5:            # Sat/Sun in that centre → closed
        return False
    return oh <= local.hour < ch


def _next_transition(now_utc: datetime, tz: str, oh: int, ch: int):
    """Soonest upcoming (utc_time, kind) for this session, kind in open/close."""
    z = ZoneInfo(tz)
    local_now = now_utc.astimezone(z)
    best = None
    for d in range(0, 8):
        day = (local_now + timedelta(days=d)).date()
        if day.weekday() >= 5:         # sessions don't run on weekends
            continue
        for hour, kind in ((oh, "open"), (ch, "close")):
            evt = datetime.combine(day, dtime(hour), tzinfo=z).astimezone(_UTC)
            if evt > now_utc and (best is None or evt < best[0]):
                best = (evt, kind)
    return best


def market_sessions(now_utc: datetime) -> dict:
    """Snapshot of the FX session clock.

    Returns {
      sessions: [(name, is_open), ...],
      overlap:  bool,          # London & New York both open (peak liquidity)
      any_open: bool,
      weekend:  bool,          # FX market shut for the weekend
      next:     {name, kind, seconds} | None,   # next session open/close
    }
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=_UTC)

    states = [(name, _is_open(now_utc, tz, oh, ch))
              for (name, tz, oh, ch) in SESSIONS]
    open_map = dict(states)
    overlap = open_map.get("London", False) and open_map.get("New York", False)
    any_open = any(o for _, o in states)

    # earliest upcoming transition across all sessions
    nxt = None
    for name, tz, oh, ch in SESSIONS:
        t = _next_transition(now_utc, tz, oh, ch)
        if t and (nxt is None or t[0] < nxt[1]):
            nxt = (name, t[0], t[1])
    next_evt = None
    if nxt:
        name, when, kind = nxt
        next_evt = {"name": name, "kind": kind,
                    "seconds": int((when - now_utc).total_seconds())}

    # weekend = nothing open and the next open is a session opening (not a close)
    weekend = (not any_open) and bool(next_evt and next_evt["kind"] == "open") \
        and _fx_weekend(now_utc)

    return {"sessions": states, "overlap": overlap, "any_open": any_open,
            "weekend": weekend, "next": next_evt}


def _fx_weekend(now_utc: datetime) -> bool:
    """True during the FX weekend gap (Fri 21:00 UTC → Sun 21:00 UTC)."""
    wd, hour = now_utc.weekday(), now_utc.hour   # Mon=0 .. Sun=6
    if wd == 5:                       # Saturday
        return True
    if wd == 4 and hour >= 21:        # Friday evening (after NY close)
        return True
    if wd == 6 and hour < 21:         # Sunday before Sydney reopens
        return True
    return False


FLAGS = {"Sydney": "🇦🇺", "Tokyo": "🇯🇵", "London": "🇬🇧", "New York": "🇺🇸"}


def session_bars(now_utc: datetime, display_tz=None) -> list:
    """Each session's active window(s) today on a 0–24 axis, for the timeline.
    Returns [{name, flag, open, segs:[(start,end)...]}]; a session that wraps
    midnight (e.g. Sydney) is split into two segments. DST-correct per centre.

    The axis reads in `display_tz` (a tzinfo) when given — each session's hours
    are converted into that zone so the whole clock localises together. Defaults
    to UTC (the historical behaviour)."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=_UTC)
    axis_tz = display_tz or _UTC
    out = []
    for name, tz, oh, ch in SESSIONS:
        z = ZoneInfo(tz)
        day = now_utc.astimezone(z).date()
        o = datetime.combine(day, dtime(oh), tzinfo=z).astimezone(axis_tz)
        c = datetime.combine(day, dtime(ch), tzinfo=z).astimezone(axis_tz)
        oh_u = o.hour + o.minute / 60.0
        ch_u = c.hour + c.minute / 60.0
        segs = [(oh_u, ch_u)] if oh_u <= ch_u else [(oh_u, 24.0), (0.0, ch_u)]
        out.append({"name": name, "flag": FLAGS.get(name, ""),
                    "open": _is_open(now_utc, tz, oh, ch), "segs": segs})
    return out


def fmt_countdown(seconds: int) -> str:
    """Seconds → compact 'Hh Mm' (or 'Mm' under an hour)."""
    if seconds < 0:
        seconds = 0
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
