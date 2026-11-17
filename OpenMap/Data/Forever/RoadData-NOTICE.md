# Forever Maps road network data

The generated `Roads.lua`, `RoadBuildings.lua`, `RoadAnchors.lua` and associated road-level metadata originate
from **Forever Maps — World Map & GPS Navigation**, by **sahnetee**, version **2.0.166**:

https://www.curseforge.com/wow/addons/forever-maps-world-map-gps-navigation/files/9632734

The fork maintainer confirmed on 2026-11-16 that the author has given permission to
redistribute this road network in this custom OpenMap GPS build. The source project's
public listing is All Rights Reserved. These data files are distributed under that
permission; this repository's MIT licence does **not** relicense them or grant broader
redistribution rights. Obtain the author's permission before using them in another project.

The data includes the supplied roads, connectivity, traversal flags, room/floor geometry
and related level metadata. The import tool preserves source provenance and hashes in
`tools/map-roads/manifest.json`. Regenerate through that tool rather than editing the
generated files.

OpenMap GPS's importer, planner, room resolver and integration code are independently
implemented and covered by the repository's MIT licence. No Forever Maps routing code
or artwork is included.
