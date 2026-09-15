import QtQuick
// Harness Process: runs the command through the Python bridge so the real
// helper is exercised, then fills the collectors and emits exited(). Setting
// running=false while in flight cancels like Quickshell (exited with 143).
QtObject {
  id: proc
  property var command: []
  property bool running: false
  property var stdout: null
  property var stderr: null
  property var environment: ({})
  property int generation: 0
  property bool inFlight: false
  signal exited(int exitCode, int exitStatus)
  onRunningChanged: {
    if (!running) {
      if (inFlight) {
        inFlight = false
        generation += 1
        Qt.callLater(function() { proc.exited(143, 1) })
      }
      return
    }
    var current = ++generation
    inFlight = true
    Harness.run(command, function(result) {
      if (!proc.inFlight || current !== proc.generation) return
      proc.inFlight = false
      if (proc.stdout) { proc.stdout.text = result.stdout; proc.stdout.streamFinished() }
      if (proc.stderr) { proc.stderr.text = result.stderr; proc.stderr.streamFinished() }
      proc.running = false
      proc.exited(result.code, 0)
    })
  }
}
