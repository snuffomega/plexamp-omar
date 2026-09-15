import QtQuick
import QtQuick.Window
import Quickshell.Io

// Headless smoke test: hosts Panel.qml with a fake Omarchy bar and walks the
// linking, browsing, and playback flows against the fake Plex servers started
// by run.py. Prints "HARNESS PASS <name>" / "HARNESS FAIL <name>: <detail>".
Window {
  id: window
  width: 1400
  height: 900
  visible: true

  property int failures: 0
  property var runCommands: []

  QtObject {
    id: fakeBar
    property color foreground: "#e6e1d7"
    property color barForeground: "#e6e1d7"
    property color background: "#1c1b19"
    property color urgent: "#e05c4a"
    property string fontFamily: "monospace"
    property string position: "top"
    property bool vertical: false
    property int barSize: 26
    property bool transparent: false
    property bool foregroundAnimationEnabled: false
    property var activePopout: null
    property var shell: QtObject {
      function summon(id, payload) { console.log("[bar] summon", id, payload) }
    }
    function run(command) { window.runCommands.push(String(command)); console.log("[bar] run", command) }
    function showTooltip(target, text) {}
    function hideTooltip(target) {}
    function requestPopout(owner) { activePopout = owner }
    function releasePopout(owner) { if (activePopout === owner) activePopout = null }
    function switchPanelFrom(owner, direction) { return false }
  }

  Loader {
    id: loader
    source: Qt.resolvedUrl("../../Panel.qml")
    onLoaded: {
      item.bar = fakeBar
      item.moduleName = "community.plexarchy"
      item.settings = ({ recentAlbumCount: 10, libraryItemCount: 50 })
      scenario.start()
    }
    onStatusChanged: if (status === Loader.Error) { console.log("HARNESS FAIL load:", sourceComponent ? sourceComponent.errorString() : "unknown"); Qt.exit(2) }
  }

  readonly property var panel: loader.item

  function check(name, condition, detail) {
    if (condition) console.log("HARNESS PASS " + name)
    else { failures += 1; console.log("HARNESS FAIL " + name + ": " + (detail === undefined ? "" : detail)) }
  }

  function waitFor(name, predicate, timeoutMs, next) {
    var started = Date.now()
    var timer = Qt.createQmlObject('import QtQuick; Timer { interval: 150; repeat: true; running: true }', window)
    timer.triggered.connect(function() {
      var ok = false
      try { ok = predicate() } catch (error) { ok = false }
      if (ok || Date.now() - started > timeoutMs) {
        timer.stop(); timer.destroy()
        check(name, ok, ok ? "" : "timed out after " + timeoutMs + "ms; view=" + panel.view + " kind=" + panel.currentParentKind + " items=" + panel.items.length + " loading=" + panel.loading + " error=" + panel.errorText)
        next()
      }
    })
  }

  QtObject {
    id: scenario
    property var steps: []
    property int index: 0

    function start() {
      steps = [
        function(next) { waitFor("initial status polled", function() { return panel.player.stage !== undefined }, 8000, next) },
        function(next) {
          check("starts unlinked", panel.stage === "unlinked", panel.stage)
          check("setup needed before linking", panel.setupNeeded === true)
          check("bar collapses to icon slot when idle", panel.implicitWidth > 0 && panel.implicitWidth <= 40, panel.implicitWidth)
          panel.open()
          waitFor("panel opens into setup", function() { return panel.opened && panel.setupVisible }, 3000, next)
        },
        function(next) {
          panel.startLink()
          waitFor("link start shows PIN code", function() { return panel.linking && panel.linkCode === "QWER" }, 6000, next)
        },
        function(next) {
          check("browser opened via bar.run", window.runCommands.some(function(c) { return c.indexOf("xdg-open") === 0 && c.indexOf("code=QWER") > 0 }), JSON.stringify(window.runCommands))
          waitFor("poll reaches server stage", function() { return panel.stage === "servers" && panel.servers.length === 2 }, 15000, next)
        },
        function(next) {
          check("reachable server first", panel.servers[0].name === "Fake Attic" && panel.servers[0].reachable === true, JSON.stringify(panel.servers))
          check("unreachable server flagged", panel.servers[1].reachable === false)
          panel.chooseServer(panel.servers[1])
          check("unreachable server is not selectable", panel.setupBusy === false)
          panel.chooseServer(panel.servers[0])
          waitFor("server selected and library auto-chosen", function() { return panel.stage === "ready" && panel.plexConnected && !panel.setupVisible }, 8000, next)
        },
        function(next) {
          waitFor("recent albums load", function() { return panel.view === "recent" && panel.items.length === 3 }, 8000, next)
        },
        function(next) {
          panel.query = "meridian"
          waitFor("search runs after debounce", function() { return panel.view === "search" && panel.items.length > 0 }, 5000, next)
        },
        function(next) {
          panel.loadView("artists")
          waitFor("artists view", function() { return panel.view === "artists" && panel.items.length === 2 }, 5000, next)
        },
        function(next) {
          panel.activateItem(panel.items[0])
          waitFor("artist opens albums", function() { return panel.view === "children" && panel.currentParentKind === "artist" && panel.items.length === 2 }, 5000, next)
        },
        function(next) {
          panel.activateItem(panel.items[0])
          waitFor("album opens tracks", function() { return panel.currentParentKind === "album" && panel.items.length === 3 }, 5000, next)
        },
        function(next) {
          panel.goBack()
          waitFor("back returns to artist albums", function() { return panel.currentParentKind === "artist" && panel.backStack.length === 1 }, 5000, next)
        },
        function(next) {
          panel.loadView("playlists")
          waitFor("playlists view", function() { return panel.view === "playlists" && panel.items.length === 1 }, 5000, next)
        },
        function(next) {
          panel.loadView("albums")
          waitFor("albums view", function() { return panel.view === "albums" && panel.items.length === 3 }, 5000, next)
        },
        function(next) {
          panel.playItemCollection(panel.items[0], false)
          waitFor("album plays through mpv", function() { return panel.activeTrack && panel.activeTrack.title === "Slow Light 1" && panel.player.playing === true }, 10000, next)
        },
        function(next) {
          check("bar expands with track, artist and controls", panel.implicitWidth >= 200, panel.implicitWidth)
          check("header artwork resolved", panel.activeThumb === "" || panel.activeThumb.indexOf("file://") === 0, panel.activeThumb)
          panel.control("toggle")
          waitFor("pause from panel", function() { return panel.player.paused === true }, 6000, next)
        },
        function(next) {
          panel.control("next")
          waitFor("next track", function() { return panel.activeTrack && panel.activeTrack.title === "Slow Light 2" }, 6000, next)
        },
        function(next) {
          panel.loadView("queue")
          waitFor("queue view marks current", function() { return panel.view === "queue" && panel.items.length === 3 && panel.items[1].current === true }, 6000, next)
        },
        function(next) {
          panel.helpVisible = true
          check("settings show server and library", panel.account.serverName === "Fake Attic" && panel.account.library === "Music", JSON.stringify(panel.account))
          panel.helpVisible = false
          panel.changeServer()
          waitFor("change server reopens picker", function() { return panel.setupVisible && panel.effectiveStage === "servers" && panel.servers.length === 2 }, 8000, next)
        },
        function(next) {
          panel.handleEscape()
          check("escape leaves picker without changes", panel.setupActive === false && panel.stage === "ready")
          panel.close()
          check("panel closes", panel.opened === false)
          check("playback survives panel close", panel.activeTrack !== null)
          next()
        }
      ]
      index = 0
      runNext()
    }

    function runNext() {
      if (index >= steps.length) {
        console.log("HARNESS DONE failures=" + window.failures)
        Qt.exit(window.failures === 0 ? 0 : 1)
        return
      }
      var step = steps[index++]
      step(runNext)
    }
  }

  Timer {
    interval: 120000
    running: true
    onTriggered: { console.log("HARNESS FAIL global timeout"); Qt.exit(3) }
  }
}
