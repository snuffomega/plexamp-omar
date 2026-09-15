import contextlib
import io
import pathlib
import stat
import tempfile
import unittest
from unittest import mock

from test_player import player


class LinkFlowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = pathlib.Path(self.folder.name)
        patches = [
            mock.patch.object(player, "CONFIG_FILE", root / "config.json"),
            mock.patch.object(player, "STATE_FILE", root / "state.json"),
            mock.patch.object(player, "CACHE_DIR", root / "cache"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_link_start_stores_private_pending_pin(self):
        with mock.patch.object(player, "plex_cloud_request", return_value={"id": 7, "code": "ABCD"}) as request:
            result = player.link_start()
        self.assertEqual(result["code"], "ABCD")
        self.assertIn("https://app.plex.tv/auth#?", result["url"])
        self.assertIn("code=ABCD", result["url"])
        self.assertEqual(request.call_args.kwargs["fields"], {"strong": "true"})
        saved = player.load_settings()
        self.assertEqual(saved["pendingLink"]["id"], "7")
        self.assertEqual(stat.S_IMODE(player.CONFIG_FILE.stat().st_mode), 0o600)
        self.assertEqual(player.account_state()["stage"], "unlinked")
        self.assertTrue(player.account_state()["linkPending"])

    def test_link_poll_saves_account_token_and_name(self):
        player.save_settings({"pendingLink": {"id": "7", "code": "ABCD", "createdAt": 10 ** 12}})
        with mock.patch.object(player, "plex_cloud_request", side_effect=[{"authToken": None}]):
            self.assertEqual(player.link_poll()["linked"], False)
        with mock.patch.object(player, "plex_cloud_request",
                               side_effect=[{"authToken": "acct"}, {"username": "dhh"}]) as request:
            result = player.link_poll()
        self.assertTrue(result["linked"])
        self.assertEqual(result["account"], "dhh")
        self.assertEqual(request.call_args_list[0].args[0], "/pins/7")
        self.assertEqual(request.call_args_list[0].kwargs["fields"], {"code": "ABCD"})
        saved = player.load_settings()
        self.assertEqual(saved["accountToken"], "acct")
        self.assertNotIn("pendingLink", saved)
        self.assertEqual(player.account_state()["stage"], "servers")

    def test_link_poll_expires_old_pins(self):
        player.save_settings({"pendingLink": {"id": "7", "code": "ABCD", "createdAt": 1}})
        with mock.patch.object(player, "plex_cloud_request") as request:
            result = player.link_poll()
        self.assertTrue(result["expired"])
        request.assert_not_called()
        self.assertNotIn("pendingLink", player.load_settings())

    def test_cloud_get_puts_fields_in_query_string(self):
        captured = {}

        class Response:
            def read(self, size):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_open(request, timeout):
            captured["url"] = request.full_url
            captured["data"] = request.data
            captured["method"] = request.get_method()
            return Response()

        with mock.patch.object(player, "safe_urlopen", side_effect=fake_open):
            player.plex_cloud_request("/pins/7", fields={"code": "ABCD"})
        self.assertEqual(captured["url"], "https://plex.tv/api/v2/pins/7?code=ABCD")
        self.assertIsNone(captured["data"])
        self.assertEqual(captured["method"], "GET")

    def resources(self):
        return [
            {"name": "Attic", "provides": "server", "clientIdentifier": "srv-1", "owned": True,
             "accessToken": "srv-token", "productVersion": "1.41", "platform": "Linux",
             "connections": [
                 {"protocol": "https", "address": "1.2.3.4", "port": 32400, "uri": "https://1-2-3-4.plex.direct:32400", "local": False, "relay": False},
                 {"protocol": "http", "address": "192.168.1.5", "port": 32400, "uri": "http://192.168.1.5:32400", "local": True, "relay": False},
                 {"protocol": "https", "address": "relay", "port": 8443, "uri": "https://relay.plex.direct:8443", "local": False, "relay": True},
             ]},
            {"name": "Phone", "provides": "player", "clientIdentifier": "phone", "connections": []},
            {"name": "Shared", "provides": "server", "clientIdentifier": "srv-2", "owned": False,
             "accessToken": "shared-token", "connections": [
                 {"protocol": "https", "address": "9.9.9.9", "port": 32400, "uri": "https://9.9.9.9:32400", "local": False, "relay": False}]},
        ]

    def test_discover_servers_prefers_reachable_local_direct_connections(self):
        reachable = {"http://192.168.1.5:32400", "https://relay.plex.direct:8443"}
        with mock.patch.object(player, "plex_cloud_request", return_value=self.resources()) as request, \
             mock.patch.object(player, "probe_server", side_effect=lambda uri, token, expected="": uri in reachable):
            servers = player.discover_servers("acct")
        self.assertEqual(request.call_args.kwargs["fields"], {"includeHttps": "1", "includeRelay": "1"})
        self.assertTrue(request.call_args.kwargs["allow_list"])
        self.assertEqual([s["name"] for s in servers], ["Attic", "Shared"])
        attic = servers[0]
        self.assertTrue(attic["reachable"])
        self.assertEqual(attic["uri"], "http://192.168.1.5:32400")
        self.assertTrue(attic["local"])
        self.assertFalse(attic["relay"])
        self.assertFalse(servers[1]["reachable"])
        self.assertNotIn("token", player.public_servers(servers)[0])

    def test_select_server_saves_server_token_and_auto_picks_single_library(self):
        player.save_settings({"accountToken": "acct", "accountName": "dhh"})
        with mock.patch.object(player, "plex_cloud_request", return_value=self.resources()), \
             mock.patch.object(player, "probe_server", return_value=True), \
             mock.patch.object(player, "sections", return_value=[{"key": "4", "title": "Music"}]) as sections:
            result = player.select_server("srv-1")
        candidate = sections.call_args.args[0]
        self.assertEqual(candidate["token"], "srv-token")
        self.assertEqual(candidate["server"], "http://192.168.1.5:32400")
        saved = player.load_settings()
        self.assertEqual(saved["accountToken"], "acct")
        self.assertEqual(saved["token"], "srv-token")
        self.assertEqual(saved["serverId"], "srv-1")
        self.assertEqual(saved["section"], "4")
        self.assertEqual(result["state"]["stage"], "ready")
        self.assertEqual(stat.S_IMODE(player.CONFIG_FILE.stat().st_mode), 0o600)

    def test_select_server_with_many_libraries_waits_for_choice(self):
        player.save_settings({"accountToken": "acct"})
        libraries = [{"key": "4", "title": "Music"}, {"key": "9", "title": "Audiobooks"}]
        with mock.patch.object(player, "plex_cloud_request", return_value=self.resources()), \
             mock.patch.object(player, "probe_server", return_value=True), \
             mock.patch.object(player, "sections", return_value=libraries):
            result = player.select_server("srv-1")
            self.assertEqual(result["state"]["stage"], "libraries")
            self.assertEqual(len(result["libraries"]), 2)
            chosen = player.select_library("9")
        self.assertEqual(chosen["library"]["title"], "Audiobooks")
        self.assertEqual(player.account_state()["stage"], "ready")
        self.assertEqual(player.account_state()["library"], "Audiobooks")

    def test_select_unreachable_server_is_rejected(self):
        player.save_settings({"accountToken": "acct"})
        with mock.patch.object(player, "plex_cloud_request", return_value=self.resources()), \
             mock.patch.object(player, "probe_server", return_value=False):
            with self.assertRaises(player.PlayerError) as raised:
                player.select_server("srv-1")
        self.assertEqual(raised.exception.code, "unreachable")
        self.assertNotIn("server", player.load_settings())

    def test_select_server_requires_linked_account(self):
        with self.assertRaises(player.PlayerError) as raised:
            player.select_server("srv-1")
        self.assertEqual(raised.exception.code, "unlinked")

    def test_health_recovers_by_re_resolving_server_address(self):
        player.save_settings({"accountToken": "acct", "serverId": "srv-1", "server": "http://old:32400",
                              "token": "srv-token", "section": "4", "sectionTitle": "Music"})
        calls = {"count": 0}

        def sections(config):
            calls["count"] += 1
            if config["server"] == "http://old:32400":
                raise player.PlayerError("offline", "unreachable")
            return [{"key": "4", "title": "Music"}]

        with mock.patch.object(player, "sections", side_effect=sections), \
             mock.patch.object(player, "plex_cloud_request", return_value=self.resources()), \
             mock.patch.object(player, "probe_server", side_effect=lambda uri, *a: uri.startswith("http://192")):
            health = player.connection_health()
        self.assertTrue(health["ok"])
        self.assertEqual(player.load_settings()["server"], "http://192.168.1.5:32400")
        self.assertEqual(calls["count"], 2)

    def test_reconnect_attempts_are_rate_limited(self):
        player.save_settings({"accountToken": "acct", "serverId": "srv-1", "server": "http://old:32400",
                              "token": "t", "lastReconnectAt": 10 ** 12})
        with mock.patch.object(player, "plex_cloud_request") as request:
            self.assertFalse(player.refresh_server_connection(player.load_settings()))
        request.assert_not_called()

    def test_logout_removes_account_and_pending_link(self):
        player.save_settings({"accountToken": "acct", "server": "http://plex:32400", "token": "t",
                              "pendingLink": {"id": "1", "code": "X", "createdAt": 10 ** 12}})
        with mock.patch.object(player, "shutdown_player", return_value={"stopped": True}), \
             mock.patch.object(player, "stop_timeline"):
            player.logout()
        saved = player.load_settings()
        self.assertEqual(set(saved), {"clientIdentifier"})
        self.assertEqual(player.account_state()["stage"], "unlinked")

    def test_terminal_login_discovers_servers_after_linking(self):
        cloud = [
            {"id": 7, "code": "ABCD"},
            {"authToken": "acct"},
            {"username": "dhh"},
            self.resources(),
            self.resources(),
        ]
        with mock.patch.object(player, "plex_cloud_request", side_effect=cloud), \
             mock.patch.object(player, "probe_server", side_effect=lambda uri, *a: uri.startswith("http://192")), \
             mock.patch.object(player, "sections", return_value=[{"key": "4", "title": "Music"}]), \
             mock.patch.object(player.subprocess, "Popen"), \
             mock.patch.object(player.time, "sleep"), \
             contextlib.redirect_stdout(io.StringIO()):
            result = player.login("")
        self.assertTrue(result["connected"])
        self.assertEqual(result["serverName"], "Attic")
        self.assertEqual(player.load_settings()["token"], "srv-token")
        self.assertEqual(player.account_state()["stage"], "ready")


if __name__ == "__main__":
    unittest.main()
