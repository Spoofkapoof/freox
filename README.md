# Freox

An all-in-one live foreign-exchange cockpit. A single-screen dashboard that shows
currency strength, per-pair trend across multiple timeframes, per-pair volatility,
and this week's economic calendar — with no API keys required.

> **Status: work in progress.** Freox is under active development. Expect rough
> edges and changing features. It is a monitoring/research tool, not trading
> software — see the disclaimer below.

## Features

- **Currency strength meter** — relative strength of the 8 major currencies over a
  selectable window (24H / 1D / 1W), computed across the 28 major pairs.
- **Pair monitor** — daily change, volatility (ATR in the instrument's native unit),
  and trend arrows for M15 / H1 / H4 / D1. Sortable ascending/descending by any column.
- **Trend heatmap** — pair × timeframe grid to spot when a trend is aligned across
  all timeframes.
- **Economic calendar** — this week's events with impact rating and a live countdown;
  each event links out to a news search. Cached to disk so a rate-limited source
  never blanks the panel.
- **Extra instruments** — gold (XAUUSD) and Bitcoin (BTCUSD) alongside the FX majors.
- **Trading-terminal UI** — dense, dark, monospace, auto-refreshing in place.

## Data sources

- **Prices / OHLC:** Yahoo Finance (indicative mid quotes).
- **Economic calendar:** Forex Factory weekly feed.

No accounts or API keys are needed.

## Requirements

- Python 3.10+

## Run

```bash
bash launch.sh
```

On first run this creates a local virtualenv and installs dependencies, then starts
the dashboard. Open <http://127.0.0.1:8502> when it says it's ready.

To run it manually instead:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8502
```

## Project layout

```
app.py          Streamlit cockpit (UI + layout)
data_feed.py    Price + economic-calendar fetching, disk cache
indicators.py   Trend, ATR volatility, currency-strength math
launch.sh       One-command launcher
requirements.txt
```

## Roadmap

- Price sparklines in the monitor
- Alerts (trend flip / imminent high-impact event)
- Per-pair candlestick detail view
- Configurable watchlists / layouts

## Disclaimer

Freox is for monitoring and research only. Prices are indicative mid quotes from a
free source, are not real-time broker quotes, and must not be used for trade
execution. Nothing here is financial advice.
