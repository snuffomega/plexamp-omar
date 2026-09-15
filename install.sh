#!/usr/bin/env bash
# Install or update Plexarchy for Omarchy 4 (Quattro). Safe to re-run.
set -euo pipefail

PLUGIN_ID="community.plexarchy"
REPO_URL="${PLEXARCHY_REPO:-https://github.com/YOUR_GITHUB_USER/plexarchy.git}"
PLUGIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/$PLUGIN_ID"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECTION="${PLEXARCHY_SECTION:-center}"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v omarchy >/dev/null 2>&1 || die "omarchy CLI not found. Plexarchy requires Omarchy 4 (Quattro)."
command -v python3 >/dev/null 2>&1 || die "python3 is required."

log "Installing dependencies (mpv, mpv-mpris)"
if command -v omarchy >/dev/null 2>&1 && omarchy pkg --help >/dev/null 2>&1; then
  omarchy pkg add mpv mpv-mpris || sudo pacman -S --needed --noconfirm mpv mpv-mpris
else
  sudo pacman -S --needed --noconfirm mpv mpv-mpris
fi

if [ -f "$SOURCE_DIR/manifest.json" ] && [ "$SOURCE_DIR" != "$PLUGIN_DIR" ]; then
  # Running from a checkout: link it so edits hot-reload in the shell.
  if [ -e "$PLUGIN_DIR" ] && [ ! -L "$PLUGIN_DIR" ]; then
    die "$PLUGIN_DIR already exists. Run: omarchy plugin remove $PLUGIN_ID"
  fi
  mkdir -p "$(dirname "$PLUGIN_DIR")"
  ln -sfn "$SOURCE_DIR" "$PLUGIN_DIR"
  log "Linked $SOURCE_DIR -> $PLUGIN_DIR"
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  omarchy plugin enable "$PLUGIN_ID" --section "$SECTION" || die "Could not enable $PLUGIN_ID"
elif [ -d "$PLUGIN_DIR/.git" ]; then
  log "Updating existing installation"
  omarchy plugin update "$PLUGIN_ID" --yes
else
  log "Adding plugin from $REPO_URL"
  omarchy plugin add "$REPO_URL" --yes
  omarchy plugin enable "$PLUGIN_ID" --section "$SECTION"
fi

chmod +x "$PLUGIN_DIR/bin/plexarchy"
log "Running self-check"
"$PLUGIN_DIR/bin/plexarchy" doctor || true

cat <<EOF

Plexarchy is installed. Click the music icon in the bar and choose
"Link Plex account" to sign in through plex.tv, then pick your server and
music library. Terminal alternative:

  $PLUGIN_DIR/bin/plexarchy login
EOF
