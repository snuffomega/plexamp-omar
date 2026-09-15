"""Runs the headless QML harness (Panel.qml + fake Plex + real mpv) when a Qt 6 `qml` runtime is available."""
import pathlib
import shutil
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "qml-harness"))
import run as harness  # noqa: E402


@unittest.skipUnless(harness.find_qml() and shutil.which("mpv"), "qml runtime or mpv is not installed")
class QmlHarnessTests(unittest.TestCase):
    def test_panel_flows_headlessly(self):
        completed = subprocess.run([sys.executable, str(HERE / "qml-harness" / "run.py")],
                                   capture_output=True, text=True, timeout=240)
        summary = [line for line in completed.stdout.splitlines() if line.startswith("harness:") or "HARNESS FAIL" in line]
        self.assertEqual(completed.returncode, 0, "\n".join(summary) or completed.stderr[-2000:])
        self.assertIn("HARNESS DONE failures=0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
