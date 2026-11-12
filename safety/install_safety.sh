#!/bin/bash
# Installs the ROOT-OWNED copy of the robot-safety layer into /etc/claude-code
# (Claude Code "managed settings"). Claude cannot modify these files without your sudo password.
# Run it yourself, from your own terminal:
#     sudo bash ~/catkin_ws/env/safety/install_safety.sh
# Re-run after you change robot_allowlist.txt (e.g. to approve a new read-only command).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
DST=/etc/claude-code

# sanity: the guard must pass its own tests before it is installed
python3 -I "$SRC/test_guard.py" > /tmp/guard_test.out || { cat /tmp/guard_test.out; echo "Self-test FAILED, not installing."; exit 1; }
tail -1 /tmp/guard_test.out

install -d -m 755 -o root -g root "$DST"
install -m 755 -o root -g root "$SRC/robot_safety_guard.py" "$DST/robot_safety_guard.py"
install -m 644 -o root -g root "$SRC/robot_allowlist.txt"   "$DST/robot_allowlist.txt"
if [ -e "$DST/managed-settings.json" ] && ! cmp -s "$SRC/managed-settings.json" "$DST/managed-settings.json"; then
    cp "$DST/managed-settings.json" "$DST/managed-settings.json.bak.$(date +%s)"
    echo "Existing managed-settings.json backed up."
fi
install -m 644 -o root -g root "$SRC/managed-settings.json" "$DST/managed-settings.json"
python3 -c "import json;json.load(open('$DST/managed-settings.json'))" && echo "managed-settings.json is valid JSON"
ls -l "$DST"
echo
echo "Installed. Start a NEW Claude Code session so it is picked up."
