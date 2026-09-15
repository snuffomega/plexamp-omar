pragma Singleton
import QtQuick
QtObject {
  readonly property var defaultAudioSink: QtObject {
    readonly property string name: "stub-sink"
    readonly property bool isSink: true
    readonly property bool isStream: false
    readonly property QtObject audio: QtObject { property real volume: 0.5; property bool muted: false }
  }
  readonly property var nodes: QtObject { readonly property var values: [] }
}
