import concurrent.futures
import contextlib
import http.server
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import stat
import struct
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin" / "plexarchy"
FAKE_PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 16, 16)
            + b"\x00\x00\x00\x00IEND\xaeB\x60\x82")


def load_player():
    loader = importlib.machinery.SourceFileLoader("omarchy_plex_music", str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    # Keep the suite from touching the developer's real Plexarchy config/cache.
    sandbox = pathlib.Path(tempfile.mkdtemp(prefix="plexarchy-tests-"))
    module.CONFIG_DIR = sandbox / "config"
    module.CONFIG_FILE = module.CONFIG_DIR / "config.json"
    module.CACHE_DIR = sandbox / "cache"
    module.STATE_FILE = module.CACHE_DIR / "state.json"
    module.SOCKET_FILE = module.CACHE_DIR / "mpv.sock"
    module.DATA_CACHE_DIR = module.CACHE_DIR / "data"
    module.ART_CACHE_DIR = module.CACHE_DIR / "art"
    return module


player = load_player()


class StorageTests(unittest.TestCase):
    def test_atomic_json_is_private_and_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / "private" / "config.json"
            player.atomic_json(target, {"token": "secret", "name": "Música"})
            self.assertEqual(player.load_json(target, {}), {"token": "secret", "name": "Música"})
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)

    def test_malformed_json_uses_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / "broken.json"
            target.write_text("{", encoding="utf-8")
            target.chmod(0o600)
            self.assertEqual(player.load_json(target, {"ok": False}), {"ok": False})

    def test_atomic_json_rejects_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            outside = root / "outside"
            outside.mkdir(mode=0o700)
            (root / "state").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(player.PlayerError, "opened safely"):
                player.atomic_json(root / "state" / "config.json", {"ok": True})
            self.assertFalse((outside / "config.json").exists())

    def test_load_json_rejects_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            outside = root / "outside"
            outside.mkdir(mode=0o700)
            target = outside / "config.json"
            player.atomic_json(target, {"ok": True})
            (root / "state").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(player.PlayerError, "opened safely"):
                player.load_json(root / "state" / "config.json", {})

    def test_private_storage_rejects_unsafe_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            unsafe = root / "unsafe"
            unsafe.mkdir(mode=0o777)
            unsafe.chmod(0o777)
            with self.assertRaisesRegex(player.PlayerError, "mode 0700"):
                player.atomic_json(unsafe / "config.json", {"ok": True})
            self.assertEqual(stat.S_IMODE(unsafe.stat().st_mode), 0o777)

            exposed = root / "exposed.json"
            exposed.write_text('{"ok": true}\n', encoding="utf-8")
            exposed.chmod(0o644)
            with self.assertRaisesRegex(player.PlayerError, "private regular file"):
                player.load_json(exposed, {})

    def test_local_storage_enforces_size_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / "data.json"
            with self.assertRaisesRegex(player.PlayerError, "security policy"):
                player.atomic_json(target, {"value": "x" * 200}, maximum=64)
            player.atomic_bytes(target, b"x" * 65)
            with self.assertRaisesRegex(player.PlayerError, "size limit"):
                player.read_regular_file(target, maximum=64)

    def test_atomic_write_stays_bound_to_opened_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state = root / "state"
            held = root / "held"
            state.mkdir(mode=0o700)
            target = state / "config.json"
            real_open = player.secure_parent_directory

            @contextlib.contextmanager
            def replace_path(path, create=False):
                with real_open(path, create=create) as opened:
                    state.rename(held)
                    state.mkdir(mode=0o700)
                    yield opened

            with mock.patch.object(player, "secure_parent_directory", replace_path):
                player.atomic_json(target, {"destination": "held"})
            self.assertEqual(player.load_json(held / "config.json", {}), {"destination": "held"})
            self.assertFalse((state / "config.json").exists())

    def test_private_read_stays_bound_to_opened_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state = root / "state"
            held = root / "held"
            state.mkdir(mode=0o700)
            player.atomic_json(state / "config.json", {"source": "held"})
            real_open = player.secure_parent_directory

            @contextlib.contextmanager
            def replace_path(path, create=False):
                with real_open(path, create=create) as opened:
                    state.rename(held)
                    state.mkdir(mode=0o700)
                    replacement = state / "config.json"
                    replacement.write_text('{"source": "replacement"}\n', encoding="utf-8")
                    replacement.chmod(0o600)
                    yield opened

            with mock.patch.object(player, "secure_parent_directory", replace_path):
                result = player.load_json(state / "config.json", {})
            self.assertEqual(result, {"source": "held"})

    def test_atomic_json_supports_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as folder:
            target = pathlib.Path(folder) / "state.json"
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                list(executor.map(lambda index: player.atomic_json(target, {"writer": index}), range(100)))
            self.assertIn("writer", player.load_json(target, {}))
            self.assertFalse(list(target.parent.glob("*.tmp")))

    def test_state_lock_serializes_read_modify_write(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "STATE_FILE", pathlib.Path(folder) / "state.json"):
            player.atomic_json(player.STATE_FILE, {"count": 0})

            def increment(_):
                with player.state_lock():
                    state = player.load_json(player.STATE_FILE, {})
                    state["count"] += 1
                    player.atomic_json(player.STATE_FILE, state)

            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                list(executor.map(increment, range(100)))
            self.assertEqual(player.load_json(player.STATE_FILE, {})["count"], 100)

    def test_client_identifier_is_generated_once(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CONFIG_FILE", pathlib.Path(folder) / "config.json"):
            first = player.client_identifier()
            second = player.client_identifier()
            self.assertEqual(first, second)
            self.assertGreater(len(first), 20)

    def test_cache_cleanup_enforces_size_limit(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CACHE_DIR", pathlib.Path(folder)), \
             mock.patch.object(player, "ART_CACHE_DIR", pathlib.Path(folder) / "art"), \
             mock.patch.object(player, "DATA_CACHE_DIR", pathlib.Path(folder) / "data"):
            player.ensure_private_dir(player.ART_CACHE_DIR)
            for index in range(3):
                (player.ART_CACHE_DIR / f"{index}.jpg").write_bytes(b"x" * 20)
            result = player.cleanup_cache(max_age_days=30, max_bytes=25)
            self.assertGreaterEqual(result["removed"], 2)
            self.assertLessEqual(sum(path.stat().st_size for path in player.ART_CACHE_DIR.iterdir()), 25)

    def test_cache_cleanup_removes_only_stale_atomic_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "ART_CACHE_DIR", pathlib.Path(folder) / "art"), \
             mock.patch.object(player, "DATA_CACHE_DIR", pathlib.Path(folder) / "data"):
            player.ensure_private_dir(player.ART_CACHE_DIR)
            fresh = player.ART_CACHE_DIR / (".cover.jpg." + "a" * 32 + ".tmp")
            stale = player.ART_CACHE_DIR / (".cover.jpg." + "b" * 32 + ".tmp")
            unrelated = player.ART_CACHE_DIR / ".cover.random.tmp"
            for path in (fresh, stale, unrelated):
                path.write_bytes(b"in progress")
            stale.touch()
            with mock.patch.object(player.time, "time", return_value=10_000):
                os.utime(stale, (1, 1))
                result = player.cleanup_cache(max_age_days=30, max_bytes=1, temp_grace_seconds=3600)
            self.assertTrue(fresh.exists())
            self.assertFalse(stale.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(result, {"removed": 1, "bytes": len(b"in progress")})

    def test_art_download_enforces_cache_size_immediately(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _):
                return FAKE_PNG

        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CACHE_DIR", pathlib.Path(folder)), \
             mock.patch.object(player, "ART_CACHE_DIR", pathlib.Path(folder) / "art"), \
             mock.patch.object(player, "DATA_CACHE_DIR", pathlib.Path(folder) / "data"), \
             mock.patch.object(player, "CACHE_MAX_BYTES", len(FAKE_PNG) + 1), \
             mock.patch.object(player, "safe_urlopen", return_value=Response()):
            player.ensure_private_dir(player.ART_CACHE_DIR)
            (player.ART_CACHE_DIR / "old.jpg").write_bytes(b"old!")
            player.art_path({"server": "http://plex", "token": "tok"}, "/thumb/1")
            total = sum(path.stat().st_size for path in player.ART_CACHE_DIR.iterdir())
        self.assertLessEqual(total, len(FAKE_PNG) + 1)

    def test_library_artwork_is_loaded_lazily(self):
        config = {"server": "http://plex", "token": "tok"}
        with mock.patch.object(player, "art_path") as art:
            items = player.compact_items(config, [
                {"ratingKey": str(index), "type": "album", "thumb": f"/cover/{index}"}
                for index in range(20)
            ])
        art.assert_not_called()
        self.assertEqual(items[7]["artSource"], "/cover/7")
        self.assertEqual(items[7]["thumb"], "")


class PlexModelTests(unittest.TestCase):
    def setUp(self):
        self.config = {"server": "http://plex.test:32400", "token": "tok", "section": "4"}

    def test_metadata_normalizes_missing_rows(self):
        self.assertEqual(player.metadata({}), [])
        self.assertEqual(player.metadata({"MediaContainer": {"Metadata": [{"title": "A"}]}}), [{"title": "A"}])
        self.assertEqual(player.metadata({"MediaContainer": {"Metadata": [None, "bad", {"title": "A"}]}}),
                         [{"title": "A"}])

    def test_malformed_numeric_metadata_uses_safe_defaults(self):
        row = {"type": "track", "year": "unknown", "duration": {}, "index": [],
               "leafCount": "many", "viewCount": None}
        result = player.compact_item(self.config, row, fetch_art=False)
        self.assertEqual((result["year"], result["duration"], result["index"],
                          result["leafCount"], result["viewCount"]), (0, 0, 0, 0, 0))

    def test_sections_keeps_music_libraries_only(self):
        payload = {"MediaContainer": {"Directory": [
            {"key": "1", "title": "Movies", "type": "movie"},
            {"key": "4", "title": "Music", "type": "artist"},
        ]}}
        with mock.patch.object(player, "plex_request", return_value=payload):
            self.assertEqual(player.sections(self.config), [{"key": "4", "title": "Music"}])

    def test_configured_music_section_avoids_discovery_request(self):
        with mock.patch.object(player, "sections") as sections:
            self.assertEqual(player.music_section(self.config), "4")
        sections.assert_not_called()

    def test_search_compacts_artwork_as_one_concurrent_batch(self):
        payload = {"MediaContainer": {"Hub": [
            {"Metadata": [{"ratingKey": "1", "type": "album"}, {"ratingKey": "2", "type": "track"}]}
        ]}}
        with mock.patch.object(player, "plex_request", return_value=payload), \
             mock.patch.object(player, "compact_items", side_effect=lambda _config, rows: rows) as compact:
            result = player.search(self.config, "test", 10)
        self.assertEqual(len(result), 2)
        compact.assert_called_once_with(self.config, payload["MediaContainer"]["Hub"][0]["Metadata"])

    def test_cross_origin_redirect_never_reaches_target_with_token(self):
        received = []

        class Target(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("X-Plex-Token"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"MediaContainer": {}}')

            def log_message(self, *_):
                pass

        target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Target)

        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/target")
                self.end_headers()

            def log_message(self, *_):
                pass

        source = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = [threading.Thread(target=server.serve_forever) for server in (source, target)]
        for thread in threads:
            thread.start()
        try:
            config = {"server": f"http://127.0.0.1:{source.server_port}", "token": "secret"}
            with self.assertRaisesRegex(player.PlayerError, "another origin") as raised:
                player.plex_request(config, "/redirect")
            self.assertEqual(raised.exception.code, "unsafe-redirect")
            self.assertEqual(received, [])
        finally:
            source.shutdown()
            target.shutdown()
            source.server_close()
            target.server_close()
            for thread in threads:
                thread.join()

    def test_same_origin_redirect_is_allowed(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/final")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"MediaContainer": {}}')

            def log_message(self, *_):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            config = {"server": f"http://127.0.0.1:{server.server_port}", "token": "secret"}
            self.assertEqual(player.plex_request(config, "/redirect"), {"MediaContainer": {}})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_https_redirect_cannot_downgrade_to_http(self):
        request = player.urllib.request.Request("https://plex.example/library")
        with self.assertRaisesRegex(player.PlayerError, "another origin") as raised:
            player.SameOriginRedirectHandler().redirect_request(
                request, None, 302, "Found", {}, "http://plex.example/library"
            )
        self.assertEqual(raised.exception.code, "unsafe-redirect")

    def test_search_skips_malformed_hubs_and_rows(self):
        payload = {"MediaContainer": {"Hub": [None, {"Metadata": "bad"},
            {"Metadata": [None, {"type": "track", "ratingKey": "1"}]}]}}
        with mock.patch.object(player, "plex_request", return_value=payload), \
             mock.patch.object(player, "compact_items", side_effect=lambda _config, rows: rows):
            result = player.search(self.config, "test", 10)
        self.assertEqual(result, [{"type": "track", "ratingKey": "1"}])

    def test_search_rejects_oversized_query_before_network(self):
        with mock.patch.object(player, "plex_request") as request:
            with self.assertRaisesRegex(player.PlayerError, "limited") as raised:
                player.search(self.config, "x" * (player.SEARCH_QUERY_MAX_CHARS + 1), 10)
        self.assertEqual(raised.exception.code, "invalid-query")
        request.assert_not_called()

    def test_compact_track(self):
        row = {
            "ratingKey": "99", "type": "track", "title": "Song",
            "grandparentTitle": "Artist", "parentTitle": "Album",
            "duration": 183250, "year": 2024, "thumb": "/thumb/99",
        }
        with mock.patch.object(player, "art_path", return_value="file:///cover.jpg"):
            result = player.compact_item(self.config, row)
        self.assertEqual(result["artist"], "Artist")
        self.assertEqual(result["album"], "Album")
        self.assertEqual(result["duration"], 183.25)
        self.assertEqual(result["thumb"], "file:///cover.jpg")

    def test_recent_uses_selected_section_and_clamps_limit(self):
        payload = {"MediaContainer": {"Metadata": [{"ratingKey": "8", "type": "album", "title": "Record"}]}}
        with mock.patch.object(player, "music_section", return_value="4"), \
             mock.patch.object(player, "plex_request", return_value=payload) as request, \
             mock.patch.object(player, "art_path", return_value=""):
            result = player.recent(self.config, 200)
        self.assertEqual(result[0]["title"], "Record")
        self.assertEqual(request.call_args.args[1], "/library/sections/4/recentlyAdded")
        self.assertEqual(request.call_args.args[2]["X-Plex-Container-Size"], 50)

    def test_stream_url_keeps_token_out_of_mpris_visible_path(self):
        url = player.stream_url({"server": "http://plex", "token": "a b&c"}, "/library/parts/7/file.flac")
        self.assertEqual(url, "http://plex/library/parts/7/file.flac")
        self.assertNotIn("token", url.lower())

    def test_mpv_auth_uses_file_local_http_header(self):
        with mock.patch.object(player, "mpv_command") as command:
            player.load_stream({"token": "a b&c"}, "http://plex/part", "replace")
        command.assert_called_once_with([
            "loadfile", "http://plex/part", "replace", -1,
            {"http-header-fields": "X-Plex-Token: a b&c"},
        ], True)

    def test_mpv_ipc_eof_fails_promptly(self):
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.recv.return_value = b""
        with mock.patch.object(player.socket, "socket", return_value=client):
            with self.assertRaisesRegex(player.PlayerError, "without a reply") as raised:
                player.mpv_command(["get_property", "pause"], True)
        self.assertEqual(raised.exception.code, "player-ipc")
        client.recv.assert_called_once()

    def test_mpv_ipc_rejects_oversized_and_malformed_replies(self):
        for reply, maximum, message in ((b"12345", 4, "oversized"), (b"not-json\n", 64, "invalid")):
            client = mock.MagicMock()
            client.__enter__.return_value = client
            client.recv.return_value = reply
            with self.subTest(message=message), \
                 mock.patch.object(player, "MPV_REPLY_MAX_BYTES", maximum), \
                 mock.patch.object(player.socket, "socket", return_value=client):
                with self.assertRaisesRegex(player.PlayerError, message):
                    player.mpv_command(["get_property", "pause"], True)

    def test_mpv_batch_uses_one_socket_and_accepts_fragmented_replies(self):
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.recv.side_effect = [
            b'{"request_id": 1, "error": "success", "data": fa',
            b'lse}\n{"request_id": 2, "error": "success", "data": 42}\n',
        ]
        with mock.patch.object(player.socket, "socket", return_value=client) as socket_factory:
            result = player.mpv_commands([["get_property", "pause"], ["get_property", "volume"]])
        self.assertEqual(result, [False, 42])
        socket_factory.assert_called_once()

    def test_mpv_batch_ignores_unsolicited_events(self):
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.recv.return_value = (b'{"event":"property-change","name":"pause","data":false}\n'
                                    b'{"request_id":1,"error":"success","data":42}\n')
        with mock.patch.object(player.socket, "socket", return_value=client):
            self.assertEqual(player.mpv_commands([["get_property", "volume"]]), [42])

    def test_load_streams_batches_playlist_on_one_ipc_call(self):
        with mock.patch.object(player, "mpv_commands") as commands:
            player.load_streams({"token": "secret"}, [f"http://plex/{index}" for index in range(500)])
        commands.assert_called_once()
        self.assertEqual(len(commands.call_args.args[0]), 500)

    def test_transient_ipc_failure_does_not_unlink_live_socket(self):
        details = mock.Mock(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.geteuid())
        with mock.patch.object(player, "secure_stat", return_value=details), \
             mock.patch.object(player, "mpv_commands", side_effect=TimeoutError("slow")), \
             mock.patch.object(player, "secure_unlink") as unlink:
            self.assertIsNone(player.mpv_properties(["pause"]))
        unlink.assert_not_called()

    def test_connection_refused_socket_is_recovered_before_start(self):
        details = mock.Mock(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.geteuid())
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.connect.side_effect = ConnectionRefusedError()
        with mock.patch.object(player, "secure_stat", return_value=details), \
             mock.patch.object(player.socket, "socket", return_value=client), \
             mock.patch.object(player, "secure_unlink") as unlink:
            player.recover_stale_mpv_socket()
        unlink.assert_called_once_with(player.SOCKET_FILE)

    def test_plex_request_rejects_oversized_json(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, maximum):
                return b"x" * maximum

        with mock.patch.object(player, "PLEX_JSON_MAX_BYTES", 8), \
             mock.patch.object(player, "safe_urlopen", return_value=Response()):
            with self.assertRaisesRegex(player.PlayerError, "oversized") as raised:
                player.plex_request(self.config, "/library/sections")
        self.assertEqual(raised.exception.code, "invalid-response")

    def test_plex_request_accepts_bounded_json(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _):
                return b'{"MediaContainer": {}}'

        with mock.patch.object(player, "safe_urlopen", return_value=Response()):
            self.assertEqual(player.plex_request(self.config, "/library/sections"), {"MediaContainer": {}})

    def test_plex_cloud_request_uses_its_smaller_response_limit(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, maximum):
                self.maximum = maximum
                return b"{}"

        response = Response()
        with mock.patch.object(player, "PLEX_CLOUD_JSON_MAX_BYTES", 32), \
             mock.patch.object(player, "safe_urlopen", return_value=response):
            self.assertEqual(player.plex_cloud_request("/user"), {})
        self.assertEqual(response.maximum, 33)

    def test_library_list_applies_client_side_limit(self):
        payload = {"MediaContainer": {"Metadata": [
            {"ratingKey": str(index), "type": "album", "title": f"Album {index}"} for index in range(20)
        ]}}
        with mock.patch.object(player, "music_section", return_value="4"), \
             mock.patch.object(player, "plex_request", return_value=payload), \
             mock.patch.object(player, "compact_items", side_effect=lambda config, rows: rows):
            result = player.library_list(self.config, "albums", 5)
        self.assertEqual(len(result), 5)

    def test_playback_metadata_never_loads_covers_eagerly(self):
        rows = [
            {"ratingKey": str(index), "type": "track", "title": f"Track {index}", "thumb": f"/thumb/{index}"}
            for index in range(20)
        ]
        with mock.patch.object(player, "art_path") as art:
            items = player.compact_playback_items(self.config, rows)
        art.assert_not_called()
        self.assertEqual(items[0]["thumb"], "")
        self.assertEqual(items[0]["_artSource"], "/thumb/0")
        self.assertEqual(items[1]["thumb"], "")
        self.assertEqual(items[1]["_artSource"], "/thumb/1")

    def test_raw_track_keeps_artwork_lazy(self):
        payload = {"MediaContainer": {"Metadata": [{
            "ratingKey": "1", "type": "track", "title": "Track", "thumb": "/thumb/1",
            "Media": [{"Part": [{"key": "/part/1"}]}],
        }]}}
        with mock.patch.object(player, "plex_request", return_value=payload), \
             mock.patch.object(player, "art_path") as art:
            item, part = player.raw_track(self.config, "1")
        art.assert_not_called()
        self.assertEqual(part, "/part/1")
        self.assertEqual(item["_artSource"], "/thumb/1")

    def test_favorites_filters_unrated_tracks_client_side(self):
        payload = {"MediaContainer": {"Metadata": [
            {"ratingKey": "1", "type": "track", "title": "Unrated"},
            {"ratingKey": "2", "type": "track", "title": "Favorite", "userRating": 10},
        ]}}
        with mock.patch.object(player, "music_section", return_value="4"), \
             mock.patch.object(player, "plex_request", return_value=payload), \
             mock.patch.object(player, "compact_items", side_effect=lambda config, rows: rows):
            result = player.library_list(self.config, "favorites", 5)
        self.assertEqual([row["title"] for row in result], ["Favorite"])

    def test_cached_items_uses_last_good_data_for_network_failure(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "DATA_CACHE_DIR", pathlib.Path(folder)):
            target = player.data_cache_path(self.config, "albums")
            player.atomic_json(target, {"items": [{"title": "Cached"}], "cachedAt": 1})
            result = player.cached_items(self.config, "albums", lambda: (_ for _ in ()).throw(player.PlayerError("offline", "unreachable")))
        self.assertTrue(result["stale"])
        self.assertEqual(result["items"][0]["title"], "Cached")

    def test_cache_paths_are_isolated_by_server_and_account(self):
        first = {"server": "http://plex-a:32400", "token": "first", "section": "4"}
        second = {"server": "http://plex-b:32400", "token": "second", "section": "4"}
        self.assertNotEqual(player.data_cache_path(first, "albums"), player.data_cache_path(second, "albums"))
        self.assertNotEqual(player.cache_namespace(first), player.cache_namespace(second))

    def test_art_cache_does_not_cross_server_boundaries(self):
        class Response:
            def __init__(self, value):
                self.value = value

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _):
                return self.value

        first = {"server": "http://plex-a:32400", "token": "first", "section": "4"}
        second = {"server": "http://plex-b:32400", "token": "second", "section": "4"}
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "ART_CACHE_DIR", pathlib.Path(folder) / "art"), \
             mock.patch.object(player, "safe_urlopen",
                               side_effect=[Response(FAKE_PNG), Response(FAKE_PNG)]) as request:
            first_uri = player.art_path(first, "/library/metadata/1/thumb/2")
            second_uri = player.art_path(second, "/library/metadata/1/thumb/2")
        self.assertNotEqual(first_uri, second_uri)
        self.assertEqual(request.call_count, 2)

    def test_art_request_keeps_token_out_of_url_and_in_header(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = FAKE_PNG
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "ART_CACHE_DIR", pathlib.Path(folder) / "art"), \
             mock.patch.object(player, "DATA_CACHE_DIR", pathlib.Path(folder) / "data"), \
             mock.patch.object(player, "safe_urlopen", return_value=response) as urlopen:
            player.art_path(self.config, "/thumb/1")
        request = urlopen.call_args.args[0]
        self.assertNotIn("tok", request.full_url)
        self.assertEqual(request.get_header("X-plex-token"), "tok")

    def test_invalid_artwork_is_not_cached(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"not an image"
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "ART_CACHE_DIR", pathlib.Path(folder) / "art"), \
             mock.patch.object(player, "safe_urlopen", return_value=response):
            self.assertEqual(player.art_path(self.config, "/thumb/invalid"), "")


class AuthenticationTests(unittest.TestCase):
    def test_server_url_is_canonical_origin_only(self):
        self.assertEqual(player.normalize_server_url("HTTPS://plex.example:32400/"),
                         "https://plex.example:32400")
        self.assertEqual(player.normalize_server_url("HTTPS://PLEX.EXAMPLE:443/"),
                         "https://plex.example")
        self.assertEqual(player.normalize_server_url("https://[::1]:32400/"),
                         "https://[::1]:32400")
        for value in ("https://plex.example/base", "https://plex.example/?x=1",
                      "https://plex.example/#fragment", "https://user@plex.example"):
            with self.subTest(value=value), self.assertRaises(player.PlayerError):
                player.normalize_server_url(value)

    def test_connection_health_preserves_transient_error_code(self):
        with mock.patch.object(player, "load_config", return_value={"server": "http://plex", "token": "x"}), \
             mock.patch.object(player, "sections", side_effect=player.PlayerError("offline", "timeout")):
            result = player.connection_health()
        self.assertEqual(result["code"], "timeout")
        self.assertFalse(result["ok"])

    def test_disabled_connection_is_preserved_but_blocked(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CONFIG_FILE", pathlib.Path(folder) / "config.json"):
            player.atomic_json(player.CONFIG_FILE, {
                "server": "http://plex:32400", "token": "secret", "connectionEnabled": False,
            })
            self.assertEqual(player.load_config(False), {})
            preserved = player.load_config(False, include_disabled=True)
            self.assertEqual(preserved["token"], "secret")
            with self.assertRaisesRegex(player.PlayerError, "turned off") as raised:
                player.load_config()
        self.assertEqual(raised.exception.code, "disconnected")

    def test_disabled_health_check_never_contacts_plex(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CONFIG_FILE", pathlib.Path(folder) / "config.json"), \
             mock.patch.object(player, "sections") as sections:
            player.atomic_json(player.CONFIG_FILE, {
                "server": "http://plex:32400", "token": "secret", "connectionEnabled": False,
            })
            result = player.connection_health()
        sections.assert_not_called()
        self.assertTrue(result["configured"])
        self.assertFalse(result["connected"])
        self.assertEqual(result["code"], "disconnected")

    def test_connection_switch_keeps_credentials_and_queue(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CONFIG_FILE", pathlib.Path(folder) / "config.json"), \
             mock.patch.object(player, "STATE_FILE", pathlib.Path(folder) / "state.json"), \
             mock.patch.object(player, "SOCKET_FILE", pathlib.Path(folder) / "mpv.sock"), \
             mock.patch.object(player, "shutdown_player") as shutdown:
            config = {"server": "http://plex:32400", "token": "secret", "section": "4"}
            player.atomic_json(player.CONFIG_FILE, config)
            player.atomic_json(player.STATE_FILE, {
                "queue": [{"key": "1", "title": "Saved track"}],
                "queueNamespace": player.cache_namespace(config),
            })
            disabled = player.set_connection(False)
            stored = player.load_settings()
            self.assertEqual(stored["token"], "secret")
            self.assertFalse(stored["connectionEnabled"])
            self.assertTrue(player.STATE_FILE.exists())
            self.assertFalse(disabled["connected"])
            shutdown.assert_called_once()

            enabled = player.set_connection(True)
            self.assertTrue(player.load_settings()["connectionEnabled"])
            self.assertTrue(enabled["connected"])

    def test_disabled_connection_blocks_timeline_network_request(self):
        config = {
            "server": "http://plex:32400", "token": "secret", "connectionEnabled": False,
        }
        report = {"trackKey": "1", "sessionId": "session", "state": "playing"}
        with mock.patch.object(player, "safe_urlopen") as request:
            self.assertFalse(player.send_timeline(config, report))
        request.assert_not_called()

    def test_logout_clears_persisted_queue_metadata(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CONFIG_FILE", pathlib.Path(folder) / "config.json"), \
             mock.patch.object(player, "STATE_FILE", pathlib.Path(folder) / "state.json"), \
             mock.patch.object(player, "shutdown_player"):
            player.atomic_json(player.CONFIG_FILE, {"server": "https://plex", "token": "secret",
                                                    "clientIdentifier": "client"})
            player.atomic_json(player.STATE_FILE, {"queue": [{"title": "Private title"}]})
            player.logout()
            self.assertFalse(player.STATE_FILE.exists())
            self.assertNotIn("token", player.load_json(player.CONFIG_FILE, {}))

    def test_logout_clears_credentials_when_shutdown_fails(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(player, "CONFIG_FILE", pathlib.Path(folder) / "config.json"), \
             mock.patch.object(player, "STATE_FILE", pathlib.Path(folder) / "state.json"), \
             mock.patch.object(player, "shutdown_player", side_effect=player.PlayerError("wedged", "player-shutdown")):
            player.atomic_json(player.CONFIG_FILE, {"server": "https://plex", "token": "secret",
                                                    "clientIdentifier": "client"})
            player.atomic_json(player.STATE_FILE, {"queue": [{"title": "Private"}]})
            result = player.logout()
            self.assertNotIn("token", player.load_json(player.CONFIG_FILE, {}))
            self.assertFalse(player.STATE_FILE.exists())
        self.assertFalse(result["stopped"])
        self.assertEqual(result["code"], "player-shutdown")

    def test_configure_parser_rejects_plaintext_token_argument(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            player.parser().parse_args(["configure", "--token", "secret"])


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.state_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_folder.cleanup)
        self.state_patch = mock.patch.object(player, "STATE_FILE", pathlib.Path(self.state_folder.name) / "state.json")
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.socket_patch = mock.patch.object(player, "SOCKET_FILE", pathlib.Path(self.state_folder.name) / "mpv.sock")
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)

    def test_play_replaces_old_queue_then_appends_album(self):
        rows = [
            {"ratingKey": "1", "type": "track", "title": "First", "Media": [{"Part": [{"key": "/part/1"}]}]},
            {"ratingKey": "2", "type": "track", "title": "Second", "Media": [{"Part": [{"key": "/part/2"}]}]},
        ]
        with mock.patch.object(player, "album_track_rows", return_value=rows), \
             mock.patch.object(player, "compact_playback_items", side_effect=lambda _config, values: [
                 {"key": row["ratingKey"], "title": row["title"]} for row in values]), \
             mock.patch.object(player, "start_mpv"), \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "raw_track") as raw, \
             mock.patch.object(player, "mpv_commands") as batch, \
             mock.patch.object(player, "mpv_command") as command, \
             mock.patch.object(player, "status", return_value={"playing": True}):
            result = player.play({"server": "http://plex", "token": "tok"}, "2", "album")
        raw.assert_not_called()
        loads = batch.call_args.args[0]
        self.assertIn("/part/2", loads[0][1])
        self.assertEqual(loads[0][2], "replace")
        self.assertEqual(loads[1][2], "append")
        self.assertIn(mock.call(["set_property", "pause", False], True), command.call_args_list)
        self.assertIn(mock.call(["set_property", "playlist-pos", 0], True), command.call_args_list)
        self.assertEqual([item["key"] for item in player.state_data()["queue"]], ["2", "1"])
        self.assertTrue(result["playing"])

    def test_collection_resolution_failure_does_not_mutate_player_or_state(self):
        rows = [
            {"ratingKey": "1", "type": "track", "title": "First"},
            {"ratingKey": "2", "type": "track", "title": "Second"},
        ]
        player.atomic_json(player.STATE_FILE, {"queue": [{"key": "old"}]})
        with mock.patch.object(player, "album_track_rows", return_value=rows), \
             mock.patch.object(player, "compact_playback_items", return_value=[
                 {"key": "1", "title": "First"}, {"key": "2", "title": "Second"}]), \
             mock.patch.object(player, "raw_track", side_effect=[
                 ({"key": "1", "title": "First"}, "/part/1"),
                 player.PlayerError("missing", "server-error"),
             ]), \
             mock.patch.object(player, "start_mpv") as start, \
             mock.patch.object(player, "mpv_command") as command:
            with self.assertRaisesRegex(player.PlayerError, "missing"):
                player.play({"server": "http://plex", "token": "tok"}, "1", "album")
        start.assert_not_called()
        command.assert_not_called()
        self.assertEqual(player.state_data()["queue"], [{"key": "old"}])

    def test_large_collection_reuses_parts_and_caps_the_queue(self):
        rows = [
            {"ratingKey": str(index), "type": "track", "title": f"Track {index}",
             "Media": [{"Part": [{"key": f"/part/{index}"}]}]}
            for index in range(750)
        ]
        compact = lambda _config, values: [
            {"key": str(row["ratingKey"]), "title": str(row["title"])} for row in values
        ]
        with mock.patch.object(player, "album_track_rows", return_value=rows) as fetch, \
             mock.patch.object(player, "compact_playback_items", side_effect=compact), \
             mock.patch.object(player, "raw_track") as raw, \
             mock.patch.object(player, "activate_queue", return_value={"playing": True}) as activate:
            result = player.play_collection({"server": "http://plex", "token": "tok"}, "album", "album")
        fetch.assert_called_once()
        raw.assert_not_called()
        self.assertEqual(len(activate.call_args.args[1]), player.PLAYBACK_QUEUE_MAX_ITEMS)
        self.assertEqual(len(activate.call_args.args[2]), player.PLAYBACK_QUEUE_MAX_ITEMS)
        self.assertTrue(result["playing"])

    def test_toggle_resumes_persisted_queue_when_mpv_is_absent(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        player.atomic_json(player.STATE_FILE, {
            "queue": [{"key": "1", "title": "First", "_part": "/part/1"}],
            "shuffle": True,
            "repeat": "all",
            "queueNamespace": player.cache_namespace(config),
        })
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_properties", return_value=None), \
             mock.patch.object(player, "start_mpv"), \
             mock.patch.object(player, "mpv_commands") as batch, \
             mock.patch.object(player, "mpv_command") as command, \
             mock.patch.object(player, "status", return_value={"playing": True}), \
             mock.patch.object(player.time, "sleep"):
            result = player.control("toggle")
        load = batch.call_args.args[0][0]
        self.assertEqual(load[1], "http://plex/part/1")
        self.assertEqual(load[2], "replace")
        self.assertIn(mock.call(["set_property", "loop-playlist", "inf"], True), command.call_args_list)
        self.assertTrue(result["playing"])

    def test_toggle_with_empty_queue_does_not_start_player(self):
        player.atomic_json(player.STATE_FILE, {"queue": [], "shuffle": False, "repeat": "off"})
        with mock.patch.object(player, "load_config", return_value={"server": "http://plex", "token": "tok"}), \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "start_mpv") as start, \
             mock.patch.object(player, "status", return_value={"playing": False}) as status:
            result = player.control("toggle")
        start.assert_not_called()
        status.assert_called_once()
        self.assertFalse(result["playing"])

    def test_toggle_resumes_queue_when_existing_mpv_is_idle(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_properties", return_value={"idle-active": True}), \
             mock.patch.object(player, "resume_queue", return_value={"playing": True}) as resume, \
             mock.patch.object(player, "mpv_command") as command:
            result = player.control("toggle")
        resume.assert_called_once_with(config)
        command.assert_not_called()
        self.assertTrue(result["playing"])

    def test_stopped_queue_selection_starts_selected_item(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        stored = [{"key": "1", "_part": "/1"}, {"key": "2", "_part": "/2"}]
        player.atomic_json(player.STATE_FILE, {"queue": stored, "queueNamespace": player.cache_namespace(config)})
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "prepare_saved_queue", side_effect=lambda _config, queue: (queue, [item["_part"] for item in queue])), \
             mock.patch.object(player, "activate_queue", return_value={"playing": True}) as activate, \
             mock.patch.object(player, "queue_view", return_value={"items": []}):
            player.queue_action("play", index=1)
        self.assertEqual([item["key"] for item in activate.call_args.args[1]], ["2", "1"])

    def test_stopped_play_next_activates_exact_persisted_order(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        stored = [{"key": "old", "_part": "/old"}]
        player.atomic_json(player.STATE_FILE, {"queue": stored, "queueNamespace": player.cache_namespace(config)})
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "raw_track", return_value=({"key": "new"}, "/new")), \
             mock.patch.object(player, "prepare_saved_queue", side_effect=lambda _config, queue: (queue, [item["_part"] for item in queue])), \
             mock.patch.object(player, "activate_queue", return_value={"playing": True}) as activate, \
             mock.patch.object(player, "queue_view", return_value={"items": []}):
            player.queue_action("play-next", track_key="new")
        queue, urls = activate.call_args.args[1:3]
        self.assertEqual([item["key"] for item in queue], ["old", "new"])
        self.assertEqual(urls, ["/old", "/new"])

    def test_stopped_queue_has_no_current_item_and_first_can_be_removed(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        player.atomic_json(player.STATE_FILE, {
            "queue": [{"key": "1"}, {"key": "2"}], "queueNamespace": player.cache_namespace(config)
        })
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "mpv_properties", return_value=None):
            result = player.queue_action("remove", index=0)
        self.assertEqual(result["currentIndex"], -1)
        self.assertEqual([item["key"] for item in result["items"]], ["2"])
        self.assertFalse(result["items"][0]["current"])

    def test_clear_upcoming_clears_the_whole_stopped_queue(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        player.atomic_json(player.STATE_FILE, {
            "queue": [{"key": "1"}, {"key": "2"}], "queueNamespace": player.cache_namespace(config)
        })
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "mpv_properties", return_value=None):
            result = player.queue_action("clear-upcoming")
        self.assertEqual(result["items"], [])

    def test_mismatched_account_queue_is_hidden(self):
        current = {"server": "http://plex", "token": "new", "section": "4"}
        previous = {"server": "http://plex", "token": "old", "section": "4"}
        player.atomic_json(player.STATE_FILE, {
            "queue": [{"key": "1", "title": "Private"}], "queueNamespace": player.cache_namespace(previous)
        })
        with mock.patch.object(player, "load_config", return_value=current), \
             mock.patch.object(player, "mpv_properties", return_value=None):
            self.assertEqual(player.queue_view()["items"], [])

    def test_status_never_blocks_on_active_artwork(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        item = {"key": "1", "title": "Track", "_streamHash": "same", "_artSource": "/cover/1"}
        player.atomic_json(player.STATE_FILE, {
            "queue": [item], "queueNamespace": player.cache_namespace(config)
        })
        with mock.patch.object(player, "mpv_properties", return_value=None), \
             mock.patch.object(player, "art_path") as artwork, \
             mock.patch.object(player, "update_timeline"):
            result = player.status(config)
        artwork.assert_not_called()
        self.assertEqual(result["track"]["artSource"], "/cover/1")
        self.assertNotIn("_artSource", result["track"])

    def test_duplicate_queue_entries_are_reconciled_by_occurrence(self):
        digest = player.hashlib.sha256(b"http://plex/repeat").hexdigest()
        first = {"key": "first", "_streamHash": digest}
        second = {"key": "second", "_streamHash": digest}
        result = player.reconcile_queue([first, second], [
            {"filename": "http://plex/repeat"}, {"filename": "http://plex/repeat"}
        ])
        self.assertEqual([item["key"] for item in result], ["first", "second"])

    def test_status_uses_one_batched_property_snapshot(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        snapshot = {"playlist": [], "playlist-pos": 0, "pause": False, "idle-active": True,
                    "time-pos": 0, "duration": 0, "volume": 100}
        with mock.patch.object(player, "mpv_properties", return_value=snapshot) as properties, \
             mock.patch.object(player, "sync_queue_from_mpv", return_value={"queue": [], "shuffle": False, "repeat": "off"}), \
             mock.patch.object(player, "update_timeline"):
            player.status(config)
        properties.assert_called_once()

    def test_rejected_load_restores_previous_state_and_stops_new_player(self):
        old = {"queue": [{"key": "old"}], "shuffle": False, "repeat": "off"}
        player.atomic_json(player.STATE_FILE, old)
        config = {"server": "http://plex", "token": "tok"}
        queue, url = player.finish_prepared_item(config, {"key": "new", "title": "New"}, "/part/new")
        with mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "start_mpv"), \
             mock.patch.object(player, "load_streams", side_effect=player.PlayerError("rejected", "player-ipc")), \
             mock.patch.object(player, "mpv_command") as command:
            with self.assertRaisesRegex(player.PlayerError, "rejected"):
                player.activate_queue(config, [queue], [url], False)
        self.assertEqual(player.state_data()["queue"], old["queue"])
        command.assert_called_once_with(["quit"])

    def test_resume_rejects_state_changed_during_preparation(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        original = {"queue": [{"key": "1", "_part": "/1"}],
                    "queueNamespace": player.cache_namespace(config)}
        player.atomic_json(player.STATE_FILE, original)

        def mutate(_config, stored):
            player.atomic_json(player.STATE_FILE, {
                "queue": [{"key": "2", "_part": "/2"}],
                "queueNamespace": player.cache_namespace(config),
            })
            return stored, ["http://plex/1"]

        with mock.patch.object(player, "prepare_saved_queue", side_effect=mutate), \
             mock.patch.object(player, "start_mpv") as start:
            with self.assertRaisesRegex(player.PlayerError, "queue changed") as raised:
                player.resume_queue(config)
        self.assertEqual(raised.exception.code, "queue-changed")
        start.assert_not_called()

    def test_oversized_state_is_rejected_before_player_mutation(self):
        config = {"server": "http://plex", "token": "tok"}
        item, url = player.finish_prepared_item(config, {"key": "1", "title": "x" * 500}, "/part/1")
        with mock.patch.object(player, "STATE_MAX_BYTES", 64), \
             mock.patch.object(player, "start_mpv") as start, \
             mock.patch.object(player, "mpv_command") as command:
            with self.assertRaisesRegex(player.PlayerError, "security policy"):
                player.activate_queue(config, [item], [url], False)
        start.assert_not_called()
        command.assert_not_called()

    def test_shutdown_reports_timeline_and_quits_mpv(self):
        config = {"server": "http://plex", "token": "tok"}
        with mock.patch.object(player, "stop_timeline") as stop, \
             mock.patch.object(player, "mpv_running", side_effect=[True, False]), \
             mock.patch.object(player, "mpv_command") as command:
            result = player.shutdown_player(config)
        stop.assert_called_once_with(config)
        command.assert_called_once_with(["quit"])
        self.assertTrue(result["stopped"])

    def test_shutdown_is_idempotent_without_player(self):
        with mock.patch.object(player, "stop_timeline") as stop, \
             mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "mpv_command") as command:
            result = player.shutdown_player({})
        stop.assert_called_once_with({})
        command.assert_not_called()
        self.assertTrue(result["stopped"])

    def test_start_timeout_terminates_spawned_mpv(self):
        process = mock.MagicMock()
        process.poll.return_value = 0
        with mock.patch.object(player, "mpv_running", return_value=False), \
             mock.patch.object(player, "recover_stale_mpv_socket"), \
             mock.patch.object(player, "shutil_which", return_value="/usr/bin/mpv"), \
             mock.patch.object(player, "ensure_private_dir"), \
             mock.patch.object(player.subprocess, "Popen", return_value=process) as popen, \
             mock.patch.object(player.time, "sleep"):
            with self.assertRaisesRegex(player.PlayerError, "did not start"):
                player.start_mpv()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=0.5)
        self.assertEqual(popen.call_args.args[0][0], "/usr/bin/mpv")

    def test_executable_lookup_rejects_relative_path_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = pathlib.Path(folder) / "mpv"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            previous = os.getcwd()
            os.chdir(folder)
            try:
                with mock.patch.dict(os.environ, {"PATH": ":relative"}):
                    self.assertIsNone(player.shutil_which("mpv"))
                with mock.patch.dict(os.environ, {"PATH": folder}):
                    self.assertEqual(player.shutil_which("mpv"), str(executable.resolve()))
            finally:
                os.chdir(previous)

    def test_control_clamps_volume(self):
        with mock.patch.object(player, "load_config", return_value={}), \
             mock.patch.object(player, "mpv_properties", return_value={"idle-active": False}), \
             mock.patch.object(player, "mpv_command") as command, \
             mock.patch.object(player, "status", return_value={"volume": 130}):
            result = player.control("volume", 999)
        self.assertIn(mock.call(["set_property", "volume", 130], True), command.call_args_list)
        self.assertEqual(result["volume"], 130)
        self.assertEqual(player.state_data()["volume"], 130)

    def test_stopped_player_remembers_volume_for_status_and_resume(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        player.atomic_json(player.STATE_FILE, {
            "queue": [{"key": "1", "_part": "/part/1"}],
            "queueNamespace": player.cache_namespace(config),
            "volume": 42,
        })
        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_properties", return_value=None), \
             mock.patch.object(player, "update_timeline"):
            result = player.control("volume", 37)
        self.assertEqual(result["volume"], 37)
        self.assertEqual(player.state_data()["volume"], 37)

    def test_unconfigured_status_does_not_start_player(self):
        with mock.patch.object(player, "load_config", return_value={}), \
             mock.patch.object(player, "load_json", return_value={"queue": []}), \
             mock.patch.object(player, "mpv_running", return_value=False):
            result = player.status()
        self.assertFalse(result["configured"])
        self.assertFalse(result["playing"])

    def test_repeat_cycles_off_all_one(self):
        state = {"queue": [], "repeat": "off", "shuffle": False}
        player.atomic_json(player.STATE_FILE, state)
        with mock.patch.object(player, "load_config", return_value={}), \
             mock.patch.object(player, "mpv_properties", return_value={"idle-active": False}), \
             mock.patch.object(player, "player_snapshot", return_value={"running": True, "urls": []}), \
             mock.patch.object(player, "mpv_command") as command, \
             mock.patch.object(player, "status", return_value={"repeat": "all"}):
            result = player.control("repeat")
        self.assertEqual(player.state_data()["repeat"], "all")
        self.assertIn(mock.call(["set_property", "loop-playlist", "inf"], True), command.call_args_list)
        self.assertEqual(result["repeat"], "all")

    def test_shuffle_toggle_shuffles_and_restores_the_queue(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        original = []
        original_playlist = []
        for key in ("1", "2", "3"):
            url = f"http://plex/part/{key}"
            original.append({"key": key, "_streamHash": player.hashlib.sha256(url.encode()).hexdigest()})
            original_playlist.append({"filename": url})
        shuffled_playlist = [original_playlist[0], original_playlist[2], original_playlist[1]]
        player.atomic_json(player.STATE_FILE, {
            "queue": original,
            "repeat": "off",
            "shuffle": False,
            "queueNamespace": player.cache_namespace(config),
        })
        playlists = iter((shuffled_playlist, original_playlist))

        def command(values, _expect_reply=False):
            if values == ["get_property", "playlist"]:
                return next(playlists)
            return None

        with mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "mpv_properties", return_value={"idle-active": False}), \
             mock.patch.object(player, "player_snapshot", return_value={"running": True, "urls": []}), \
             mock.patch.object(player, "mpv_command", side_effect=command) as mpv_command, \
             mock.patch.object(player, "status", side_effect=({"shuffle": True}, {"shuffle": False})), \
             mock.patch.object(player.time, "sleep"):
            self.assertTrue(player.control("shuffle")["shuffle"])
            self.assertEqual([item["key"] for item in player.state_data()["queue"]], ["1", "3", "2"])
            self.assertFalse(player.control("shuffle")["shuffle"])

        self.assertIn(mock.call(["playlist-shuffle"], True), mpv_command.call_args_list)
        self.assertIn(mock.call(["playlist-unshuffle"], True), mpv_command.call_args_list)
        self.assertEqual([item["key"] for item in player.state_data()["queue"]], ["1", "2", "3"])

    def test_queue_remove_updates_mpv_and_state(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        state = {"queue": [{"key": "1"}, {"key": "2"}], "repeat": "off", "shuffle": False,
                 "queueNamespace": player.cache_namespace(config)}
        player.atomic_json(player.STATE_FILE, state)
        with mock.patch.object(player, "mpv_running", return_value=True), \
             mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "property_or", return_value=0), \
             mock.patch.object(player, "player_snapshot", return_value={"running": True, "urls": []}), \
             mock.patch.object(player, "mpv_commands") as commands, \
             mock.patch.object(player, "queue_view", return_value={"items": [{"key": "1"}]}):
            result = player.queue_action("remove", index=1)
        commands.assert_called_once_with([["playlist-remove", 1]])
        self.assertEqual(player.state_data()["queue"], [{"key": "1"}])
        self.assertEqual(len(result["items"]), 1)

    def test_rejected_queue_command_does_not_commit_local_state(self):
        config = {"server": "http://plex", "token": "tok", "section": "4"}
        original = {"queue": [{"key": "1"}, {"key": "2"}], "repeat": "off", "shuffle": False,
                    "queueNamespace": player.cache_namespace(config)}
        player.atomic_json(player.STATE_FILE, original)
        with mock.patch.object(player, "mpv_running", return_value=True), \
             mock.patch.object(player, "load_config", return_value=config), \
             mock.patch.object(player, "property_or", return_value=0), \
             mock.patch.object(player, "player_snapshot", return_value={"running": True, "urls": []}), \
             mock.patch.object(player, "mpv_commands", side_effect=player.PlayerError("rejected", "player-ipc")), \
             mock.patch.object(player, "restore_player") as restore:
            with self.assertRaisesRegex(player.PlayerError, "rejected"):
                player.queue_action("remove", index=1)
        self.assertEqual(player.state_data()["queue"], original["queue"])
        restore.assert_called_once()

    def test_current_queue_track_cannot_be_moved_or_removed(self):
        state = {"queue": [{"key": "1"}, {"key": "2"}], "repeat": "off", "shuffle": False}
        with mock.patch.object(player, "state_data", return_value=state), \
             mock.patch.object(player, "mpv_running", return_value=True), \
             mock.patch.object(player, "property_or", return_value=1), \
             mock.patch.object(player, "mpv_command") as command:
            for action in ("move", "remove"):
                with self.assertRaisesRegex(player.PlayerError, "currently playing"):
                    player.queue_action(action, index=1, destination=0)
        command.assert_not_called()

    def test_demo_never_requires_plex(self):
        result = player.demo_dispatch(mock.Mock(command="library", view="artists"))
        self.assertTrue(result["demo"])
        self.assertEqual({item["type"] for item in result["items"]}, {"artist"})

    def test_timeline_request_posts_player_identity_and_position(self):
        response = mock.MagicMock(status=200)
        context = mock.MagicMock()
        context.__enter__.return_value = response
        config = {"server": "http://plex", "token": "secret", "clientIdentifier": "client-1"}
        report = {"sessionId": "session-1", "trackKey": "42", "state": "playing",
                  "positionMs": 1234, "durationMs": 5678}
        with mock.patch.object(player, "safe_urlopen", return_value=context) as urlopen:
            self.assertTrue(player.send_timeline(config, report))
        request = urlopen.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data, b"")
        self.assertEqual(query["ratingKey"], ["42"])
        self.assertEqual(query["state"], ["playing"])
        self.assertEqual(query["time"], ["1234"])
        self.assertEqual(headers["x-plex-client-identifier"], "client-1")
        self.assertEqual(headers["x-plex-session-identifier"], "session-1")
        self.assertEqual(headers["x-plex-product"], "Plexarchy")
        self.assertNotIn("X-Plex-Token", request.full_url)

    def test_timeline_is_throttled_and_pause_is_immediate(self):
        config = {"server": "http://plex", "token": "secret", "clientIdentifier": "client-1"}
        playing = {"playing": True, "paused": False, "track": {"key": "42"},
                   "position": 1.0, "duration": 10.0}
        paused = {**playing, "playing": False, "paused": True, "position": 2.0}
        with mock.patch.object(player, "send_timeline", return_value=True) as send, \
             mock.patch.object(player.uuid, "uuid4", return_value="session-1"), \
             mock.patch.object(player.time, "time", side_effect=(100, 100, 105, 106, 106, 111)):
            player.update_timeline(config, playing)
            player.update_timeline(config, {**playing, "position": 1.5})
            player.update_timeline(config, paused)
            player.update_timeline(config, paused)
        self.assertEqual([call.args[1]["state"] for call in send.call_args_list],
                         ["playing", "paused"])
        self.assertEqual({call.args[1]["sessionId"] for call in send.call_args_list}, {"session-1"})

    def test_timeline_reports_playback_progress_every_ten_seconds(self):
        config = {"server": "http://plex", "token": "secret", "clientIdentifier": "client-1"}
        playing = {"playing": True, "paused": False, "track": {"key": "42"},
                   "position": 1.0, "duration": 30.0}
        with mock.patch.object(player, "send_timeline", return_value=True) as send, \
             mock.patch.object(player.uuid, "uuid4", return_value="session-1"), \
             mock.patch.object(player.time, "time", side_effect=(100, 100, 111, 111)):
            player.update_timeline(config, playing)
            player.update_timeline(config, {**playing, "position": 12.0})
        self.assertEqual([call.args[1]["positionMs"] for call in send.call_args_list], [1000, 12000])

    def test_track_change_stops_old_session_and_starts_a_new_one(self):
        config = {"server": "http://plex", "token": "secret", "clientIdentifier": "client-1"}
        first = {"playing": True, "paused": False, "track": {"key": "1"},
                 "position": 9.0, "duration": 10.0}
        second = {"playing": True, "paused": False, "track": {"key": "2"},
                  "position": 0.2, "duration": 20.0}
        with mock.patch.object(player, "send_timeline", return_value=True) as send, \
             mock.patch.object(player.uuid, "uuid4", side_effect=("session-1", "session-2")), \
             mock.patch.object(player.time, "time", side_effect=(100, 100, 101, 101)):
            player.update_timeline(config, first)
            player.update_timeline(config, second)
        reports = [call.args[1] for call in send.call_args_list]
        self.assertEqual([(row["trackKey"], row["state"]) for row in reports],
                         [("1", "playing"), ("1", "stopped"), ("2", "playing")])
        self.assertEqual(reports[-1]["sessionId"], "session-2")

    def test_stop_clears_timeline_without_interrupting_on_network_error(self):
        config = {"server": "http://plex", "token": "secret", "clientIdentifier": "client-1"}
        playing = {"playing": True, "paused": False, "track": {"key": "42"},
                   "position": 1.0, "duration": 10.0}
        stopped = {**playing, "playing": False, "paused": False, "position": 4.0}
        with mock.patch.object(player, "send_timeline", return_value=False) as send, \
             mock.patch.object(player.uuid, "uuid4", return_value="session-1"), \
             mock.patch.object(player.time, "time", side_effect=(100, 100, 101, 101)):
            player.update_timeline(config, playing)
            player.update_timeline(config, stopped)
        self.assertEqual(send.call_args_list[-1].args[1]["state"], "stopped")
        self.assertEqual(send.call_args_list[-1].args[1]["positionMs"], 4000)
        self.assertNotIn("timeline", player.state_data())


class RepositoryContractTests(unittest.TestCase):
    def test_manifest_and_entry_point(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "community.plexarchy")
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertIn("bar-widget", manifest["kinds"])
        self.assertTrue((ROOT / manifest["entryPoints"]["barWidget"]).is_file())
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertIn(f'APP_VERSION = "{manifest["version"]}"', HELPER.read_text(encoding="utf-8"))

    def test_mpris_client_name_is_a_valid_bus_component(self):
        helper = (ROOT / "bin" / "plexarchy").read_text(encoding="utf-8")
        self.assertIn('"--audio-client-name=Plexarchy"', helper)

    def test_no_credentials_are_tracked(self):
        forbidden = b"X-Plex" + b"-Token=" + b"real"
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts:
                source = path.read_bytes()
                self.assertNotIn(forbidden, source, str(path))
