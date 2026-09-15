"""End-to-end test: real helper CLI + real mpv against a fake plex.tv / Plex Media Server.

Skipped automatically when mpv is not installed.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import unittest

import fake_plex

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin" / "plexarchy"


@unittest.skipUnless(shutil.which("mpv"), "mpv is not installed")
class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.state = fake_plex.serve()
        cls.home = tempfile.mkdtemp(prefix="plexarchy-e2e-")
        mpv_dir = pathlib.Path(cls.home) / "config" / "mpv"
        mpv_dir.mkdir(parents=True)
        (mpv_dir / "mpv.conf").write_text("ao=null\n")
        cls.env = dict(os.environ, HOME=cls.home,
                       XDG_CONFIG_HOME=str(pathlib.Path(cls.home) / "config"),
                       XDG_CACHE_HOME=str(pathlib.Path(cls.home) / "cache"),
                       PLEXARCHY_PLEX_TV_URL=cls.state.base_url + "/api/v2")

    @classmethod
    def tearDownClass(cls):
        cls.run_helper("shutdown", check=False)
        cls.server.shutdown()
        shutil.rmtree(cls.home, ignore_errors=True)

    @classmethod
    def run_helper(cls, *args, check=True):
        result = subprocess.run([str(HELPER), *args], env=cls.env, capture_output=True, text=True, timeout=60)
        if check and result.returncode != 0:
            raise AssertionError(f"{args} failed: {result.stderr}")
        payload = result.stdout if result.returncode == 0 else result.stderr
        return json.loads(payload) if payload.strip() else {}

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.run_helper("status")
            if predicate(status):
                return status
            time.sleep(0.25)
        raise AssertionError(f"timed out waiting; last status {status}")

    def test_full_flow(self):
        # 1. Account linking through the PIN flow.
        self.assertEqual(self.run_helper("account")["stage"], "unlinked")
        started = self.run_helper("link", "start")
        self.assertEqual(started["code"], "QWER")
        self.assertFalse(self.run_helper("link", "poll")["linked"])
        polled = self.run_helper("link", "poll")
        self.assertTrue(polled["linked"])
        self.assertEqual(polled["account"], "tester")
        self.assertEqual(self.run_helper("account")["stage"], "servers")
        config = json.loads((pathlib.Path(self.home) / "config" / "plexarchy" / "config.json").read_text())
        self.assertEqual(oct(os.stat(pathlib.Path(self.home) / "config" / "plexarchy" / "config.json").st_mode & 0o777), "0o600")
        self.assertEqual(config["accountToken"], "account-token")

        # 2. Server discovery picks the reachable connection and the server token.
        servers = self.run_helper("servers")["servers"]
        self.assertEqual([s["name"] for s in servers], ["Fake Attic", "Offline Box"])
        self.assertTrue(servers[0]["reachable"])
        self.assertEqual(servers[0]["uri"], self.state.base_url)
        self.assertFalse(servers[1]["reachable"])
        self.assertNotIn("token", servers[0])
        selected = self.run_helper("select-server", self.state.machine)
        self.assertEqual(selected["state"]["stage"], "ready")
        self.assertEqual(selected["state"]["library"], "Music")
        health = self.run_helper("health")
        self.assertTrue(health["ok"], health)

        # 3. Browsing, search, artist/album/playlist navigation.
        recent = self.run_helper("library", "recent", "--limit", "10")["items"]
        self.assertEqual(recent[0]["title"], "Paper Maps")
        art = self.run_helper("art", recent[0]["artSource"])["thumb"]
        self.assertTrue(art.startswith("file://"), art)
        artists = self.run_helper("library", "artists")["items"]
        self.assertEqual([a["title"] for a in artists], ["Aurora Fields", "Night Cartographers"])
        albums = self.run_helper("children", "artist", "100")["items"]
        self.assertEqual([a["title"] for a in albums], ["Slow Light", "Meridian"])
        tracks = self.run_helper("children", "album", "110")["items"]
        self.assertEqual(len(tracks), 3)
        self.assertEqual(tracks[0]["artist"], "Aurora Fields")
        search = self.run_helper("search", "meridian")["items"]
        self.assertEqual({row["type"] for row in search}, {"album", "track"})
        playlists = self.run_helper("library", "playlists")["items"]
        self.assertEqual(playlists[0]["title"], "Evening Drive")
        self.assertEqual(len(self.run_helper("children", "playlist", "900")["items"]), 2)

        # 4. Playback through mpv: play, progress, pause, next, queue, shuffle/repeat.
        status = self.run_helper("play", "1101", "--album", "110")
        self.assertEqual(status["track"]["title"], "Slow Light 1")
        self.assertEqual(status["queueLength"], 3)
        status = self.wait_for(lambda s: s["playing"] and s["position"] > 0.2)
        self.assertGreater(status["duration"], 3)
        self.assertIn("account-token", self.state.tokens_seen)
        self.assertIn("server-token", self.state.tokens_seen)
        paused = self.run_helper("control", "toggle")
        self.assertTrue(paused["paused"])
        self.run_helper("control", "toggle")
        moved = self.run_helper("control", "next")
        self.assertEqual(moved["track"]["title"], "Slow Light 2")
        self.assertEqual(moved["queueIndex"], 1)
        queue = self.run_helper("queue")["items"]
        self.assertTrue(queue[1]["current"])
        self.run_helper("control", "seek", "2")
        status = self.wait_for(lambda s: s["position"] >= 1.5)
        self.assertEqual(self.run_helper("control", "shuffle")["shuffle"], True)
        self.assertEqual(self.run_helper("control", "repeat")["repeat"], "all")
        self.run_helper("control", "volume", "60")
        self.assertAlmostEqual(self.run_helper("status")["volume"], 60, delta=1)
        self.run_helper("queue-action", "play-next", "--track", "2101")
        titles = [row["title"] for row in self.run_helper("queue")["items"]]
        self.assertIn("Paper Maps 1", titles)
        self.assertEqual(titles.index("Paper Maps 1"), titles.index("Slow Light 2") + 1)

        # 5. Plex timeline reporting.
        self.run_helper("status")
        states = {row.get("state") for row in self.state.timelines}
        self.assertIn("playing", states)
        self.assertTrue(all(row.get("ratingKey") for row in self.state.timelines))
        self.assertTrue(all(row.get("X-Plex-Token") is None for row in self.state.timelines))

        # 6. Recovery: the server token rotates; health re-resolves it from plex.tv.
        self.state.server_token = "rotated-token"
        health = self.run_helper("health")
        self.assertTrue(health["ok"], health)
        self.assertIn("rotated-token", self.state.tokens_seen)

        # 7. Shutdown reports stopped and terminates mpv.
        result = self.run_helper("shutdown")
        self.assertTrue(result.get("stopped", True))
        self.assertIn("stopped", {row.get("state") for row in self.state.timelines})
        self.assertFalse(self.run_helper("status")["playing"])

        # 8. Logout wipes credentials.
        self.run_helper("logout")
        self.assertEqual(self.run_helper("account")["stage"], "unlinked")


if __name__ == "__main__":
    unittest.main()
