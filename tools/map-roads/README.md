# Bundled roads import

Run `python -P tools/map-roads/import.py ForeverMaps.zip` to import the permitted
Forever Maps 2.0.166 dataset, or add `--check` to verify the generated files.

The importer never executes downloaded Lua. Its literal-only grammar reads road-node
assignments and the associated building/area tables; routing code, NPC catalogues,
shops and art are not imported. The road data remains attributed to sahnetee and is
used with author permission confirmed by the fork maintainer. It is not relicensed
under MIT; see `OpenMap/Data/Forever/RoadData-NOTICE.md`.

Generated files:

- `Data/Forever/Roads.lua`: `ns.GPSRoadData`, with 8,944 nodes across Eastern Kingdoms,
  Kalimdor, Zephras Isle and two isolated mapless nodes. Every adjacency and node
  metadata field is retained. Coordinates become `wx = source[2]`, `wy = source[1]`,
  `map = source[3]`; `zone` retains the original source-zone key. Metadata such as
  `oneway`, `nostart`, `layer`, `piece`, `tower`, `elevator` and unknown future fields
  is preserved rather than inferred or discarded.
- `Data/Forever/RoadBuildings.lua`: `ns.GPSBuildingData`, with 1,061 buildings and their
  pieces, height ranges and doorway polygons. Source HBD `(x,y)` coordinates are
  converted once to `(wx=y,wy=x)`. Building `bounds` are `{minWX,minWY,maxWX,maxWY}`;
  pieces are keyed by group and contain `indoor`, `zmin`, `zmax` and `polygon` points.
  Portal normals are swapped the same way. The original spatial cells remain keyed
  by `(floor(wy/cell)+128)*256+floor(wx/cell)+128`, where `cell=256` yards.
- `Data/Forever/RoadLevels.lua`: `ns.GPSRoadLevels`, retaining the source `areas`,
  `zones` and `dungeons` level tables.
- `Data/Forever/RoadAreas.lua`: `ns.GPSRoadAreas`, retaining the source Zephras-only
  area grid and its character lookup. The source has no area grid for the two base
  continents.
- `Data/Forever/RoadAnchors.lua`: `ns.GPSRoadAnchors`, retaining the four destinations
  explicitly linked to stair tops (Brill and Grom'gol). A destination's explicit
  position override wins over its recorded place coordinates; a top node's own
  coordinates are never substituted. These passenger-platform positions let the
  router recognize an existing platform without walking the stairs again. Other
  stair tops have no such linked destinations in this source version.
- `manifest.json`: source archive/member hashes, source version, semantic hashes of
  all five outputs, coverage counts and schema inventory. Source links are not pruned.

Run `python -P tools/offline-test/roads_import.py` for parser and audit checks. The
committed dataset is checked against semantic hashes, including all links and cell
references. Set `OPENMAP_ROAD_SOURCE` to the original permitted ZIP for exact all-node
metadata and all-building geometry round trips. No input ZIP is committed.
