#!/usr/bin/env bash
# Remove Plexarchy from Omarchy. Pass --purge to also delete credentials and caches.
set -euo pipefail

PLUGIN_ID="community.plexarchy"
PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/$PLUGIN_ID"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/plexarchy"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/plexarchy"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

if [ -x "$PLUGIN_DIR/bin/plexarchy" ]; then
  log "Stopping playback and reporting the session as stopped to Plex"
  "$PLUGIN_DIR/bin/plexarchy" shutdown >/dev/null 2>&1 || true
fi

log "Disabling the bar widget"
omarchy plugin disable "$PLUGIN_ID" >/dev/null 2>&1 || true

if [ -L "$PLUGIN_DIR" ]; then
  rm -f "$PLUGIN_DIR"
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  log "Removed symlink $PLUGIN_DIR"
elif [ -d "$PLUGIN_DIR" ]; then
  omarchy plugin remove "$PLUGIN_ID" --yes || rm -rf "$PLUGIN_DIR"
fi

if [ "${1:-}" = "--purge" ]; then
  log "Deleting Plex credentials and caches"
  rm -rf "$CONFIG_DIR" "$CACHE_DIR"
else
  echo "Kept $CONFIG_DIR (Plex token) and $CACHE_DIR (artwork cache). Re-run with --purge to delete them."
fi
