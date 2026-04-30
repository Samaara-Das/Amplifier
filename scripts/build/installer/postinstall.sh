#!/bin/bash
# Mac postinstall: register LaunchAgent so Amplifier auto-starts at login.
# This script is placed in scripts/build/installer/scripts/ and invoked by
# the macOS installer (pkgbuild --scripts ...) after the payload is installed.
# build_mac_installer.sh runs chmod +x on this file before invoking pkgbuild.

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/com.pointcapitalis.amplifier.plist"

mkdir -p "$PLIST_DIR"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pointcapitalis.amplifier</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/Amplifier.app/Contents/MacOS/Amplifier</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF

# Load the LaunchAgent for the current login session (errors are non-fatal)
launchctl load -w "$PLIST" 2>/dev/null || true

exit 0
