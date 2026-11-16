# Bundled road network decisions

## Source and permission

- Reference release: Forever Maps 2.0.166, file9632734, supplied road network and associated
  floor/room data. On 2026-11-16 the fork maintainer confirmed author permission to redistribute
  it in this custom build. The data has a separate notice; it is not presented as MIT-licensed.
- Import data as literals with a restricted parser. Never execute the downloaded addon to extract
  its data. Keep hashes and exact counts, and test metadata/connectivity preservation.
- Implement planning and guidance independently. Copying the reference routing implementation
  is unnecessary and outside the stated data permission.

## Topology and coordinates

- Preserve all 8,944 source nodes, including two isolated dungeon-map entries. Preserve exact
  supplied adjacency and one-way annotations. Do not invent junctions between nearby roads.
- Source positions use worldY then worldX; normalized output explicitly names `wx` and `wy`.
  Display conversion uses the client's map APIs. Zephras Isle uses its native map outside the
  stitched Azeroth canvas.
- Attach endpoints to nearby road segments while preserving direction and room/floor context.
  A straight line between nearby coordinates is not evidence of a walkable connection.
- Preserve the reference's endpoint-entry policy: nearby alternatives within its entry slack,
  per-component entry points, and twice-weighted off-road approaches. These are explicitly marked
  connectors, not new graph links. Keeping only one nearest segment changed valid reference routes.
- Treat OpenMap's coordinate destinations as reference map pins: leave the road at its nearest
  compatible projection and charge the final walk with the source's off-road weighting. Do not
  cap the tail at an invented 600 yards. The reference's separate named-destination 200-yard
  auto-link classification is audited but does not redefine OpenMap's coordinate pins.
- Treat OpenMap coordinates, pins and search selections as reference map-pin destinations: choose
  the nearest eligible road projection and charge the final off-road approach with the same
  weighting as entry. Do not impose an invented 600-yard target cutoff. The reference's separate
  200-yard automatic named-place classification does not turn an OpenMap coordinate into a named
  entry from its catalog.
- Retain direction checks on the final partial road segment. The reference can approach a pin by
  reversing a one-way drop; reproducing that defect would contradict the supplied traversal flag.
  A regression covers the protected partial segment. Exact reproduction of that case was rejected;
  this deliberate difference is disclosed alongside the parity audit.
- Keep `nostart`, faction, swimming, stairs, elevators, indoor layers and room-piece metadata.
  Coordinate proximity alone must not advance between overlapping floors.
- Preserve the reference product's off-road factors: Shortest = 1, Avoid = 4, Only when needed =
  1000; high-level avoidance = 1000. Never is an explicit exclusion. For living players, plan the
  route with faction warnings, then stop guidance at its last safe point before an enemy road.
  Allow enemy roads resumes the original destination with warnings. Ghost routing removes these
  restrictions and penalties. Hard-blocking every enemy node was rejected because it could
  replace the reference's useful safe prefix with a different itinerary or no route at all.

## Vertical navigation

- Road nodes generally have no height. Preserve the floor/room graph and infer live membership
  from imported geometry, portal crossings, WMO-change timing and recent movement. Optional plain
  player height is evidence, not a replacement for that topology. Observe rooms while GPS is idle.
- Room footprints are WMO group bounding polygons and may overlap. Keep uncertainty rather than
  inventing a floor. Reset continuity across loading, teleports, long position gaps and bounds exits.
- Multiple room boxes on the same known floor may share an endpoint without choosing one room.
  Require compatible layers and indoor state and a common known height interval across every
  candidate. Reject unresolved different floors or missing-height ambiguity.
- Undercity's map covers the Ruins above it. A numeric city map alone is not live-floor evidence:
  compare the localized Ruins area name with the current subzone, and keep surface and underground
  separate. Same-building pieces with less than 0.5 yards of vertical overlap are other floors;
  different adjacent rooms on one floor are not automatically other floors.
- Expand spiral stairs from the foot, top and intermediate exits in winding order. The configured
  winding level and the stop's placed bearing jointly determine its effective turn. Follow the
  resulting path using unwrapped angular progress, including the very first movement interval.
  A 15-yard arrival radius must not consume a small staircase without climbing it.
- Known platform entry uses the four source destination anchors at Brill and Grom'gol, within the
  source's 15-yard threshold. Preserve explicit position overrides; do not substitute stair-node
  coordinates or invent platform anchors for the other towers.
- Rejoin missed ordinary road corners only on a confirmed compatible floor. Never scan across
  stairs, elevators or one-way drops. Elevators are independent flags and may coexist with faction
  restrictions. One-way drops suppress reverse traversal even though stored adjacency is symmetric.

## Integration and parity

- Keep the isolated `OpenMapGPS` addon identity and standby/switching behavior from gps.2.
  Original OpenMap settings, commands and named frames stay separate.
- Continue supporting existing pins, search, recorded routes and map-closed guidance. Imported
  data is read-only; user recordings remain separately saved.
- Supply GPS translations for all ten supported locales. The tiny standby bootstrap can still
  fall back to English before the active addon's locale tables load; it does not load the original
  addon's settings to translate switch messages.
- Distinguish missing road coverage from a blocked or ambiguous route. Do not conceal a topology
  or floor failure with an apparently valid straight-line road route.
- Check data parity separately from behavior parity. Exact source counts alone do not establish
  correct one-way/faction/floor/stair behavior. Keep the goal active until the road functionality
  is verified against source-backed cases; report any unverified behavior explicitly.
