pragma Singleton
import QtQuick
import "HarnessConfig.js" as Config
// Bridges the Process stub to the Python driver, which runs the real helper.
QtObject {
  function run(command, callback) {
    var xhr = new XMLHttpRequest()
    xhr.open("POST", "http://127.0.0.1:" + Config.port + "/run")
    xhr.setRequestHeader("Content-Type", "application/json")
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE) return
      var result = { stdout: "", stderr: "bridge error", code: 1 }
      try { result = JSON.parse(xhr.responseText) } catch (error) {}
      callback(result)
    }
    xhr.send(JSON.stringify({ command: command }))
  }
}
