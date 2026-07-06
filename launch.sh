#!/usr/bin/env bash
# Launch the Freox dashboard on http://127.0.0.1:8502
# Creates a local virtualenv on first run, then reuses it.
set -e
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE"

if [ ! -d ".venv" ]; then
  echo "First run — creating virtualenv and installing dependencies…"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
else
  source .venv/bin/activate
fi

echo "Starting Freox — open http://127.0.0.1:8502 once it's ready. Keep this terminal open."

exec streamlit run app.py \
  --server.headless true \
  --server.address 127.0.0.1 \
  --server.port 8502 \
  --browser.gatherUsageStats false \
  --theme.base dark \
  --theme.primaryColor "#00e28a" \
  --theme.backgroundColor "#07090d" \
  --theme.secondaryBackgroundColor "#0d1017" \
  --theme.textColor "#d7dde8"
