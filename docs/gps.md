# Custom GPS test build

This build adds GPS guidance to OpenMap: an arrow and distance while the map is closed,
a route on the map, automatic progress through turns, and a recorder for roads and repeatable
walking routes. It is an independent implementation inspired by the publicly described
[Forever Maps GPS feature](https://www.curseforge.com/wow/addons/forever-maps-world-map-gps-navigation).
The Forever package includes the 2.0.166 road network and associated room/floor metadata with
author permission. The importer and routing code are independently implemented; no Forever Maps
routing implementation or art is included. See the [data notice](../OpenMap/Data/Forever/RoadData-NOTICE.md).

## Install

Use **OpenMapGPS-v0.8.10-gps.5-forever.zip**, the separate-addon build. The older gps.1 ZIP
used the original addon's folder and should not be used for a side-by-side install.
If you already installed gps.1 into `OpenMap`, reinstall the official OpenMap there first.

1. Quit WoW. Leave your existing `Interface/AddOns/OpenMap` folder in place.
2. Extract the Forever GPS ZIP into `Interface/AddOns`. The new folder must be
   `Interface/AddOns/OpenMapGPS`, containing `OpenMapGPS.toc`.
3. Enable **OpenMap GPS Test** in the AddOns list. You can leave the original enabled too:
   the GPS addon stays in standby and the original controls the map.
4. Enter `/omgps use gps` to test the GPS build. It disables the original for your current
   character and reloads the UI. `/omgps use original` enables the original and reloads again;
   GPS stays enabled in standby so you can switch back with the same command.

Switch outside combat. You can always switch manually through the AddOns list and reload.
If updating from gps.3, first `/reload` to load the corrected switcher, then run `/omgps use gps`.
If a GPS command says Original OpenMap is active, GPS is in standby and its map controls are not
running. The gps.3 switcher could reload without actually switching the current character;
gps.4 saves the GUID-specific selection before reloading.
The GPS build has independent `OpenMapGPSDB` and `OpenMapGPSCharDB` saved variables, its own
named frames, key bindings, addon-message prefixes and public API (`OpenMapGPSAPI`). It does not
read, copy or overwrite the original's settings. Its commands are `/openmapgps` and `/omgps`;
the original retains `/openmap` and `/omap`.

For example, `/omgps gps` opens the GPS controls, `/omgps gps record Elwynn road` starts a
recording, and `/omgps gps save` saves it. `/console scriptErrors 1` enables error reports.
TomTom is optional. The test build retains OpenMap's normal map and pins.

### Copy the original's preferences

After updating, `/reload` once, then run `/omgps sync settings` outside combat. GPS switches to
original OpenMap, copies shared display/window/filter/control preferences from its live profile,
and switches back to GPS. This involves two automatic UI reloads. The completion message confirms
when the copy has actually happened; installing the update alone does not copy settings.

The original's profile is read, not edited. GPS routing options, recorded trails, HUD positions,
pins and drawings are preserved. Temporary navigation state, performance reports, cached flight
data and other addon-specific records are not imported. This is a one-time copy when requested,
not a shared saved-variable store or automatic ongoing synchronization.

## First navigation

- Alt-left-click a destination on the map.
- Shift-click a result in OpenMap's search to navigate to it (plain click still moves the view).
- Open one of your map pins and press GPS.
- Or set a waypoint normally and use the GPS controls to navigate to it.

Ordinary right-click retains OpenMap's zoom-out action. This build does not have a right-click
Go Here context menu. Alt-left-click empty terrain; click an existing OpenMap pin normally and
press GPS in its card. Controller-view mouse input supports the same Alt-click shortcut.

The arrow continues updating with the map closed. Stop GPS from its controls or with
`/omgps gps stop`. The player still walks, boards vessels and operates the game normally.

While navigating, a solid green line connects your current position to the remaining waypoint
nodes. The destination has a larger marker. Passed sections disappear as guidance advances;
rerouting replaces the remaining line. Line width and node size stay steady while zooming.
This drawing works on the stitched map and controller view and on Zephras's native map.

## Record a road or farming route

Start a recording with `/omgps gps record Elwynn road`, walk the road, then use
`/omgps gps save`. Record another road starting at an existing junction to expand your network.
Routes are stored in OpenMap's account saved variables, while active guidance is temporary.
Save before reloading or logging out: an unfinished recording is temporary too. Playback must
start within 100 yards of its first point (the last point for reverse playback). The road planner
attaches your position and destination to nearby samples within 100 yards; those short connectors
are direct segments whose terrain is not checked. Junctions merge within 10 yards, so avoid
recording overlapping floors as separate roads.

Commands:

| Command | Action |
| --- | --- |
| `/omgps gps` | Open controls |
| `/omgps gps waypoint` | Guide to the current waypoint |
| `/omgps gps go 1429 42 65` | Guide to normalized map coordinates given as percentages |
| `/omgps gps record Elwynn road` | Start recording |
| `/omgps gps save` | Save recording |
| `/omgps gps savepartial` | Explicitly save the recorded section before a detected gap |
| `/omgps gps cancelrecord` | Discard unfinished recording |
| `/omgps gps follow reverse Elwynn road` | Replay; modes: `once`, `reverse`, `loop`, `pingpong` |
| `/omgps gps list` | List saved route names |
| `/omgps gps delete Elwynn road` | Delete saved route |
| `/omgps gps stop` | Stop navigation; recording is separate |
| `/omgps gps status` | Print current status |
| `/omgps gps roads on` | Show the bundled road network on the stitched map (`off` hides it) |

Flights or teleports interrupt road recording. The controls offer Save partial or Discard recording
rather than adding the jump as a walkable road. Loops must end within 100 yards of their start;
record the complete return path to avoid a direct closing segment across unknown terrain.

The GPS controls list saved routes and offer playback modes. Saved walking trails also supply
the road graph for destination routing. Only record paths you intend to walk; map points alone
cannot identify cliffs, walls, locked doors or a path's vertical level.

## Bundled roads and coverage

The Forever package starts with **8,944 supplied nodes**: 4,467 in the Eastern Kingdoms, 4,134 in
Kalimdor, 341 on Zephras Isle, and two isolated entries without a map assignment. All 19,416 adjacency
entries are retained, together with one-way directions, faction types, swimming, no-start flags,
staircases, intermediate landings, elevators, room identities and layers. The associated geometry
contains 1,061 buildings with room footprints, height intervals and portals.

Use bundled roads is on by default. The map menu's Road network switch shows the network; Options
provides Use bundled roads, Allow enemy roads, Off-road paths and Off-road paths above your level.
Off-road choices are Shortest, Avoid, Only when needed and Never; level choices are Warn, Avoid and
Never. Avoid applies a cost penalty; it does not promise that the route avoids every such path.
Changing routing preferences replans the active destination. User recordings can extend the
supplied graph without changing its source data. Faction restrictions and floor identities remain
separate.

Living players stop at the last safe point before an enemy-faction road unless Allow enemy roads
is enabled. The HUD explains the stop; enabling the option resumes the requested destination and
warns along the enemy section. Ghost routing ignores faction and level restrictions and off-road
penalties, matching the reference's walking-network policy.

Directions follow stairs by angular progress and retain intermediate exits; elevators and swimming
have their own instructions. Live room inference uses room bounds, portal crossings, recent movement
and WMO change events. It resets after loading or teleports and keeps unresolved floors ambiguous.
The Ruins above Undercity are distinguished from the underground city by subzone evidence.

Zephras routes use its native maps (2521 and 2665), with the GPS route drawn on their own canvas.
Set a waypoint there and choose Guide to waypoint, or use the `go` command. Stitched-map Alt-click
continues working across the two main continents. Native-map gestures keep the game's behavior.

Missing coverage can fall back to explicitly labeled direct guidance. A blocked, disconnected or
ambiguous floor route is reported instead of silently drawing a road through it. Short approaches
to the network are off-road connectors; the data does not establish that every such approach is
walkable. The source network itself is still beta and does not cover every path in the game.

This goal concerns the supplied walking network. Multi-continent flight/boat itinerary planning,
the reference addon's complete road editor and its full public API are not part of this pass.
See [parity and validation](gps-validation.md) for verified cases and remaining live checks.

Position reads can be unavailable or secret in instances or combat. Guidance waits rather than
doing arithmetic on those values. Setting a different waypoint lets another addon take over;
GPS must not replace that addon's destination.

## In-game acceptance test

1. Navigate to a nearby pin on level ground; close the map, turn in place and check the arrow.
2. Arrive and confirm guidance completes. Start again, stop, and confirm the GPS waypoint clears.
3. Record an L-shaped road. Save it, walk to its start, and navigate to its far end. Confirm the
   route follows the recorded bend and advances through it.
4. Replay a saved route in each mode. Check loop and ping-pong only on a path with a walkable
   return. Reload and confirm saved routes remain.
5. While navigating, set another waypoint. Confirm GPS yields and leaves the new waypoint intact.
6. Enter combat or an instance and check for Lua errors and stale guidance. Return outdoors.
7. Repeat with TomTom if installed and with the controller view if used.
8. Enable Road network and plan a bundled route without recording first. Check the route, toggle
   the overlay, pan and zoom, then change a routing preference while navigating.
9. Test a known staircase, an intermediate landing and an elevator. On overlapping floors, check
   that the route does not finish until you reach the indicated floor. Test Brill's upper platform
   when possible, and the Ruins above Undercity separately from the city below.
10. Check a faction border: stop before the enemy road, then enable Allow enemy roads to resume.
    Test a Zephras waypoint on its native map. Switch back with `/omgps use original`, confirm the
    original settings and map, and switch to GPS again.

Offline tests cover the Lua logic and stubbed client behavior. Arrow alignment, actual protected
API behavior, terrain, and the live window layout still require this game-client test.
