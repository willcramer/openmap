-- GPS uses trails recorded by the player. No road geometry from another addon is bundled.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local S, Safe, L = ns.MapStitch, ns.Safe, ns.L

mod.defaults.gpsRoutes = {}

local MAX_ROUTES, MAX_POINTS, MAX_TOTAL = 50, 2000, 10000
local SAMPLE, REACH, JOIN, ATTACH = 12, 15, 10, 100 -- yards
local active, recording, graph, owned, lastPlayer
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
	if not S.Rect(mapID) then return end
	local u, v = mod.ToWorld(mapID, x, y)
	if not u or not C_Map.GetWorldPosFromMapPos or not CreateVector2D then return end
	local ok, continent, pos = pcall(C_Map.GetWorldPosFromMapPos, mapID, CreateVector2D(x, y))
	continent = Safe.Value(continent)
	if not ok or not Number(continent) or not Safe.Value(pos) then return end
	local wx, wy = Safe.XY(pos)
	wx, wy = Number(wx), Number(wy)
	if not wx or not wy then return end
	return { map = mapID, x = x, y = y, u = u, v = v, cont = continent, wx = wx, wy = wy }
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
	if p then return p.map, p.x, p.y, p.u, p.v, p.cont, p.wx, p.wy end
end

local function Player()
	local mapID, x, y, u, v, cont, wx, wy = mod.GPSPlayer()
	if mapID then return { map = mapID, x = x, y = y, u = u, v = v, cont = cont, wx = wx, wy = wy } end
end

local function Distance(a, b)
	if a.cont ~= b.cont then return math.huge end
	return math.sqrt((a.wx - b.wx) ^ 2 + (a.wy - b.wy) ^ 2)
end

local function Compact(p)
	return { p.map, p.x, p.y }
end

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
	if not p then return end
	owned = p
	if mod.TrackPoint then mod.TrackPoint(p.map, p.x, p.y, active.title) end
end

local function Stop(state, clear)
	local ours = SameWaypoint(owned)
	active, owned = nil, nil
	status.active, status.state = false, state or "stopped"
	status.bearing, status.distance, status.remaining = nil, nil, nil
	status.instruction = L["GPS stopped."]
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
			local p = type(sample) == "table" and Point(sample[1], sample[2], sample[3])
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

local function Start(route, title, state, mode, target)
	Stop("stopped", false)
	lastPlayer = nil
	active = { route = route, index = 1, title = title or L["GPS"], state = state, mode = mode, target = target }
	status.route, status.title, status.state = route, active.title, state
	status.active, status.index, status.total = true, 1, #route
	Track()
	Notify()
	mod.GPSUpdate()
	return true
end

function mod.GPSStart(mapID, x, y, title)
	local target, player = Point(mapID, x, y), Player()
	if not target then return nil, L["GPS cannot navigate to that location."] end
	if not player then return nil, L["GPS is waiting for your position."] end
	local route = RoadRoute(player, target)
	if route then return Start(route, Name(title), "recorded", "navigate", target) end
	if player.cont ~= target.cont then return nil, L["No recorded route connects these continents."] end
	return Start({ target }, Name(title), "direct", "navigate", target)
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
	recording, graph = nil, nil
	status.recording, status.recorded, status.recordingState = nil, 0, nil
	Notify()
	return true
end

function mod.GPSDelete(name)
	if not Routes()[name] then return nil, L["GPS route not found."] end
	Routes()[name], graph = nil, nil
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
		local p = type(sample) == "table" and Point(sample[1], sample[2], sample[3])
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

function mod.GPSUpdate()
	if not active and not recording then return end
	local player = Player()
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
		status.state, status.instruction, status.bearing = "waiting", L["GPS is waiting for your position."], nil
		status.distance, status.remaining = nil, nil
		return
	end
	local route, index = active.route, active.index
	local p = route[index]
	if player.cont ~= p.cont then
		status.state, status.instruction, status.bearing = "waiting", L["Return to the route's continent to continue GPS."], nil
		status.distance, status.remaining = nil, nil
		return
	end
	local d = Distance(player, p)
	local passed = false
	if index > 1 then
		local close, t = SegmentDistance(player, route[index - 1], p)
		passed = close < REACH and t >= 0.98
	end
	if d <= REACH or passed then
		if index == #route then
			if active.mode == "loop" then active.index = 1
			elseif active.mode == "pingpong" then
				local reversed = {}
				for i = #route, 1, -1 do reversed[#reversed + 1] = route[i] end
				active.route, active.index, status.route = reversed, 2, reversed
			else Stop("arrived", true) status.instruction = L["You have arrived."] return end
		else active.index = index + 1 end
		Track()
		Notify()
		index, route = active.index, active.route
		p = route[index]
		d = Distance(player, p)
	end
	-- Replan after leaving the current road, with a cooldown and actual movement required.
	local now = GetTime()
	if active.mode == "navigate" and active.state == "recorded" and now >= (active.replanAt or 0) then
		local off = index > 1 and SegmentDistance(player, route[index - 1], p) or d
		if off > 60 and (not lastPlayer or Distance(lastPlayer, player) > 20) then
			active.replanAt, lastPlayer = now + 5, player
			local newRoute = RoadRoute(player, active.target)
			if not newRoute and player.cont == active.target.cont then
				newRoute, active.state = { active.target }, "direct"
			end
			if newRoute then
				active.route, active.index, status.route = newRoute, 1, newRoute
				Track()
				Notify()
				route, index, p = newRoute, 1, newRoute[1]
				d = Distance(player, p)
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
	elseif status.turn == "left" then status.instruction = L["Turn left at the next point."]
	elseif status.turn == "right" then status.instruction = L["Turn right at the next point."]
	else status.instruction = L["Follow the recorded trail."] end
end

function mod.GPSStatus() return status end
