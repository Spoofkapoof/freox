# Changelog

All notable changes to Freox are documented here. Versioning is loose while in beta.

## [0.3] — 2026-07-08 · beta

### Added
- **FX session clock** — a strip showing which sessions (Sydney / Tokyo / London / New York)
  are live, a **London–New York overlap** (peak-liquidity) call-out, and a countdown to the
  next open/close. DST-accurate per financial centre (`zoneinfo`) and weekend-aware.
- **Correlation matrix** — 34-day rolling correlation of daily returns across the watchlist,
  **grouped by currency** (USD pairs first, base-side apart from quote-side) so the
  positive/negative blocks read as clean quadrants. Diverging amber/blue palette.
- **Per-pair live-activity dot** — today's range vs the pair's average, right of the pair name.
- **⚙ Settings popover + GitHub link** in the header — timeframes, strength window, auto-refresh,
  news impact, and force-refresh consolidated behind a gear icon (replacing the sidebar).

### Changed
- **Fibonacci-tuned throughout** — trend is now a **21/55/89** EMA ribbon (was 20/50/100), ATR
  uses **13** (was 14), heat/correlation windows use **13/34**, and activity thresholds sit on the
  Fibonacci retracement ratios **0.382 / 0.618 / 0.786**.
- **Trend heatmap → Volatility heatmap** — the grid now shows how hot each pair is running *right
  now* (recent range ÷ ATR, self-normalised) instead of restating the trend arrows. Rendered as an
  HTML table so it updates in place with **no canvas flicker**.
- **Stronger trend confirmation** — a "strong" arrow (▲▲/▼▼) now requires three EMAs aligned, not two.
- **Live 5-second refresh** (was 30s) with in-place updates and a subtle **number-roll animation** on
  values that actually change; the whole board fades in softly instead of hard-flickering.

### Fixed
- Changing the refresh rate no longer wipes the watchlist (the run-every reconciliation is now done
  after all widgets render, so no widget state is garbage-collected).
- Pair-monitor sort now sinks no-data rows to the bottom in **both** sort directions.

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
