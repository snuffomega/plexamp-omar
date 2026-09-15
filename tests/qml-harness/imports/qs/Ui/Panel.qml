import QtQuick
import Quickshell.Io
import qs.Commons
Item {
  id: root
  property QtObject bar: null
  property string moduleName: ""
  property var settings: ({})
  property string ipcTarget: ""
  property bool manageIpc: true
  property alias controller: panelController
  property bool popoutSwitching: false
  property bool popoutSwitchClosing: false
  readonly property bool opened: panelController.open
  readonly property color barForeground: bar ? bar.barForeground : Color.foreground
  function open() { panelController.show() }
  function close() { panelController.hide() }
  function toggle() { opened ? close() : open() }
  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null ? fallback : value
  }
  PanelController { id: panelController }
}
