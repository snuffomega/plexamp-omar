import QtQuick
import qs.Commons
// Harness stand-in for the Quickshell popup: a plain Item that hosts content.
Item {
  id: root
  required property Item anchorItem
  required property QtObject bar
  property var owner: null
  property int margin: Style.gapsOut
  property int padding: Style.spacing.popupPadding
  property int contentWidth: Style.space(280)
  property int contentHeight: Style.space(200)
  property bool centerOnBar: false
  property bool open: false
  property Item focusTarget: null
  default property alias contentItem: contentHolder.children
  readonly property real availableCardWidth: 1200
  readonly property real availableCardHeight: 1000
  readonly property real verticalContentInset: padding * 2
  function fittedContentWidth(width, cap) { return Math.round(Math.min(Number(width) || 1, availableCardWidth)) }
  function fittedContentHeight(h, cap) { var d = (Number(h) || 0) + verticalContentInset; if (cap > 0) d = Math.min(d, cap); return Math.round(Math.min(d, availableCardHeight)) }
  width: contentWidth + padding * 2
  height: contentHeight
  visible: open
  Item { id: contentHolder; anchors.fill: parent; anchors.margins: root.padding }
}
