# GPS road-network validation

Candidate: **v0.8.10-gps.7**, Forever Maps dataset **2.0.166**, separate addon **OpenMapGPS**
(display name **OpenMap - GPS**).
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
  Existing focused tests also pass. The consolidated local run has 44 successful invocations.
- Nine GPS core and seven original integration tests preserve recording, playback modes,
  partial-save handling, arrival, rerouting and external waypoint ownership.
- Twelve bundled full-addon integration tests pass on Forever (ten plus two source-only skips on
  Retail). They exercise actual road data, recorded extensions, Brill's upper platform, Zephras,
  faction border stops with a persistent HUD, resuming the original target after changing the
  faction option, and ghost routing through otherwise restricted paths.
- Six road-overlay, eight stitched route-view and fourteen native-map tests cover solid green
  line geometry, actual waypoint/destination nodes, clipping, view caching, player-head movement,
  completed segment removal and reuse of drawing regions. Both route renderers retain all bends
  for valid routes within a 25,000-point budget; the optional network views still use at most
  800 markers on each canvas. Unprojectable points and continent gaps do not become shortcuts.
- Eight package-transform and sixteen coexistence/settings tests check both clients. The original and
  GPS addon load in the same Lua runtime without sharing saved variables, API, commands, frames,
  bindings or message prefixes. Original-first loading leaves GPS dormant. Explicit Group metadata
  gives GPS its own AddOn List entry. Quick-switch commands are absent and do not change enable
  state or reload; manual selection is through AddOns. Only settings import uses an internal handoff.
- Six settings-import cases cover the active-GPS-to-original-to-GPS reload round trip, deep-copy
  isolation, supported preference fields, preserving GPS recordings/options/user data, missing
  original/combat/save failures and consuming failed requests without a login loop. Shared
  preferences are copied only after the user explicitly invokes `/omgps sync settings`.
- A live gps.3 report exposed that the switcher used a character name and omitted saving addon
  enable changes. gps.4 uses the GUID and saves before reloading, matching the Forever AddOns UI.
  Regression tests model pending/committed GUID-specific states and rebuild the Lua runtime from
  the committed selection to check GPS activation and switching back to original standby.
- Eighteen press tests and thirty controller-waypoint/input tests cover Alt-click GPS, right-click
  menu selection, independent right-drag suppression, ordinary zoom, controller zoom buttons and
  drawing/pin/dungeon tools. Fifteen context-menu tests cover captured target coordinates, the
  three actions, stale callback revocation, Escape/outside/owner-hide behavior, native Zephras
  input and note-only pin creation without replacing an active waypoint.
- The context-menu default is tested through real Core.InitDB on fresh and old profiles,
  including one-time adoption, retained existing migrations/data and later Zoom out choices.
- Python tools compile; Lua lint passes. New output is generated through its importer, changelog
  builder or locale builder. The package builder reruns the routing and coexistence checks.
- New GPS/context-menu strings have translations in each of the ten supported locales. Placeholder and
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
the live HUD or new road overlay. Before/after drawing previews were instead generated from the
actual stitched/native Lua drawing commands on a labeled synthetic grid and visually inspected;
they establish line/node geometry and styling, not terrain or live game rendering. No rendered
HUD or in-game screenshot is claimed.

The imported network has the coverage and limits of its source beta. Endpoint approaches are
explicit off-network connectors, not terrain-verified roads. An uncertain overlapping floor is
reported rather than guessed. Source-compatible route costs and topology do not establish that
every connector crosses walkable terrain. Multi-continent flight/boat itineraries, the complete
reference road editor and reference public API are outside this walking-network pass.

See [gps-decisions.md](gps-decisions.md) for decisions, supporting evidence and alternatives.
