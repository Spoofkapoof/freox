#!/usr/bin/env bash
# Installs a "Freox" entry into your applications menu so you can launch the
# dashboard as a desktop app (its own window + icon), like any other program.
#
# The .desktop file is GENERATED here with this machine's real paths — it is
# NOT committed to the repo, so no local/home paths ever leak to GitHub.
set -e
HERE="$(dirname "$(readlink -f "$0")")"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="$APPS/Freox.desktop"

mkdir -p "$APPS"
chmod +x "$HERE/desktop_app.sh"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Freox
GenericName=Forex Cockpit
Comment=Live forex cockpit — strength, volatility, correlation, sessions
Exec=$HERE/desktop_app.sh
Icon=$HERE/assets/freox-icon.svg
Terminal=false
Categories=Office;Finance;
Keywords=forex;trading;fx;dashboard;currency;
StartupWMClass=Freox
EOF
chmod +x "$DESKTOP"

update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed: $DESKTOP"
echo "Search 'Freox' in your app menu, or run: $HERE/desktop_app.sh"
echo "To uninstall: rm \"$DESKTOP\""
