"""Literal-only import and lossless audit of the permitted bundled road data.

Run: python -P tools/offline-test/roads_import.py
The optional OPENMAP_ROAD_SOURCE ZIP enables full original-source round-trip checks.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("openmap_roads_import", ROOT / "tools/map-roads/import.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)
DATA = ROOT / "OpenMap/Data/Forever"


def generated_roads():
    out = None
    for line in (DATA / "Roads.lua").read_text().splitlines():
        if line.startswith("local D = "):
            out = importer.literal(line.partition(" = ")[2])
            out["networks"] = {}
        match = re.fullmatch(r'D\.networks\[(\d+)\] = (.+)', line)
        if match:
            out["networks"][int(match[1])] = importer.literal(match[2])
        match = re.fullmatch(r'D\.networks\[(\d+)\]\.nodes\[(\d+)\] = (.+)', line)
        if match:
            out["networks"][int(match[1])]["nodes"][int(match[2])] = importer.literal(match[3])
    return out


def generated_buildings():
    out = None
    for line in (DATA / "RoadBuildings.lua").read_text().splitlines():
        if line.startswith("local D = "):
            out = importer.literal(line.partition(" = ")[2])
        match = re.fullmatch(r'D\.networks\[(\d+)\] = (.+)', line)
        if match:
            out["networks"][int(match[1])] = importer.literal(match[2])
        match = re.fullmatch(r'D\.networks\[(\d+)\]\.buildings\[(\d+)\] = (.+)', line)
        if match:
            out["networks"][int(match[1])]["buildings"][int(match[2])] = importer.literal(match[3])
    return out


def building_numbers(building):
    """Inverse coordinate normalization reconstructs every original geometry number."""
    x0, y0, x1, y1 = building["bounds"][2], building["bounds"][1], building["bounds"][4], building["bounds"][3]
    values = [building["id"], x0, y0, x1, y1, len(building["pieces"]), len(building["portals"])]
    for group, piece in building["pieces"].items():
        values.extend([group, int(piece["indoor"]), piece["zmin"], piece["zmax"]])
        for point in piece["polygon"].values():
            values.extend([point[2], point[1]])
    for portal in building["portals"].values():
        values.extend([portal["from"], portal["to"], portal["ny"], portal["nx"], portal["zmin"], portal["zmax"], len(portal["polygon"])])
        for point in portal["polygon"].values():
            values.extend([point[2], point[1]])
    return values


class LiteralTests(unittest.TestCase):
    def test_nested_tables_numbers_and_strings(self):
        value = importer.literal('{[0]={x=-1.25e2,links={[7]=true},flag=false}, "caf\\195\\169", ["quoted"]=\'it\\\'s\'}')
        self.assertEqual(value, {0: {"x": -125.0, "links": {7: True}, "flag": False}, 1: "café", "quoted": "it's"})
        self.assertEqual(importer.literal(importer.lua(value)), value)

    def test_literal_parser_rejects_executable_and_ambiguous_input(self):
        for text in ('os.execute("bad")', '{x=function() end}', 'setmetatable({}, {})', '{x=1+2}',
                     '{}; print("bad")', '{x=trueX}', '{[1]=1,[1]=2}', '0/0', '1e999', '{x=nil}', '0x12'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                importer.literal(text)

    def test_control_character_strings_round_trip_without_literal_code(self):
        value = {"text": 'tab\tnewline\nNUL\x001quote"slash\\é'}
        serialized = importer.lua(value)
        self.assertNotIn('\x00', serialized)
        self.assertEqual(importer.literal(serialized), value)

    def test_import_preserves_unknown_metadata_and_special_zone_nodes(self):
        text = ('local S = { version = "test" }\n'
                'S.base[0].zones[1].nodes[7]={[1]=12,[2]=-34,[3]=1,links={[8]=true},oneway={[8]=true},layer=1458,newField={future=42},[4]="extra"}\n'
                'S.base[2806].zones["map"].nodes[1]={[1]=1,[2]=2,links={}}\n')
        _, networks = importer.parse_roads(text)
        node = networks[0]["nodes"][7]
        self.assertEqual((node["wx"], node["wy"], node["map"]), (-34, 12, 1))
        self.assertEqual(node["newField"], {"future": 42})
        self.assertEqual(node[4], "extra")
        self.assertEqual(node["oneway"], {8: True})
        self.assertNotIn("map", networks[2806]["nodes"][1])
        self.assertEqual(importer.denormalize_node(node), importer.literal(text.splitlines()[1].partition('=')[2]))

    def test_building_conversion_preserves_height_portals_and_coordinate_order(self):
        encoded = '7,1,2,9,10,1,1,0,1,-5,5,1,2,3,4,5,6,7,8,0,-1,1,0,-4,4,2,2,3,8,9'
        building = importer.building_record(encoded)
        self.assertEqual(building["bounds"], {1: 2.0, 2: 1.0, 3: 10.0, 4: 9.0})
        self.assertEqual(building["pieces"][0]["polygon"][1], {1: 2.0, 2: 1.0})
        self.assertEqual(building["portals"][1]["nx"], 0.0)
        self.assertEqual(building["portals"][1]["ny"], 1.0)
        self.assertEqual(building_numbers(building), [float(x) for x in encoded.split(',')])
        with self.assertRaises(ValueError):
            importer.building_record(encoded + ',999')

    def test_top_anchors_use_explicit_destination_position_then_place_fallback(self):
        text = ('local S = { version = "test" }\n'
                'S.base[0]={zones={},dest={entries={west={node=2}}}}\n'
                'S.base[0].zones[1]={places={west={x=30,y=40,kind="zeppelin"},east={x=50,y=60}},dest={west={pos={10,20}},east={node=2}}}\n'
                'S.base[0].zones[1].nodes[1]={[1]=0,[2]=0,[3]=1,links={[2]=true},tower={top=2}}\n'
                'S.base[0].zones[1].nodes[2]={[1]=999,[2]=999,[3]=1,links={[1]=true}}\n')
        _, networks = importer.parse_roads(text)
        anchors = importer.parse_top_anchors(text, networks)['networks'][0]
        by_key = {a['key']: a for a in anchors.values()}
        self.assertEqual((by_key['west']['wx'], by_key['west']['wy']), (20, 10))
        self.assertTrue(by_key['west']['positionOverride'])
        self.assertEqual((by_key['east']['wx'], by_key['east']['wy']), (60, 50))
        self.assertFalse(by_key['east']['positionOverride'])
        self.assertEqual(by_key['west']['place'], {'x': 30, 'y': 40, 'kind': 'zeppelin'})
        self.assertEqual(by_key['west']['link'], {'node': 2, 'pos': {1: 10, 2: 20}})
        with self.assertRaises(ValueError):
            importer.parse_top_anchors(text.replace('east={x=50,y=60}', 'east={}'), networks)


class BundledAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roads = generated_roads()
        cls.buildings = generated_buildings()
        cls.manifest = json.loads((ROOT / 'tools/map-roads/manifest.json').read_text())

    def test_committed_graph_exact_semantic_hash_and_all_network_counts(self):
        self.assertEqual(importer.semantic_hash(self.roads), self.manifest['roads_sha256'])
        self.assertEqual({i: len(n['nodes']) for i, n in self.roads['networks'].items()},
                         {0: 4467, 1: 4134, 2806: 2, 2991: 341})
        self.assertEqual(sum(len(n['links']) for g in self.roads['networks'].values() for n in g['nodes'].values()), 19416)
        for network in self.roads['networks'].values():
            nodes = network['nodes']
            for node in nodes.values():
                self.assertTrue(set(node['links']).issubset(nodes))

    def test_committed_buildings_exact_semantic_hash_and_valid_cell_references(self):
        self.assertEqual(importer.semantic_hash(self.buildings), self.manifest['buildings_sha256'])
        self.assertEqual({i: len(n['buildings']) for i, n in self.buildings['networks'].items()}, {0: 661, 1: 376, 2991: 24})
        for network in self.buildings['networks'].values():
            for indices in network['cells'].values():
                self.assertTrue(set(indices.values()).issubset(network['buildings']))

    def test_area_and_level_metadata_match_source_audit(self):
        for filename, name, key in [('RoadLevels.lua', 'GPSRoadLevels', 'levels_sha256'),
                                    ('RoadAreas.lua', 'GPSRoadAreas', 'areas_sha256'),
                                    ('RoadAnchors.lua', 'GPSRoadAnchors', 'anchors_sha256')]:
            text = (DATA / filename).read_text()
            value = importer.literal(text.partition('ns.' + name + ' = ')[2])
            self.assertEqual(importer.semantic_hash(value), self.manifest[key])

    def test_source_top_anchor_inventory_is_exact_and_excludes_unlinked_tops(self):
        text = (DATA / 'RoadAnchors.lua').read_text()
        anchors = importer.literal(text.partition('ns.GPSRoadAnchors = ')[2])['networks']
        self.assertEqual(set(anchors), {0})
        self.assertEqual(len(anchors[0]), 4)
        self.assertEqual({a['node'] for a in anchors[0].values()}, {4452, 4454})
        self.assertEqual(sum(a['positionOverride'] for a in anchors[0].values()), 2)
        for anchor in anchors[0].values():
            self.assertEqual(anchor['link']['node'], anchor['node'])
            self.assertIn('place', anchor)

    def test_source_archive_exact_metadata_and_geometry_round_trip(self):
        source = Path(os.environ.get('OPENMAP_ROAD_SOURCE', '/tmp/ForeverMaps-reference.zip'))
        if not source.exists():
            self.skipTest('set OPENMAP_ROAD_SOURCE to verify the original permitted source ZIP')
        outputs, roads, buildings = importer.create_outputs(source)
        for path, expected in outputs.items():
            self.assertEqual(path.read_text(), expected, str(path.relative_to(ROOT)))
        self.assertEqual(roads, self.roads)
        self.assertEqual(buildings, self.buildings)
        with zipfile.ZipFile(source) as z:
            original = z.read(importer.ROAD_FILE).decode('utf-8-sig')
            seen = 0
            for line in original.splitlines():
                match = importer.NODE.fullmatch(line)
                if match:
                    node = self.roads['networks'][int(match[1])]['nodes'][int(match[3])]
                    self.assertEqual(importer.denormalize_node(node), importer.literal(match[4]))
                    seen += 1
            self.assertEqual(seen, 8944)
            raw = importer.parse_buildings(z.read(importer.BUILDING_FILE).decode('utf-8-sig'))
            for instance, network in raw.items():
                if instance == 'CELL':
                    continue
                for i, encoded in network['b'].items():
                    building = self.buildings['networks'][instance]['buildings'][i]
                    # Group insertion order is source order in this direct regenerated object.
                    self.assertEqual(building_numbers(buildings['networks'][instance]['buildings'][i]),
                                     [float(x) for x in encoded.split(',')])
                    self.assertEqual(building, buildings['networks'][instance]['buildings'][i])


if __name__ == '__main__':
    unittest.main()
