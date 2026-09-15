# Plexarchy

Plex music for the **Omarchy 4 (Quattro)** bar. A native Quickshell/QML
bar widget with an attached player panel: browse your Plex music library,
search, open artists, albums and playlists, manage the queue, and play locally
through mpv — all inside `omarchy-shell`, following the active theme and font.

Plexarchy is an adaptation of [Tunarchy](https://github.com/flathack/omarchy-tunarchy)
(MIT, © flathack), rebuilt around plex.tv account linking with automatic server
discovery, an in-panel setup flow, inline bar transport controls, and a headless
QML test harness. It is not affiliated with Plex, Inc.

## What you get

**Bar widget**

- Album cover (or a music glyph) plus *track title* and *artist* in the bar
- Inline previous · play/pause · next buttons (`showBarControls`, on by default)
- Left-click opens the panel · middle-click play/pause · scroll previous/next ·
  right-click opens the terminal token fallback
- Collapses to a single icon slot when nothing is loaded; works on top, bottom,
  and vertical bars

**Attached panel**

- Header with artwork, title, artist · album, seek bar, and volume slider
  (system output via PipeWire by default, or mpv-local 0–130 %)
- Transport row: shuffle, previous, play/pause, next, repeat (off/all/one)
- Views: Home (recently added), Artists → albums → tracks, Albums, Playlists,
  Recent (history), Top, Favourites, Queue, and live search
- Queue: play, play-next, reorder, remove, clear upcoming; the playing row is marked
- Full keyboard navigation (F1 shows the map), Esc closes, Ctrl+Space toggles

**Playback engine**

- One private `mpv` process (IPC socket in `~/.cache/plexarchy/`) shared by every
  monitor and every panel opening — the widget only talks to it, it never owns it
- Gapless queue handling, seek, volume, shuffle, repeat
- Hardware media keys and desktop controls through `mpv-mpris`
- Plex timeline reporting (playing/paused/stopped + progress) so the Plex
  dashboard and “Continue listening” stay correct
- Queue and settings survive shell restarts; stale sockets are recovered

**Account and server**

- **PIN linking**: click *Link Plex account* → the panel shows a 4-letter code and
  opens `plex.tv/link` in your browser. No password or token is ever typed into
  the plugin.
- **Server discovery**: every server on the account is listed with reachability
  probes; local, non-relay, HTTPS connections are preferred automatically
- **Library selection**: single music library is chosen for you, several are
  offered as a list
- **Recovery**: if the server address or token changes (DHCP, remote → local,
  token rotation) the health check re-resolves it from plex.tv without asking you
  to re-link; expired sessions offer a one-click re-link
- Credentials live in a mode-`0600` file outside the plugin directory; the token
  reaches mpv as an HTTP header, never as a URL or argument

## Requirements

- Omarchy 4.0 / Quattro with the plugin-based `omarchy-shell`
- `mpv` and `mpv-mpris` (`omarchy pkg add mpv mpv-mpris`)
- Python ≥ 3.10 (standard library only)
- A Plex account with access to a Plex Media Server that has a music library

## Install

```bash
omarchy plugin add https://github.com/YOUR_GITHUB_USER/plexarchy.git --yes
omarchy pkg add mpv mpv-mpris
omarchy plugin enable community.plexarchy --section center
```

Or use the bundled script (installs dependencies, links or clones the plugin,
enables it, and runs `doctor`):

```bash
git clone https://github.com/YOUR_GITHUB_USER/plexarchy.git
cd plexarchy && ./install.sh
```

Running `./install.sh` from a checkout symlinks it into
`~/.config/omarchy/plugins/community.plexarchy` so edits hot-reload. Set
`PLEXARCHY_SECTION=right` to change the bar section. Move it later with
`omarchy bar move community.plexarchy --section right`.

Your existing `shell.json`, theme, and bar layout are untouched: enabling adds a
single `{ "id": "community.plexarchy" }` entry to the chosen section.

### Connect Plex

1. Click the music icon in the bar → **Link Plex account**.
2. Approve the device in the browser that opens (or enter the code at
   [plex.tv/link](https://plex.tv/link)).
3. Pick your server from the list (unreachable servers are greyed out), then the
   music library if the server has more than one.

Terminal alternatives:

```bash
P=~/.config/omarchy/plugins/community.plexarchy/bin/plexarchy
$P login                 # PIN flow with server discovery
$P login --server https://plex.example.net:32400   # PIN flow, fixed server
$P configure             # manual token entry (non-echoing prompt)
$P doctor                # runtime + config self-check
```

Open **Settings** (gear icon or F1) in the panel to change the server or
library, switch the volume slider target, or unlink the account.

## Update

```bash
omarchy plugin update community.plexarchy      # shows a diff, fast-forwards
# or, for a symlinked checkout:
git -C ~/.config/omarchy/plugins/community.plexarchy pull && omarchy-shell shell rescanPlugins
```

Saving files in the plugin directory hot-reloads the widget; the mpv session
keeps playing across reloads and shell restarts.

## Uninstall

```bash
~/.config/omarchy/plugins/community.plexarchy/uninstall.sh          # keeps credentials + cache
~/.config/omarchy/plugins/community.plexarchy/uninstall.sh --purge  # removes them too
```

Manual equivalent: `bin/plexarchy shutdown`, `omarchy plugin remove
community.plexarchy`, then optionally delete `~/.config/plexarchy` and
`~/.cache/plexarchy`.

## Configuration

Inline options on the widget entry (also in **Setup › Plugins**):

```bash
omarchy bar set community.plexarchy showBarControls false --json
omarchy bar set community.plexarchy recentAlbumCount 30
omarchy bar set community.plexarchy libraryItemCount 150
omarchy bar set community.plexarchy volumeMode Plex
omarchy bar set community.plexarchy demoMode true --json   # fictional library, no Plex, no mpv
```

## Theming

The widget uses only Omarchy tokens: `Color.foreground/accent/urgent`,
`Color.popups.*`, `Style.font.*`, `Style.space()`, `Style.spacing.*`,
`Style.cornerRadius`, `Border.controlSpec()` via `BorderSurface`, and the shared
`KeyboardPanel`, `WidgetButton`, `PanelActionButton`, `PanelSlider`,
`CursorSurface`, and `TextField` components from `qs.Ui`. Theme and font changes
(`omarchy theme set`, `omarchy font set`, `[font] base-size`, `[spacing] scale`)
apply live without a restart.

## Architecture

```
Panel.qml        Quickshell/QML bar widget + attached KeyboardPanel (UI, keyboard, state)
Model.js         Pure view helpers (formatting, navigation state) — unit tested with node
bin/plexarchy    Dependency-free Python helper: Plex API, plex.tv linking, mpv IPC,
                 queue/state persistence, timeline reporting, artwork cache
mpv              Single long-lived audio process, controlled over a Unix socket;
                 mpv-mpris exposes it to media keys
```

The QML side never holds credentials; every Plex or mpv action is a short helper
invocation that prints JSON. Status is polled every 3 s while the panel is open
and slower when closed. Library responses are cached so the panel stays usable
when the server is briefly offline.

## Testing

```bash
python3 -m unittest discover -s tests -v   # 150+ helper, linking, QML-contract and e2e tests
node --test tests/test_model.js
python3 tests/validate_manifest.py
qmlformat Panel.qml > /dev/null            # QML syntax
python3 tests/qml-harness/run.py           # headless Panel.qml run (needs qml + mpv)
```

`tests/test_e2e.py` runs the real helper CLI and a real `mpv` (null audio
output) against `tests/fake_plex.py`, a fake plex.tv + Plex Media Server. It
covers PIN linking, server discovery, library selection, browsing, search,
playlists, playback, pause/next/seek/shuffle/repeat/volume, play-next queueing,
timeline reporting, token-rotation recovery, shutdown, and logout.

`tests/qml-harness/` loads the actual `Panel.qml` in Qt's `qml` runtime
(offscreen) with a fake bar and stub `Quickshell` modules while using the real
`qs.Ui` widgets and `Border` token code from Omarchy. It walks the complete UI
flow — link → server → library → browse → play → pause → next → queue → settings
→ change server → close — with 31 assertions.

### Validation status

**Verified in CI-style tests here (no Omarchy desktop available):**
helper logic, plex.tv linking, server discovery, library selection, mpv playback
and controls, Plex timeline reporting, connection recovery, queue editing, QML
parse/format, QML behaviour under the `qml` runtime with stubbed Quickshell.

**Remaining desktop checks (run on a real Omarchy 4 machine):**

1. `omarchy plugin validate .` and `omarchy plugin enable community.plexarchy`
   — widget appears in the chosen section, bar layout otherwise unchanged.
2. Click the icon → panel anchors under the widget (top/bottom/vertical bars),
   uses the theme's popup colors/border; `omarchy theme set <other>` and
   `omarchy font set <other>` update it live.
3. Link → approve in browser → server list → library → Home view loads artwork.
4. Play an album; the bar shows cover + title + artist and the inline controls
   work; the panel seek/volume sliders track mpv; `playerctl play-pause` and
   media keys toggle playback (mpv-mpris); Plex dashboard shows the session.
5. Open the panel on a second monitor: same track/queue, no second mpv
   (`pgrep -a mpv` shows one `--title=Plexarchy` process).
6. `omarchy-restart-shell` while playing: audio continues, widget reconnects.
7. Disconnect from the network for a minute: panel shows an actionable error with
   Retry; reconnect and it recovers (health re-resolves the server from plex.tv).
8. `./uninstall.sh` removes the widget without touching other `shell.json` entries.

## License

MIT. Includes code from Tunarchy © 2026 flathack (MIT); see `LICENSE`.
