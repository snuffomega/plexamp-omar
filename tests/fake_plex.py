"""Fake plex.tv + Plex Media Server used by the end-to-end tests and the QML harness.

Serves a tiny music library with real (silent) WAV tracks so mpv can play them.
"""
from __future__ import annotations

import http.server
import json
import struct
import threading
import urllib.parse
import zlib

def make_png() -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes([245, 185, 66]) * 16 for _ in range(16))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = make_png()


def silent_wav(seconds: float = 4.0, rate: int = 8000) -> bytes:
    frames = int(seconds * rate)
    data = b"\x00\x00" * frames
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data))
    return header + data


ARTISTS = [("100", "Aurora Fields"), ("200", "Night Cartographers")]
ALBUMS = [("110", "100", "Slow Light", 2021), ("120", "100", "Meridian", 2023), ("210", "200", "Paper Maps", 2019)]
TRACKS = []
for album_key, artist_key, album_title, _ in ALBUMS:
    for index in range(1, 4):
        TRACKS.append((f"{album_key}{index}", album_key, artist_key, f"{album_title} {index}", index))


def artist_title(key):
    return dict(ARTISTS)[key]


def album_row(album):
    key, artist_key, title, year = album
    return {"ratingKey": key, "key": f"/library/metadata/{key}/children", "type": "album", "title": title,
            "parentTitle": artist_title(artist_key), "parentRatingKey": artist_key, "year": year,
            "thumb": f"/library/metadata/{key}/thumb/1", "leafCount": 3, "addedAt": 1700000000 + int(key)}


def track_row(track):
    key, album_key, artist_key, title, index = track
    album = next(a for a in ALBUMS if a[0] == album_key)
    return {"ratingKey": key, "key": f"/library/metadata/{key}", "type": "track", "title": title,
            "parentTitle": album[2], "parentRatingKey": album_key, "grandparentTitle": artist_title(artist_key),
            "grandparentRatingKey": artist_key, "index": index, "duration": 4000, "viewCount": index,
            "userRating": 10 if index == 1 else 0, "parentThumb": f"/library/metadata/{album_key}/thumb/1",
            "Media": [{"Part": [{"key": f"/library/parts/{key}/file.wav", "container": "wav"}]}]}


def artist_row(artist):
    key, title = artist
    return {"ratingKey": key, "key": f"/library/metadata/{key}/children", "type": "artist", "title": title,
            "thumb": f"/library/metadata/{key}/thumb/1"}


class State:
    def __init__(self):
        self.polls_before_auth = 1
        self.pin_polls = 0
        self.timelines: list[dict] = []
        self.requests: list[str] = []
        self.tokens_seen: set[str] = set()
        self.server_token = "server-token"
        self.account_token = "account-token"
        self.machine = "fake-machine-1"
        self.base_url = ""
        self.libraries = [{"key": "4", "title": "Music", "type": "artist"}]
        self.reject_server_token = False


