#!/bin/bash
# Yatagarasu installer - sets up launchd jobs for automated sweeps
# Run: bash ~/Tools/yatagarasu/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_DIR="$HOME/Library/LaunchAgents"
PYTHON="/opt/anaconda3/bin/python3"

echo "=== Yatagarasu Installer ==="

# 1. Install Python deps
echo "[1/4] Installing Python dependencies..."
$PYTHON -m pip install pyyaml --quiet 2>/dev/null || echo "pyyaml already installed"

# 2. Make scripts executable
chmod +x "$SCRIPT_DIR/run.sh"
chmod +x "$SCRIPT_DIR/yatagarasu.py"

# 3. Create Obsidian digest directory
DIGEST_DIR="$HOME/Documents/Obsidian Vault/00 - Command Center/Yatagarasu"
mkdir -p "$DIGEST_DIR"
echo "[2/4] Digest directory: $DIGEST_DIR"

# 4. Create launchd plists
echo "[3/4] Creating launchd jobs..."

# Morning sweep (6:30 AM) - full
cat > "$PLIST_DIR/com.yatagarasu.morning.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yatagarasu.morning</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/run.sh</string>
        <string>full</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/yatagarasu.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/yatagarasu.log</string>
</dict>
</plist>
EOF

# Midday sweep (12:30 PM) - light
cat > "$PLIST_DIR/com.yatagarasu.midday.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yatagarasu.midday</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/run.sh</string>
        <string>light</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>12</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/yatagarasu.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/yatagarasu.log</string>
</dict>
</plist>
EOF

# Evening sweep (6:30 PM) - light
cat > "$PLIST_DIR/com.yatagarasu.evening.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yatagarasu.evening</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/run.sh</string>
        <string>light</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/yatagarasu.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/yatagarasu.log</string>
</dict>
</plist>
EOF

# 5. Load the jobs
echo "[4/4] Loading launchd jobs..."
launchctl load "$PLIST_DIR/com.yatagarasu.morning.plist" 2>/dev/null || true
launchctl load "$PLIST_DIR/com.yatagarasu.midday.plist" 2>/dev/null || true
launchctl load "$PLIST_DIR/com.yatagarasu.evening.plist" 2>/dev/null || true

echo ""
echo "=== Yatagarasu installed ==="
echo "Schedule: 6:30am (full), 12:30pm (light), 6:30pm (light)"
echo "Digests:  $DIGEST_DIR"
echo "Logs:     $SCRIPT_DIR/yatagarasu.log"
echo ""
echo "Manual run:  cd $SCRIPT_DIR && bash run.sh full"
echo "Dry run:     cd $SCRIPT_DIR && source .env && python3 yatagarasu.py --dry-run"
echo "Sources only: cd $SCRIPT_DIR && source .env && python3 yatagarasu.py --sources-only"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/com.yatagarasu.*.plist"
echo "  rm ~/Library/LaunchAgents/com.yatagarasu.*.plist"
