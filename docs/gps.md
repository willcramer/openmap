# Custom GPS test build

This build adds GPS guidance to OpenMap: an arrow and distance while the map is closed,
a route on the map, automatic progress through turns, and a recorder for roads and repeatable
walking routes. It is an independent implementation inspired by the publicly described
[Forever Maps GPS feature](https://www.curseforge.com/wow/addons/forever-maps-world-map-gps-navigation).
The Forever package includes the 2.0.166 road network and associated room/floor metadata with
author permission. The importer and routing code are independently implemented; no Forever Maps
routing implementation or art is included. See the [data notice](../OpenMap/Data/Forever/RoadData-NOTICE.md).

The current GPS build includes official OpenMap **v0.8.10**, merged from upstream main at
`0f4d2e4b6fe82b9032618fd3b824eaaa5b36dcef`, together with the GPS customizations.

## Install

Use **OpenMapGPS-v0.8.10-gps.13-forever.zip**, the separate-addon build. The older gps.1 ZIP
used the original addon's folder and should not be used for a side-by-side install.
If you already installed gps.1 into `OpenMap`, reinstall the official OpenMap there first.

1. Quit WoW. Leave your existing `Interface/AddOns/OpenMap` folder in place.
2. Extract the Forever GPS ZIP into `Interface/AddOns`. The new folder must be
   `Interface/AddOns/OpenMapGPS`, containing `OpenMapGPS.toc`.
3. Restart the client on first install, or after updates that add textures. Updating gps.12 to
   gps.13 changes Lua only, so `/reload` is enough. **OpenMap - GPS** has
   its own entry, rather than being nested under OpenMap.
4. In AddOns, enable **OpenMap - GPS** and disable original **OpenMap**, then reload. To use
   the original again, enable it and disable OpenMap - GPS in that same list.

The quick-switch commands were removed in gps.6. Both entries are independently selectable.
If both are enabled, the original loads first and GPS remains in standby to avoid duplicate map
implementations. A message that Original OpenMap is active means you must select GPS in AddOns.
The original is an optional load-order dependency, not a required addon; GPS runs on its own.
The GPS build has independent `OpenMapGPSDB` and `OpenMapGPSCharDB` saved variables, its own
named frames, key bindings, addon-message prefixes and public API (`OpenMapGPSAPI`). Settings stay
separate; the original's preferences are read only by the explicit import command below.
Its commands are `/openmapgps` and `/omgps`;
the original retains `/openmap` and `/omap`.

Open the map, press its **OpenMap** menu button, then choose **GPS navigation**. Its controls
offer road display, tracker visibility, recording, saving, saved-route selection, playback and
confirmed deletion, plus **Edit road network** for placing nodes directly on the map. These
actions do not require slash commands. You can star GPS navigation
in the map menu to give it a shortcut on the map. `/omgps gps` also opens the same controls.
The GPS action and its starred shortcut use the client's blue handheld-computer icon
([inv_111_gallywixcomputer_blackwater](https://www.wowhead.com/forever/icon=6383475/inv-111-gallywixcomputer-blackwater)).
`/console scriptErrors 1` enables error reports.
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

Right-click opens the location menu by default. This update enables it once for existing profiles
that inherited the old zoom default. To use zoom-out instead, open `/omgps`, choose **More**, and
disable **Right-click opens location menu** under **Moving about**. The full option **Right-click
on the map** also offers **Zoom out** and **Open location menu**. Changes take effect immediately,
and later choices stay saved across reloads.

Right-click empty terrain to choose **Place waypoint**, **Add note** or **Go Here**. The action
uses the location where you opened the menu, even if you move the cursor afterward. Add note opens
the existing pin editor without changing your current waypoint or stopping GPS. Go Here starts
GPS navigation to that location. The same behavior is supported by the controller view's mouse
and native Zephras maps; controller zoom buttons retain their existing behavior.

Alt-left-click remains a shortcut. Click an existing OpenMap pin normally and press GPS in its
card. Drawing tools, pin placement modes and dungeon overlays keep their own input behavior.

The arrow continues updating with the map closed. Stop GPS from its controls or with
`/omgps gps stop`. The player still walks, boards vessels and operates the game normally.

While navigating, a solid green line connects your current position to the remaining waypoint
nodes. The destination has a larger marker. Passed sections disappear as guidance advances;
rerouting replaces the remaining line. Line width and node size stay steady while zooming.
This drawing works on the stitched map and controller view and on Zephras's native map.

### Hide the custom tracker while using TomTom

Clear **GPS tracker** in the GPS navigation window, press **Hide** on the guidance window, or
run `/omgps gps tracker off`. Navigation, the green
map route and TomTom waypoint updates continue. The choice remains saved for later journeys
and reloads. The Stop button still stops navigation; Hide only changes the window's visibility.

Restore it with `/omgps gps tracker on`, or open `/omgps` → **More** → **Moving about** and
enable **GPS tracker**. The same preference is available in the full GPS options. TomTom is
optional; tracker visibility can be selected independently of whether it is installed.

## Place and connect road nodes on the map

1. Open **OpenMap menu → GPS navigation → Edit road network**. The road display turns on.
2. Right-click near an existing gold node and choose **Select road node**.
3. Right-click the next point on your new path and choose **Add connected node**. This places
   a custom node, connects it to the selection and selects the new node. Repeat along bends.
4. To create a separate node, choose **Add road node**. To join two existing nodes, select the
   first, right-click near the second, then choose **Connect selected node**.
5. Choose **Finish editing** when done. GPS can use the new connections for destination routing.

**Cyan** nodes and links are your map edits; **white** marks the selected node. Gold nodes are
bundled roads and orange samples are recorded trails. Zoom in to select a junction accurately;
right-click selection looks for a road node within 25 yards. Recorded samples remain managed
through their saved routes rather than the manual node editor.

Changes save immediately in OpenMapGPS's own profile, with limits of 2,000 custom nodes and 4,000
custom connections. Select a node and choose **Clear selection**
to leave it in place. **Disconnect selected node** removes a connection you added between the
selection and the node near the menu location. **Delete road node** asks before deleting one of
your custom nodes and its connections. Bundled nodes and source connections cannot be deleted.
A connection directly between existing one-way road endpoints cannot reverse the supplied direction.

Connections are straight segments you explicitly mark as usable paths; place intermediate nodes
around corners. Map coordinates do not establish terrain clearance or the vertical shape of a
staircase. Nodes must be on the same continent and a compatible known floor; ambiguous overlapping
floors are rejected. The editor does not add automatic junctions just because nodes are nearby.

The same menu works on the controller view with the mouse and on native Zephras maps. While editing,
right-click opens the editor even if you normally use right-click to zoom out. Finish editing
restores that preference, and controller zoom buttons retain their behavior. Hiding Road network
ends editing. Editing mode and selection are temporary; the nodes and connections persist across
reloads. Active GPS destinations replan after topology changes, while tracker visibility stays saved.

## Record a road or farming route

1. Open the map's **OpenMap** menu and choose **GPS navigation**.
2. Enable **Road network** to see the existing roads and nodes. Start close to an existing node
   on the same floor when connecting a new trail to the network.
3. Enter a **Route name**, then press **Record** and walk the missing path.
4. Press **Save route**. It becomes available for future GPS destination planning.
5. Use **Saved routes** to select a recording. Choose its **Playback** mode and press
   **Follow saved route**, or press **Delete** and confirm to remove it.

Record another road starting at an existing junction to expand your network. The matching
commands are `/omgps gps record Elwynn road` and `/omgps gps save`.
Routes are stored in OpenMapGPS's account saved variables, while active guidance is temporary.
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
| `/omgps gps tracker off` | Hide only the custom tracker; use `on` to show it again |
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

Use bundled roads is on by default. **Road network** in the GPS navigation window or the map
menu's **On the map** tab shows the network. Small dots trace the road links; larger markers show
actual bundled nodes, saved trail samples and manually placed nodes. Recorded and manual paths have
distinct colors. Zoom in when
inspecting a junction: wide views limit the marker count. Options
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

This build covers walking-network planning, recorded paths and explicit manual node/link editing.
Multi-continent flight/boat itinerary planning, advanced travel/floor-metadata editing and the
reference addon's full public API are not part of this pass.
See [parity and validation](gps-validation.md) for verified cases and remaining live checks.

Position reads can be unavailable or secret in instances or combat. Guidance waits rather than
doing arithmetic on those values. Setting a different waypoint lets another addon take over;
GPS must not replace that addon's destination.

## Automatic replanning

When you move away from a road route, GPS calculates its replacement across frames rather than
blocking one frame for the entire search. Planning and route-marker drawing share a target of
1 ms of addon CPU time per frame. Individual API calls and guidance updates can exceed that
target; it is not a guaranteed frame-time ceiling. The existing five-second cooldown and movement
thresholds remain. The current route and waypoint stay in place until a valid replacement is ready.

Destination attachments and recorded-road projections are cached with their routing context.
Changes to preferences, topology, source data or profiles invalidate the relevant work. Stopping,
changing waypoint ownership, teleporting, taking a taxi or changing floors cancels stale results.
Green map lines are built in a hidden staging layer and swapped when complete; closing the map
defers marker work while guidance and TomTom continue. An explicit new destination or routing-option
change still plans synchronously. This change targets recurring automatic off-route hitches.

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
    Test a Zephras waypoint on its native map. Select the original in AddOns, confirm its settings
    and map, then select OpenMap - GPS again. Confirm neither quick-switch command changes addon state.
11. Toggle Right-click opens location menu. Check zoom-out when off and all three actions when on.
    Move the cursor after opening the menu and confirm the action still uses the original point.
    While navigating, add a note and confirm the GPS destination stays intact. Test Escape and
    clicking outside the menu, map close/reopen, and the native/controller map when available.
12. Use only the map menu and GPS navigation window to toggle roads/tracker, record and save a
    new trail, select it, change playback mode, follow it and delete it with confirmation. Check
    that the road display updates after saving/deleting without panning, and that Cancel in the
    delete prompt preserves the trail. Close/reopen the controls and confirm the saved preferences.
13. Open Edit road network, select an existing road node and extend a path with Add connected node.
    Place separate nodes and connect them. Check cyan links and the white selection on the world,
    controller and Zephras maps. Navigate over the new path, disconnect/delete your edits, and check
    rerouting. Cancel the delete prompt once. Reload and confirm edits persist but editing is off.
    Repeat with normal right-click configured as Zoom out; Finish editing must restore zoom-out.
14. Start a long bundled route and walk more than 60 yards off its current segment. Continue moving
    for several recalculations with the map closed, then open. Check for recurring five-second
    FPS dips, complete green lines and continued TomTom updates with the tracker hidden. Stop or
    replace the waypoint during a recalculation and confirm no older route returns.

Offline tests cover the Lua logic and stubbed client behavior. Arrow alignment, actual protected
API behavior, terrain, and the live window layout still require this game-client test.
