# Security

## Credentials

Account linking stores the plex.tv account token, the selected server's URL and
server access token, a persistent random client identifier, and the selected
music library in `${XDG_CONFIG_HOME:-~/.config}/plexarchy/config.json`. While a
PIN sign-in is pending, its id and one-time code are kept in the same private
file and removed on completion, cancellation, or expiry (15 minutes). The
directory is created with mode `0700` and the file with mode `0600`. Credentials
are never stored in this repository or in `shell.json`.

Local configuration and cache operations are bound to opened directory file
descriptors. Symlinked path components, files not owned by the current user,
group- or world-accessible files, and oversized payloads are rejected. Updates
are written to private, exclusively created temporary files and atomically
replaced within the same verified directory.

The PIN login exchanges its one-time code directly with `plex.tv`. The resulting
token is sent only to Plex, the configured Plex server, and the local mpv process.
Plexarchy passes it to mpv as a file-local HTTP header over a user-owned Unix
socket; it is not included in process arguments, playback URLs, or MPRIS metadata,
and unrelated URLs opened in mpv do not inherit it. API, timeline, and cover-art
requests also use headers instead of credential-bearing URLs and reject redirects
to a different origin. Cover art and
last-good library payloads are stored in
`${XDG_CACHE_HOME:-~/.cache}/plexarchy`, whose size and age are
bounded automatically. Demo mode does not read credentials or contact Plex.

Use an HTTPS Plex server URL whenever possible. TLS certificates are verified
with the system trust store, and credential-bearing API and timeline redirects
are restricted to the original scheme, host, and port. Plain HTTP exposes the
token to anyone able to observe that network path and should only be used on a
trusted private network or through an encrypted tunnel such as Tailscale.
Manual token entry uses a non-echoing prompt; tokens are intentionally rejected
as command-line arguments because process listings and shell history are not
private credential stores.

The in-panel Plex power switch intentionally preserves the server URL, token,
client identifier, and selected library in the same private configuration file.
While switched off, Plexarchy stops playback and timeline reporting and does not
make Plex API, health, artwork, or library requests. Use `plexarchy logout` when
the stored credentials should be removed instead of temporarily disabled.

As with every Omarchy shell plugin, the QML and helper execute unsandboxed as
the logged-in user. Review updates before accepting them.

## Reporting a vulnerability

Please open a private GitHub security advisory instead of a public issue. Do
not include Plex tokens, server addresses, or library contents in reports.
