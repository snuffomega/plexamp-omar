pragma Singleton
import QtQuick
QtObject {
  function env(name) { return "" }
  function execDetached(argv) { console.log("[stub] execDetached", JSON.stringify(argv)) }
}
