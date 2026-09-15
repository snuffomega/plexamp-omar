.pragma library

var MAX_PENDING_ACTIONS = 8

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, Number(value) || 0))
}

function formatTime(seconds) {
  var value = Math.max(0, Math.floor(Number(seconds) || 0))
  var minutes = Math.floor(value / 60)
  var rest = value % 60
  return minutes + ":" + (rest < 10 ? "0" : "") + rest
}

function barLabel(status) {
  if (!status || !status.configured) return "\uf1c0"
  if (!status.track || !status.track.title) return "\uf001"
  return (status.playing ? "\uf04c  " : "\uf04b  ") + status.track.title
}

function safeArray(value) {
  return Array.isArray(value) ? value : []
}

function subtitle(item) {
  if (!item) return ""
  var artist = String(item.artist || "")
  var album = String(item.album || "")
  if (artist && album && artist !== album) return artist + " · " + album
  return artist || album
}

function artistLine(item) {
  if (!item) return ""
  return String(item.artist || item.album || "")
}

function serverLine(server) {
  if (!server) return ""
  if (server.reachable !== true) return server.online === false ? "Offline" : "Not reachable from this device"
  var parts = [String(server.uri || "")]
  if (server.relay === true) parts.push("relay")
  else if (server.local === true) parts.push("local network")
  if (server.owned === false) parts.push("shared")
  return parts.join(" · ")
}

function connectionLabel(state) {
  if (!state) return ""
  var parts = []
  if (state.serverName) parts.push(String(state.serverName))
  if (state.library) parts.push(String(state.library))
  if (state.account) parts.push(String(state.account))
  return parts.join(" · ")
}

function defaultView(status) {
  return status && (status.playing === true || status.paused === true) ? "queue" : "recent"
}

function navigationState(view, key, kind, title, query, selectedIndex) {
  return {
    view: String(view || "recent"),
    parentKey: String(key || ""),
    parentKind: String(kind || ""),
    title: String(title || ""),
    query: String(query || ""),
    selectedIndex: Math.max(0, Number(selectedIndex) || 0)
  }
}

function navigationArgs(state, recentLimit, libraryLimit) {
  var previous = state || navigationState("recent")
  if (previous.view === "children")
    return ["children", previous.parentKind, previous.parentKey]
  if (previous.view === "search")
    return ["search", previous.query, "--limit", "35"]
  if (previous.view === "queue") return ["queue"]
  return ["library", previous.view, "--limit",
          String(previous.view === "recent" ? recentLimit : libraryLimit)]
}

function actionKind(command) {
  var values = safeArray(command)
  for (var index = 0; index < values.length - 1; index++)
    if (values[index] === "control") return String(values[index + 1])
  return "transport"
}

function queueAction(pending, nextCommand) {
  var queued = safeArray(pending)
  var kind = actionKind(nextCommand)
  if (kind !== "seek" && kind !== "volume")
    return queued.concat([nextCommand]).slice(-MAX_PENDING_ACTIONS)
  var retained = []
  for (var index = 0; index < queued.length; index++)
    if (actionKind(queued[index]) !== kind) retained.push(queued[index])
  return retained.concat([nextCommand]).slice(-MAX_PENDING_ACTIONS)
}
