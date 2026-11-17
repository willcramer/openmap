# GPS road-network validation

Candidate: **v0.8.10-gps.13**, Forever Maps dataset **2.0.166**, separate addon **OpenMapGPS**
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
  Existing focused tests also pass. The consolidated local run has 50 successful invocations,
  including upstream's new performance and flight-discovery suites.
- Official OpenMap v0.8.10 (`0f4d2e4b6fe82b9032618fd3b824eaaa5b36dcef`) is merged into the
  GPS branch. Changelog sections retain both custom history and official release notes; locale
  sources were merged by English key and regenerated, with no competing translation changes.
  GPS guidance, road dots and node markers all participate in the shared instance-hide filter,
  including layers created after the filter first changes.
- Nine GPS core and thirteen full-addon integration tests preserve recording, playback modes,
  partial-save handling, arrival, rerouting and external waypoint ownership.
- Tracker visibility tests exercise the actual Hide button, commands and full options table,
  confirming that TomTom waypoints, route drawing, recorded-road rerouting, arrival and recording
  continue while hidden. The preference persists through profile initialization and later routes;
  Stop still stops. A before/after out-of-game layout preview used actual Lua control positions.
- The map menu's actual GPS navigation action opens controls that are tested through their real
  button callbacks without slash commands: road/tracker toggles, named recording, save/partial
  save/discard, saved-route selection, playback modes, following, stopping and confirmed deletion.
  Deletion captures the chosen route so later edits cannot delete a different recording.
- Ten manual-road tests cover placed nodes, explicit bidirectional links, atomic add-and-connect,
  limits, invalid inputs, same-floor/continent validation, one-way protection, no proximity joins,
  deletion cleanup, source immutability, profile/reload persistence, active-route replanning and
  hidden-tracker preferences. Manual-only routing works with no supplied dataset and with bundled
  roads disabled. The new suite is required by CI and the package builder.
- Twelve bundled full-addon integration tests pass on Forever (ten plus two source-only skips on
  Retail). They exercise actual road data, recorded extensions, Brill's upper platform, Zephras,
  faction border stops with a persistent HUD, resuming the original target after changing the
  faction option, and ghost routing through otherwise restricted paths.
- Fourteen road-overlay, eight stitched route-view and twenty-one native-map tests cover solid green
  line geometry, actual waypoint/destination nodes, clipping, view caching, player-head movement,
  completed segment removal and reuse of drawing regions. Both route renderers retain all bends
  for valid routes within a 25,000-point budget. Optional network views add exact bundled-node
  and saved-sample markers, with separate budgets of 500 nodes and 800 road-link dots per canvas.
  View caching invalidates after save/delete or profile replacement. Isolated and special nodes
  remain visible without unsafe straight links. Unprojectable points and continent gaps do not
  become shortcuts. Manual nodes/links are cyan; the selected node is white and retains a slot in
  the bounded marker pool even in crowded views. Selection and manual-data revisions invalidate
  the cache on world/controller/native views.
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
- Twenty press tests and thirty-two controller-waypoint/input tests cover Alt-click GPS, right-click
  menu selection, independent right-drag suppression, ordinary zoom, controller zoom buttons and
  drawing/pin/dungeon tools. Twenty-one context-menu tests cover captured target coordinates, the
  three actions, stale callback revocation, Escape/outside/owner-hide behavior, native Zephras
  input and note-only pin creation without replacing an active waypoint. Editor actions capture
  selection and target references, protect delete confirmation across profile changes and restore
  normal mouse zoom when editing ends. A full-TOC menu/model/router test builds a connected path
  through clicks without moving the player and confirms that GPS uses its manually placed bends.
- The context-menu default is tested through real Core.InitDB on fresh and old profiles,
  including one-time adoption, retained existing migrations/data and later Zoom out choices.
- Python tools compile; Lua lint passes. New output is generated through its importer, changelog
  builder or locale builder. The package builder reruns the routing and coexistence checks.
