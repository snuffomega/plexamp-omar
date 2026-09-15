const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "Model.js"), "utf8")
  .replace(/^\.pragma library\s*/u, "");
const model = {};
vm.createContext(model);
vm.runInContext(source, model);

test("nested navigation snapshots retain full parent context", () => {
  const state = model.navigationState("children", "artist-1", "artist", "Artist", "query", 7);
  assert.deepEqual(JSON.parse(JSON.stringify(state)), {
    view: "children",
    parentKey: "artist-1",
    parentKind: "artist",
    title: "Artist",
    query: "query",
    selectedIndex: 7,
  });
  assert.deepEqual(Array.from(model.navigationArgs(state, 20, 100)),
                   ["children", "artist", "artist-1"]);
});

test("top-level and search states produce executable helper arguments", () => {
  assert.deepEqual(Array.from(model.navigationArgs(model.navigationState("albums"), 20, 100)),
                   ["library", "albums", "--limit", "100"]);
  assert.deepEqual(Array.from(model.navigationArgs(model.navigationState("search", "", "", "", "tuna"), 20, 100)),
                   ["search", "tuna", "--limit", "35"]);
});

test("active or paused playback opens on the queue", () => {
  assert.equal(model.defaultView({ playing: true, paused: false }), "queue");
  assert.equal(model.defaultView({ playing: false, paused: true }), "queue");
  assert.equal(model.defaultView({ playing: false, paused: false, track: { title: "Saved" } }), "recent");
  assert.equal(model.defaultView(null), "recent");
});

test("transport actions queue while sliders coalesce to the newest intent", () => {
  const helper = "/plugin/bin/plexarchy";
  const previous = [
    [helper, "control", "next"],
    [helper, "control", "seek", "10"],
    [helper, "control", "volume", "50"],
  ];
  const seek = model.queueAction(previous, [helper, "control", "seek", "20"]);
  assert.deepEqual(JSON.parse(JSON.stringify(seek)), [
    [helper, "control", "next"],
    [helper, "control", "volume", "50"],
    [helper, "control", "seek", "20"],
  ]);
  const transport = model.queueAction(seek, [helper, "control", "previous"]);
  assert.equal(transport.length, 4);
  assert.deepEqual(Array.from(transport[3]), [helper, "control", "previous"]);
});

test("pending transport actions have a strict bound", () => {
  const helper = "/plugin/bin/plexarchy";
  let pending = [];
  for (let index = 0; index < 20; index += 1)
    pending = model.queueAction(pending, [helper, "control", index % 2 ? "next" : "previous"]);
  assert.equal(pending.length, model.MAX_PENDING_ACTIONS);
  assert.equal(pending.length, 8);
});
