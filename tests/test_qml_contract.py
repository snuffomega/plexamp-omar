import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
QML = (ROOT / "Panel.qml").read_text(encoding="utf-8")
MODEL = (ROOT / "Model.js").read_text(encoding="utf-8")


def text_blocks(source):
    blocks = []
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s*Text \{", line):
            continue
        block = [line]
        depth = line.count("{") - line.count("}")
        for following in lines[index + 1:]:
            if depth <= 0:
                break
            block.append(following)
            depth += following.count("{") - following.count("}")
        blocks.append("\n".join(block))
    return blocks


class QmlContractTests(unittest.TestCase):
    def test_native_panel_contract(self):
        self.assertIn("Panel {", QML)
        self.assertIn('moduleName: "community.plexarchy"', QML)
        self.assertIn("KeyboardPanel {", QML)
        self.assertIn("WidgetButton {", QML)

    def test_helper_uses_argument_array(self):
        self.assertIn('command(["search", value', QML)
        self.assertNotIn("X-Plex-Token", QML)

    def test_setup_uses_shell_quoting(self):
        self.assertIn("Util.shellQuote(helperPath)", QML)

    def test_player_controls_are_present(self):
        for action in ('control("toggle")', 'control("previous")', 'control("next")', 'control("seek"',
                       'control("volume"', 'control("shuffle")', 'control("repeat")'):
            self.assertIn(action, QML)

    def test_bar_shows_active_album_cover_with_glyph_fallback(self):
        self.assertIn("readonly property string activeThumb", QML)
        self.assertIn("id: barCover", QML)
        self.assertIn("source: root.activeThumb", QML)
        self.assertIn("id: barLogo", QML)
        self.assertIn("text: root.logoGlyph", QML)
        self.assertIn("visible: !barCover.visible", QML)
        self.assertIn("fixedHeight: vertical ? Style.bar.iconSlot", QML)
        self.assertNotIn("assets/", QML)

    def test_bar_shows_artist_and_inline_transport_controls(self):
        self.assertIn("id: barArtist", QML)
        self.assertIn("Model.artistLine(root.activeTrack)", QML)
        self.assertIn("id: barControls", QML)
        self.assertIn('setting("showBarControls", true)', QML)
        for action in ('"previous"', '"toggle"', '"next"'):
            self.assertIn("action: " + action, QML)
        self.assertIn("onClicked: root.control(barControl.modelData.action)", QML)

    def test_in_panel_plex_linking_flow(self):
        for step in ('command(["link", "start"])', 'command(["link", "poll"])', 'command(["link", "cancel"])',
                     'command(["servers"])', 'command(["libraries"])', 'command(["select-server"',
                     'command(["select-library"', 'command(["account"])', 'command(["logout"])'):
            self.assertIn(step, QML)
        self.assertIn('bar.run("xdg-open " + Util.shellQuote(linkUrl))', QML)
        self.assertIn("id: linkCodeText", QML)
        for stage in ('"unlinked"', '"servers"', '"libraries"', '"ready"'):
            self.assertIn("effectiveStage === " + stage if stage != '"ready"' else 'stage === "ready"', QML)
        self.assertIn("readonly property bool setupNeeded", QML)
        self.assertIn("modelData.reachable === true", QML)
        self.assertNotIn("omarchy launch floating terminal with presentation \" + Util.shellQuote(helperPath) + \" login", QML)

    def test_play_button_reflects_playback_state(self):
        self.assertIn("id: playButton", QML)
        self.assertIn('iconText: root.player && root.player.playing ? "\\uf04c" : "\\uf04b"', QML)
        self.assertIn('tooltipText: root.player && root.player.playing ? "Pause" : "Play"', QML)
        self.assertGreaterEqual(QML.count('root.player && root.player.playing ? "\\uf04c" : "\\uf04b"'), 2)
        self.assertIn('status.playing ? "\\uf04c  " : "\\uf04b  "', MODEL)

    def test_library_and_queue_navigation_are_present(self):
        for view in ('"artists"', '"albums"', '"playlists"', '"history"', '"frequent"', '"favorites"', '"queue"'):
            self.assertIn(view, QML)
        self.assertIn('runQueueAction("remove"', QML)
        self.assertIn('"play-next"', QML)
        self.assertGreaterEqual(QML.count("items[selectedIndex].current === true"), 2)

    def test_opening_during_playback_defaults_to_the_queue(self):
        self.assertIn("loadView(Model.defaultView(player))", QML)
        self.assertIn("function defaultView(status)", MODEL)

    def test_arrow_keys_switch_library_tabs(self):
        self.assertIn('sequence: "Left"', QML)
        self.assertIn('sequence: "Right"', QML)
        self.assertIn("event.key === Qt.Key_Left", QML)
        self.assertIn("event.key === Qt.Key_Right", QML)
        self.assertIn("root.switchNavigation(-1)", QML)
        self.assertIn("root.switchNavigation(1)", QML)
        self.assertIn("readonly property bool navigationShortcutsEnabled", QML)
        self.assertIn("!searchField.activeFocus", QML)
        self.assertIn("!seekFocus.activeFocus", QML)
        self.assertIn("!volumeFocus.activeFocus", QML)

    def test_rapid_tab_switches_only_apply_the_latest_request(self):
        self.assertIn("property int requestedDataRequestId: 0", QML)
        self.assertIn("property int activeDataRequestId: 0", QML)
        self.assertIn("property int queuedDataRequestId: 0", QML)
        self.assertIn("finishedRequestId === requestedDataRequestId", QML)
        self.assertIn("root.finishData(exitCode, dataOutput.text, dataError.text)", QML)
        self.assertNotIn("onStreamFinished: root.handleData(text)", QML)

    def test_nested_navigation_preserves_complete_context(self):
        self.assertIn("Model.navigationState(", QML)
        self.assertIn("backStack.concat", QML)
        self.assertIn("currentParentKey = String(previous.parentKey", QML)
        self.assertIn("currentParentKind = String(previous.parentKind", QML)
        self.assertIn("pendingSelectedIndex = Number(previous.selectedIndex", QML)
        self.assertIn("Model.navigationArgs(previous", QML)
        for field in ("parentKey", "parentKind", "selectedIndex"):
            self.assertIn(field, MODEL)

    def test_player_actions_are_queued_and_slider_updates_coalesced(self):
        self.assertIn("property var pendingActions: []", QML)
        self.assertIn("pendingActions = Model.queueAction(pendingActions, nextCommand)", QML)
        self.assertIn('kind !== "seek" && kind !== "volume"', MODEL)
        self.assertIn("root.pendingActions = root.pendingActions.slice(1)", QML)
        self.assertIn("MAX_PENDING_ACTIONS = 8", MODEL)
        self.assertIn("pendingQueueEdits.length >= 16", QML)
        self.assertNotIn("if (actionProc.running) return", QML)

    def test_volume_updates_optimistically_while_the_slider_moves(self):
        self.assertIn("function setVolume(value)", QML)
        self.assertIn("updated.volume = next", QML)
        self.assertIn("onMoved: function(next) { root.setVolume(next) }", QML)
        self.assertIn("volumeSlider.dragging ? volumeSlider.liveValue", QML)
        self.assertNotIn("property bool volumeDragging", QML)

    def test_volume_defaults_to_system_output_with_player_option(self):
        self.assertIn("import Quickshell.Services.Pipewire", QML)
        self.assertIn('setting("volumeMode", "System")', QML)
        self.assertIn('volumeSink.audio.volume = next / 100', QML)
        self.assertIn('control("volume", next)', QML)
        self.assertIn('["omarchy", "bar", "set", moduleName, "volumeMode"', QML)
        self.assertIn('command: ["omarchy-audio-output-sink"]', QML)
        self.assertIn('Accessible.role: Accessible.RadioButton', QML)
        self.assertIn('label: "System"', QML)
        self.assertIn('label: "Plex"', QML)

    def test_status_polling_is_adaptive(self):
        self.assertIn("root.opened ? 3000", QML)
        self.assertIn("root.player && root.player.playing ? 10000", QML)
        self.assertIn("root.activeTrack ? 15000 : 30000", QML)
        self.assertIn("root.advanceProgress()", QML)

    def test_queue_mutations_are_not_sent_through_cancellable_data_process(self):
        queue_function = QML[QML.index("function runQueueAction"):QML.index("function playNext")]
        self.assertIn("runQueueEdit(command(args))", queue_function)
        self.assertNotIn("runData(", queue_function)
        self.assertIn('if (root.view === "queue") root.runData', QML)

    def test_artwork_is_lazy_bounded_and_decode_limited(self):
        self.assertIn('command(["art", activeArtwork])', QML)
        self.assertIn("pendingArtwork.length >= 32", QML)
        self.assertIn("property int artworkGeneration: 0", QML)
        self.assertIn("requestedArtwork[value]", QML)
        self.assertIn("if (artProc.running) artProc.running = false", QML)
        self.assertIn("generation === root.artworkGeneration", QML)
        self.assertIn("resolvedArtworkOrder", QML)
        self.assertIn("while (order.length > 128)", QML)
        self.assertIn("root.artworkThumb(mediaRow.modelData)", QML)
        self.assertNotIn("var nextItems = []", QML)
        self.assertGreaterEqual(QML.count("sourceSize.width:"), 3)
        self.assertIn("maximumLength: 256", QML)

    def test_status_and_health_process_errors_are_visible(self):
        self.assertIn("id: statusError", QML)
        self.assertIn("id: healthError", QML)
        self.assertIn('"Could not refresh player status."', QML)
        self.assertIn('code: "helper-error"', QML)
        self.assertIn("message.length > 400", QML)

    def test_active_artwork_uses_async_frontend_pipeline(self):
        self.assertIn("if (parsed.track && (parsed.connected !== false || demoMode)) requestArtwork(parsed.track.artSource)", QML)
        self.assertIn("plexConnected && activeTrack ? artworkThumb(activeTrack)", QML)
        self.assertIn("source: root.activeThumb", QML)

    def test_panel_text_items_are_explicitly_plain_text(self):
        blocks = text_blocks(QML)
        self.assertGreaterEqual(len(blocks), 20)
        for block in blocks:
            self.assertIn("textFormat: Text.PlainText", block)

    def test_connection_toggle_preserves_setup_and_gates_plex_ui(self):
        self.assertIn("readonly property bool plexConnected", QML)
        self.assertIn("function setConnection(enabled)", QML)
        self.assertIn('command(["connection", enabled ? "on" : "off"])', QML)
        self.assertIn("id: connectionButton", QML)
        self.assertIn('tooltipText: root.plexConnected ? "Disconnect from Plex" : "Connect to Plex"', QML)
        self.assertIn("enabled: !connectionProc.running", QML)
        self.assertIn("visible: !root.helpVisible && root.plexConnected", QML)
        self.assertIn('root.health.code === "disconnected"', QML)
        for process in ("dataProc", "artProc", "actionProc", "queueEditProc", "healthProc", "statusProc"):
            self.assertIn(f"if ({process}.running) {process}.running = false", QML)
        self.assertIn("if (root.disconnecting) return", QML)

    def test_complete_keyboard_navigation_contract(self):
        self.assertGreaterEqual(QML.count("focusable: true"), 15)
        self.assertGreaterEqual(QML.count("activeFocusOnTab: true"), 3)
        for contract in ('sequence: "Escape"', 'sequence: "Ctrl+Space"', "root.handleEscape()",
                         "moveQueueSelection", "removeSelectedQueueItem", "Accessible.name"):
            self.assertIn(contract, QML)
        self.assertIn('event.key === Qt.Key_Left && text === ""', QML)
        self.assertIn('event.key === Qt.Key_Right && text === ""', QML)

    def test_keyboard_help_is_available_from_button_and_f1(self):
        self.assertIn("property bool helpVisible: false", QML)
        self.assertIn("readonly property var keyboardHelp", QML)
        self.assertIn('id: helpButton', QML)
        self.assertIn('iconText: root.helpVisible ? "\\uf00d" : "\\uf013"', QML)
        self.assertIn('id: headerLogo', QML)
        self.assertIn('font.pixelSize: root.helpVisible ? Style.font.displayLarge : Style.font.display', QML)
        self.assertNotIn('iconText: "?"', QML)
        self.assertIn('sequence: "F1"', QML)
        self.assertIn('text: root.helpVisible || !root.plexConnected ? "Plexarchy"', QML)
        self.assertIn('text: root.helpVisible ? "Help · Keyboard map and player settings"', QML)
        self.assertNotIn("↑↓ Select  ·  Enter Play", QML)

    def test_plex_login_and_demo_mode_are_present(self):
        self.assertIn('function startLink()', QML)
        self.assertIn('setting("demoMode", false)', QML)


if __name__ == "__main__":
    unittest.main()
