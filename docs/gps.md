# Custom GPS test build

This build adds GPS guidance to OpenMap: an arrow and distance while the map is closed,
a route on the map, automatic progress through turns, and a recorder for roads and repeatable
walking routes. It is an independent implementation inspired by the publicly described
[Forever Maps GPS feature](https://www.curseforge.com/wow/addons/forever-maps-world-map-gps-navigation).
No Forever Maps source, road data or art is included.

## Install

Use **OpenMapGPS-v0.8.10-gps.2-forever.zip**, the separate-addon build. The older gps.1 ZIP
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
The GPS build has independent `OpenMapGPSDB` and `OpenMapGPSCharDB` saved variables, its own
named frames, key bindings, addon-message prefixes and public API (`OpenMapGPSAPI`). It does not
read, copy or overwrite the original's settings. Its commands are `/openmapgps` and `/omgps`;
the original retains `/openmap` and `/omap`.

For example, `/omgps gps` opens the GPS controls, `/omgps gps record Elwynn road` starts a
recording, and `/omgps gps save` saves it. `/console scriptErrors 1` enables error reports.
TomTom is optional. The test build retains OpenMap's normal map and pins.

## First navigation

- Alt-left-click a destination on the map.
- Shift-click a result in OpenMap's search to navigate to it (plain click still moves the view).
- Open one of your map pins and press GPS.
- Or set a waypoint normally and use the GPS controls to navigate to it.

The arrow continues updating with the map closed. Stop GPS from its controls or with
`/omgps gps stop`. The player still walks, boards vessels and operates the game normally.

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

Flights or teleports interrupt road recording. The controls offer Save partial or Discard recording
rather than adding the jump as a walkable road. Loops must end within 100 yards of their start;
record the complete return path to avoid a direct closing segment across unknown terrain.

The GPS controls list saved routes and offer playback modes. Saved walking trails also supply
the road graph for destination routing. Only record paths you intend to walk; map points alone
cannot identify cliffs, walls, locked doors or a path's vertical level.

## Coverage and remaining parity work

This is a test build, not complete parity with Forever Maps. OpenMap's upstream data includes
flight and sailing routes but no walkable road graph. This build starts with **no recorded roads**.
Where no usable recorded connection exists it labels the result **direct guidance**, which points
toward the destination without knowing the terrain. It must not be treated as a safe walking path.
On a different continent, record/follow only supported walking sections; transport itinerary planning
and automatic flight/boat transfers are not implemented.

Full parity requires a sourced, redistributable road network (including city interiors, entrances,
bridges, heights and one-way links), connecting it to faction/learned-flight-aware transport legs,
and in-game verification of each transport transition. Forever Maps' proprietary road data is not
part of this build. Its route editing tools and complete public API are also outside this first build.

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

Offline tests cover the Lua logic and stubbed client behavior. Arrow alignment, actual protected
API behavior, terrain, and the live window layout still require this game-client test.
