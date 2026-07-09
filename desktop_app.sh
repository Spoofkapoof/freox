#!/usr/bin/env bash
# Freox — desktop app launcher.
# Starts the Streamlit server and opens it in a chrome-less browser "app" window
# (no tabs, no address bar). Closing the window shuts the server back down.
set -e
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE"
PORT=8502
URL="http://127.0.0.1:$PORT"

# --- first run: create the local virtualenv + install dependencies ---
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

# --- start the dashboard server in the background ---
# Bind to 0.0.0.0 (all interfaces), NOT just localhost, so the SAME server that
# powers this desktop window is also reachable from your phone on the same Wi-Fi
# (http://<this-PC-ip>:PORT). One server → desktop + phone show identical live
# data, both auto-refreshing. The window below still connects via 127.0.0.1.
./.venv/bin/streamlit run app.py \
  --server.headless true --server.address 0.0.0.0 --server.port "$PORT" \
  --browser.gatherUsageStats false \
  --theme.base dark --theme.primaryColor "#00e28a" \
  --theme.backgroundColor "#07090d" --theme.secondaryBackgroundColor "#0d1017" \
  --theme.textColor "#d7dde8" >/dev/null 2>&1 &
SERVER_PID=$!

# stop the server whenever this script exits (i.e. when the window is closed)
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

# --- wait for the server to accept connections (up to ~30s) ---
for _ in $(seq 1 120); do
  (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1 && break
  sleep 0.25
done

# --- open the chrome-less app window (blocks until the window is closed) ---
# A dedicated user-data-dir keeps this separate from your normal browser and
# guarantees its own window (so closing it cleanly ends the app).
# Sized to a phone (iPhone 12/13/14/15 = 390x844, the most common viewport) so
# it opens as the mobile layout — a phone app on your desktop.
APP_PROFILE="${XDG_DATA_HOME:-$HOME/.local/share}/freox-app"
PHONE_W=390
PHONE_H=844
CHROME="$(command -v chromium || command -v chromium-browser \
  || command -v google-chrome-stable || command -v google-chrome \
  || command -v brave || command -v brave-browser || true)"

if [ -n "$CHROME" ]; then
  # ?view=phone → the app renders its phone layout (this window mimics a phone)
  "$CHROME" --app="$URL/?view=phone" --class=Freox --name=Freox \
    --user-data-dir="$APP_PROFILE" \
    --window-size="$PHONE_W,$PHONE_H" --window-position=120,60 \
    >/dev/null 2>&1
else
  # No Chromium-family browser found — fall back to the default browser and
  # keep the server alive until you Ctrl+C this terminal.
  echo "Freox is running at $URL  (Ctrl+C here to stop)"
  xdg-open "$URL" >/dev/null 2>&1 || true
  wait "$SERVER_PID"
fi
