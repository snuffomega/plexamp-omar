# Contributing

Bug reports and pull requests are welcome. Keep the runtime dependency-light:
QML/Quickshell for the interface, Python's standard library for Plex access,
and mpv for playback.

Run the checks before opening a pull request:

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_model.js
omarchy plugin validate .
qmlformat Panel.qml > /dev/null
python3 tests/qml-harness/run.py   # needs a Qt 6 `qml` runtime and mpv
```

Never add real Plex URLs, tokens, library names, or media metadata to fixtures.
