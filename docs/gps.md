# Custom GPS test build

This build adds GPS guidance to OpenMap: an arrow and distance while the map is closed,
a route on the map, automatic progress through turns, and a recorder for roads and repeatable
walking routes. It is an independent implementation inspired by the publicly described
[Forever Maps GPS feature](https://www.curseforge.com/wow/addons/forever-maps-world-map-gps-navigation).
No Forever Maps source, road data or art is included.

## Install

1. Quit WoW and back up your current `Interface/AddOns/OpenMap` folder and OpenMap saved variables.
2. Extract the Forever ZIP into your WoW Forever client's `Interface/AddOns` folder. The result
   must be `Interface/AddOns/OpenMap/OpenMap.toc`, without an extra nested directory.
3. Enable OpenMap on the character selection screen, log in, and enter `/console scriptErrors 1`.
4. Type `/openmap gps`, or open the map's OpenMap menu and choose GPS.

The custom build replaces OpenMap; install only one copy. Other world map addons should be
disabled for the first test. TomTom is optional. The build retains OpenMap's normal map and pins.

## First navigation

- Alt-left-click a destination on the map.
- Shift-click a result in OpenMap's search to navigate to it (plain click still moves the view).
- Open one of your map pins and press GPS.
- Or set a waypoint normally and use the GPS controls to navigate to it.

The arrow continues updating with the map closed. Stop GPS from its controls or with
`/openmap gps stop`. The player still walks, boards vessels and operates the game normally.

## Record a road or farming route

Start a recording with `/openmap gps record Elwynn road`, walk the road, then use
`/openmap gps save`. Record another road starting at an existing junction to expand your network.
Routes are stored in OpenMap's account saved variables, while active guidance is temporary.
Save before reloading or logging out: an unfinished recording is temporary too. Playback must
start within 100 yards of its first point (the last point for reverse playback). The road planner
attaches your position and destination to nearby samples within 100 yards; those short connectors
are direct segments whose terrain is not checked. Junctions merge within 10 yards, so avoid
recording overlapping floors as separate roads.

Commands:

| Command | Action |
| --- | --- |
| `/openmap gps` | Open controls |
| `/openmap gps waypoint` | Guide to the current waypoint |
| `/openmap gps go 1429 42 65` | Guide to normalized map coordinates given as percentages |
| `/openmap gps record Elwynn road` | Start recording |
| `/openmap gps save` | Save recording |
| `/openmap gps savepartial` | Explicitly save the recorded section before a detected gap |
| `/openmap gps cancelrecord` | Discard unfinished recording |
| `/openmap gps follow reverse Elwynn road` | Replay; modes: `once`, `reverse`, `loop`, `pingpong` |
| `/openmap gps list` | List saved route names |
| `/openmap gps delete Elwynn road` | Delete saved route |
| `/openmap gps stop` | Stop navigation; recording is separate |
| `/openmap gps status` | Print current status |

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
