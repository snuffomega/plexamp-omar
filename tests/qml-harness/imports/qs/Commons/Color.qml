pragma Singleton
import QtQuick
QtObject {
  readonly property var shellValues: ({})
  readonly property color foreground: "#e6e1d7"
  readonly property color background: "#1c1b19"
  readonly property color accent: "#f5b942"
  readonly property color urgent: "#e05c4a"
  readonly property QtObject popups: QtObject { readonly property color background: "#1c1b19"; readonly property color border: "#f5b942"; readonly property color text: "#e6e1d7" }
  readonly property QtObject tooltip: QtObject { readonly property color background: "#1c1b19"; readonly property color border: "#f5b942"; readonly property color text: "#e6e1d7" }
  readonly property QtObject bar: QtObject { readonly property color background: "#1c1b19"; readonly property color foreground: "#e6e1d7" }
}