class Handler(http.server.BaseHTTPRequestHandler):
    state: State = None  # set by serve()

    def log_message(self, *args):
        pass

    def reply(self, payload, status=200, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        state = self.state
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        path = parsed.path
        state.requests.append(path)
        token = self.headers.get("X-Plex-Token", "") or (query.get("X-Plex-Token") or [""])[0]
        if token:
            state.tokens_seen.add(token)

        # --- plex.tv ---
        if path == "/api/v2/pins":
            return self.reply({"id": 7, "code": "QWER"}, 201)
        if path == "/api/v2/pins/7":
            state.pin_polls += 1
            done = state.pin_polls > state.polls_before_auth
            return self.reply({"id": 7, "code": "QWER", "authToken": state.account_token if done else None})
        if path == "/api/v2/user":
            return self.reply({"username": "tester", "title": "Tester"})
        if path == "/api/v2/resources":
            if token != state.account_token:
                return self.reply({"errors": [{"code": 1001, "message": "Unauthorized"}]}, 401)
            host = urllib.parse.urlparse(state.base_url)
            return self.reply([
                {"name": "Fake Attic", "provides": "server", "clientIdentifier": state.machine, "owned": True,
                 "accessToken": state.server_token, "productVersion": "1.41.0", "platform": "Linux", "presence": True,
                 "connections": [
                     {"protocol": "https", "address": "10.0.0.9", "port": 32400, "uri": "http://127.0.0.1:9", "local": True, "relay": False},
                     {"protocol": "http", "address": host.hostname, "port": host.port, "uri": state.base_url, "local": True, "relay": False},
                 ]},
                {"name": "Offline Box", "provides": "server", "clientIdentifier": "offline-2", "owned": False,
                 "accessToken": "x", "presence": False,
                 "connections": [{"protocol": "http", "address": "10.255.255.1", "port": 1, "uri": "http://127.0.0.1:1", "local": False, "relay": False}]},
                {"name": "Phone", "provides": "player", "clientIdentifier": "phone", "connections": []},
            ])

        # --- Plex Media Server ---
        if path == "/identity":
            return self.reply({"MediaContainer": {"machineIdentifier": state.machine, "version": "1.41.0"}})
        if token != state.server_token or state.reject_server_token:
            return self.reply({"error": "unauthorized"}, 401)
        if path == "/library/sections":
            return self.reply({"MediaContainer": {"Directory": state.libraries}})
        if path.endswith("/recentlyAdded"):
            return self.reply({"MediaContainer": {"Metadata": [album_row(a) for a in reversed(ALBUMS)]}})
        if path.startswith("/library/sections/") and path.endswith("/all"):
            kind = (query.get("type") or ["9"])[0]
            if kind == "8":
                rows = [artist_row(a) for a in ARTISTS]
            elif kind == "10":
                rows = [track_row(t) for t in TRACKS]
            else:
                rows = [album_row(a) for a in ALBUMS]
            return self.reply({"MediaContainer": {"Metadata": rows}})
        if path == "/playlists":
            return self.reply({"MediaContainer": {"Metadata": [
                {"ratingKey": "900", "key": "/playlists/900/items", "type": "playlist", "title": "Evening Drive",
                 "leafCount": 2, "composite": "/playlists/900/composite/1"}]}})
        if path == "/playlists/900/items":
            return self.reply({"MediaContainer": {"Metadata": [track_row(TRACKS[0]), track_row(TRACKS[4])]}})
        if path == "/status/sessions/history/all":
            return self.reply({"MediaContainer": {"Metadata": [track_row(TRACKS[1])]}})
        if path == "/hubs/search":
            needle = (query.get("query") or [""])[0].lower()
            albums = [album_row(a) for a in ALBUMS if needle in a[2].lower()]
            tracks = [track_row(t) for t in TRACKS if needle in t[3].lower()]
            return self.reply({"MediaContainer": {"Hub": [{"type": "album", "Metadata": albums}, {"type": "track", "Metadata": tracks}]}})
        if path == "/:/timeline":
            state.timelines.append({k: v[0] for k, v in query.items()})
            return self.reply({"MediaContainer": {}})
        if path.startswith("/library/parts/") and path.endswith("/file.wav"):
            return self.reply(silent_wav(), content_type="audio/wav")
        if "/thumb/" in path or "/composite/" in path:
            return self.reply(PNG, content_type="image/png")
        if path.startswith("/library/metadata/"):
            parts = path.split("/")
            key = parts[3]
            children = len(parts) > 4 and parts[4] == "children"
            album = next((a for a in ALBUMS if a[0] == key), None)
            artist = next((a for a in ARTISTS if a[0] == key), None)
            track = next((t for t in TRACKS if t[0] == key), None)
            if album and children:
                return self.reply({"MediaContainer": {"Metadata": [track_row(t) for t in TRACKS if t[1] == key]}})
            if artist and children:
                return self.reply({"MediaContainer": {"Metadata": [album_row(a) for a in ALBUMS if a[1] == key]}})
            if track:
                return self.reply({"MediaContainer": {"Metadata": [track_row(track)]}})
            if album:
                return self.reply({"MediaContainer": {"Metadata": [album_row(album)]}})
            return self.reply({"MediaContainer": {"Metadata": []}}, 404)
        return self.reply({"error": "not found", "path": path}, 404)


def serve() -> tuple[http.server.ThreadingHTTPServer, State]:
    state = State()
    handler = type("BoundHandler", (Handler,), {"state": state})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    state.base_url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, state


if __name__ == "__main__":
    server, state = serve()
    print(state.base_url, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
