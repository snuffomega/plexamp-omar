#!/usr/bin/env python3
"""Deterministic release validation for the Omarchy plugin manifest."""

import json
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"


def require(condition, message):
    if not condition:
        raise SystemExit(f"manifest.json: {message}")


data = json.loads(MANIFEST.read_text(encoding="utf-8"))
require(data.get("schemaVersion") == 1, "schemaVersion must be 1")
require(re.fullmatch(r"[a-z0-9]+(?:\.[a-z0-9-]+)+", str(data.get("id", ""))), "id must be reverse-DNS")
for key in ("name", "version", "author", "license", "description"):
    require(isinstance(data.get(key), str) and data[key].strip(), f"{key} is required")
require(re.fullmatch(r"\d+\.\d+\.\d+", data["version"]), "version must be semantic x.y.z")
require(data.get("kinds") == ["bar-widget"], "kinds must declare bar-widget")
entry = data.get("entryPoints", {}).get("barWidget")
require(isinstance(entry, str) and (ROOT / entry).is_file(), "barWidget entry point must exist")

widget = data.get("barWidget")
require(isinstance(widget, dict), "barWidget object is required")
require(widget.get("category") == "Media", "barWidget category must be Media")
require(widget.get("defaultSection") in ("left", "center", "right"), "defaultSection is invalid")
schema = widget.get("schema")
require(isinstance(schema, list), "barWidget schema must be a list")
keys = [row.get("key") for row in schema if isinstance(row, dict)]
require(len(keys) == len(schema) == len(set(keys)), "setting keys must be unique objects")
defaults = widget.get("defaults")
require(isinstance(defaults, dict) and set(defaults) == set(keys), "defaults and schema keys must match")
for row in schema:
    require(row.get("type") in ("boolean", "integer", "number", "string", "enum"), f"invalid type for {row.get('key')}")
    if row.get("type") == "enum":
        require(isinstance(row.get("options"), list) and len(row["options"]) >= 2, f"enum options missing for {row.get('key')}")
        require(row.get("defaultValue") in row["options"], f"enum default is not an option for {row.get('key')}")
    require(row.get("defaultValue") == defaults[row["key"]], f"default mismatch for {row['key']}")

print("manifest.json: valid")
