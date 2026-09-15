#!/usr/bin/env python3
"""Run Panel.qml headlessly against fake Plex servers using the Qt `qml` runtime.

Requires: qml (Qt 6), QtQuick Controls/Layouts modules, mpv. Exercised by
tests/test_qml_harness.py; can also be run directly for debugging.
"""
from __future__ import annotations

import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import fake_plex  # noqa: E402


def find_qml() -> str | None:
    for name in ("qml", "qml6", "qml-qt6"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in ("/usr/lib/qt6/bin/qml", "/usr/lib/x86_64-linux-gnu/qt6/bin/qml"):
        if os.access(candidate, os.X_OK):
            return candidate
    return None


class Bridge(http.server.BaseHTTPRequestHandler):
    env: dict[str, str] = {}
    log: list[list[str]] = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        command = [str(part) for part in payload.get("command", [])]
        self.log.append(command)
        if os.environ.get("HARNESS_DEBUG"):
            print("[bridge]", " ".join(command[1:]), file=sys.stderr, flush=True)
        if command and command[0] == "omarchy-audio-output-sink":
            result = {"stdout": "stub-sink\n", "stderr": "", "code": 0}
        elif command and command[0] == "omarchy":
            result = {"stdout": "ok\n", "stderr": "", "code": 0}
        else:
            try:
                completed = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=60)
                result = {"stdout": completed.stdout, "stderr": completed.stderr, "code": completed.returncode}
            except (OSError, subprocess.TimeoutExpired) as error:
                result = {"stdout": "", "stderr": str(error), "code": 127}
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    qml = find_qml()
    if not qml:
        print("qml runtime not found", file=sys.stderr)
        return 5
    plex_server, state = fake_plex.serve()
    home = tempfile.mkdtemp(prefix="plexarchy-harness-")
    mpv_dir = pathlib.Path(home) / "config" / "mpv"
    mpv_dir.mkdir(parents=True)
    (mpv_dir / "mpv.conf").write_text("ao=null\n")
    env = dict(os.environ, HOME=home,
               XDG_CONFIG_HOME=str(pathlib.Path(home) / "config"),
               XDG_CACHE_HOME=str(pathlib.Path(home) / "cache"),
               PLEXARCHY_PLEX_TV_URL=state.base_url + "/api/v2")
    Bridge.env = env
    bridge = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Bridge)
    threading.Thread(target=bridge.serve_forever, daemon=True).start()
    (HERE / "imports" / "Quickshell" / "Io" / "HarnessConfig.js").write_text(f"var port = {bridge.server_port}\n")

    qml_env = dict(env, QT_QPA_PLATFORM="offscreen", QML_IMPORT_PATH=str(HERE / "imports"),
                   QT_LOGGING_RULES="qt.qml.binding.removal.info=false")
    try:
        completed = subprocess.run([qml, "-platform", "offscreen", str(HERE / "Main.qml")], env=qml_env,
                                   capture_output=True, text=True, timeout=150)
    finally:
        subprocess.run([str(ROOT / "bin" / "plexarchy"), "shutdown"], env=env, capture_output=True, timeout=30)
        plex_server.shutdown()
        bridge.shutdown()
        shutil.rmtree(home, ignore_errors=True)
    output = completed.stdout + completed.stderr
    print(output)
    passes = output.count("HARNESS PASS")
    fails = output.count("HARNESS FAIL")
    print(f"harness: {passes} passed, {fails} failed, exit {completed.returncode}")
    return completed.returncode if completed.returncode != 0 else (1 if fails else 0)


if __name__ == "__main__":
    raise SystemExit(main())
