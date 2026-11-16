-- A bounded, optional view of road nodes and links. The active route keeps its
-- own markers; displaying the bundled network and saved trails never changes it.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local S, Safe = ns.MapStitch, ns.Safe
mod.defaults.gpsShowRoads = false

local LIMIT, NODE_LIMIT, CELL = 800, 500, 0.025
local set, nodeSet, source, recordings, revision, grid, nodeGrid, longEdges, previous
local NODE = { atlas = "WhiteCircle-RaidBlips", texture = "Interface\\Buttons\\WHITE8X8", size = 6, color = { 1, 0.8, 0.35 } }
local RECORDED = { atlas = NODE.atlas, texture = NODE.texture, size = 7, color = { 1, 0.45, 0.1 } }
local LOOKS = {
	default = { texture = "Interface\\Buttons\\WHITE8X8", size = 3, color = { 0.72, 0.67, 0.51 } },
	alliance = { texture = "Interface\\Buttons\\WHITE8X8", size = 3, color = { 0.3, 0.5, 0.9 } },
	horde = { texture = "Interface\\Buttons\\WHITE8X8", size = 3, color = { 0.8, 0.3, 0.25 } },
	swim = { texture = "Interface\\Buttons\\WHITE8X8", size = 3, color = { 0.3, 0.75, 0.8 } },
	offroad = { texture = "Interface\\Buttons\\WHITE8X8", size = 3, color = { 0.5, 0.5, 0.5 } },
	recorded = { texture = "Interface\\Buttons\\WHITE8X8", size = 3, color = RECORDED.color },
}

local function Number(value)
	value = Safe.Value(value)
	if type(value) == "number" and value == value and math.abs(value) < math.huge then return value end
end

local function Compatible(a, b)
	return a.piece == b.piece and a.layer == b.layer and not a.tower and not b.tower
		and not a.towerOf and not b.towerOf and not a.elevator and not b.elevator
end

