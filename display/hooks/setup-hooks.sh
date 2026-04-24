#!/usr/bin/env bash
# setup-hooks.sh — Wire lobster-status into OpenClaw (Claude Code) hooks.
#
# Run as the user who will be running OpenClaw (NOT as root):
#   bash ~/LCDlobster/display/hooks/setup-hooks.sh

set -euo pipefail

HOOKS_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/openclaw.json"
CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"

if [ ! -f "$HOOKS_SRC" ]; then
    echo "ERROR: hooks file not found at $HOOKS_SRC" >&2
    exit 1
fi

mkdir -p "$CLAUDE_DIR"

if [ -f "$SETTINGS" ]; then
    echo "Existing $SETTINGS found."
    echo ""
    echo "Add this block manually under the top-level object:"
    echo ""
    cat "$HOOKS_SRC"
    echo ""
    echo "Or back up and replace:"
    echo "  cp $SETTINGS ${SETTINGS}.bak"
    echo "  cp $HOOKS_SRC $SETTINGS"
else
    cp "$HOOKS_SRC" "$SETTINGS"
    echo "Hooks installed to $SETTINGS"
    echo ""
    echo "OpenClaw will now send raccoon state updates automatically:"
    echo "  PreToolUse  → working / building"
    echo "  PostToolUse → thinking"
    echo "  Stop        → idle"
fi

echo ""
echo "Test the display right now:"
echo "  lobster-status thinking"
echo "  lobster-status idle"
