#!/usr/bin/env bash
# Freox — view it on your PHONE (same Wi-Fi, no hosting needed).
# Serves the dashboard on your local network and prints the address to open in
# your phone's browser. Press Ctrl+C here to stop.
set -e
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE"
PORT=8502

# first run: create the local virtualenv + install dependencies
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

# detect this machine's LAN IP (the address your phone will use)
LANIP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
[ -z "$LANIP" ] && LANIP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$LANIP" ] && LANIP="<your-PC-ip>"

# If Freox is already running on this port (e.g. the desktop app, which now
# also serves the network), don't start a second server on the same port —
# just point the phone at the one that's already running.
if (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1; then
  echo
  echo "  Freox is already running on port $PORT (the desktop app, perhaps)."
  echo "  On your phone (same Wi-Fi) just open:   http://$LANIP:$PORT/?view=phone"
  echo
  echo "  (To run a separate phone-only server, close the other one first.)"
  echo
  exit 0
fi

echo
echo "  ============================================================"
echo "    On your PHONE (connected to the SAME Wi-Fi), open:"
echo
echo "        http://$LANIP:$PORT/?view=phone"
echo
echo "    Tip: browser menu -> \"Add to Home Screen\" for an app icon."
echo "    Keep this window open. Press Ctrl+C to stop."
echo "  ============================================================"
echo

# serve on ALL interfaces (0.0.0.0) so other devices on the Wi-Fi can reach it
exec ./.venv/bin/streamlit run app.py \
  --server.headless true --server.address 0.0.0.0 --server.port "$PORT" \
  --browser.gatherUsageStats false \
  --theme.base dark --theme.primaryColor "#00e28a" \
  --theme.backgroundColor "#07090d" --theme.secondaryBackgroundColor "#0d1017" \
  --theme.textColor "#d7dde8"
