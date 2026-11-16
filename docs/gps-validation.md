# GPS test build validation — 2026-11-16

Base: upstream OpenMap `9ebb7d3` (v0.8.9). Custom package: `v0.8.10-gps.1`.

## Passed locally

- Lint: zero problems; generated changelog and locale consistency checks passed.
- Forever and Retail: all six loader modes (`plain`, `combat`, `secret`, `pad`, `padmap`,
  `padview`), navigation and controller-waypoint tests.
- Forever: all applicable existing focused tests (bosses, brightness, caves, combat, exploration,
  sea chart, friends, instances, controller friends, player, press, Questie and quests).
- GPS core: nine tests, run on both clients. Recorded-road detours and junctions, arrival,
  reverse/loop/pingpong playback, gap detection and explicit partial save, recording cancellation,
  rerouting, secret coordinates, taxi/position loss, and external waypoint ownership.
- GPS integration: seven tests, run on both clients. Full toc and Init boot, slash commands,
  map-closed HUD/arrival, mixed-case route names, external waypoint takeover, missing/secret
  positions, idempotent initialization and HUD recording discard.
- Map click tests: ten passed, including Alt-click GPS and Alt-drag suppression.
- Python tools compile successfully (an existing invalid-escape warning in `caves.py` is unrelated).

The consolidated local run contained 32 successful check invocations. GPS core/integration were
also run separately with `OPENMAP_CLIENT=retail`. Packaging reruns lint, the principal loader
scenarios and the GPS tests.

## Still requires the game

This environment has no running WoW Forever client. The stock terrain renderer needs the game's
DB2 tables and texture cache and does not render the new live HUD; no visual render of the HUD is
claimed. Actual arrow orientation, protected API behavior, layout at your UI scale, frame rate on
a large recorded network, terrain correctness and controller interaction remain in-game checks.
Follow the acceptance steps in [gps.md](gps.md).

This build has no preloaded walking-road graph and no multi-transport itinerary planner.
Unknown routes use direct guidance. All source changes are independent of Forever Maps' code.
