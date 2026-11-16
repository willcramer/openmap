-- GPS combines the supplied road network with trails recorded by the player.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local S, Safe, L = ns.MapStitch, ns.Safe, ns.L

mod.defaults.gpsRoutes = {}
mod.defaults.gpsUseRoads = true
mod.defaults.gpsOffroad = "avoid"
mod.defaults.gpsAllowEnemy = false
mod.defaults.gpsAboveLevel = "avoid"

local MAX_ROUTES, MAX_POINTS, MAX_TOTAL = 50, 2000, 10000
local SAMPLE, REACH, JOIN, ATTACH = 12, 15, 10, 100 -- yards
local active, recording, graph, owned, lastPlayer
local roadsRevision = 0
local status = { active = false, state = "stopped", recorded = 0 }

local function Number(n)
	n = Safe.Value(n)
	return type(n) == "number" and n == n and n > -math.huge and n < math.huge and n or nil
end

local function Name(name)
	if type(name) ~= "string" then return end
	name = name:gsub("|", ""):gsub("[%c]", ""):gsub("^%s+", ""):gsub("%s+$", "")
	if name ~= "" and #name <= 80 then return name end
end

local function Routes()
	return mod.db.gpsRoutes
end

local function Point(mapID, x, y)
	mapID, x, y = Number(mapID), Number(x), Number(y)
	if not mapID or mapID < 1 or mapID % 1 ~= 0 or not x or not y or x < 0 or x > 1 or y < 0 or y > 1 then return end
	local u, v
	if S.Rect(mapID) then u, v = mod.ToWorld(mapID, x, y) end
	if not C_Map.GetWorldPosFromMapPos or not CreateVector2D then return end
	local ok, continent, pos = pcall(C_Map.GetWorldPosFromMapPos, mapID, CreateVector2D(x, y))
	continent = Safe.Value(continent)
	if not ok or not Number(continent) or not Safe.Value(pos) then return end
	local wx, wy = Safe.XY(pos)
	wx, wy = Number(wx), Number(wy)
	if not wx or not wy then return end
	local p = { map = mapID, x = x, y = y, u = u, v = v, cont = continent, wx = wx, wy = wy }
	if mod.GPSRoomContext then
		local room = mod.GPSRoomContext(continent, wx, wy, nil, mapID)
		if room then for k, value in pairs(room) do p[k] = value end end
	end
	return p
end

