#!/usr/bin/env bash
# Freox — one command: open the cockpit as a desktop app window AND serve it to
# your phone on the same Wi-Fi (one server, identical live data). Prints a QR
# code you scan with your phone.
#
#   ./freox.sh              # open the desktop cockpit window + serve the phone
#   ./freox.sh --no-window  # serve only (phone / headless) — no desktop window
#
# Close the window (or press Ctrl+C) to stop.
set -e
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE"
PORT=8502
OPEN_WINDOW=1
[ "$1" = "--no-window" ] && OPEN_WINDOW=0

# --- first run: create the local virtualenv + install dependencies ---
if [ ! -d ".venv" ]; then
  echo "First run — setting up (creating virtualenv, installing dependencies)…"
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi
PY="./.venv/bin/python"

# --- find this machine's LAN IP (the address your phone connects to) ---
LANIP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
[ -z "$LANIP" ] && LANIP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$LANIP" ] && LANIP="<your-PC-ip>"
PC_URL="http://127.0.0.1:$PORT"
PHONE_URL="http://$LANIP:$PORT/?view=phone"
APP_URL="$PC_URL/?view=phone"   # the desktop window loads the phone cockpit

# --- print the URLs + a scannable QR for the phone ---
show_banner() {
  echo
  echo "  ────────────────────────────────────────────────────────────"
  echo "    FREOX is running."
  echo
  echo "    On this computer:   $PC_URL"
  echo "    On your PHONE:      $PHONE_URL"
  echo "    (phone must be on the same Wi-Fi)"
  echo "  ────────────────────────────────────────────────────────────"
  echo
  echo "    Scan this with your phone camera:"
  echo
  "$PY" - "$PHONE_URL" <<'PYQR' || echo "    (QR unavailable — just type the URL above)"
import sys, qrcode
qr = qrcode.QRCode(border=2)
qr.add_data(sys.argv[1]); qr.make(fit=True)
qr.print_ascii(invert=True)
PYQR
  echo "    Tip: on the phone, browser menu → \"Add to Home Screen\" for an app icon."
  echo
}

# --- open the chrome-less desktop cockpit window (390x844 phone frame) ---------
# A dedicated user-data-dir keeps it separate from your normal browser and gives
# it its own window, so closing it cleanly ends the app. Returns 0 if a Chromium
# window was opened (blocks until it's closed), 1 if it fell back to the default
# browser (does NOT block).
open_desktop_window() {
  local profile="${XDG_DATA_HOME:-$HOME/.local/share}/freox-app"
  local chrome
  chrome="$(command -v chromium || command -v chromium-browser \
    || command -v google-chrome-stable || command -v google-chrome \
    || command -v brave || command -v brave-browser || true)"
  if [ -n "$chrome" ]; then
    "$chrome" --app="$APP_URL" --class=Freox --name=Freox \
      --user-data-dir="$profile" \
      --window-size=390,844 --window-position=120,60 >/dev/null 2>&1 || true
    return 0
  fi
  echo "    (no Chromium-family browser found — opening your default browser)"
  xdg-open "$PC_URL" >/dev/null 2>&1 || true
  return 1
}

# --- start the server if it isn't already running -----------------------------
WE_STARTED=0
if (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1; then
  echo "  Freox is already running on port $PORT — reusing it."
else
  ./.venv/bin/streamlit run app.py \
    --server.headless true --server.address 0.0.0.0 --server.port "$PORT" \
    --browser.gatherUsageStats false \
    --theme.base dark --theme.primaryColor "#00e28a" \
    --theme.backgroundColor "#07090d" --theme.secondaryBackgroundColor "#0d1017" \
    --theme.textColor "#d7dde8" >/dev/null 2>&1 &
  SERVER_PID=$!
  WE_STARTED=1
  # stop the server when this script exits — but only if WE started it
  cleanup() { [ "$WE_STARTED" = 1 ] && kill "$SERVER_PID" 2>/dev/null || true; }
  trap cleanup EXIT INT TERM
  # wait until it's actually listening
  for _ in $(seq 1 120); do
    (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1 && break
    sleep 0.25
  done
fi

show_banner

# --- open the desktop cockpit window (unless --no-window) ----------------------
if [ "$OPEN_WINDOW" = 1 ]; then
  echo "    Opening the desktop cockpit window… (close it to stop)"
  echo
  if open_desktop_window; then
    :                                   # window closed → fall through to cleanup
  else
    [ "$WE_STARTED" = 1 ] && wait "$SERVER_PID"   # fallback: keep serving
  fi
else
  echo "    Serving only (no desktop window). Press Ctrl+C to stop."
  echo
  [ "$WE_STARTED" = 1 ] && wait "$SERVER_PID"
fi
