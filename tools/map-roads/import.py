"""Import the permitted Forever Maps road dataset without executing downloaded Lua.

Usage: python -P tools/map-roads/import.py ForeverMaps.zip [--check]
Only literal road-node assignments and the building table are read. Navigation
code, NPC catalogues, shops and art are never imported.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ROAD_FILE = "ForeverMaps/GameData/ShippedData.lua"
BUILDING_FILE = "ForeverMaps/GameData/BuildingData.lua"
LEVEL_FILE = "ForeverMaps/GameData/AreaLevelData.lua"
AREA_FILE = "ForeverMaps/GameData/AreaChunkData.lua"
SOURCE_URL = "https://www.curseforge.com/wow/addons/forever-maps-world-map-gps-navigation/files/9632734"
AUTHOR = "sahnetee"
PERMISSION = "Used with author permission confirmed by the fork maintainer; not relicensed under MIT."
NODE = re.compile(r'^S\.base\[(\d+)\]\.zones\[(\d+|"map")\]\.nodes\[(\d+)\]=(.+)$')
NUMBER = re.compile(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')


class LiteralError(ValueError):
    pass


class LiteralParser:
    """Small Lua-literal grammar: no names as values, expressions or function calls."""

    def __init__(self, text: str):
        if len(text) > 16_000_000:
            raise LiteralError("literal input is too large")
        self.text, self.at = text, 0

    def space(self):
        while self.at < len(self.text):
            if self.text[self.at].isspace():
                self.at += 1
            elif self.text.startswith("--", self.at):
                end = self.text.find("\n", self.at)
                self.at = len(self.text) if end < 0 else end + 1
            else:
                break

    def take(self, token):
        self.space()
        if not self.text.startswith(token, self.at):
            raise LiteralError(f"expected {token!r} at character {self.at}")
        self.at += len(token)

    def string(self):
        quote = self.text[self.at]
        self.at += 1
        out = bytearray()
        escapes = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11,
                   "\\": 92, '"': 34, "'": 39}
        while self.at < len(self.text):
            char = self.text[self.at]
            self.at += 1
            if char == quote:
                return out.decode("utf-8")
            if char in "\n\r":
                raise LiteralError("unescaped newline in string")
            if char != "\\":
                out.extend(char.encode("utf-8"))
                continue
            if self.at >= len(self.text):
                break
            char = self.text[self.at]
            self.at += 1
            if char in escapes:
                out.append(escapes[char])
            elif char.isdigit() and char.isascii():
                digits = char
                while len(digits) < 3 and self.at < len(self.text) and self.text[self.at] in "0123456789":
                    digits += self.text[self.at]
                    self.at += 1
                if int(digits) > 255:
                    raise LiteralError("decimal string escape exceeds one byte")
                out.append(int(digits))
            else:
                raise LiteralError("unsupported Lua string escape")
        raise LiteralError("unterminated string")

    def value(self, depth=0):
        if depth > 32:
            raise LiteralError("literal nesting is too deep")
        self.space()
        if self.at >= len(self.text):
            raise LiteralError("expected a literal")
        char = self.text[self.at]
        if char in "\"'":
            return self.string()
        if char == "{":
            self.at += 1
            table, next_index = {}, 1
            while True:
                self.space()
                if self.at >= len(self.text):
                    raise LiteralError("unterminated table")
                if self.text[self.at] == "}":
                    self.at += 1
                    return table
                if self.text[self.at] == "[":
                    self.at += 1
                    key = self.value(depth + 1)
                    if isinstance(key, (dict, bool)) or not isinstance(key, (str, int, float)):
                        raise LiteralError("invalid table key")
                    self.take("]")
                    self.take("=")
                    value = self.value(depth + 1)
                else:
                    name = IDENT.match(self.text, self.at)
                    after_name = name.end() if name else self.at
                    while after_name < len(self.text) and self.text[after_name].isspace():
                        after_name += 1
                    if name and self.text[after_name:after_name + 1] == "=":
                        key = name[0]
                        self.at = after_name + 1
                        value = self.value(depth + 1)
                    else:
                        key, next_index = next_index, next_index + 1
                        value = self.value(depth + 1)
                if key in table:
                    raise LiteralError("duplicate literal table key")
                table[key] = value
                self.space()
                if self.at < len(self.text) and self.text[self.at] in ",;":
                    self.at += 1
                elif self.at >= len(self.text) or self.text[self.at] != "}":
                    raise LiteralError("expected table separator")
        number = NUMBER.match(self.text, self.at)
        if number:
            self.at = number.end()
            value = float(number[0]) if any(c in number[0] for c in ".eE") else int(number[0])
            if not math.isfinite(value):
                raise LiteralError("non-finite number")
            return value
        for token, value in (("true", True), ("false", False)):
            if self.text.startswith(token, self.at):
                self.at += len(token)
                return value
        raise LiteralError(f"non-literal input at character {self.at}")

    def parse(self):
        result = self.value()
        self.space()
        if self.at != len(self.text):
            raise LiteralError("trailing expressions are not allowed")
        return result


def literal(text):
    return LiteralParser(text).parse()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    """Typed keys keep numeric node IDs distinct from metadata names in the audit."""
    if isinstance(value, dict):
        return [[str(type(k).__name__) + ":" + str(k), canonical(v)]
                for k, v in sorted(value.items(), key=lambda item: (isinstance(item[0], str), item[0]))]
    return value


def semantic_hash(value):
    return digest(json.dumps(canonical(value), ensure_ascii=False, separators=(",", ":")).encode())


def parse_roads(text):
    version = re.search(r'local S = \{ version = ("[^"\n]*") \}', text)
    if not version:
        raise ValueError("missing shipped data version")
    networks = {}
    count = 0
    for line in text.splitlines():
        if ".nodes[" not in line:
            continue
        match = NODE.fullmatch(line)
        if not match:
            raise ValueError("unrecognized road-node assignment")
        instance, zone, node_id = int(match[1]), literal(match[2]), int(match[3])
        node = literal(match[4])
        if not isinstance(node, dict) or not all(isinstance(node.get(k), (int, float)) and not isinstance(node[k], bool) for k in (1, 2)):
            raise ValueError("road node has no finite coordinate pair")
        if not isinstance(node.get("links"), dict) or any(type(k) is not int or v is not True for k, v in node["links"].items()):
            raise ValueError("unexpected road adjacency format")
        nodes = networks.setdefault(instance, {"nodes": {}})["nodes"]
        if node_id in nodes:
            raise ValueError("duplicate node ID in a network")
        normalized = {k: v for k, v in node.items() if k not in (1, 2, 3)}
        normalized.update(wx=node[2], wy=node[1], zone=zone)
        if 3 in node:
            normalized["map"] = node[3]
        nodes[node_id] = normalized
        count += 1
    if not count:
        raise ValueError("no road nodes found")
    # Dangling source links are reported rather than silently pruned.
    return literal(version[1]), networks


def denormalize_node(node):
    raw = {k: v for k, v in node.items() if k not in ("wx", "wy", "map", "zone")}
    raw[1], raw[2] = node["wy"], node["wx"]
    if "map" in node:
        raw[3] = node["map"]
    return raw


def parse_top_anchors(text, networks):
    """Only explicit destination links to stair tops can identify a platform.

    An edited destination position wins over its original place position. A road
    node's coordinate is not a substitute: it can be at the stairs rather than
    where passengers wait on the platform.
    """
    tops = {cont: {n['tower']['top'] for n in network['nodes'].values() if 'tower' in n}
            for cont, network in networks.items()}
    seeds, zones = {}, {}
    for line in text.splitlines():
        base = re.fullmatch(r'S\.base\[(\d+)\]=(.+)', line)
        if base:
            seeds[int(base[1])] = literal(base[2])
        zone = re.fullmatch(r'S\.base\[(\d+)\]\.zones\[(\d+|"map")\]=(.+)', line)
        if zone:
            zones[int(zone[1]), literal(zone[2])] = literal(zone[3])
    records = {}
    for cont, seed in seeds.items():
        for key, entry in seed.get('dest', {}).get('entries', {}).items():
            if isinstance(entry, dict):
                records[cont, key] = {"entry": dict(entry)}
    for (cont, zone), seed in zones.items():
        for key, place in seed.get('places', {}).items():
            records.setdefault((cont, key), {})['place'] = place
        for key, entry in seed.get('dest', {}).items():
            if isinstance(entry, dict):
                record = records.setdefault((cont, key), {})
                record.setdefault('entry', {}).update(entry)
                record['zone'] = zone
    out = {"networks": {}}
    for (cont, key), record in sorted(records.items()):
        entry = record.get('entry', {})
        node = entry.get('node')
        if node not in tops.get(cont, set()):
            continue
        place = record.get('place', {})
        pos = entry.get('pos')
        if pos:
            x, y = pos.get(1), pos.get(2)
        else:
            x, y = place.get('x'), place.get('y')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (x, y)):
            raise ValueError('a top-linked destination has no explicit place position')
        anchor = {'node': node, 'wx': y, 'wy': x, 'key': key,
                  'zone': record.get('zone', networks[cont]['nodes'][node].get('map')),
                  'positionOverride': bool(pos), 'link': entry, 'place': place}
        for field in ('name', 'kind', 'faction', 'to'):
            value = entry.get(field, place.get(field))
            if value is not None:
                anchor[field] = value
        network = out['networks'].setdefault(cont, {})
        network[len(network) + 1] = anchor
    return out


def parse_table_assignment(text, name):
    assignment = re.search(r'\bns\.' + re.escape(name) + r'\s*=\s*', text)
    if not assignment:
        raise ValueError("missing " + name + " data table")
    return literal(text[assignment.end():])


def parse_buildings(text):
    return parse_table_assignment(text, "BuildingData")


def building_record(encoded):
    values = [float(v) for v in encoded.split(",")]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("non-finite building geometry")
    cursor = 0
    def read(n=1):
        nonlocal cursor
        if cursor + n > len(values):
            raise ValueError("truncated building geometry")
        out = values[cursor:cursor+n]
        cursor += n
        return out[0] if n == 1 else out
    uid, x0, y0, x1, y1, pieces, portals = read(7)
    if any(v < 0 or v != int(v) for v in (uid, pieces, portals)) or pieces > 10000 or portals > 100000:
        raise ValueError("invalid building identifier or geometry count")
    out = {"id": int(uid), "bounds": {1: y0, 2: x0, 3: y1, 4: x1}, "pieces": {}, "portals": {}}
    for _ in range(int(pieces)):
        group, indoor, zmin, zmax = read(4)
        if group < 0 or group != int(group) or indoor not in (0, 1):
            raise ValueError("invalid building group")
        polygon = {}
        for i in range(1, 5):
            x, y = read(2)
            polygon[i] = {1: y, 2: x}
        if int(group) in out["pieces"]:
            raise ValueError("duplicate building group")
        out["pieces"][int(group)] = {"indoor": bool(indoor), "zmin": zmin, "zmax": zmax, "polygon": polygon}
    for i in range(1, int(portals) + 1):
        plus, minus, nx, ny, zmin, zmax, count = read(7)
        if plus != int(plus) or minus != int(minus) or count != int(count) or count < 2 or count > 10000:
            raise ValueError("invalid building portal")
        polygon = {}
        for k in range(1, int(count) + 1):
            x, y = read(2)
            polygon[k] = {1: y, 2: x}
        out["portals"][i] = {"from": int(plus), "to": int(minus), "nx": ny, "ny": nx,
                              "zmin": zmin, "zmax": zmax, "polygon": polygon}
    if cursor != len(values):
        raise ValueError("unconsumed building geometry")
    return out


def normalize_buildings(raw):
    networks = {}
    for instance, network in raw.items():
        if instance == "CELL":
            continue
        networks[instance] = {"buildings": {i: building_record(s) for i, s in network["b"].items()},
                              "cells": network["cells"]}
    return {"cell": raw["CELL"], "networks": networks}


def lua(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = re.sub(r'[\x00-\x1f\x7f]', lambda m: "\\%03d" % ord(m[0]), escaped)
        return '"' + escaped + '"'
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("non-finite output")
        return repr(value)
    if isinstance(value, dict):
        return "{" + ",".join("[" + lua(k) + "]=" + lua(v) for k, v in sorted(value.items(), key=lambda item: (isinstance(item[0], str), item[0]))) + "}"
    raise TypeError(type(value))


def road_lua(data):
    lines = ["-- Generated by tools/map-roads/import.py; regenerate rather than edit.",
             "-- Forever Maps road data by sahnetee; used with author permission. See RoadData-NOTICE.md.",
             "local _, ns = ...", "local D = " + lua({k: v for k, v in data.items() if k != "networks"}),
             "ns.GPSRoadData = D", "D.networks = {}"]
    for instance, network in sorted(data["networks"].items()):
        prefix = f"D.networks[{instance}]"
        lines.append(prefix + " = { nodes = {} }")
        for node_id, node in sorted(network["nodes"].items()):
            lines.append(prefix + f".nodes[{node_id}] = " + lua(node))
    return "\n".join(lines) + "\n"


def building_lua(data):
    lines = ["-- Generated by tools/map-roads/import.py; regenerate rather than edit.",
             "-- Associated Forever Maps room geometry; see RoadData-NOTICE.md.",
             "local _, ns = ...", "local D = { cell = " + lua(data["cell"]) + ", networks = {} }", "ns.GPSBuildingData = D"]
    for instance, network in sorted(data["networks"].items()):
        prefix = f"D.networks[{instance}]"
        lines.append(prefix + " = { buildings = {}, cells = " + lua(network["cells"]) + " }")
        for index, building in sorted(network["buildings"].items()):
            lines.append(prefix + f".buildings[{index}] = " + lua(building))
    return "\n".join(lines) + "\n"


def table_lua(data, name):
    return ("-- Generated by tools/map-roads/import.py; regenerate rather than edit.\n"
            "-- Associated Forever Maps road metadata; see RoadData-NOTICE.md.\n"
            "local _, ns = ...\nns." + name + " = " + lua(data) + "\n")


def create_outputs(archive):
    archive = Path(archive)
    with zipfile.ZipFile(archive) as z:
        for member in (ROAD_FILE, BUILDING_FILE, LEVEL_FILE, AREA_FILE):
            if z.getinfo(member).file_size > 16_000_000:
                raise ValueError("source data member is too large")
        road_bytes, building_bytes = z.read(ROAD_FILE), z.read(BUILDING_FILE)
        level_bytes, area_bytes = z.read(LEVEL_FILE), z.read(AREA_FILE)
        toc = z.read("ForeverMaps/ForeverMaps.toc").decode("utf-8-sig")
        if not re.search(r'^## Version:\s*2\.0\.166\s*$', toc, re.M):
            raise ValueError("this importer targets the documented 2.0.166 source archive")
    version, networks = parse_roads(road_bytes.decode("utf-8-sig"))
    anchors = parse_top_anchors(road_bytes.decode("utf-8-sig"), networks)
    anchors.update(version=version, source=SOURCE_URL)
    buildings = normalize_buildings(parse_buildings(building_bytes.decode("utf-8-sig")))
    levels = parse_table_assignment(level_bytes.decode("utf-8-sig"), "AreaLevelData")
    areas = parse_table_assignment(area_bytes.decode("utf-8-sig"), "AreaChunks")
    data = {"schema": 1, "version": version, "source": SOURCE_URL, "networks": networks}
    fields, types, summary = Counter(), Counter(), {}
    for instance, network in sorted(networks.items()):
        nodes = network["nodes"]
        for node in nodes.values():
            fields.update(k for k in node if isinstance(k, str))
            types.update([node.get("type", "road")])
        summary[str(instance)] = {"nodes": len(nodes), "links": sum(len(n["links"]) for n in nodes.values()),
                                  "zones": len(set(n["zone"] for n in nodes.values())),
                                  "unplaced": sum("map" not in n for n in nodes.values()),
                                  "dangling_links": [[i, j] for i, n in nodes.items() for j in n["links"] if j not in nodes]}
    manifest = {"source_url": SOURCE_URL, "source_archive_sha256": digest(archive.read_bytes()),
                "source_members": {ROAD_FILE: digest(road_bytes), BUILDING_FILE: digest(building_bytes),
                                   LEVEL_FILE: digest(level_bytes), AREA_FILE: digest(area_bytes)},
                "source_version": version, "author": AUTHOR, "permission": PERMISSION,
                "roads_sha256": semantic_hash(data), "buildings_sha256": semantic_hash(buildings),
                "levels_sha256": semantic_hash(levels), "areas_sha256": semantic_hash(areas),
                "anchors_sha256": semantic_hash(anchors),
                "top_anchors": {str(i): len(a) for i, a in anchors['networks'].items()},
                "nodes": sum(len(n["nodes"]) for n in networks.values()), "networks": summary,
                "node_fields": dict(sorted(fields.items())), "node_types": dict(sorted(types.items())),
                "buildings": {str(i): len(n["buildings"]) for i, n in buildings["networks"].items()}}
    return {ROOT / "OpenMap/Data/Forever/Roads.lua": road_lua(data),
            ROOT / "OpenMap/Data/Forever/RoadBuildings.lua": building_lua(buildings),
            ROOT / "OpenMap/Data/Forever/RoadLevels.lua": table_lua(levels, "GPSRoadLevels"),
            ROOT / "OpenMap/Data/Forever/RoadAreas.lua": table_lua(areas, "GPSRoadAreas"),
            ROOT / "OpenMap/Data/Forever/RoadAnchors.lua": table_lua(anchors, "GPSRoadAnchors"),
            ROOT / "tools/map-roads/manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"}, data, buildings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs, data, _ = create_outputs(args.archive)
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"stale generated file: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print("wrote", path.relative_to(ROOT))
    print("verified" if args.check else "imported", sum(len(n["nodes"]) for n in data["networks"].values()), "road nodes")


if __name__ == "__main__":
    main()
