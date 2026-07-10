#!/usr/bin/env bash
# Freox desktop app — thin wrapper. The desktop cockpit window is now launched by
# freox.sh (one launcher for the desktop window + phone serving). This is kept so
# the installed app-menu entry (install-desktop-app.sh) keeps working.
exec "$(dirname "$(readlink -f "$0")")/freox.sh" "$@"
