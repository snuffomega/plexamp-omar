import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "community.plexarchy"
  ipcTarget: "community.plexarchy"

  property var player: ({ configured: false, connected: false, playing: false, track: null, position: 0, duration: 0, volume: 100, shuffle: false, repeat: "off" })
  property var items: []
  property var health: ({ ok: false, code: "unconfigured", message: "Connect your Plex account to start listening." })
  property var backStack: []
  property string view: "recent"
  property string currentParentKey: ""
  property string currentParentKind: ""
  property string currentParentTitle: ""
  property string query: ""
  property string errorText: ""
  property bool loading: false
  property int selectedIndex: 0
  property int nextDataRequestId: 0
  property int requestedDataRequestId: 0
  property int activeDataRequestId: 0
  property int queuedDataRequestId: 0
  property string queuedDataMode: ""
  property var queuedDataCommand: []
  property bool suppressSearch: false
  property int pendingSelectedIndex: -1
  property bool helpVisible: false
  property var pendingActions: []
  property var pendingQueueEdits: []
  property var pendingArtwork: []
  property var requestedArtwork: ({})
  property var resolvedArtwork: ({})
  property var resolvedArtworkOrder: []
  property string activeArtwork: ""
  property int artworkGeneration: 0
  property int activeArtworkGeneration: 0
  property string volumeSinkName: ""
  property string volumeModeOverride: ""
  property bool disconnecting: false
  property var account: ({ stage: "unlinked", linked: false, account: "", serverName: "", library: "" })
  property bool setupActive: false
  property string setupView: ""
  property bool linking: false
  property string linkCode: ""
  property string linkUrl: ""
  property var servers: []
  property var libraries: []
  property bool setupBusy: false
  property string setupError: ""
  property string statusFailure: ""

  readonly property string stage: account && account.stage ? String(account.stage) : "unlinked"
  readonly property string effectiveStage: setupView !== "" ? setupView : stage
  readonly property bool setupNeeded: !demoMode && (stage !== "ready" || setupActive)
  readonly property bool setupVisible: setupNeeded && !helpVisible
  readonly property bool showBarControls: setting("showBarControls", true) === true

  readonly property var navigation: [
    { id: "recent", label: "Home", icon: "\uf015" },
    { id: "artists", label: "Artists", icon: "\uf0c0" },
    { id: "albums", label: "Albums", icon: "\uf51f" },
    { id: "playlists", label: "Lists", icon: "\uf03a" },
    { id: "history", label: "Recent", icon: "\uf1da" },
    { id: "frequent", label: "Top", icon: "\uf201" },
    { id: "favorites", label: "Favs", icon: "\uf004" },
    { id: "queue", label: "Queue", icon: "\uf03b" }
  ]

  readonly property var keyboardHelp: [
    { keys: "← / →", action: "Switch library tabs" },
    { keys: "↑ / ↓", action: "Select a list item" },
    { keys: "Enter", action: "Open or play" },
    { keys: "Tab / Shift+Tab", action: "Move keyboard focus" },
    { keys: "Ctrl+Enter", action: "Play a collection" },
    { keys: "Shift+Enter", action: "Shuffle or play next" },
    { keys: "Ctrl+↑ / ↓", action: "Move a Queue item" },
    { keys: "Delete", action: "Remove a Queue item" },
    { keys: "Ctrl+Space", action: "Play or pause" },
    { keys: "Home / End", action: "Set a slider to its limit" },
    { keys: "Esc", action: "Clear, go back, or close" },
    { keys: "F1", action: "Toggle this help" }
  ]

  readonly property url helperUrl: Qt.resolvedUrl("bin/plexarchy")
  readonly property string helperPath: decodeURIComponent(String(helperUrl).replace(/^file:\/\//, ""))
  readonly property string logoGlyph: "\uf001"
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var activeTrack: player && player.track ? player.track : null
  readonly property string activeThumb: plexConnected && activeTrack ? artworkThumb(activeTrack) : ""
  readonly property bool configured: player && player.configured === true
  readonly property bool demoMode: setting("demoMode", false) === true
  readonly property bool plexConnected: demoMode || (configured && player.connected !== false && !setupNeeded)
  readonly property var audioSink: Pipewire.defaultAudioSink
  readonly property var audioNodes: Pipewire.nodes ? Pipewire.nodes.values : []
  readonly property var candidateAudioSinks: {
    var list = []
    for (var index = 0; index < audioNodes.length; index++) {
      var node = audioNodes[index]
      if (node && node.isSink && !node.isStream) list.push(node)
    }
    return list
  }
  readonly property var volumeSink: {
    if (volumeSinkName === "" || !audioSink || volumeSinkName === String(audioSink.name)) return audioSink
    for (var index = 0; index < audioNodes.length; index++) {
      var node = audioNodes[index]
      if (node && node.isSink && !node.isStream && String(node.name) === volumeSinkName && node.audio)
        return node
    }
    return audioSink
  }
  readonly property string configuredVolumeMode: normalizeVolumeMode(setting("volumeMode", "System"))
  readonly property string volumeMode: volumeModeOverride || configuredVolumeMode
  readonly property real systemVolume: volumeSink && volumeSink.audio
    ? Math.max(0, Math.min(100, Number(volumeSink.audio.volume) * 100)) : 0
  readonly property real displayedVolume: volumeMode === "system"
    ? systemVolume : Math.max(0, Math.min(130, Number(player.volume) || 0))
  readonly property real volumeMaximum: volumeMode === "system" ? 100 : 130
  readonly property bool volumeAvailable: volumeMode !== "system" || !!(volumeSink && volumeSink.audio)
  readonly property bool navigationShortcutsEnabled: opened && plexConnected
    && !helpVisible && !searchField.activeFocus && !seekFocus.activeFocus && !volumeFocus.activeFocus

  onAudioSinkChanged: resolveVolumeSink()

  function normalizeVolumeMode(value) {
    return String(value || "").toLowerCase() === "plex" ? "plex" : "system"
  }

  function resolveVolumeSink() {
    if (!volumeSinkProc.running) volumeSinkProc.running = true
  }

  function selectVolumeMode(mode) {
    var next = normalizeVolumeMode(mode)
    volumeModeOverride = next
    volumeModeProc.command = ["omarchy", "bar", "set", moduleName, "volumeMode", next === "plex" ? "Plex" : "System"]
    if (!volumeModeProc.running) volumeModeProc.running = true
    if (next === "system") resolveVolumeSink()
  }

  function command(args) {
    var result = [helperPath]
    if (demoMode) result.push("--demo")
    for (var index = 0; index < args.length; index++) result.push(String(args[index]))
    return result
  }

  function open() {
    helpVisible = false
    controller.show()
    refreshStatus()
    refreshHealth()
    if (plexConnected) loadView(Model.defaultView(player))
    if (setupNeeded) enterSetup()
    Qt.callLater(searchField.forceActiveFocus)
  }

  function close() {
    controller.hide()
    query = ""
    errorText = ""
    helpVisible = false
    setupActive = false
    setupView = ""
    setupError = ""
  }

  function enterSetup() {
    setupError = ""
    if (effectiveStage === "servers") loadServers()
    else if (effectiveStage === "libraries") loadLibraries()
    else if (effectiveStage === "unlinked") refreshAccount()
  }

  function refreshAccount() {
    accountProc.command = command(["account"])
    if (!accountProc.running) accountProc.running = true
  }

  function applyAccount(parsed) {
    if (!parsed) return
    account = parsed
    if (parsed.linkPending === true && effectiveStage === "unlinked") {
      linkCode = String(parsed.linkCode || "")
      linkUrl = String(parsed.linkUrl || "")
      linking = true
    } else if (parsed.stage !== "unlinked") {
      linking = false
    }
  }

  function startLink() {
    if (linkProc.running) return
    setupError = ""
    setupActive = true
    setupView = "unlinked"
    linkProc.step = "start"
    linkProc.command = command(["link", "start"])
    linkProc.running = true
  }

  function pollLink() {
    if (!linking || linkProc.running) return
    linkProc.step = "poll"
    linkProc.command = command(["link", "poll"])
    linkProc.running = true
  }

  function cancelLink() {
    linking = false
    linkCode = ""
    linkUrl = ""
    if (linkProc.running) linkProc.running = false
    linkProc.step = "cancel"
    linkProc.command = command(["link", "cancel"])
    linkProc.running = true
  }

  function openLinkPage() {
    if (linkUrl !== "" && bar) bar.run("xdg-open " + Util.shellQuote(linkUrl))
  }

  function loadServers() {
    setupError = ""
    setupView = "servers"
    setupBusy = true
    serversProc.command = command(["servers"])
    if (serversProc.running) serversProc.running = false
    serversProc.running = true
  }

  function loadLibraries() {
    setupError = ""
    setupView = "libraries"
    setupBusy = true
    librariesProc.command = command(["libraries"])
    if (librariesProc.running) librariesProc.running = false
    librariesProc.running = true
  }

  function chooseServer(server) {
    if (!server || server.reachable !== true || selectProc.running) return
    setupError = ""
    setupBusy = true
    selectProc.command = command(["select-server", String(server.clientIdentifier)])
    selectProc.running = true
  }

  function chooseLibrary(library) {
    if (!library || selectProc.running) return
    setupError = ""
    setupBusy = true
    selectProc.command = command(["select-library", String(library.key)])
    selectProc.running = true
  }

  function finishSetup(state) {
    setupBusy = false
    if (state) account = state
    if (state && state.stage === "libraries") { loadLibraries(); return }
    setupView = ""
    setupActive = false
    servers = []
    libraries = []
    refreshStatus()
    refreshHealth()
    if (opened) Qt.callLater(function() { if (root.plexConnected) root.loadView("recent") })
  }

  function unlinkAccount() {
    if (selectProc.running) return
    setupBusy = true
    linking = false
    setupView = "unlinked"
    selectProc.command = command(["logout"])
    selectProc.running = true
  }

  function changeServer() {
    setupActive = true
    loadServers()
  }

  function parseJson(raw, fallback) {
    try { return JSON.parse(String(raw || "{}")) }
    catch (error) { return fallback }
  }

  function errorMessage(raw, fallback) {
    var value = String(raw || "").trim()
    var parsed = parseJson(value, null)
    var message = parsed && parsed.message ? String(parsed.message) : (value || fallback)
    return message.length > 400 ? message.slice(0, 397) + "…" : message
  }

  function refreshStatus() {
    if (disconnecting) return
    statusProc.command = command(["status"])
    if (!statusProc.running) statusProc.running = true
  }

  function refreshHealth() {
    if (disconnecting) return
    healthProc.command = command(["health"])
    if (!healthProc.running) healthProc.running = true
  }

  function retryCurrent() {
    if (health.code === "disconnected") {
      setConnection(true)
      return
    }
    refreshHealth()
    if (view === "queue") runData("queue", command(["queue"]))
    else if (view === "children") runData("children", command(["children", currentParentKind, currentParentKey]))
    else if (view === "search") searchNow()
    else loadView(view)
  }

  function applyStatus(raw) {
    var parsed = parseJson(raw, null)
    if (parsed) {
      var wasConnected = plexConnected
      player = parsed
      statusFailure = ""
      if (parsed.stage !== undefined) {
        var previousStage = stage
        account = { stage: parsed.stage, linked: parsed.linked === true, account: parsed.account || "",
                    serverName: parsed.serverName || "", library: parsed.library || "" }
        if (parsed.stage !== "unlinked") linking = false
        if (opened && previousStage !== parsed.stage && setupView === "" && parsed.stage !== "ready") enterSetup()
      }
      if (parsed.track && (parsed.connected !== false || demoMode)) requestArtwork(parsed.track.artSource)
      if (opened && !wasConnected && (parsed.connected !== false || demoMode) && items.length === 0 && !loading)
        loadView("recent")
    }
  }

  function setConnection(enabled) {
    if (connectionProc.running || !configured || demoMode) return
    errorText = ""
    if (!enabled) {
      disconnecting = true
      requestedDataRequestId += 1
      activeDataRequestId = 0
      queuedDataRequestId = 0
      loading = false
      items = []
      query = ""
      pendingActions = []
      pendingQueueEdits = []
      if (dataProc.running) dataProc.running = false
      if (artProc.running) artProc.running = false
      if (actionProc.running) actionProc.running = false
      if (queueEditProc.running) queueEditProc.running = false
      if (healthProc.running) healthProc.running = false
      if (statusProc.running) statusProc.running = false
      invalidateArtworkJobs()
    }
    connectionProc.command = command(["connection", enabled ? "on" : "off"])
    connectionProc.running = true
  }

  function startData(requestId, mode, nextCommand) {
    if (requestId !== requestedDataRequestId || activeDataRequestId !== 0) return
    activeDataRequestId = requestId
    dataProc.command = nextCommand
    dataProc.running = true
  }

  function runData(mode, nextCommand) {
    nextDataRequestId += 1
    requestedDataRequestId = nextDataRequestId
    loading = true
    errorText = ""
    invalidateArtworkJobs()

    if (activeDataRequestId !== 0) {
      queuedDataRequestId = requestedDataRequestId
      queuedDataMode = mode
      queuedDataCommand = nextCommand
      if (dataProc.running) dataProc.running = false
      return
    }

    startData(requestedDataRequestId, mode, nextCommand)
  }

  function finishData(exitCode, raw, rawError) {
    var finishedRequestId = activeDataRequestId
    var isLatest = finishedRequestId === requestedDataRequestId
    activeDataRequestId = 0

    if (isLatest) {
      if (exitCode === 0) handleData(raw)
      else {
        loading = false
        errorText = errorMessage(rawError, "Could not load the Plex library.")
      }
    }

    if (queuedDataRequestId !== 0) {
      var nextRequestId = queuedDataRequestId
      var nextMode = queuedDataMode
      var nextCommand = queuedDataCommand
      queuedDataRequestId = 0
      queuedDataMode = ""
      queuedDataCommand = []
      Qt.callLater(function() { root.startData(nextRequestId, nextMode, nextCommand) })
    }
  }

  function loadView(nextView) {
    suppressSearch = true
    query = ""
    searchDebounce.stop()
    Qt.callLater(function() { root.suppressSearch = false })
    view = nextView
    currentParentKey = ""
    currentParentKind = ""
    currentParentTitle = ""
    backStack = []
    if (nextView === "queue") {
      runData("queue", command(["queue"]))
      Qt.callLater(itemList.forceActiveFocus)
    }
    else {
      var limit = nextView === "recent" ? setting("recentAlbumCount", 20) : setting("libraryItemCount", 100)
      runData(nextView, command(["library", nextView, "--limit", String(limit)]))
      Qt.callLater(searchField.forceActiveFocus)
    }
  }

  function searchNow() {
    var value = query.trim()
    if (value === "") { loadView("recent"); return }
    view = "search"
    currentParentKey = ""
    currentParentKind = ""
    currentParentTitle = ""
    runData("search", command(["search", value, "--limit", "35"]))
  }

  function openContainer(item) {
    backStack = backStack.concat([Model.navigationState(
      view, currentParentKey, currentParentKind, currentParentTitle, query, selectedIndex)])
    suppressSearch = true
    query = ""
    searchDebounce.stop()
    Qt.callLater(function() { root.suppressSearch = false })
    currentParentKey = String(item.key || "")
    currentParentKind = String(item.type || "album")
    currentParentTitle = String(item.title || "Collection")
    view = "children"
    runData("children", command(["children", currentParentKind, currentParentKey]))
  }

  function goBack() {
    var previous = backStack.length > 0
      ? backStack[backStack.length - 1] : Model.navigationState("recent")
    backStack = backStack.slice(0, Math.max(0, backStack.length - 1))
    suppressSearch = true
    query = String(previous.query || "")
    searchDebounce.stop()
    Qt.callLater(function() { root.suppressSearch = false })
    view = String(previous.view || "recent")
    currentParentKey = String(previous.parentKey || "")
    currentParentKind = String(previous.parentKind || "")
    currentParentTitle = String(previous.title || "")
    pendingSelectedIndex = Number(previous.selectedIndex || 0)
    var args = Model.navigationArgs(previous, setting("recentAlbumCount", 20), setting("libraryItemCount", 100))
    runData(view, command(args))
  }

  function handleEscape() {
    if (helpVisible) {
      helpVisible = false
      Qt.callLater(helpButton.forceActiveFocus)
    } else if (setupActive && stage === "ready") {
      setupActive = false
      setupView = ""
      setupError = ""
    } else if (query.trim() !== "") {
      suppressSearch = true
      query = ""
      searchDebounce.stop()
      Qt.callLater(function() { root.suppressSearch = false })
      loadView("recent")
    } else if (view === "children") goBack()
    else close()
  }

  function handleData(raw) {
    var parsed = parseJson(raw, null)
    loading = false
    if (!parsed) { errorText = "Plex returned unreadable data."; return }
    items = Model.safeArray(parsed.items)
    if (parsed.stale === true) errorText = parsed.warning || "Showing cached library data while Plex is offline."
    selectedIndex = pendingSelectedIndex >= 0
      ? Math.max(0, Math.min(items.length - 1, pendingSelectedIndex)) : 0
    pendingSelectedIndex = -1
  }

  function activateItem(item) {
    if (!item) return
    if (item.type === "album" || item.type === "artist" || item.type === "playlist") { openContainer(item); return }
    if (view === "queue") { runQueueAction("play", Number(item.queueIndex)); return }
    var args = ["play", String(item.key)]
    if (view === "children" && currentParentKind === "album") args.push("--album", currentParentKey)
    if (view === "children" && currentParentKind === "playlist") args.push("--playlist", currentParentKey)
    runAction(command(args))
  }

  function runAction(nextCommand) {
    if (actionProc.running) {
      pendingActions = Model.queueAction(pendingActions, nextCommand)
      return
    }
    actionProc.command = nextCommand
    actionProc.running = true
  }

  function control(action, value) {
    var args = ["control", action]
    if (value !== undefined) args.push(String(value))
    runAction(command(args))
  }

  function setVolume(value) {
    var next = Math.max(0, Math.min(volumeMaximum, Number(value) || 0))
    if (volumeMode === "system") {
      if (!volumeSink || !volumeSink.audio) {
        errorText = "The system audio output is not available."
        return
      }
      volumeSink.audio.volume = next / 100
      if (bar && bar.shell) bar.shell.summon("omarchy.osd", JSON.stringify({ icon: "\uf028", value: Math.round(next) }))
      return
    }
    var updated = Object.assign({}, player)
    updated.volume = next
    player = updated
    control("volume", next)
  }

  function connectPlex() {
    if (stage === "unlinked" || health.code === "unauthorized") startLink()
    else changeServer()
  }

  function manualSetup() {
    close()
    if (bar) bar.run("omarchy launch floating terminal with presentation " + Util.shellQuote(helperPath) + " configure")
  }

  function playCollection(shuffle) {
    if (currentParentKind !== "album" && currentParentKind !== "playlist") return
    var args = ["play-collection", currentParentKind, currentParentKey]
    if (shuffle) args.push("--shuffle")
    runAction(command(args))
  }

  function playItemCollection(item, shuffle) {
    if (!item || (item.type !== "album" && item.type !== "playlist")) return
    var args = ["play-collection", item.type, String(item.key)]
    if (shuffle) args.push("--shuffle")
    runAction(command(args))
  }

  function runQueueAction(action, index, destination) {
    var args = ["queue-action", action]
    if (index !== undefined) args.push("--index", String(index))
    if (destination !== undefined) args.push("--to", String(destination))
    if (queueEditProc.running) {
      errorText = "A Queue update is already in progress. Try again in a moment."
      return
    }
    runQueueEdit(command(args))
  }

  function playNext(item) {
    if (!item) return
    if (!activeTrack) { activateItem(item); return }
    runQueueEdit(command(["queue-action", "play-next", "--track", String(item.key)]))
  }

  function runQueueEdit(nextCommand) {
    if (queueEditProc.running) {
      if (pendingQueueEdits.length >= 16) {
        errorText = "Too many player actions are waiting."
        return
      }
      pendingQueueEdits = pendingQueueEdits.concat([nextCommand])
      return
    }
    queueEditProc.command = nextCommand
    queueEditProc.running = true
  }

  function requestArtwork(source) {
    var value = String(source || "")
    if (value === "" || value.indexOf("/") !== 0 || value.indexOf("//") === 0) return
    if (resolvedArtwork[value]) return
    var lastAttempt = Number(requestedArtwork[value] || 0)
    if (Date.now() - lastAttempt < 60000) return
    if (pendingArtwork.length >= 32) return
    var attempts = Object.assign({}, requestedArtwork)
    attempts[value] = Date.now()
    requestedArtwork = attempts
    pendingArtwork = pendingArtwork.concat([{ source: value, generation: artworkGeneration }])
    startNextArtwork()
  }

  function invalidateArtworkJobs() {
    artworkGeneration += 1
    pendingArtwork = []
    requestedArtwork = ({})
    if (artProc.running) artProc.running = false
    else {
      activeArtwork = ""
      activeArtworkGeneration = 0
    }
  }

  function startNextArtwork() {
    if (artProc.running || activeArtwork !== "" || pendingArtwork.length === 0) return
    var job = pendingArtwork[0]
    pendingArtwork = pendingArtwork.slice(1)
    if (!job || job.generation !== artworkGeneration) { Qt.callLater(startNextArtwork); return }
    activeArtwork = String(job.source || "")
    activeArtworkGeneration = Number(job.generation)
    artProc.command = command(["art", activeArtwork])
    artProc.running = true
  }

  function applyArtwork(source, raw) {
    var parsed = parseJson(raw, null)
    var thumb = parsed && parsed.thumb ? String(parsed.thumb) : ""
    if (thumb === "") return
    var cache = Object.assign({}, resolvedArtwork)
    var order = resolvedArtworkOrder.filter(function(entry) { return entry !== source })
    cache[source] = thumb
    order.push(source)
    while (order.length > 128) {
      var expired = order.shift()
      delete cache[expired]
    }
    resolvedArtwork = cache
    resolvedArtworkOrder = order
  }

  function artworkThumb(item) {
    if (!item) return ""
    return String(item.thumb || resolvedArtwork[String(item.artSource || "")] || "")
  }

  function advanceProgress() {
    if (!player || player.playing !== true) return
    var updated = Object.assign({}, player)
    updated.position = Math.min(Number(updated.duration || 0), Number(updated.position || 0) + 1)
    player = updated
  }

  function moveSelection(delta) {
    if (items.length === 0) return
    selectedIndex = Math.max(0, Math.min(items.length - 1, selectedIndex + delta))
    Qt.callLater(function() { itemList.positionViewAtIndex(selectedIndex, ListView.Contain) })
  }

  function moveQueueSelection(delta) {
    if (view !== "queue" || items.length === 0) return
    if (items[selectedIndex].current === true) return
    var destination = Math.max(0, Math.min(items.length - 1, selectedIndex + delta))
    if (destination === selectedIndex) return
    pendingSelectedIndex = destination
    runQueueAction("move", Number(items[selectedIndex].queueIndex), destination)
  }

  function removeSelectedQueueItem() {
    if (view !== "queue" || items.length === 0) return
    if (items[selectedIndex].current === true) return
    pendingSelectedIndex = Math.max(0, Math.min(items.length - 2, selectedIndex))
    runQueueAction("remove", Number(items[selectedIndex].queueIndex))
  }

  function activateSelection(modifiers) {
    if (items.length === 0) return
    var item = items[selectedIndex]
    if ((modifiers & Qt.ShiftModifier) && item.type === "track" && view !== "queue") {
      playNext(item); return
    }
    if ((modifiers & Qt.ShiftModifier) && (item.type === "album" || item.type === "playlist")) {
      playItemCollection(item, true); return
    }
    if ((modifiers & Qt.ControlModifier) && (item.type === "album" || item.type === "playlist")) {
      playItemCollection(item, false); return
    }
    activateItem(item)
  }

  function handleListKey(event) {
    if (event.key === Qt.Key_Down) {
      if ((event.modifiers & Qt.ControlModifier) && view === "queue") moveQueueSelection(1)
      else moveSelection(1)
      event.accepted = true
    } else if (event.key === Qt.Key_Up) {
      if ((event.modifiers & Qt.ControlModifier) && view === "queue") moveQueueSelection(-1)
      else moveSelection(-1)
      event.accepted = true
    } else if (event.key === Qt.Key_Delete && view === "queue") {
      removeSelectedQueueItem(); event.accepted = true
    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      activateSelection(event.modifiers); event.accepted = true
    }
  }

  function switchNavigation(delta) {
    if (!plexConnected || navigation.length === 0) return
    var activeView = view
    if (view === "children" && backStack.length > 0) activeView = backStack[0].view
    var current = 0
    for (var index = 0; index < navigation.length; index++) {
      if (navigation[index].id === activeView) { current = index; break }
    }
    var next = (current + delta + navigation.length) % navigation.length
    loadView(navigation[next].id)
  }

  Shortcut {
    sequence: "Left"
    context: Qt.ApplicationShortcut
    enabled: root.navigationShortcutsEnabled
    onActivated: root.switchNavigation(-1)
  }

  Shortcut {
    sequence: "Escape"
    context: Qt.ApplicationShortcut
    enabled: root.opened
    onActivated: root.handleEscape()
  }

  Shortcut {
    sequence: "Ctrl+Space"
    context: Qt.ApplicationShortcut
    enabled: root.opened && root.plexConnected && (root.activeTrack !== null || Number(root.player.queueLength || 0) > 0)
    onActivated: root.control("toggle")
  }

  Shortcut {
    sequence: "F1"
    context: Qt.ApplicationShortcut
    enabled: root.opened
    onActivated: {
      root.helpVisible = !root.helpVisible
      Qt.callLater(helpButton.forceActiveFocus)
    }
  }

  Shortcut {
    sequence: "Right"
    context: Qt.ApplicationShortcut
    enabled: root.navigationShortcutsEnabled
    onActivated: root.switchNavigation(1)
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: statusProc
    stdout: StdioCollector { id: statusOutput; waitForEnd: true }
    stderr: StdioCollector { id: statusError; waitForEnd: true }
    onExited: function(exitCode) {
      if (root.disconnecting) return
      if (exitCode === 0) root.applyStatus(statusOutput.text)
      else if (root.opened) root.errorText = root.errorMessage(statusError.text, "Could not refresh player status.")
    }
  }

  PwObjectTracker { objects: root.candidateAudioSinks }

  Process {
    id: volumeSinkProc
    command: ["omarchy-audio-output-sink"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.volumeSinkName = String(text).trim()
    }
  }

  Process {
    id: volumeModeProc
    stderr: StdioCollector { id: volumeModeError; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.volumeModeOverride = ""
        root.errorText = root.errorMessage(volumeModeError.text, "Could not save the volume preference.")
      }
    }
  }

  Process {
    id: queueEditProc
    stderr: StdioCollector { id: queueEditError; waitForEnd: true }
    onExited: function(exitCode) {
      if (root.disconnecting) return
      if (exitCode !== 0) root.errorText = root.errorMessage(queueEditError.text, "Could not update the queue.")
      root.refreshStatus()
      if (root.view === "queue") root.runData("queue", root.command(["queue"]))
      if (root.pendingQueueEdits.length > 0) {
        var nextCommand = root.pendingQueueEdits[0]
        root.pendingQueueEdits = root.pendingQueueEdits.slice(1)
        Qt.callLater(function() { root.runQueueEdit(nextCommand) })
      }
    }
  }

  Process {
    id: artProc
    stdout: StdioCollector { id: artOutput; waitForEnd: true }
    onExited: function(exitCode) {
      var source = root.activeArtwork
      var generation = root.activeArtworkGeneration
      if (exitCode === 0 && generation === root.artworkGeneration) root.applyArtwork(source, artOutput.text)
      root.activeArtwork = ""
      root.activeArtworkGeneration = 0
      Qt.callLater(root.startNextArtwork)
    }
  }

  Process {
    id: healthProc
    stdout: StdioCollector { id: healthOutput; waitForEnd: true }
    stderr: StdioCollector { id: healthError; waitForEnd: true }
    onExited: function(exitCode) {
      if (root.disconnecting) return
      if (exitCode === 0) {
        var parsed = root.parseJson(healthOutput.text, null)
        if (parsed) root.health = parsed
      } else {
        var message = root.errorMessage(healthError.text, "Could not check the Plex connection.")
        root.health = ({ ok: false, code: "helper-error", message: message })
        if (root.opened) root.errorText = message
      }
    }
  }

  Process {
    id: connectionProc
    stdout: StdioCollector { id: connectionOutput; waitForEnd: true }
    stderr: StdioCollector { id: connectionError; waitForEnd: true }
    onExited: function(exitCode) {
      root.disconnecting = false
      if (exitCode === 0) {
        root.applyStatus(connectionOutput.text)
        var parsed = root.parseJson(connectionOutput.text, {})
        if (parsed.warning) root.errorText = String(parsed.warning)
        root.refreshHealth()
      } else {
        root.errorText = root.errorMessage(connectionError.text, "Could not change the Plex connection.")
        root.refreshStatus()
        root.refreshHealth()
      }
    }
  }

  Process {
    id: dataProc
    stdout: StdioCollector { id: dataOutput; waitForEnd: true }
    stderr: StdioCollector { id: dataError; waitForEnd: true }
    onExited: function(exitCode) {
      root.finishData(exitCode, dataOutput.text, dataError.text)
    }
  }

  Process {
    id: accountProc
    stdout: StdioCollector { id: accountOutput; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode === 0) root.applyAccount(root.parseJson(accountOutput.text, null))
    }
  }

  Process {
    id: linkProc
    property string step: ""
    stdout: StdioCollector { id: linkOutput; waitForEnd: true }
    stderr: StdioCollector { id: linkError; waitForEnd: true }
    onExited: function(exitCode) {
      var parsed = root.parseJson(linkOutput.text, null)
      if (exitCode !== 0) {
        var message = root.errorMessage(linkError.text, "Plex sign-in failed.")
        var code = root.parseJson(linkError.text, {}).code
        if (step === "poll" && code === "no-link") { root.linking = false; return }
        root.setupError = message
        if (step === "start") root.linking = false
        return
      }
      if (step === "start" && parsed) {
        root.linkCode = String(parsed.code || "")
        root.linkUrl = String(parsed.url || "")
        root.linking = true
        root.openLinkPage()
      } else if (step === "poll" && parsed) {
        if (parsed.linked === true) {
          root.linking = false
          root.linkCode = ""
          root.setupError = ""
          root.refreshStatus()
          root.loadServers()
        } else if (parsed.expired === true) {
          root.linking = false
          root.linkCode = ""
          root.setupError = "The Plex sign-in code expired. Start again."
        }
      } else if (step === "cancel") {
        root.applyAccount(parsed)
      }
    }
  }

  Process {
    id: serversProc
    stdout: StdioCollector { id: serversOutput; waitForEnd: true }
    stderr: StdioCollector { id: serversError; waitForEnd: true }
    onExited: function(exitCode) {
      root.setupBusy = false
      if (exitCode !== 0) {
        var code = root.parseJson(serversError.text, {}).code
        if (code === "unlinked") { root.setupView = "unlinked"; root.refreshAccount(); return }
        root.setupError = root.errorMessage(serversError.text, "Could not list your Plex servers.")
        return
      }
      var parsed = root.parseJson(serversOutput.text, null)
      root.servers = parsed ? Model.safeArray(parsed.servers) : []
      if (parsed && parsed.state) root.account = parsed.state
      if (root.servers.length === 0) root.setupError = "No Plex Media Server is available on this account."
    }
  }

  Process {
    id: librariesProc
    stdout: StdioCollector { id: librariesOutput; waitForEnd: true }
    stderr: StdioCollector { id: librariesError; waitForEnd: true }
    onExited: function(exitCode) {
      root.setupBusy = false
      if (exitCode !== 0) {
        root.setupError = root.errorMessage(librariesError.text, "Could not list the music libraries.")
        return
      }
      var parsed = root.parseJson(librariesOutput.text, null)
      root.libraries = parsed ? Model.safeArray(parsed.libraries) : []
      if (parsed && parsed.state) root.account = parsed.state
    }
  }

  Process {
    id: selectProc
    stdout: StdioCollector { id: selectOutput; waitForEnd: true }
    stderr: StdioCollector { id: selectError; waitForEnd: true }
    onExited: function(exitCode) {
      var parsed = root.parseJson(selectOutput.text, null)
      if (exitCode !== 0) {
        root.setupBusy = false
        root.setupError = root.errorMessage(selectError.text, "Could not save the Plex selection.")
        return
      }
      if (parsed && parsed.libraries !== undefined) root.libraries = Model.safeArray(parsed.libraries)
      if (parsed && parsed.connected === false) {
        root.setupBusy = false
        root.servers = []
        root.libraries = []
        root.setupView = ""
        root.setupActive = false
        root.refreshStatus()
        root.refreshHealth()
        root.refreshAccount()
        return
      }
      root.finishSetup(parsed ? parsed.state : null)
    }
  }

  Timer {
    interval: 2500
    running: root.linking && root.opened
    repeat: true
    triggeredOnStart: true
    onTriggered: root.pollLink()
  }

  Process {
    id: actionProc
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.applyStatus(text) }
    stderr: StdioCollector { id: actionError; waitForEnd: true }
    onExited: function(exitCode) {
      if (root.disconnecting) return
      if (exitCode !== 0) root.errorText = root.errorMessage(actionError.text, "Player action failed.")
      root.refreshStatus()
      if (root.view === "queue") root.runData("queue", root.command(["queue"]))
      if (root.pendingActions.length > 0) {
        var nextCommand = root.pendingActions[0]
        root.pendingActions = root.pendingActions.slice(1)
        Qt.callLater(function() { root.runAction(nextCommand) })
      }
    }
  }

  Timer {
    interval: root.opened ? 3000 : (root.player && root.player.playing ? 10000 : (root.activeTrack ? 15000 : 30000))
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refreshStatus()
  }

  Timer {
    interval: 15000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.resolveVolumeSink()
  }

  Timer {
    interval: 1000
    running: root.player && root.player.playing === true
    repeat: true
    onTriggered: root.advanceProgress()
  }

  Timer {
    interval: 30000
    running: root.opened
    repeat: true
    onTriggered: root.refreshHealth()
  }

  Timer {
    id: searchDebounce
    interval: 350
    onTriggered: root.searchNow()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    labelVisible: false
    hasVisualContent: true
    fixedWidth: vertical ? -1 : (root.plexConnected && root.activeTrack
      ? Style.space(root.showBarControls ? 236 : 180) : Style.bar.iconSlot)
    fixedHeight: vertical ? Style.bar.iconSlot : -1
    tooltipText: !root.plexConnected && root.configured && root.stage === "ready" ? "Plexarchy · Plex connection off" : root.activeTrack
      ? root.activeTrack.title + (Model.subtitle(root.activeTrack) ? " · " + Model.subtitle(root.activeTrack) : "")
      : (root.stage === "ready" ? "Plexarchy" : "Plexarchy · Link your Plex account")
    active: root.player && root.player.playing === true
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) root.manualSetup()
      else if (mouseButton === Qt.MiddleButton && root.activeTrack) root.control("toggle")
      else root.toggle()
    }
    onWheelMoved: function(delta) {
      if (root.activeTrack) root.control(delta > 0 ? "previous" : "next")
    }

    Row {
      id: barContent
      anchors.centerIn: parent
      width: button.vertical ? coverFrame.width : parent.width - Style.space(16)
      height: coverFrame.height
      spacing: Style.space(7)

      Rectangle {
        id: coverFrame
        width: Math.min(Style.space(20), button.barSize - Style.space(8))
        height: width
        anchors.verticalCenter: parent.verticalCenter
        radius: Math.max(2, Style.cornerRadius / 2)
        color: Style.selectedFillFor(button.foreground, Color.accent)
        clip: true
        opacity: root.player && root.player.playing ? 1 : 0.78

        Image {
          id: barCover
          anchors.fill: parent
          source: root.activeThumb
          fillMode: Image.PreserveAspectCrop
          asynchronous: true
          sourceSize.width: Math.max(1, Math.round(width * 2))
          sourceSize.height: Math.max(1, Math.round(height * 2))
          cache: true
          visible: root.activeThumb !== "" && status === Image.Ready
        }

        Text {
          id: barLogo
          textFormat: Text.PlainText
          anchors.centerIn: parent
          text: root.logoGlyph
          color: button.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.iconSmall
          visible: !barCover.visible
        }
      }

      Column {
        id: barLabels
        visible: root.plexConnected && root.activeTrack !== null && !button.vertical
        width: Math.max(0, parent.width - coverFrame.width - parent.spacing
          - (barControls.visible ? barControls.width + parent.spacing : 0))
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        Text {
          id: barTitle
          textFormat: Text.PlainText
          width: parent.width
          text: root.activeTrack ? root.activeTrack.title : ""
          color: button.foreground
          font.family: root.fontFamily
          font.pixelSize: Model.subtitle(root.activeTrack) !== "" && button.barSize >= Style.space(26) ? Style.font.caption : Style.font.bodySmall
          elide: Text.ElideRight
        }

        Text {
          id: barArtist
          textFormat: Text.PlainText
          width: parent.width
          visible: text !== "" && button.barSize >= Style.space(26)
          text: root.activeTrack ? Model.artistLine(root.activeTrack) : ""
          color: Qt.darker(button.foreground, 1.35)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }

      Row {
        id: barControls
        visible: root.showBarControls && root.plexConnected && root.activeTrack !== null && !button.vertical
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)

        Repeater {
          model: [
            { action: "previous", icon: "\uf048", label: "Previous" },
            { action: "toggle", icon: "", label: "" },
            { action: "next", icon: "\uf051", label: "Next" }
          ]
          delegate: Item {
            id: barControl
            required property var modelData
            readonly property bool isToggle: modelData.action === "toggle"
            width: Style.space(18)
            height: coverFrame.height
            Accessible.role: Accessible.Button
            Accessible.name: isToggle ? (root.player && root.player.playing ? "Pause" : "Play") : modelData.label

            Text {
              textFormat: Text.PlainText
              anchors.centerIn: parent
              text: barControl.isToggle ? (root.player && root.player.playing ? "\uf04c" : "\uf04b") : barControl.modelData.icon
              color: button.foreground
              opacity: barControlArea.containsMouse ? 1 : 0.8
              font.family: root.fontFamily
              font.pixelSize: barControl.isToggle ? Style.font.iconSmall : Style.font.caption
            }

            MouseArea {
              id: barControlArea
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              acceptedButtons: Qt.LeftButton
              onClicked: root.control(barControl.modelData.action)
            }
          }
        }
      }
    }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: root.helpVisible ? helpButton : root.setupVisible
      ? (root.effectiveStage === "unlinked" ? (root.linking ? openLinkButton : connectButton) : (root.effectiveStage === "servers" ? refreshServersButton : setupCard))
      : root.plexConnected
      ? (root.view === "queue" ? itemList : searchField) : (root.configured ? connectionButton : helpButton)
    contentWidth: fittedContentWidth(Style.space(540))
    contentHeight: fittedContentHeight(contentColumn.implicitHeight, Style.space(790))

    Column {
      id: contentColumn
      width: parent.width
      spacing: Style.space(12)

      RowLayout {
        width: parent.width
        spacing: Style.space(12)

        Rectangle {
          Layout.preferredWidth: Style.space(82)
          Layout.preferredHeight: Style.space(82)
          radius: Style.cornerRadius
          color: Style.selectedFillFor(root.foreground, Color.accent)
          clip: true

          Image {
            id: headerCover
            anchors.fill: parent
            source: root.activeThumb
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            sourceSize.width: Math.max(1, Math.round(width * 2))
            sourceSize.height: Math.max(1, Math.round(height * 2))
            visible: !root.helpVisible && status === Image.Ready
          }

          Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            visible: !root.helpVisible && headerCover.status !== Image.Ready
            text: ""
          }

          Text {
            id: headerLogo
            textFormat: Text.PlainText
            anchors.centerIn: parent
            visible: root.helpVisible || headerCover.status !== Image.Ready
            text: root.logoGlyph
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: root.helpVisible ? Style.font.displayLarge : Style.font.display
            opacity: root.helpVisible ? 1 : 0.8
          }
        }

        ColumnLayout {
          Layout.fillWidth: true
          spacing: Style.space(3)

          Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: root.helpVisible || !root.plexConnected ? "Plexarchy" : (root.activeTrack ? root.activeTrack.title : "Plexarchy")
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            font.bold: true
            elide: Text.ElideRight
          }

          Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: root.helpVisible ? "Help · Keyboard map and player settings"
              : (root.setupNeeded ? (root.effectiveStage === "unlinked" ? "Link your Plex account"
                : (root.effectiveStage === "servers" ? "Choose a Plex server" : (root.effectiveStage === "libraries" ? "Choose a music library" : "Plex connection")))
              : (!root.plexConnected && root.configured ? "Plex connection is off"
              : (root.activeTrack ? Model.subtitle(root.activeTrack)
              : (root.configured ? (Model.connectionLabel(root.account) || "Choose something to play") : "Connect your Plex server"))))
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
          }

          RowLayout {
            visible: root.activeTrack !== null && root.plexConnected && !root.helpVisible
            Layout.fillWidth: true
            spacing: Style.space(8)

            Text {
              textFormat: Text.PlainText
              text: Model.formatTime(root.player.position)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            BorderSurface {
              id: seekFocus
              Layout.fillWidth: true
              Layout.preferredHeight: seekSlider.implicitHeight + Style.space(4)
              radius: Style.cornerRadius
              color: activeFocus ? Style.focusFillFor(root.foreground, Color.accent) : "transparent"
              borderSpec: activeFocus ? Border.controlSpec("focus", root.foreground, Color.accent) : Border.none()
              activeFocusOnTab: true
              Accessible.role: Accessible.Slider
              Accessible.name: "Playback position"
              Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Left || event.key === Qt.Key_Down) {
                  root.control("seek", Math.max(0, Number(root.player.position) - 5)); event.accepted = true
                } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Up) {
                  root.control("seek", Math.min(Number(root.player.duration) || 0, Number(root.player.position) + 5)); event.accepted = true
                } else if (event.key === Qt.Key_Home) {
                  root.control("seek", 0); event.accepted = true
                } else if (event.key === Qt.Key_End) {
                  root.control("seek", Number(root.player.duration) || 0); event.accepted = true
                }
              }

              PanelSlider {
                id: seekSlider
                anchors.fill: parent
                anchors.margins: Style.space(2)
                bar: root.bar
                value: Number(root.player.position) || 0
                maximum: Math.max(1, Number(root.player.duration) || 1)
                step: 5
                onReleased: function(next) { root.control("seek", next) }
              }
            }
            Text {
              textFormat: Text.PlainText
              text: Model.formatTime(root.player.duration)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          RowLayout {
            visible: root.activeTrack !== null && root.plexConnected && !root.helpVisible
            Layout.fillWidth: true
            spacing: Style.space(8)

            Text {
              textFormat: Text.PlainText
              text: "\uf028"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            BorderSurface {
              id: volumeFocus
              Layout.fillWidth: true
              Layout.preferredHeight: volumeSlider.implicitHeight + Style.space(4)
              radius: Style.cornerRadius
              color: activeFocus ? Style.focusFillFor(root.foreground, Color.accent) : "transparent"
              borderSpec: activeFocus ? Border.controlSpec("focus", root.foreground, Color.accent) : Border.none()
              activeFocusOnTab: true
              enabled: root.volumeAvailable
              Accessible.role: Accessible.Slider
              Accessible.name: root.volumeMode === "system" ? "System volume" : "Plex player volume"
              Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Left || event.key === Qt.Key_Down) {
                  root.setVolume(Math.max(0, root.displayedVolume - 5)); event.accepted = true
                } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Up) {
                  root.setVolume(Math.min(root.volumeMaximum, root.displayedVolume + 5)); event.accepted = true
                } else if (event.key === Qt.Key_Home) {
                  root.setVolume(0); event.accepted = true
                } else if (event.key === Qt.Key_End) {
                  root.setVolume(root.volumeMaximum); event.accepted = true
                }
              }

              PanelSlider {
                id: volumeSlider
                anchors.fill: parent
                anchors.margins: Style.space(2)
                bar: root.bar
                value: root.displayedVolume
                minimum: 0
                maximum: root.volumeMaximum
                step: 5
                integer: true
                onMoved: function(next) { root.setVolume(next) }
              }
            }
            Text {
              textFormat: Text.PlainText
              text: root.volumeAvailable
                ? Math.round(volumeSlider.dragging ? volumeSlider.liveValue : root.displayedVolume) + "%" : "N/A"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              Layout.preferredWidth: Style.space(36)
              horizontalAlignment: Text.AlignRight
            }
          }
        }

        PanelActionButton {
          id: connectionButton
          visible: root.configured && root.stage === "ready" && !root.demoMode && !root.helpVisible && !root.setupActive
          Layout.alignment: Qt.AlignTop
          size: Style.space(28)
          iconText: "\uf011"
          tooltipText: root.plexConnected ? "Disconnect from Plex" : "Connect to Plex"
          foreground: root.plexConnected ? root.foreground : Color.urgent
          fontFamily: root.fontFamily
          fontSize: Style.font.body
          bordered: true
          focusable: true
          enabled: !connectionProc.running && !root.disconnecting
          Accessible.role: Accessible.Button
          Accessible.name: tooltipText
          Accessible.description: "Keeps the saved Plex account and server settings"
          onClicked: root.setConnection(!root.plexConnected)
        }

        PanelActionButton {
          id: helpButton
          Layout.alignment: Qt.AlignTop
          size: Style.space(28)
          iconText: root.helpVisible ? "\uf00d" : "\uf013"
          tooltipText: root.helpVisible ? "Close help and settings" : "Help and settings"
          foreground: root.foreground
          fontFamily: root.fontFamily
          fontSize: Style.font.body
          bordered: root.helpVisible
          focusable: true
          Accessible.name: tooltipText
          onClicked: {
            root.helpVisible = !root.helpVisible
            forceActiveFocus()
          }
        }
      }

      BorderSurface {
        visible: root.helpVisible
        width: parent.width
        implicitHeight: helpColumn.implicitHeight + Style.space(20)
        radius: Style.cornerRadius
        color: Style.selectedFillFor(root.foreground, Color.accent)
        borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

        Column {
          id: helpColumn
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          anchors.leftMargin: Style.space(10)
          anchors.rightMargin: Style.space(10)
          spacing: Style.space(4)

          Text {
            textFormat: Text.PlainText
            width: helpColumn.width
            text: "Volume control"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.bold: true
          }

          Row {
            width: helpColumn.width
            height: Style.space(32)
            spacing: Style.space(6)

            Repeater {
              model: [
                { value: "system", label: "System", icon: "\uf028" },
                { value: "plex", label: "Plex", icon: "\uf001" }
              ]
              delegate: BorderSurface {
                required property var modelData
                width: (helpColumn.width - Style.space(6)) / 2
                height: Style.space(32)
                radius: Style.cornerRadius
                color: activeFocus
                  ? Style.focusFillFor(root.foreground, Color.accent)
                  : (root.volumeMode === modelData.value
                    ? Style.selectedFillFor(root.foreground, Color.accent) : "transparent")
                borderSpec: activeFocus
                  ? Border.controlSpec("focus", root.foreground, Color.accent)
                  : Border.controlSpec(root.volumeMode === modelData.value ? "hover-cursor" : "normal", root.foreground, Color.accent)
                activeFocusOnTab: true
                enabled: !volumeModeProc.running
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label + " volume"
                Accessible.checked: root.volumeMode === modelData.value
                Keys.onReturnPressed: root.selectVolumeMode(modelData.value)
                Keys.onEnterPressed: root.selectVolumeMode(modelData.value)
                Keys.onSpacePressed: root.selectVolumeMode(modelData.value)

                Text {
                  textFormat: Text.PlainText
                  anchors.centerIn: parent
                  text: parent.modelData.icon + "  " + parent.modelData.label
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  font.bold: root.volumeMode === parent.modelData.value
                }

                MouseArea {
                  anchors.fill: parent
                  enabled: parent.enabled
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    parent.forceActiveFocus()
                    root.selectVolumeMode(parent.modelData.value)
                  }
                }
              }
            }
          }

          Text {
            textFormat: Text.PlainText
            width: helpColumn.width
            text: root.volumeMode === "system"
              ? "The slider changes Omarchy's current audio output."
              : "The slider changes only Plexarchy's local mpv player."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Item { width: 1; height: Style.space(6) }

          Text {
            textFormat: Text.PlainText
            width: helpColumn.width
            text: "Plex connection"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.bold: true
          }

          Text {
            id: settingsConnectionLabel
            textFormat: Text.PlainText
            width: helpColumn.width
            text: root.demoMode ? "Demo mode · fictional library"
              : (root.stage === "ready" ? (Model.connectionLabel(root.account) || "Connected") : "No Plex account linked")
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }

          Row {
            width: helpColumn.width
            spacing: Style.space(6)
            visible: !root.demoMode

            PanelActionButton {
              id: changeServerButton
              width: (helpColumn.width - Style.space(6)) / 2
              height: Style.space(30)
              iconText: root.account.linked ? "\uf233  Change server" : "\uf1c0  Link account"
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: Style.font.bodySmall
              bordered: true
              focusable: true
              Accessible.name: iconText
              onClicked: {
                root.helpVisible = false
                if (root.account.linked) root.changeServer()
                else root.startLink()
              }
            }

            PanelActionButton {
              id: unlinkButton
              width: (helpColumn.width - Style.space(6)) / 2
              height: Style.space(30)
              visible: root.account.linked === true
              iconText: "\uf08b  Unlink account"
              foreground: Color.urgent
              fontFamily: root.fontFamily
              fontSize: Style.font.bodySmall
              bordered: true
              focusable: true
              enabled: !selectProc.running
              Accessible.name: "Unlink Plex account"
              onClicked: {
                root.helpVisible = false
                root.unlinkAccount()
              }
            }
          }

          Item { width: 1; height: Style.space(4) }

          Repeater {
            model: root.keyboardHelp
            delegate: RowLayout {
              required property var modelData
              width: helpColumn.width
              spacing: Style.space(10)

              BorderSurface {
                Layout.preferredWidth: Style.space(142)
                Layout.preferredHeight: Style.space(22)
                radius: Style.cornerRadius / 2
                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.05)
                borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

                Text {
                  textFormat: Text.PlainText
                  anchors.centerIn: parent
                  text: modelData.keys
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
              }

              Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: modelData.action
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
              }
            }
          }
        }
      }

      Row {
        visible: root.activeTrack !== null && root.plexConnected && !root.helpVisible
        width: parent.width
        spacing: Style.space(16)

        Item { width: Math.max(0, (parent.width - controls.width) / 2); height: 1 }
        Row {
          id: controls
          spacing: Style.space(10)
          PanelActionButton {
            iconText: "\uf074"; tooltipText: root.player && root.player.shuffle ? "Shuffle on" : "Shuffle off"
            foreground: root.player && root.player.shuffle ? Color.urgent : root.foreground
            fontFamily: root.fontFamily; bordered: root.player && root.player.shuffle === true; focusable: true
            Accessible.name: tooltipText
            onClicked: root.control("shuffle")
          }
          PanelActionButton {
            iconText: "\uf048"; tooltipText: "Previous"; foreground: root.foreground; fontFamily: root.fontFamily
            focusable: true; Accessible.name: tooltipText
            onClicked: root.control("previous")
          }
          PanelActionButton {
            id: playButton
            size: Style.space(34)
            iconText: root.player && root.player.playing ? "\uf04c" : "\uf04b"
            tooltipText: root.player && root.player.playing ? "Pause" : "Play"
            foreground: root.foreground; fontFamily: root.fontFamily; bordered: true; focusable: true
            Accessible.name: tooltipText
            onClicked: root.control("toggle")
          }
          PanelActionButton {
            iconText: "\uf051"; tooltipText: "Next"; foreground: root.foreground; fontFamily: root.fontFamily
            focusable: true; Accessible.name: tooltipText
            onClicked: root.control("next")
          }
          PanelActionButton {
            iconText: root.player && root.player.repeat === "one" ? "\uf366" : "\uf363"
            tooltipText: root.player && root.player.repeat === "one" ? "Repeat one" : (root.player && root.player.repeat === "all" ? "Repeat all" : "Repeat off")
            foreground: root.player && root.player.repeat !== "off" ? Color.urgent : root.foreground
            fontFamily: root.fontFamily; bordered: root.player && root.player.repeat !== "off"; focusable: true
            Accessible.name: tooltipText
            onClicked: root.control("repeat")
          }
        }
      }

      BorderSurface {
        id: setupCard
        visible: root.setupVisible
        width: parent.width
        implicitHeight: setupColumn.implicitHeight + Style.space(24)
        radius: Style.cornerRadius
        color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.04)
        borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)

        Column {
          id: setupColumn
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          anchors.leftMargin: Style.space(12)
          anchors.rightMargin: Style.space(12)
          spacing: Style.space(10)

          Row {
            width: setupColumn.width
            spacing: Style.space(8)

            Repeater {
              model: [
                { id: "unlinked", label: "1  Account" },
                { id: "servers", label: "2  Server" },
                { id: "libraries", label: "3  Library" }
              ]
              delegate: Text {
                required property var modelData
                textFormat: Text.PlainText
                text: modelData.label
                color: root.effectiveStage === modelData.id ? Color.accent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: root.effectiveStage === modelData.id
              }
            }
          }

          // Stage 1 — link the Plex account through plex.tv (PIN flow).
          Column {
            visible: root.effectiveStage === "unlinked"
            width: setupColumn.width
            spacing: Style.space(10)

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: root.linking
                ? "Approve Plexarchy in the browser, or enter this code at plex.tv/link. Your password stays on plex.tv."
                : "Sign in on plex.tv to link this device. No password or token is typed into the plugin."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Text {
              id: linkCodeText
              textFormat: Text.PlainText
              visible: root.linking && root.linkCode !== ""
              width: parent.width
              text: root.linkCode
              color: Color.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.displayLarge
              font.bold: true
              font.letterSpacing: Style.space(6)
              horizontalAlignment: Text.AlignHCenter
            }

            Text {
              textFormat: Text.PlainText
              visible: root.linking
              width: parent.width
              text: "Waiting for Plex to approve this device…"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              horizontalAlignment: Text.AlignHCenter
            }

            Row {
              width: parent.width
              spacing: Style.space(6)

              PanelActionButton {
                id: connectButton
                visible: !root.linking
                width: manualButton.visible ? (parent.width - Style.space(6)) / 2 : parent.width
                height: Style.space(38)
                iconText: "\uf1c0  Link Plex account"
                foreground: root.foreground
                fontFamily: root.fontFamily
                bordered: true
                focusable: true
                enabled: !linkProc.running
                Accessible.name: "Link Plex account"
                onClicked: root.startLink()
              }

              PanelActionButton {
                id: manualButton
                visible: !root.linking
                width: (parent.width - Style.space(6)) / 2
                height: Style.space(38)
                iconText: "\uf120  Manual token setup"
                foreground: root.dim
                fontFamily: root.fontFamily
                fontSize: Style.font.bodySmall
                bordered: true
                focusable: true
                Accessible.name: "Manual token setup in a terminal"
                onClicked: root.manualSetup()
              }

              PanelActionButton {
                id: openLinkButton
                visible: root.linking
                width: (parent.width - Style.space(6)) / 2
                height: Style.space(38)
                iconText: "\uf08e  Open plex.tv/link"
                foreground: root.foreground
                fontFamily: root.fontFamily
                bordered: true
                focusable: true
                Accessible.name: "Open the Plex sign-in page"
                onClicked: root.openLinkPage()
              }

              PanelActionButton {
                id: cancelLinkButton
                visible: root.linking
                width: (parent.width - Style.space(6)) / 2
                height: Style.space(38)
                iconText: "\uf00d  Cancel"
                foreground: root.dim
                fontFamily: root.fontFamily
                fontSize: Style.font.bodySmall
                bordered: true
                focusable: true
                Accessible.name: "Cancel Plex sign-in"
                onClicked: root.cancelLink()
              }
            }
          }

          // Stage 2 — pick a server discovered on the linked account.
          Column {
            visible: root.effectiveStage === "servers"
            width: setupColumn.width
            spacing: Style.space(6)

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: root.setupBusy ? "Looking for your Plex servers…"
                : (root.servers.length > 0 ? "Servers on " + (root.account.account ? root.account.account : "your account") + ". Reachable servers can be selected."
                  : "No servers found yet.")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Repeater {
              model: root.servers
              delegate: CursorSurface {
                id: serverRow
                required property var modelData
                width: setupColumn.width
                height: Style.space(44)
                foreground: root.foreground
                enabled: modelData.reachable === true && !selectProc.running
                opacity: modelData.reachable === true ? 1 : 0.55
                activeFocusOnTab: modelData.reachable === true
                Accessible.role: Accessible.Button
                Accessible.name: modelData.name + " · " + Model.serverLine(modelData)
                Keys.onReturnPressed: root.chooseServer(modelData)
                Keys.onEnterPressed: root.chooseServer(modelData)

                RowLayout {
                  anchors.fill: parent
                  anchors.leftMargin: Style.space(10)
                  anchors.rightMargin: Style.space(10)
                  spacing: Style.space(10)

                  Text {
                    textFormat: Text.PlainText
                    text: serverRow.modelData.reachable === true ? "\uf233" : "\uf127"
                    color: serverRow.modelData.reachable === true ? Color.accent : Color.urgent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.icon
                  }

                  Column {
                    Layout.fillWidth: true
                    spacing: Style.space(1)
                    Text {
                      textFormat: Text.PlainText
                      width: parent.width
                      text: serverRow.modelData.name
                      color: root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.body
                      font.bold: true
                      elide: Text.ElideRight
                    }
                    Text {
                      textFormat: Text.PlainText
                      width: parent.width
                      text: Model.serverLine(serverRow.modelData)
                      color: root.dim
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      elide: Text.ElideMiddle
                    }
                  }

                  Text {
                    textFormat: Text.PlainText
                    visible: root.account.serverName === serverRow.modelData.name && root.stage === "ready"
                    text: "\uf00c"
                    color: Color.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.icon
                  }
                }

                MouseArea {
                  anchors.fill: parent
                  enabled: serverRow.enabled
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.chooseServer(serverRow.modelData)
                }
              }
            }

            Row {
              width: parent.width
              spacing: Style.space(6)

              PanelActionButton {
                id: refreshServersButton
                width: (parent.width - Style.space(6)) / 2
                height: Style.space(32)
                iconText: "\uf2f1  Refresh"
                foreground: root.foreground
                fontFamily: root.fontFamily
                fontSize: Style.font.bodySmall
                bordered: true
                focusable: true
                enabled: !root.setupBusy
                Accessible.name: "Refresh the server list"
                onClicked: root.loadServers()
              }

              PanelActionButton {
                width: (parent.width - Style.space(6)) / 2
                height: Style.space(32)
                iconText: root.stage === "ready" ? "\uf060  Keep current" : "\uf08b  Unlink account"
                foreground: root.stage === "ready" ? root.foreground : Color.urgent
                fontFamily: root.fontFamily
                fontSize: Style.font.bodySmall
                bordered: true
                focusable: true
                enabled: !selectProc.running
                Accessible.name: iconText
                onClicked: root.stage === "ready" ? root.handleEscape() : root.unlinkAccount()
              }
            }
          }

          // Stage 3 — pick the music library on the chosen server.
          Column {
            visible: root.effectiveStage === "libraries"
            width: setupColumn.width
            spacing: Style.space(6)

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: root.setupBusy ? "Loading music libraries…"
                : "Music libraries on " + (root.account.serverName || "this server")
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Repeater {
              model: root.libraries
              delegate: CursorSurface {
                id: libraryRow
                required property var modelData
                width: setupColumn.width
                height: Style.space(36)
                foreground: root.foreground
                enabled: !selectProc.running
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: modelData.title
                Keys.onReturnPressed: root.chooseLibrary(modelData)
                Keys.onEnterPressed: root.chooseLibrary(modelData)

                RowLayout {
                  anchors.fill: parent
                  anchors.leftMargin: Style.space(10)
                  anchors.rightMargin: Style.space(10)
                  spacing: Style.space(10)

                  Text {
                    textFormat: Text.PlainText
                    text: "\uf001"
                    color: Color.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.icon
                  }
                  Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: libraryRow.modelData.title
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    elide: Text.ElideRight
                  }
                  Text {
                    textFormat: Text.PlainText
                    visible: root.account.library === libraryRow.modelData.title
                    text: "\uf00c"
                    color: Color.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.icon
                  }
                }

                MouseArea {
                  anchors.fill: parent
                  enabled: libraryRow.enabled
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.chooseLibrary(libraryRow.modelData)
                }
              }
            }

            PanelActionButton {
              width: parent.width
              height: Style.space(32)
              iconText: "\uf060  Choose another server"
              foreground: root.foreground
              fontFamily: root.fontFamily
              fontSize: Style.font.bodySmall
              bordered: true
              focusable: true
              enabled: !root.setupBusy
              Accessible.name: "Choose another server"
              onClicked: root.loadServers()
            }
          }

          Text {
            textFormat: Text.PlainText
            visible: root.setupError !== ""
            width: setupColumn.width
            text: root.setupError
            color: Color.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }
        }
      }

      CursorSurface {
        visible: !root.helpVisible && !root.setupVisible && !root.health.ok && root.health.code !== "unconfigured" && !root.demoMode
        width: parent.width
        height: healthRow.implicitHeight + Style.space(14)
        foreground: Color.urgent

        RowLayout {
          id: healthRow
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          anchors.leftMargin: Style.space(8)
          anchors.rightMargin: Style.space(8)
          spacing: Style.space(8)
          Text { textFormat: Text.PlainText; text: "\uf071"; color: Color.urgent; font.family: root.fontFamily; font.pixelSize: Style.font.icon }
          Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: root.health.message || "Plex is not reachable."
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }
          PanelActionButton {
            iconText: root.health.code === "disconnected" ? "\uf011" : "\uf2f1"
            tooltipText: root.health.code === "disconnected" ? "Connect to Plex" : "Retry"
            foreground: root.foreground; fontFamily: root.fontFamily
            focusable: true; Accessible.name: tooltipText
            onClicked: root.retryCurrent()
          }
          PanelActionButton {
            visible: root.health.code === "unauthorized" || root.health.code === "library-missing"
            iconText: "\uf013"; tooltipText: "Reconnect"; foreground: root.foreground; fontFamily: root.fontFamily
            focusable: true; Accessible.name: tooltipText
            onClicked: root.connectPlex()
          }
        }
      }

      Flickable {
        visible: !root.helpVisible && root.plexConnected
        width: parent.width
        height: Style.space(38)
        contentWidth: navRow.implicitWidth
        contentHeight: height
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Row {
          id: navRow
          spacing: Style.space(4)

          Repeater {
            model: root.navigation
            delegate: CursorSurface {
              id: navItem
              required property var modelData
              width: Style.space(59)
              height: Style.space(34)
              activeFocusOnTab: true
              hasCursor: activeFocus
              current: root.view === modelData.id || (root.view === "children" && root.backStack.length > 0 && root.backStack[0].view === modelData.id)
              foreground: root.foreground
              Accessible.role: Accessible.PageTab
              Accessible.name: modelData.label
              Keys.onReturnPressed: root.loadView(modelData.id)
              Keys.onEnterPressed: root.loadView(modelData.id)
              Keys.onSpacePressed: root.loadView(modelData.id)

              Text {
                textFormat: Text.PlainText
                id: navLabel
                anchors.centerIn: parent
                text: navItem.modelData.icon + " " + navItem.modelData.label
                color: navItem.hasCursor ? root.foreground : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: navItem.hasCursor
              }
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.loadView(navItem.modelData.id)
              }
            }
          }
        }
      }

      TextField {
        id: searchField
        visible: !root.helpVisible && root.plexConnected && root.view !== "queue"
        width: parent.width
        placeholderText: "Search Plex…"
        Accessible.name: "Search Plex music"
        foreground: root.foreground
        font.family: root.fontFamily
        text: root.query
        maximumLength: 256
        onTextChanged: {
          root.query = text
          if (!root.suppressSearch) searchDebounce.restart()
        }
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Left && text === "") { root.switchNavigation(-1); event.accepted = true }
          else if (event.key === Qt.Key_Right && text === "") { root.switchNavigation(1); event.accepted = true }
          else if (event.key === Qt.Key_Escape) { root.handleEscape(); event.accepted = true }
          else root.handleListKey(event)
        }
      }

      RowLayout {
        visible: !root.helpVisible && root.plexConnected
        width: parent.width

        PanelActionButton {
          visible: root.view === "children"
          iconText: "\uf060"
          tooltipText: "Back"
          foreground: root.foreground
          fontFamily: root.fontFamily
          focusable: true
          Accessible.name: tooltipText
          onClicked: root.goBack()
        }
        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          text: root.view === "children" ? root.currentParentTitle
            : (root.view === "search" ? "Search results"
            : (root.view === "queue" ? "Up next"
            : (root.navigation.find(function(entry) { return entry.id === root.view }) || { label: "Library" }).label))
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          font.bold: true
          elide: Text.ElideRight
        }
        PanelActionButton {
          visible: root.view === "children" && (root.currentParentKind === "album" || root.currentParentKind === "playlist")
          iconText: "\uf04b"; tooltipText: "Play collection"; foreground: root.foreground; fontFamily: root.fontFamily; bordered: true
          focusable: true; Accessible.name: tooltipText
          onClicked: root.playCollection(false)
        }
        PanelActionButton {
          visible: root.view === "children" && (root.currentParentKind === "album" || root.currentParentKind === "playlist")
          iconText: "\uf074"; tooltipText: "Shuffle collection"; foreground: root.foreground; fontFamily: root.fontFamily
          focusable: true; Accessible.name: tooltipText
          onClicked: root.playCollection(true)
        }
        PanelActionButton {
          visible: root.view === "queue" && root.items.length > 0
          iconText: "\uf2ed"; tooltipText: "Clear upcoming"; foreground: root.foreground; fontFamily: root.fontFamily
          focusable: true; Accessible.name: tooltipText
          onClicked: root.runQueueAction("clear-upcoming")
        }
        Text {
          textFormat: Text.PlainText
          text: root.loading ? "Loading…" : root.items.length + (root.items.length === 1 ? " item" : " items")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      Text {
        textFormat: Text.PlainText
        visible: !root.helpVisible && root.errorText !== ""
        width: parent.width
        text: root.errorText
        color: Color.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
      }

      Text {
        textFormat: Text.PlainText
        visible: !root.helpVisible && root.plexConnected && !root.loading && root.errorText === "" && root.items.length === 0
        width: parent.width
        text: root.view === "search" ? "No matches." : "Nothing here yet."
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        horizontalAlignment: Text.AlignHCenter
      }

      ListView {
        id: itemList
        visible: !root.helpVisible && root.plexConnected && root.items.length > 0
        width: parent.width
        height: Math.min(contentHeight, Style.space(330))
        spacing: Style.space(5)
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: root.items
        currentIndex: root.selectedIndex
        activeFocusOnTab: true
        Accessible.role: Accessible.List
        Accessible.name: root.view === "queue" ? "Playback queue" : "Media results"
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) { root.handleEscape(); event.accepted = true }
          else root.handleListKey(event)
        }

        Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }

        delegate: CursorSurface {
          id: mediaRow
          required property var modelData
          required property int index
          width: ListView.view.width
          height: Style.space(54)
          hasCursor: root.selectedIndex === index
          foreground: root.foreground
          Accessible.role: Accessible.ListItem
          Accessible.name: (modelData.title || "Untitled") + ", " + Model.subtitle(modelData)
          Component.onCompleted: root.requestArtwork(modelData.artSource)

          MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: root.selectedIndex = mediaRow.index
            onClicked: root.activateItem(mediaRow.modelData)
          }

          RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Style.space(8)
            anchors.rightMargin: Style.space(8)
            spacing: Style.space(10)

            Rectangle {
              Layout.preferredWidth: Style.space(38)
              Layout.preferredHeight: Style.space(38)
              radius: Style.cornerRadius / 2
              color: Style.selectedFillFor(root.foreground, Color.accent)
              clip: true
              Image {
                anchors.fill: parent
                source: root.artworkThumb(mediaRow.modelData)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                sourceSize.width: Math.max(1, Math.round(width * 2))
                sourceSize.height: Math.max(1, Math.round(height * 2))
              }
            }
            ColumnLayout {
              Layout.fillWidth: true
              spacing: 1
              Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: mediaRow.modelData.title || "Untitled"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
                elide: Text.ElideRight
              }
              Text {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: Model.subtitle(mediaRow.modelData)
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }
            Text {
              textFormat: Text.PlainText
              visible: root.view !== "queue" && mediaRow.modelData.type !== "album" && mediaRow.modelData.type !== "playlist"
              text: mediaRow.modelData.type === "artist" ? mediaRow.modelData.leafCount + " albums" : Model.formatTime(mediaRow.modelData.duration)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
            PanelActionButton {
              visible: root.view !== "queue" && mediaRow.modelData.type === "track"
              iconText: "\uf2f9"; tooltipText: "Play next"; foreground: root.foreground; fontFamily: root.fontFamily
              focusable: true; Accessible.name: tooltipText + ": " + (mediaRow.modelData.title || "track")
              onClicked: root.playNext(mediaRow.modelData)
            }
            Row {
              visible: (mediaRow.modelData.type === "album" || mediaRow.modelData.type === "playlist") && root.view !== "queue"
              spacing: Style.space(3)
              PanelActionButton {
                iconText: "\uf04b"; tooltipText: "Play"; foreground: root.foreground; fontFamily: root.fontFamily
                focusable: true; Accessible.name: tooltipText + ": " + (mediaRow.modelData.title || "collection")
                onClicked: root.playItemCollection(mediaRow.modelData, false)
              }
              PanelActionButton {
                iconText: "\uf074"; tooltipText: "Shuffle"; foreground: root.foreground; fontFamily: root.fontFamily
                focusable: true; Accessible.name: tooltipText + ": " + (mediaRow.modelData.title || "collection")
                onClicked: root.playItemCollection(mediaRow.modelData, true)
              }
              Text { textFormat: Text.PlainText; text: "\uf054"; color: root.dim; font.family: root.fontFamily; font.pixelSize: Style.font.caption; anchors.verticalCenter: parent.verticalCenter }
            }
            Row {
              visible: root.view === "queue"
              spacing: Style.space(2)
              Text {
                textFormat: Text.PlainText
                visible: mediaRow.modelData.current === true
                text: root.player && root.player.playing ? "\uf04c" : "\uf04b"
                color: Color.urgent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.verticalCenter: parent.verticalCenter
              }
              PanelActionButton {
                visible: !mediaRow.modelData.current
                iconText: "\uf062"; tooltipText: "Move up"; foreground: root.foreground; fontFamily: root.fontFamily
                enabled: mediaRow.index > 0
                focusable: true; Accessible.name: tooltipText + ": " + (mediaRow.modelData.title || "track")
                onClicked: root.runQueueAction("move", Number(mediaRow.modelData.queueIndex), Math.max(0, Number(mediaRow.modelData.queueIndex) - 1))
              }
              PanelActionButton {
                visible: !mediaRow.modelData.current
                iconText: "\uf063"; tooltipText: "Move down"; foreground: root.foreground; fontFamily: root.fontFamily
                enabled: mediaRow.index < root.items.length - 1
                focusable: true; Accessible.name: tooltipText + ": " + (mediaRow.modelData.title || "track")
                onClicked: root.runQueueAction("move", Number(mediaRow.modelData.queueIndex), Math.min(root.items.length - 1, Number(mediaRow.modelData.queueIndex) + 1))
              }
              PanelActionButton {
                visible: !mediaRow.modelData.current
                iconText: "\uf00d"; tooltipText: "Remove"; foreground: root.foreground; fontFamily: root.fontFamily
                focusable: true; Accessible.name: tooltipText + ": " + (mediaRow.modelData.title || "track")
                onClicked: root.runQueueAction("remove", Number(mediaRow.modelData.queueIndex))
              }
            }
          }
        }
      }

    }
  }
}