local function Build()
	local trails = mod.db and mod.db.gpsRoutes
	local changed = mod.GPSRoadsRevision and mod.GPSRoadsRevision() or 0
	if source == ns.GPSRoadData and recordings == trails and revision == changed and grid then return end
	source, recordings, revision = ns.GPSRoadData, trails, changed
	grid, nodeGrid, longEdges, previous = {}, {}, {}, nil
	local function point(continent, raw, look)
		local u, v = S.FromYards(continent, raw.wx, raw.wy)
		u, v = Number(u), Number(v)
		if not u or not v then return end
		local p = { u = u, v = v, raw = raw, look = look }
		local key = math.floor(u / CELL) .. ":" .. math.floor(v / CELL)
		nodeGrid[key] = nodeGrid[key] or {}
		nodeGrid[key][#nodeGrid[key] + 1] = p
		return p
	end
	local function edge(a, b, look)
		local e = { a.u, a.v, b.u, b.v, look }
		local x0, x1 = math.floor(math.min(e[1], e[3]) / CELL), math.floor(math.max(e[1], e[3]) / CELL)
		local y0, y1 = math.floor(math.min(e[2], e[4]) / CELL), math.floor(math.max(e[2], e[4]) / CELL)
		if (x1 - x0 + 1) * (y1 - y0 + 1) > 200 then
			longEdges[#longEdges + 1] = e
		else
			for x = x0, x1 do for y = y0, y1 do
				local key = x .. ":" .. y
				grid[key] = grid[key] or {}
				grid[key][#grid[key] + 1] = e
			end end
		end
	end
	for continent, network in pairs(source and source.networks or {}) do
		local points = {}
		for id, node in pairs(network.nodes or {}) do
			if Number(node.wx) and Number(node.wy) then points[id] = point(continent, node, NODE) end
		end
		for id, point in pairs(points) do
			for target, linked in pairs(point.raw.links or {}) do
				local other = points[target]
				-- Draw a reciprocal pair once, without adding a missing reverse link.
				local reciprocal = other and other.raw.links and other.raw.links[id]
				if linked and other and (not reciprocal or id < target) and Compatible(point.raw, other.raw) then
					local kind = point.raw.type or other.raw.type or "default"
					edge(point, other, LOOKS[kind] or LOOKS.default)
				end
			end
		end
	end
	for _, trail in pairs(trails or {}) do
		local before
		for _, sample in ipairs(type(trail) == "table" and trail.points or {}) do
			local raw = mod.GPSRecordedPoint and mod.GPSRecordedPoint(sample)
			local p = raw and Number(raw.cont) and Number(raw.wx) and Number(raw.wy) and point(raw.cont, raw, RECORDED)
			if p and before and raw.cont == before.raw.cont and Compatible(raw, before.raw)
				and (raw.wx - before.raw.wx) ^ 2 + (raw.wy - before.raw.wy) ^ 2 <= 100 ^ 2 then
				edge(before, p, LOOKS.recorded)
			end
			before = p
		end
	end
end

local function Clip(edge, box)
	local ax, ay, bx, by = edge[1], edge[2], edge[3], edge[4]
	local dx, dy, start, finish = bx - ax, by - ay, 0, 1
	for _, axis in ipairs({ { ax, dx, box[1], box[3] }, { ay, dy, box[2], box[4] } }) do
		if axis[2] == 0 then
			if axis[1] < axis[3] or axis[1] > axis[4] then return end
		else
			local lo, hi = (axis[3] - axis[1]) / axis[2], (axis[4] - axis[1]) / axis[2]
			if lo > hi then lo, hi = hi, lo end
			start, finish = math.max(start, lo), math.min(finish, hi)
			if finish <= start then return end
		end
	end
	local x, y, u, v = ax + start * dx, ay + start * dy, ax + finish * dx, ay + finish * dy
	local length = math.sqrt((u - x) ^ 2 + ((v - y) * 1.5) ^ 2)
	if length > 0 then return { x, y, u, v, edge[5], length } end
end

local function Visible()
	local map = _G.WorldMapFrame
	local stitched = mod.IsStitched and mod.IsStitched() or mod.PadViewOn and mod.PadViewOn()
	return mod.db and mod.db.gpsShowRoads and S.IsBuilt() and stitched
		and map and map:IsShown() and not mod.instanceWorldHidden
		and not (mod.db.hideWorldPinsInInstances and Safe.Call(IsInInstance) and not mod.instanceWorldBrowsing)
end

function mod.GPSRoadsShown() return mod.db and mod.db.gpsShowRoads == true or false end

function mod.GPSSetRoadsShown(shown)
	if not mod.db then return end
	mod.db.gpsShowRoads = shown and true or false
	mod.GPSRefreshRoadView()
	if mod.GPSRefreshPanel then mod.GPSRefreshPanel() end
	if mod.RefreshPanel then mod:RefreshPanel() end
	if ns.NotifyOptions then ns.NotifyOptions() end
end

function mod.GPSRefreshRoadView()
	if not Visible() then
		if set then S.SetPinSetOn(set, false) end
		if nodeSet then S.SetPinSetOn(nodeSet, false) end
		return
	end
	Build()
	if not set then set = S.PinSet("gpsroads", 0, 2) end
	if not nodeSet then nodeSet = S.PinSet("gpsroadnodes", 0, 3) end
	S.SetPinSetOn(set, true)
	S.SetPinSetOn(nodeSet, true)
	local u, v, zoom = mod.ViewNow()
	u, v, zoom = Number(u), Number(v), Number(zoom)
	if not u or not v or not zoom then S.SetPinSetOn(set, false) S.SetPinSetOn(nodeSet, false) return end
	local hu, hv
	if mod.PadViewOn and mod.PadViewOn() and mod.PadViewHalfExtents then hu, hv = mod.PadViewHalfExtents(zoom)
	else hu, hv = mod.ViewHalfExtents(zoom) end
	hu, hv = Number(hu), Number(hv)
	if not hu or not hv or hu <= 0 or hv <= 0 then S.SetPinSetOn(set, false) S.SetPinSetOn(nodeSet, false) return end
	local box = { u - hu, v - hv, u + hu, v + hv }
	if previous and previous[1] == box[1] and previous[2] == box[2]
		and previous[3] == box[3] and previous[4] == box[4] then return end
	previous = box
	local segments, nodes, seen, total = {}, {}, {}, 0
	local function Consider(edge)
		if seen[edge] then return end
		seen[edge] = true
		local clipped = Clip(edge, box)
		if clipped then segments[#segments + 1], total = clipped, total + clipped[6] end
	end
	local x0, x1 = math.floor(box[1] / CELL), math.floor(box[3] / CELL)
	local y0, y1 = math.floor(box[2] / CELL), math.floor(box[4] / CELL)
	local function Nodes(bucket)
		for _, p in ipairs(bucket or {}) do
			if p.u >= box[1] and p.u <= box[3] and p.v >= box[2] and p.v <= box[4] then nodes[#nodes + 1] = p end
		end
	end
	if (x1 - x0 + 1) * (y1 - y0 + 1) > 4096 then
		for _, bucket in pairs(grid) do for _, edge in ipairs(bucket) do Consider(edge) end end
		for _, bucket in pairs(nodeGrid) do Nodes(bucket) end
	else
		for x = x0, x1 do for y = y0, y1 do
			for _, edge in ipairs(grid[x .. ":" .. y] or {}) do Consider(edge) end
			Nodes(nodeGrid[x .. ":" .. y])
		end end
	end
	for _, edge in ipairs(longEdges) do Consider(edge) end
	S.ClearPinSet(nodeSet)
	-- These are actual samples, not the interpolated dots used for road links.
	-- Thin only crowded views; zooming in reveals every visible junction.
	table.sort(nodes, function(a, b) return a.u < b.u or a.u == b.u and a.v < b.v end)
	local stride = math.max(1, #nodes / NODE_LIMIT)
	for i = 1, math.min(#nodes, NODE_LIMIT) do
		local p = nodes[math.floor((i - 1) * stride) + 1]
		local pin = S.AddPin(nodeSet, p.u, p.v, p.look)
		pin:EnableMouse(false)
	end
	S.ClearPinSet(set)
	if total == 0 then return end
	-- Sample the complete visible network by length, rather than filling the
	-- budget with the first roads encountered at the widest zoom.
	local spacing = math.max((box[3] - box[1]) / 100, total / (LIMIT - 1))
	local carry, count = spacing / 2, 0
	for _, segment in ipairs(segments) do
		local along, length = carry, segment[6]
		while along <= length and count < LIMIT do
			local t = along / length
			local pin = S.AddPin(set, segment[1] + t * (segment[3] - segment[1]),
				segment[2] + t * (segment[4] - segment[2]), segment[5])
			pin:EnableMouse(false)
			count, along = count + 1, along + spacing
		end
		carry = along - length
		if count >= LIMIT then break end
	end
end
