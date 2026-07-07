# Changelog

All notable changes to Freox are documented here. Versioning is loose while in beta.

## [0.2.1] — 2026-07-07 · beta

### Added
- **Top Setups** panel — shortlists the pairs whose timeframes are aligned (the highest-conviction
  long/short setups), derived from the trend data.
- Settings now **survive a hard page refresh** — watchlist, timeframes, sort, filters, and strength
  window persist via URL query params (also makes the view shareable/bookmarkable).

### Changed
- **"Trend breadth" KPI → "Market Activity"** — measures how much the market is actually moving
  (today's range vs average daily range) rather than trend direction, since in FX you trade both ways.
- Each window consolidated into a single bordered box (title + controls + content together).
- Next High-Impact KPI shows the next 3 events left→right; Economic Calendar rows are fully clickable.
- Watchlist dropdown centered under its button.

### Fixed / Efficiency
- **~⅓ fewer network calls** — a short OHLC memo cache dedupes the shared H1/H4 and daily fetches;
  currency-strength reuses the cached daily data.
- Data cache TTL aligned to the 30s refresh so data + timestamp move in lockstep.
- Verified accuracy end-to-end (prices ~99.8% vs independent sources, ATR exact, strength correct);
  confirmed the daily-change convention (live vs prior daily close) and documented the
  `chartPreviousClose` range-dependency trap.

## [0.2.0] — 2026-07-06 · beta

### Changed
- **Consolidated layout** — each window (Pair Monitor, Trend Heatmap, Calendar, Currency
  Strength) is now a single bordered box holding its title, controls, and content together,
  instead of being scattered across separate boxes.
- **Next High-Impact KPI** now shows the next **3** high-impact events laid out left/middle/right
  (soonest → last): currency in red + countdown on one line, short news label beneath.
- **Economic Calendar rows are fully clickable** — the whole row (not just the title) opens the
  news search, with a hover highlight for a bigger tap target.

## [0.1.0] — 2026-07-06 · first beta

The first tagged beta of Freox — a single-screen live forex cockpit.

### Added
- **Command cockpit** layout (single screen, trading-terminal styling, auto-refresh).
- **KPI strip** — Strongest · Top Mover · Weakest currency box, trend breadth, next high-impact event.
- **Pair Monitor** — daily change, ATR volatility (unit-aware: pips / points / $), multi-timeframe
  trend arrows (M15/H1/H4/D1), sortable by any column.
- **Currency Strength meter** — 8-currency relative strength over 24H / 1D / 1W.
- **Trend Heatmap** — pair × timeframe grid with timeframe labels on top.
- **Economic Calendar** — Forex Factory feed, disk-cached with fallback, event news links, countdowns.
- **Watchlist picker** — grouped by Majors / Minors 1 (liquid) / Minors 2 (thin) / Metal & Crypto,
  with per-group toggle buttons. Default watchlist = the 7 majors.
- Gold (XAUUSD) and Bitcoin (BTCUSD) alongside FX.
- No API keys — data via Yahoo Finance + Forex Factory. Runs on free tiers.

### Notes
- **Beta / work in progress** — features change, data may be delayed or wrong, not for live trading.
