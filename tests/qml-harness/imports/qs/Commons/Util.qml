pragma Singleton
import QtQuick
QtObject {
  function clampAlpha(v) { var n = Number(v); return isFinite(n) ? Math.max(0, Math.min(1, n)) : 1 }
  function alpha(c, opacity) {
    var a = clampAlpha(opacity)
    if (!c) return Qt.rgba(0, 0, 0, a)
    if (typeof c === "string") c = Qt.color(c)
    return Qt.rgba(c.r, c.g, c.b, a)
  }
  function shellQuote(v) { return "'" + String(v).replace(/'/g, "'\\''") + "'" }
}
