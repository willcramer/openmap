# GPS road-network validation

Candidate: **v0.8.10-gps.4**, Forever Maps dataset **2.0.166**, separate addon **OpenMapGPS**.
This is an offline-verified test build. No live game-client verification is claimed.

## Data and routing

- The restricted importer preserves all 8,944 nodes and 19,416 adjacency entries, every supplied
  node metadata field, 1,061 buildings with room polygons/height intervals/portals, level tables,
  the Zephras area grid and four explicitly linked upper-platform anchors. Eleven import tests
  pass, including an exact round trip against the permitted source archive. The manifest records
  source/member hashes and semantic output hashes. No source archive or reference code is bundled.
- Twenty-two required router tests cover explicit topology, direction, room/layer compatibility,
  faction and level constraints, off-road costs, segment attachment, stair winding/exits, elevator
  flags, recorded extensions and cache invalidation. Nearby roads never become new junctions.
- The optional differential audit runs the separately installed reference Graph in an isolated
  Lua state without filesystem, OS, Python or network access. It checks all 19,416 adjacency
  directions, 24 staircase stop windings, room/layer entry cases, 100 known-node journeys, 100
  offset-start journeys, 100 map-pin destinations with both endpoints offset, and 100 journeys
  using source product preferences. All 400 sampled route
  costs agree within relative tolerance 1e-8. Boundary fixtures also compare final connectors at
  199, 201, 600, 1,000 and 1,500 yards and the reference's named-destination auto-link threshold.
  OpenMap coordinate destinations use map-pin semantics. The audit prints reference version and
  implementation hashes.
  This evidence covers those contracts; it is not proof of every possible journey.
  A deliberate difference protects the last partial segment against reversing a one-way drop,
  which the reference can allow on its final pin approach. See the decision record.
- Seventeen room tests and twelve full-addon vertical tests cover real building geometry,
  249,563 same-building floor pairs, stairs in both directions, intermediate exits, first movement
  without a pause, floor-safe arrival, idle room observation, missed road corners, elevator flags
  without player height, and the Ruins above Undercity separately from its underground map.

## OpenMap integration and installation

- All six loader modes, navigation and controller-waypoint checks pass for Forever and Retail.
  Existing focused tests also pass. The consolidated local run has 42 successful invocations.
- Nine GPS core and seven original integration tests preserve recording, playback modes,
  partial-save handling, arrival, rerouting and external waypoint ownership.
- Twelve bundled full-addon integration tests pass on Forever (ten plus two source-only skips on
  Retail). They exercise actual road data, recorded extensions, Brill's upper platform, Zephras,
  faction border stops with a persistent HUD, resuming the original target after changing the
  faction option, and ghost routing through otherwise restricted paths.
- Six road-overlay and nine native-map tests cover bounded drawing pools, clipping, view caching,
  controller geometry, map visibility and coexistence with other map content. Active native routes
  use at most 300 dots; optional network views use at most 800 markers on each canvas.
- Seven package-transform and ten coexistence/switch tests check both clients. The original and
  GPS addon load in the same Lua runtime without sharing saved variables, API, commands, frames,
  bindings or message prefixes. Original-first loading leaves GPS dormant. Switching changes
  character enable state and reloads; combat and missing-original cases leave the working addon on.
- A live gps.3 report exposed that the switcher used a character name and omitted saving addon
  enable changes. gps.4 uses the GUID and saves before reloading, matching the Forever AddOns UI.
  Regression tests model pending/committed GUID-specific states and rebuild the Lua runtime from
  the committed selection to check GPS activation and switching back to original standby.
- Seven additional mouse-input cases exercise the complete controller view's actual mouse scripts:
  Alt-click at the mouse rather than controller cursor, drag suppression, ordinary zoom, and
  drawing/pin/dungeon tools. All 24 controller-waypoint/input tests pass.
- Python tools compile; Lua lint passes. New output is generated through its importer, changelog
  builder or locale builder. The package builder reruns the routing and coexistence checks.
- All 94 GPS strings have translations in each of the ten supported locales. Placeholder and
  command checks report zero problems. Six pre-existing unrelated strings remain untranslated.
  Standby/bootstrap messages can fall back to English before active locale tables are loaded.

The reference-dependent checks are optional in public CI because the reference addon is not
redistributed as a test dependency. To reproduce locally, set `OPENMAP_ROAD_SOURCE` to the permitted
2.0.166 ZIP and `FOREVER_MAPS_REFERENCE` to a separately installed reference addon, then run
`roads_import.py` and `gps_road_parity.py` under `tools/offline-test/` with Python and lupa.

## Still requires the game

The live HUD's arrow alignment, UI-scale layout, actual protected/secret API behavior, controller
interaction, performance and terrain walkability need the acceptance checks in [gps.md](gps.md).
The stock map-preview renderer needs the game's DB2 tables and texture cache and does not render
the live HUD or new road overlay; no rendered HUD or in-game screenshot is claimed.

The imported network has the coverage and limits of its source beta. Endpoint approaches are
explicit off-network connectors, not terrain-verified roads. An uncertain overlapping floor is
reported rather than guessed. Source-compatible route costs and topology do not establish that
every connector crosses walkable terrain. Multi-continent flight/boat itineraries, the complete
reference road editor and reference public API are outside this walking-network pass.

See [gps-decisions.md](gps-decisions.md) for decisions, supporting evidence and alternatives.
