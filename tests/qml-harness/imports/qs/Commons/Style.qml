pragma Singleton
import QtQuick
QtObject {
  id: root
  readonly property int cornerRadius: 6
  readonly property int gapsOut: 10
  readonly property var styleOverrides: ({})
  readonly property real normalFillAlpha: 0.0
  readonly property real hoverFillAlpha: 0.14
  readonly property real focusFillAlpha: 0.14
  readonly property real selectedFillAlpha: 0.1
  readonly property real pressedFillAlpha: 0.2
  readonly property real selectionFillAlpha: 0.3
  readonly property real normalBorderAlpha: 0.3
  readonly property real hoverBorderAlpha: 0.6
  readonly property real focusBorderAlpha: 0.6
  readonly property real selectedBorderAlpha: 0.5
  readonly property int normalBorderWidth: 1
  readonly property int hoverBorderWidth: 1
  readonly property int focusBorderWidth: 1
  readonly property int selectedBorderWidth: 0
  function normalStateColor(f, a, u) { return f }
  function hoverStateColor(f, a, u) { return a }
  function focusStateColor(f, a, u) { return a }
  function selectedStateColor(f, a, u) { return f }
  function pressedStateColor(f, a, u) { return a }
  function selectionStateColor(f, a, u) { return f }
  function normalFillFor(f, a, u) { return Util.alpha(normalStateColor(f, a, u), normalFillAlpha) }
  function hoverFillFor(f, a, u) { return Util.alpha(hoverStateColor(f, a, u), hoverFillAlpha) }
  function selectedFillFor(f, a, u) { return Util.alpha(selectedStateColor(f, a, u), selectedFillAlpha) }
  function pressedFillFor(f, a, u) { return Util.alpha(pressedStateColor(f, a, u), pressedFillAlpha) }
  function focusFillFor(f, a, u) { return Util.alpha(focusStateColor(f, a, u), focusFillAlpha) }
  function selectionFillFor(f, a, u) { return Util.alpha(selectionStateColor(f, a, u), selectionFillAlpha) }
  function normalBorderFor(f, a, u) { return Util.alpha(f, normalBorderAlpha) }
  function hoverBorderFor(f, a, u) { return Util.alpha(a, hoverBorderAlpha) }
  function focusBorderFor(f, a, u) { return Util.alpha(a, focusBorderAlpha) }
  function selectedBorderFor(f, a, u) { return Util.alpha(f, selectedBorderAlpha) }
  function controlFill(focused, hot, f, a) { return focused ? focusFillFor(f, a) : (hot ? hoverFillFor(f, a) : normalFillFor(f, a)) }
  function controlBorder(focused, hot, f, a) { return focused ? focusBorderFor(f, a) : (hot ? hoverBorderFor(f, a) : normalBorderFor(f, a)) }
  function controlBorderWidth(focused, hot) { return 1 }
  function spaceReal(px) { var n = Number(px); return isFinite(n) && n > 0 ? n : 0 }
  function space(px) { var n = spaceReal(px); return n <= 0 ? 0 : Math.max(1, Math.round(n)) }
  readonly property QtObject font: QtObject {
    readonly property string family: "monospace"
    readonly property int caption: 10
    readonly property int bodySmall: 11
    readonly property int body: 12
    readonly property int subtitle: 13
    readonly property int title: 14
    readonly property int heading: 16
    readonly property int display: 24
    readonly property int displayLarge: 28
    readonly property int iconSmall: 11
    readonly property int icon: 14
    readonly property int iconLarge: 18
  }
  readonly property QtObject spacing: QtObject {
    readonly property int hairline: 1
    readonly property int xxs: 2
    readonly property int xs: 4
    readonly property int sm: 6
    readonly property int md: 8
    readonly property int lg: 12
    readonly property int xl: 16
    readonly property int controlPaddingX: 10
    readonly property int controlPaddingY: 6
    readonly property int inputPaddingY: 6
    readonly property int controlHeight: 28
    readonly property int popupRowHeight: 28
    readonly property int controlGap: 6
    readonly property int labelGap: 6
    readonly property int rowGap: 8
    readonly property int rowPaddingX: 10
    readonly property int panelGap: 12
    readonly property int panelPadding: 16
    readonly property int popupPadding: 14
  }
  readonly property QtObject bar: QtObject {
    readonly property int sizeHorizontal: 26
    readonly property int sizeVertical: 28
    readonly property int iconSlot: 28
    readonly property int statusSlot: 34
  }
}