- Installation fixtures verify the one new editor module is added safely, a failure after its
  addition rolls back both new and replaced files including timestamps, concurrent GPS edits
  refuse overwrites, and original OpenMap remains unchanged.
- The upstream merge adds 223 Portuguese zone textures in one new directory, with no removed
  files. Their decoding and upstream credits are verified. The installer validates the exact
  addition manifest and supports rolling back the added files and directory along with replaced
  files and existing parent-directory timestamps.
- New GPS/context-menu strings have translations in each of the ten supported locales. Placeholder and
  command checks report zero problems. Six pre-existing unrelated strings remain untranslated.
  Standby/bootstrap messages can fall back to English before active locale tables are loaded.

The reference-dependent checks are optional in public CI because the reference addon is not
redistributed as a test dependency. To reproduce locally, set `OPENMAP_ROAD_SOURCE` to the permitted
2.0.166 ZIP and `FOREVER_MAPS_REFERENCE` to a separately installed reference addon, then run
`roads_import.py` and `gps_road_parity.py` under `tools/offline-test/` with Python and lupa.

## Automatic-replanning performance

The previous build synchronously searched the network from its guidance update after moving
off-route, with a five-second minimum cooldown. The new build keeps that cooldown and the movement
thresholds, but resumes automatic planning and route drawing every frame within a shared 1 ms
target budget. Bounded checkpoints also cover cold graph construction, recorded-road projection,
route reconstruction and recycling old drawing regions. Hidden staging layers prevent partial
green lines from becoming visible. Closed maps defer route geometry while guidance continues.

- Seven planner tests cover cooperative work, destination attachment reuse, cache invalidation
  and route parity. Scheduler tests cover frame budgets, fallback operation limits, atomic route
  publication, waypoint ownership, cancellation and recorded-sample cache invalidation. Three
  drawing-pool tests verify interrupted cleanup cannot recycle a region twice. Native rendering
  tests additionally cover staged publication, cancellation and map-host changes.
- Independent Lua 5.1 measurements use the committed gps.12 baseline and four fixed node pairs.
  Median raw route CPU time across 15 samples per pair changes from 52.0–63.5 ms to 32.9–44.2 ms
  without destination reuse, or 21.8–32.9 ms with it. Final costs and route-point counts match.
  A further 100 moving-start queries to reused destinations match baseline costs and reasons.
- A full-addon OnUpdate harness measures guidance, planning, publication and deferred stitched
  drawing through completion. Across the four routes, maximum update CPU time is 1.07–1.68 ms
  with the map closed. With the stitched map open and a simulated 10 microseconds per drawing API
  call, maxima are 1.07–1.13 ms, versus 70.3–112.2 ms in a single update in the old build using
  the same model. Planning and drawing complete in 29–59 frames at simulated 120 Hz. A native
  Zephras journey drops from 9.41 ms to a 1.05 ms peak, completing in five frames. Completed
  staged geometry matches direct drawing on both map types.

These are offline CPU measurements with mocked client APIs; the simulated drawing cost is not a
measurement of the game's renderer. They do not establish a live FPS result or a hard 1 ms ceiling.
Individual API calls, garbage collection and guidance updates can overrun the target. Explicitly
starting a new journey or changing routing options still plans synchronously. The recurring
automatic off-route calculation is the scope of this change. Live acceptance must include moving
off-route with the map closed and open, the tracker hidden, and TomTom enabled.

## Still requires the game

The GPS menu/shortcut icon references client FileDataID 6383475 directly. Its 64×64 BLP was
read and decoded from the installed Forever 1.60.1.70938 client and visually inspected. No
additional texture is bundled. Live UI appearance remains part of the acceptance check.

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
every connector crosses walkable terrain. Multi-continent flight/boat itineraries, advanced
travel/floor-metadata editing and the reference public API are outside this walking-network pass.

See [gps-decisions.md](gps-decisions.md) for decisions, supporting evidence and alternatives.
