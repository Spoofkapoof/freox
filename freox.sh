#!/usr/bin/env bash
# Freox — one command to run the dashboard on your computer AND your phone.
#
#   ./freox.sh
#
# Serves Freox on your local network (one server → PC + phone, same live data)
# and prints a QR code you scan with your phone. Press Ctrl+C to stop.
set -e
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE"
PORT=8502

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
  echo "    Keep this window open. Press Ctrl+C to stop."
  echo
}

# --- already running on this port? just show how to reach it and exit ---
if (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1; then
  echo "  Freox is already running on port $PORT."
  show_banner
  echo "  (To restart it, stop the other one first.)"
  exit 0
fi

# --- start the server on ALL interfaces (0.0.0.0) so the phone can reach it ---
./.venv/bin/streamlit run app.py \
  --server.headless true --server.address 0.0.0.0 --server.port "$PORT" \
  --browser.gatherUsageStats false \
  --theme.base dark --theme.primaryColor "#00e28a" \
  --theme.backgroundColor "#07090d" --theme.secondaryBackgroundColor "#0d1017" \
  --theme.textColor "#d7dde8" >/dev/null 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# --- wait until it's actually listening, then show the QR banner ---
for _ in $(seq 1 120); do
  (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1 && break
  sleep 0.25
done
show_banner

wait "$SERVER_PID"