-- A supplied node's world position on either the stitched map or its own native
-- map (Zephras Isle is outside the stitched Azeroth canvas).
function mod.GPSRoadPoint(node, continent)
	local wx, wy = Number(node.wx), Number(node.wy)
	if not wx or not wy then return end
	local p = {}
	for k, value in pairs(node) do p[k] = value end
	p.wx, p.wy, p.cont = wx, wy, continent
	if S.FromYards then
		local ok, u, v = pcall(S.FromYards, continent, wx, wy)
		if ok then p.u, p.v = Number(u), Number(v) end
	end
	local maps = {}
	if Number(node.map) then maps[#maps + 1] = node.map end
	local continentMap = ({ [0] = 1415, [1] = 1414, [2991] = 2521 })[continent]
	if continentMap and continentMap ~= node.map then maps[#maps + 1] = continentMap end
	if p.u and p.v and mod.FromWorld then
		for _, mapID in ipairs(maps) do
			if S.Rect(mapID) then
				local x, y = mod.FromWorld(mapID, p.u, p.v)
				if x and y and x >= 0 and x <= 1 and y >= 0 and y <= 1 then p.map, p.x, p.y = mapID, x, y break end
			end
		end
	end
	if not p.x and C_Map.GetMapPosFromWorldPos and CreateVector2D then
		for _, id in ipairs(maps) do
			local ok, mapID, pos = pcall(C_Map.GetMapPosFromWorldPos, continent, CreateVector2D(wx, wy), id)
			mapID, pos = Number(mapID), Safe.Value(pos)
			if ok and mapID and pos then
				local x, y = Safe.XY(pos)
				x, y = Number(x), Number(y)
				if x and y and x >= 0 and x <= 1 and y >= 0 and y <= 1 then p.map, p.x, p.y = mapID, x, y break end
			end
		end
	end
	if not p.x and p.u and p.v and mod.FromWorld then
		for _, mapID in ipairs(maps) do
			if S.Rect(mapID) then
				local x, y = mod.FromWorld(mapID, p.u, p.v)
				if x and y and x >= 0 and x <= 1 and y >= 0 and y <= 1 then p.map, p.x, p.y = mapID, x, y break end
			end
		end
	end
	if not p.u and p.map and p.x and S.Rect(p.map) then p.u, p.v = mod.ToWorld(p.map, p.x, p.y) end
	if mod.GPSRoadNodeContext then
		local room = mod.GPSRoadNodeContext(continent, node)
		if room then for k, value in pairs(room) do if k ~= "map" then p[k] = value end end end
	end
	return p
end

function mod.GPSPlayer()
	local mapID = Safe.Call(C_Map.GetBestMapForUnit, "player")
	if not mapID then return end
	local pos = Safe.Call(C_Map.GetPlayerMapPosition, mapID, "player")
	if not pos then return end
	local x, y = Safe.XY(pos)
	x, y = Number(x), Number(y)
	if not x or not y or x == 0 and y == 0 then return end
	local p = Point(mapID, x, y)
	if p then
		local z
		if type(UnitPosition) == "function" then
			local ok, _, _, height, cont = pcall(UnitPosition, "player")
			if ok and Number(cont) == p.cont then z = Number(height) end
		end
		return p.map, p.x, p.y, p.u, p.v, p.cont, p.wx, p.wy, z
	end
end

local function Player()
	local mapID, x, y, u, v, cont, wx, wy, z = mod.GPSPlayer()
	if mapID then
		local p = { map = mapID, x = x, y = y, u = u, v = v, cont = cont, wx = wx, wy = wy, z = z }
		if mod.GPSObserveRoom or mod.GPSRoomContext then
			local room
			if mod.GPSObserveRoom then room = mod.GPSObserveRoom(cont, wx, wy, mapID, z)
			else room = mod.GPSRoomContext(cont, wx, wy, z, mapID) end
			if room then for k, value in pairs(room) do p[k] = value end end
		end
		local info = Safe.Call(C_Map.GetMapInfo, mapID)
		local subzone = Safe.Call(_G.GetSubZoneText)
		if info and type(info.name) == "string" and type(subzone) == "string" and subzone ~= "" then
			p.area = subzone == info.name and subzone or (info.name .. " / " .. subzone)
		end
		return p
	end
end

local function Distance(a, b)
	if a.cont ~= b.cont then return math.huge end
	return math.sqrt((a.wx - b.wx) ^ 2 + (a.wy - b.wy) ^ 2)
end

local function Compact(p)
	return { p.map, p.x, p.y, z = p.z, piece = p.piece, layer = p.layer }
end

local function SamplePoint(sample)
	if type(sample) ~= "table" then return end
	local p = Point(sample[1], sample[2], sample[3])
	if not p then return end
	p.z = Number(sample.z)
	if p.z and mod.GPSRoomContext then
		local room = mod.GPSRoomContext(p.cont, p.wx, p.wy, p.z, p.map)
		if room then for k, value in pairs(room) do p[k] = value end end
	end
	if type(sample.piece) == "string" then p.piece, p.ambiguous = sample.piece, false end
	if type(sample.layer) == "boolean" or Number(sample.layer) then p.layer = sample.layer end
	return p
end

-- Overlay views use the same saved-sample projection and revision as routing.
function mod.GPSRecordedPoint(sample) return SamplePoint(sample) end
function mod.GPSRoadsRevision() return roadsRevision end

local function Notify()
	if mod.OnGPSChanged then mod.OnGPSChanged() end
end

local function SameWaypoint(p)
	if not p or not mod.WaypointPoint then return false end
	local mapID, x, y = mod.WaypointPoint()
	mapID, x, y = Number(mapID), Number(x), Number(y)
	return mapID == p.map and x and y and math.abs(x - p.x) < 0.00001 and math.abs(y - p.y) < 0.00001
end

local function Track()
	local p = active and active.route[active.index]
	if not p or not p.map or not p.x or not p.y then return end
	owned = p
	if mod.TrackPoint then mod.TrackPoint(p.map, p.x, p.y, active.title) end
end

local function Stop(state, clear)
	local ours = SameWaypoint(owned)
	active, owned = nil, nil
	status.active, status.state = false, state or "stopped"
	status.player = nil
	status.bearing, status.distance, status.remaining = nil, nil, nil
	status.instruction = L["GPS stopped."]
	if state ~= "faction-stop" then status.resumeTarget, status.resumeTitle = nil, nil end
	if clear and ours and mod.ClearPin then mod.ClearPin() end
	Notify()
end

function mod.GPSStop() Stop("stopped", true) return true end

function mod.GPSCancelRecording()
	recording = nil
	status.recording, status.recorded, status.recordingState = nil, 0, nil
	Notify()
	return true
end

-- Nearby samples from separate walks form junctions. A grid bounds the comparisons.
local function BuildGraph()
	if graph then return graph end
	local nodes, links, cells = {}, {}, {}
	local function key(p, dx, dy)
		return p.cont .. ":" .. (math.floor(p.wx / JOIN) + (dx or 0)) .. ":" .. (math.floor(p.wy / JOIN) + (dy or 0))
	end
	local function edge(a, b, d)
		links[a][#links[a] + 1] = { b, d }
		links[b][#links[b] + 1] = { a, d }
	end
	for _, name in ipairs(mod.GPSList()) do
		local trail = Routes()[name]
		local previous
		for _, sample in ipairs(trail.points or {}) do
			if #nodes >= MAX_TOTAL then break end
			local p = SamplePoint(sample)
			if p then
				local id = #nodes + 1
				nodes[id], links[id] = p, {}
				for dx = -1, 1 do for dy = -1, 1 do
					for _, other in ipairs(cells[key(p, dx, dy)] or {}) do
						local d = Distance(p, nodes[other])
						if d <= JOIN then edge(id, other, d) end
					end
				end end
				local cell = key(p)
				cells[cell] = cells[cell] or {}
				cells[cell][#cells[cell] + 1] = id
				if previous and Distance(p, nodes[previous]) <= 100 then edge(previous, id, Distance(p, nodes[previous])) end
				previous = id
			else previous = nil end
		end
	end
	graph = { nodes = nodes, links = links }
	return graph
end

-- Heap-backed Dijkstra keeps a recorded network from blocking a frame on a quadratic scan.
local function RoadRoute(from, to)
	local g = BuildGraph()
	local distances, prev, heap = {}, {}, {}
	local function push(id, cost)
		local i = #heap + 1
		while i > 1 do
			local parent = math.floor(i / 2)
			if heap[parent][2] <= cost then break end
			heap[i], i = heap[parent], parent
		end
		heap[i] = { id, cost }
	end
	local function pop()
		local first, tail = heap[1], table.remove(heap)
		if #heap > 0 then
			local i = 1
			while i * 2 <= #heap do
				local child = i * 2
				if child < #heap and heap[child + 1][2] < heap[child][2] then child = child + 1 end
				if tail[2] <= heap[child][2] then break end
				heap[i], i = heap[child], child
			end
			heap[i] = tail
		end
		return first[1], first[2]
	end
	local startID, finishID, startDistance, finishDistance
	for id, p in ipairs(g.nodes) do
		local ds, df = Distance(from, p), Distance(to, p)
		if ds <= ATTACH and (not startDistance or ds < startDistance) then startID, startDistance = id, ds end
		if df <= ATTACH and (not finishDistance or df < finishDistance) then finishID, finishDistance = id, df end
	end
	if not startID or not finishID or startID == finishID then return end
	distances[startID] = startDistance
	push(startID, startDistance)
	local best, total
	while #heap > 0 do
		local id, cost = pop()
		if total and cost >= total then break end
		if distances[id] == cost then
			if id == finishID then best, total = id, cost + finishDistance break end
			for _, e in ipairs(g.links[id]) do
				local nextCost = cost + e[2]
				if not distances[e[1]] or nextCost < distances[e[1]] then
					distances[e[1]], prev[e[1]] = nextCost, id
					push(e[1], nextCost)
				end
			end
		end
	end
	if not best then return end
	local reversed, out = {}, {}
	while best do reversed[#reversed + 1], best = g.nodes[best], prev[best] end
	for i = #reversed, 1, -1 do out[#out + 1] = reversed[i] end
	if #out == 0 or Distance(out[#out], to) > 1 then out[#out + 1] = to end
	return out
end

local levelNames, levelData
local function ChunkArea(node)
	local chunks = ns.GPSRoadAreas
	local grid = chunks and chunks[tostring(node.cont)]
	if not grid or not chunks.CHARS then return end
	local tile = 1600 / 3
	local gx, gy = 32 - node.wy / tile, 32 - node.wx / tile
	local column, row = math.floor(gx), math.floor(gy)
	local text = grid.tiles and grid.tiles[column * 64 + row]
	if not text then return end
	local cx, cy = math.floor((gx - column) * 16), math.floor((gy - row) * 16)
	local character = text:sub(cy * 16 + cx + 1, cy * 16 + cx + 1)
	local at = chunks.CHARS:find(character, 1, true)
	return at and grid.ids[at]
end

local function RoadLevel(node)
	local data = ns.GPSRoadLevels
	if data then
		local area = ChunkArea(node)
		if area and data.areas and data.areas[area] then return data.areas[area] end
		local explore = C_MapExplorationInfo and C_MapExplorationInfo.GetExploredAreaIDsAtPosition
		if node.map and node.x and type(explore) == "function" then
			local areas = Safe.Call(explore, node.map, CreateVector2D(node.x, node.y))
			for _, id in ipairs(type(areas) == "table" and areas or {}) do
				if data.areas and data.areas[id] then return data.areas[id] end
			end
		end
	end
	if data and data ~= levelData then
		levelData, levelNames = data, {}
		for id, level in pairs(data.areas or {}) do
			local name = Safe.Call(C_Map.GetAreaInfo, id)
			if name then levelNames[name] = level end
		end
	end
	if levelNames and node.area then
		local area = node.area:match(".*/%s*(.-)%s*$") or node.area
		if levelNames[area] then return levelNames[area] end
	end
	local range = data and data.zones and data.zones[node.sourceMap or node.map]
	if range then return range.low or range[1] end
	local zone = ns.MapLevels and ns.MapLevels[node.map]
	return zone and zone[1]
end

local function Plan(from, to)
	if mod.db.gpsUseRoads ~= false and mod.GPSRoadRoute then
		local ghost = Safe.Call(_G.UnitIsGhost, "player") == true
		local extras = {}
		for name, trail in pairs(Routes()) do
			local points = {}
			for _, sample in ipairs(type(trail) == "table" and trail.points or {}) do
				local p = SamplePoint(sample)
				if p then points[#points + 1] = p end
			end
			if #points > 1 then extras[name] = { points = points } end
		end
		local route, reason, stats = mod.GPSRoadRoute(from, to, {
			tops = mod.GPSRoadTopsAt and mod.GPSRoadTopsAt(from),
			faction = Safe.Call(UnitFactionGroup, "player"), playerLevel = Safe.Call(UnitLevel, "player"),
			allowEnemy = true, ghost = ghost, offroad = mod.db.gpsOffroad,
			aboveLevel = mod.db.gpsAboveLevel, minLevel = RoadLevel,
			extraRoutes = extras, extraRevision = roadsRevision,
		})
		if route then
			if not ghost and mod.db.gpsAllowEnemy ~= true then
				for i, point in ipairs(route) do
					if point.enemy then
						if i == 1 then return nil, "blocked" end
						local safe = {}
						for j = 1, i - 1 do safe[j] = route[j] end
						safe[#safe].factionStop = true
						if stats then stats.factionStop = true end
						route = safe
						break
					end
				end
			end
			return route, "bundled", stats
		end
		if reason and reason ~= "no-data" and reason ~= "no-coverage" then return nil, reason end
	end
	local recorded = RoadRoute(from, to)
	if recorded then return recorded, "recorded" end
	if from.cont == to.cont then return { to }, "direct" end
	return nil, "continent"
end

local function RouteError(reason)
	if reason == "floor" then return L["Choose a destination on a known floor or at its entrance."] end
	if reason == "blocked" then return L["No road route meets your faction and travel preferences."] end
	if reason == "disconnected" then return L["The road network does not connect these locations."] end
	return L["No road route connects these continents."]
end

local function Start(route, title, state, mode, target)
	Stop("stopped", false)
	lastPlayer = nil
	active = { route = route, index = 1, title = title or L["GPS"], state = state, mode = mode, target = target, origin = Player() }
	status.route, status.title, status.state = route, active.title, state
	status.roadSource = state
	if state ~= "bundled" then status.roadStats = nil end
	status.active, status.index, status.total = true, 1, #route
	status.player = active.origin
	Track()
	Notify()
	mod.GPSUpdate()
	return true
end

function mod.GPSStart(mapID, x, y, title)
	local target, player = Point(mapID, x, y), Player()
	if not target then return nil, L["GPS cannot navigate to that location."] end
	if not player then return nil, L["GPS is waiting for your position."] end
	local route, source, stats = Plan(player, target)
	if not route then return nil, RouteError(source) end
	status.roadSource, status.roadStats = source, stats
	return Start(route, Name(title), source, "navigate", target)
end

function mod.GPSList()
	local out = {}
	for name, trail in pairs(Routes()) do
		if type(name) == "string" and type(trail) == "table" and type(trail.points) == "table" then out[#out + 1] = name end
	end
	table.sort(out)
	return out
end

function mod.GPSRecord(name)
	name = Name(name)
	if not name then return nil, L["Give the route a name of up to 80 characters."] end
	if recording then return nil, L["Save the current recording first."] end
	if Routes()[name] then return nil, L["A route with that name already exists."] end
	if #mod.GPSList() >= MAX_ROUTES then return nil, L["The GPS route limit has been reached."] end
	local p = Player()
	if not p then return nil, L["GPS is waiting for your position."] end
	if Safe.Call(UnitOnTaxi, "player") then return nil, L["Land before recording a walking route."] end
	recording = { name = name, points = { Compact(p) }, last = p }
	status.recording, status.recorded, status.recordingState = name, 1, "recording"
	Notify()
	return true
end

function mod.GPSSave(allowPartial)
	if not recording then return nil, L["No GPS recording is in progress."] end
	local p = Player()
	if p and recording.last and (Distance(recording.last, p) > 100 or Safe.Call(UnitOnTaxi, "player")) then
		recording.gap, status.recordingState = true, "gap"
	end
	if recording.gap and not allowPartial then return nil, L["A gap interrupted recording. Save the partial route or discard it."] end
	if not recording.gap and not Safe.Call(UnitOnTaxi, "player") and p and recording.last and Distance(recording.last, p) > 1 and Distance(recording.last, p) <= 100 and #recording.points < MAX_POINTS then
		recording.points[#recording.points + 1] = Compact(p)
	end
	if #recording.points < 2 then return nil, L["Walk farther before saving this route."] end
	local total = #recording.points
	for _, trail in pairs(Routes()) do if type(trail) == "table" and type(trail.points) == "table" then total = total + #trail.points end end
	if total > MAX_TOTAL then return nil, L["The GPS route limit has been reached."] end
	Routes()[recording.name] = { points = recording.points }
	roadsRevision = roadsRevision + 1
	recording, graph = nil, nil
	status.recording, status.recorded, status.recordingState = nil, 0, nil
	Notify()
	return true
end

function mod.GPSDelete(name)
	if not Routes()[name] then return nil, L["GPS route not found."] end
	Routes()[name], graph = nil, nil
	roadsRevision = roadsRevision + 1
	Notify()
	return true
end

function mod.GPSPlay(name, mode)
	local trail = Routes()[name]
	if type(trail) ~= "table" or type(trail.points) ~= "table" then return nil, L["GPS route not found."] end
	mode = mode or "once"
	if mode ~= "once" and mode ~= "reverse" and mode ~= "loop" and mode ~= "pingpong" then return nil, L["Unknown GPS playback mode."] end
	local route = {}
	for _, sample in ipairs(trail.points) do
		local p = SamplePoint(sample)
		if not p or #route > 0 and Distance(route[#route], p) > 100 then return nil, L["This recording has a gap and cannot be followed."] end
		route[#route + 1] = p
	end
	if #route < 2 then return nil, L["GPS route not found."] end
	if mode == "loop" and Distance(route[1], route[#route]) > 100 then return nil, L["A loop must finish near its starting point."] end
	if mode == "reverse" then
		local reversed = {}
		for i = #route, 1, -1 do reversed[#reversed + 1] = route[i] end
		route = reversed
	end
	local player = Player()
	if not player then return nil, L["GPS is waiting for your position."] end
	if player.cont ~= route[1].cont then return nil, L["No recorded route connects these continents."] end
	if Distance(player, route[1]) > ATTACH then return nil, L["Move within 100 yards of the route's starting point."] end
	return Start(route, name, "recorded", mode)
end

local function SegmentDistance(p, a, b)
	if p.cont ~= a.cont or p.cont ~= b.cont then return math.huge end
	local dx, dy = b.wx - a.wx, b.wy - a.wy
	local length = dx * dx + dy * dy
	local t = length > 0 and math.max(0, math.min(1, ((p.wx - a.wx) * dx + (p.wy - a.wy) * dy) / length)) or 0
	return math.sqrt((p.wx - a.wx - dx * t) ^ 2 + (p.wy - a.wy - dy * t) ^ 2), t
end

local function FloorMatches(player, point)
	local low, high = point.minZ or point.zmin, point.maxZ or point.zmax
	if player.z and low and high and (player.z < low - 3 or player.z > high + 3) then return false end
	if point.piece and player.pieces and next(player.pieces) and mod.GPSOtherFloor then
		local allOther = true
		for piece in pairs(player.pieces) do
			local here = mod.GPSRoadNodeContext(player.cont, { piece = piece })
			local other = mod.GPSOtherFloor(here, point)
			if player.ambiguous and not player.z and other then return false end
			if not other then allOther = false end
		end
		if allOther then return false end
	end
	if point.layer and player.layer and point.layer ~= player.layer then return false end
	if point.layer and not player.layer then
		local knownRoom = point.piece and player.pieces and player.pieces[point.piece]
		local knownHeight = player.z and low and high and player.z >= low - 3 and player.z <= high + 3
		if not knownRoom and not knownHeight then return false end
	end
	return true
end

local function StairReached(player, point, previous)
	if not point.stairOwner or not point.stairDirection then active.stairs = nil return true end
	local angle = math.atan2(player.wy - point.centerWY, player.wx - point.centerWX)
	local stair = active.stairs
	if not stair or stair.owner ~= point.stairOwner then
		local initial = previous and previous.stairOwner == point.stairOwner and previous.stairTurn or point.stairStartTurn or 0
		stair = { owner = point.stairOwner, angle = angle, turn = initial }
		active.stairs = stair
	else
		local delta = (angle - stair.angle + math.pi) % (2 * math.pi) - math.pi
		stair.turn = stair.turn + delta / (2 * math.pi) * (point.stairAngleSign or 1)
		stair.angle = angle
	end
	return (stair.turn - point.stairTurn) * point.stairDirection >= -0.06
end

local function Special(point)
	return point.stairOwner or point.elevator or point.onewayDrop or point.kind == "drop"
end

-- Rejoin a later ordinary stretch after missing a corner. Never scan across a
-- stair, lift, drop, or a point on an unconfirmed floor.
local function Rejoin(player)
	if active.mode ~= "navigate" then return end
	local route, index = active.route, active.index
	local previous = route[index - 1] or active.origin
	if not previous or Special(route[index]) or Special(previous) then return end
	local off = SegmentDistance(player, previous, route[index])
	if off <= REACH or Distance(player, route[index]) <= REACH then return end
	local best, nearest
	for j = index + 1, #route do
		local a, b = route[j - 1], route[j]
		if Special(a) or Special(b) then break end
		if FloorMatches(player, a) and FloorMatches(player, b) then
			local close, along = SegmentDistance(player, a, b)
			if close < REACH and along > 0.05 and (not nearest or close <= nearest) then best, nearest = j, close end
		end
	end
	if best then active.index = best Track() Notify() end
end

function mod.GPSUpdate()
	local player = Player()
	status.player = active and player or nil
	-- Room continuity must be observed before a journey starts; entering a
	-- building with GPS stopped still tells the next journey which floor is ours.
	if not active and not recording then return end
	if recording then
		if player and recording.last then
			local d = Distance(recording.last, player)
			-- A loading screen, flight or teleport must not silently become a walkable road.
			if d > 100 or Safe.Call(UnitOnTaxi, "player") then
				recording.gap = true
			elseif d >= SAMPLE and not recording.gap and #recording.points < MAX_POINTS then
				recording.points[#recording.points + 1] = Compact(player)
				recording.last = player
			end
		end
		status.recorded = #recording.points
		status.recordingState = recording.gap and "gap" or (#recording.points >= MAX_POINTS and "full" or "recording")
	end
	if not active then return end
	if owned and not SameWaypoint(owned) then Stop("stopped", false) return end
	if not player or Safe.Call(UnitOnTaxi, "player") then
		status.player = nil
		status.state, status.instruction, status.bearing = "waiting", L["GPS is waiting for your position."], nil
		status.distance, status.remaining = nil, nil
		return
	end
	Rejoin(player)
	local route, index = active.route, active.index
	local p = route[index]
	if player.cont ~= p.cont then
		status.player = nil
		status.state, status.instruction, status.bearing = "waiting", L["Return to the route's continent to continue GPS."], nil
		status.distance, status.remaining = nil, nil
		return
	end
	local d = Distance(player, p)
	local floorMatches = FloorMatches(player, p)
	local stairReached = StairReached(player, p, route[index - 1])
	local passed = false
	if index > 1 and not p.stairOwner then
		local close, t = SegmentDistance(player, route[index - 1], p)
		passed = close < REACH and t >= 0.98
	end
	local reach = p.stairDirection and math.min(REACH, 4) or REACH
	if floorMatches and stairReached and (d <= reach or passed) then
		if index == #route then
			if active.mode == "loop" then active.index = 1
			elseif active.mode == "pingpong" then
				local reversed = {}
				for i = #route, 1, -1 do reversed[#reversed + 1] = route[i] end
				active.route, active.index, status.route = reversed, 2, reversed
			else
				local factionStop = p.factionStop
				if factionStop then status.resumeTarget, status.resumeTitle = active.target, active.title end
				Stop(factionStop and "faction-stop" or "arrived", true)
				status.instruction = factionStop and L["GPS stopped before the other faction's roads."] or L["You have arrived."]
				return
			end
		else active.index = index + 1 end
		Track()
		Notify()
		index, route = active.index, active.route
		p = route[index]
		d = Distance(player, p)
		floorMatches = FloorMatches(player, p)
		StairReached(player, p, route[index - 1])
	end
	-- Replan after leaving the current road, with a cooldown and actual movement required.
	local now = GetTime()
	if active.mode == "navigate" and (active.state == "recorded" or active.state == "bundled")
		and not p.stairOwner and now >= (active.replanAt or 0) then
		local off = index > 1 and SegmentDistance(player, route[index - 1], p) or d
		if off > 60 and (not lastPlayer or Distance(lastPlayer, player) > 20) then
			active.replanAt, lastPlayer = now + 5, player
			local newRoute, source, stats = Plan(player, active.target)
			if newRoute then
				active.state, status.roadSource, status.roadStats = source, source, stats
				active.route, active.index, status.route = newRoute, 1, newRoute
				Track()
				Notify()
				route, index, p = newRoute, 1, newRoute[1]
				d = Distance(player, p)
				floorMatches = FloorMatches(player, p)
			end
		end
	end
	local remaining = d
	for i = index + 1, #route do remaining = remaining + Distance(route[i - 1], route[i]) end
	status.active, status.state, status.title = true, active.state, active.title
	status.index, status.total = index, #route
	status.map, status.x, status.y, status.u, status.v = p.map, p.x, p.y, p.u, p.v
	status.distance, status.remaining = d < math.huge and d or nil, remaining < math.huge and remaining or nil
	status.bearing = player.cont == p.cont and math.atan2(p.wy - player.wy, p.wx - player.wx) or nil
	status.turn = "straight"
	if index < #route then
		local a = index > 1 and route[index - 1] or player
		local b = route[index + 1]
		local cross = (p.wx - a.wx) * (b.wy - p.wy) - (p.wy - a.wy) * (b.wx - p.wx)
		local dot = (p.wx - a.wx) * (b.wx - p.wx) + (p.wy - a.wy) * (b.wy - p.wy)
		local angle = math.atan2(cross, dot)
		if math.abs(angle) > 0.6 then status.turn = angle > 0 and "left" or "right" end
	end
	if active.state == "direct" then status.instruction = L["Head toward the destination; terrain is not checked."]
	elseif not floorMatches then status.instruction = L["Continue to the indicated floor."]
	elseif p.kind == "stairs" and p.stairDirection and p.stairDirection > 0 then status.instruction = L["Go up the stairs to the next landing."]
	elseif p.kind == "stairs" and p.stairDirection and p.stairDirection < 0 then status.instruction = L["Go down the stairs to the next landing."]
	elseif p.kind == "stairs" then status.instruction = L["Follow the stairs to the next landing."]
	elseif p.kind == "elevator" then status.instruction = L["Take the elevator, then continue along the route."]
	elseif p.kind == "drop" or p.onewayDrop then status.instruction = L["Drop down along the one-way path."]
	elseif p.kind == "swim" then status.instruction = L["Swim along the indicated route."]
	elseif p.connectorRole == "finish" then status.instruction = L["Reach the destination directly; terrain is not checked on this approach."]
	elseif p.connector then status.instruction = L["Reach the road directly; terrain is not checked on this approach."]
	elseif p.enemy then status.instruction = L["This route enters the other faction's territory."]
	elseif p.highLevel then status.instruction = L["This off-road path is above your level."]
	elseif status.turn == "left" then status.instruction = L["Turn left at the next point."]
	elseif status.turn == "right" then status.instruction = L["Turn right at the next point."]
	elseif active.state == "bundled" then status.instruction = L["Follow the road."]
	else status.instruction = L["Follow the recorded trail."] end
end

function mod.GPSStatus() return status end

function mod.GPSSetRoutingOption(key, value)
	if key == "gpsUseRoads" or key == "gpsAllowEnemy" then value = value and true or false
	elseif key == "gpsOffroad" then
		if value ~= "allow" and value ~= "shortest" and value ~= "avoid" and value ~= "needed" and value ~= "deny" then return false end
	elseif key == "gpsAboveLevel" then
		if value ~= "allow" and value ~= "warn" and value ~= "avoid" and value ~= "never" and value ~= "deny" then return false end
	else return false end
	mod.db[key] = value
	if not active and status.state == "faction-stop" and status.resumeTarget and mod.db.gpsAllowEnemy == true then
		local target, title = status.resumeTarget, status.resumeTitle
		local ok, err = mod.GPSStart(target.map, target.x, target.y, title)
		if not ok then ns:Print(err) end
		Notify()
		return true
	end
	if active and active.mode == "navigate" then
		local player = Player()
		if player then
			local route, source, stats = Plan(player, active.target)
			if route then
				local target, title = active.target, active.title
				status.roadSource, status.roadStats = source, stats
				Start(route, title, source, "navigate", target)
			else
				Stop("stopped", true)
				status.instruction = RouteError(source)
				ns:Print(status.instruction)
			end
		end
	end
	Notify()
	return true
end

function mod:GPSOptions(opts, get, off)
	local function set(info, value) mod.GPSSetRoutingOption(info[#info], value) end
	opts.gpsUseRoads = { type = "toggle", name = L["Use bundled roads"], order = 35.1, get = get, set = set, disabled = off,
		desc = L["Plan over the supplied road network and your recorded extensions."] }
	opts.gpsAllowEnemy = { type = "toggle", name = L["Allow enemy roads"], order = 35.2, get = get, set = set, disabled = off,
		desc = L["Allow routes through roads marked for the other faction, with a warning."] }
	opts.gpsOffroad = { type = "select", name = L["Off-road paths"], order = 35.3,
		values = { allow = L["Shortest"], avoid = L["Avoid"], needed = L["Only when needed"], deny = L["Never"] }, get = get, set = set, disabled = off }
	opts.gpsAboveLevel = { type = "select", name = L["Off-road paths above your level"], order = 35.4,
		values = { allow = L["Warn"], avoid = L["Avoid"], deny = L["Never"] }, get = get, set = set, disabled = off }
end
