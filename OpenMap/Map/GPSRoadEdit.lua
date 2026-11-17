-- Player-authored road nodes and explicit links live apart from the shipped graph.
-- Map coordinates cannot establish terrain walkability: every link is the player's choice.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local Safe, L = ns.Safe, ns.L
mod.defaults.gpsManualRoads = { nextID = 1, nodes = {}, links = {} }

local NODE_LIMIT, LINK_LIMIT = 2000, 4000
local editing, selected = false, nil
local data, roadData, buildings, snapshot
local revision = 0

local function Number(value)
	value = Safe.Value(value)
	return type(value) == "number" and value == value and math.abs(value) < math.huge and value or nil
end

local function Database()
	if not mod.db then return end
	local db = mod.db.gpsManualRoads
	if type(db) ~= "table" then db = { nextID = 1, nodes = {}, links = {} } mod.db.gpsManualRoads = db end
	if type(db.nodes) ~= "table" then db.nodes = {} end
	if type(db.links) ~= "table" then db.links = {} end
	if db ~= data or roadData ~= ns.GPSRoadData or buildings ~= ns.GPSBuildingData then
		data, roadData, buildings, snapshot = db, ns.GPSRoadData, ns.GPSBuildingData, nil
		revision = revision + 1
		selected = nil
	end
	return db
end

local function Custom(ref)
	if type(ref) ~= "string" then return end
	local id = tonumber(ref:match("^m:(%d+)$"))
	id = Number(id)
	return id and id >= 1 and id % 1 == 0 and "m:" .. id == ref and id or nil
end

local function Bundled(ref)
	if type(ref) ~= "string" then return end
	local continent, id = ref:match("^b:(%-?%d+):(%d+)$")
	continent, id = Number(continent and tonumber(continent)), Number(id and tonumber(id))
	if continent and id and id >= 1 and id % 1 == 0 and "b:" .. continent .. ":" .. id == ref then return continent, id end
end

local function Point(ref)
	local db = Database()
	if not db then return end
	if Custom(ref) then
		local p = mod.GPSRecordedPoint(db.nodes[ref])
		if p then p.source, p.editRef = "manual", ref end
		return p
	end
	local continent, id = Bundled(ref)
	if continent and mod.GPSRoadNode then
		local p = mod.GPSRoadNode(continent, id)
		if p then p.editRef = ref end
		return p
	end
end

local function Known(p)
	return p and Number(p.cont) and Number(p.wx) and Number(p.wy)
		and not p.unknown and (not p.ambiguous or p.floorResolved)
end

local function Compatible(a, b)
	return Known(a) and Known(b) and a.cont == b.cont and a.layer == b.layer
		and not (mod.GPSOtherFloor and mod.GPSOtherFloor(a, b))
end

local function OneWay(a, b)
	local continent, first = Bundled(a)
	local other, last = Bundled(b)
	if not continent or continent ~= other or not mod.GPSRoadCanWalk then return false end
	return mod.GPSRoadCanWalk(continent, first, last) ~= mod.GPSRoadCanWalk(continent, last, first)
end

local function Pair(a, b)
	if type(a) ~= "string" or type(b) ~= "string" then return end
	if a > b then a, b = b, a end
	return a .. "|" .. b, a, b
end

local function Count(items)
	local count = 0
	for _ in pairs(items) do count = count + 1 end
	return count
end

local function Refresh()
	if mod.GPSRefreshPanel then mod.GPSRefreshPanel() end
	if mod.RefreshPanel then mod:RefreshPanel() end
	if ns.NotifyOptions then ns.NotifyOptions() end
end

local function Changed()
	revision, snapshot = revision + 1, nil
	if mod.GPSManualRoadsChanged then mod.GPSManualRoadsChanged() end
	Refresh()
end

function mod.GPSRoadEditPoint(ref) return Point(ref) end

function mod.GPSRoadEditSnapshot()
	local db = Database()
	if not db then return { nodes = {}, links = {}, revision = revision } end
	if snapshot then return snapshot end
	local out = { nodes = {}, links = {}, revision = revision }
	local refs = {}
	for ref in pairs(db.nodes) do if Custom(ref) then refs[#refs + 1] = ref end end
	table.sort(refs)
	for i = 1, math.min(#refs, NODE_LIMIT) do
		local p = Point(refs[i])
		if Known(p) then out.nodes[refs[i]] = p end
	end
	local keys = {}
	for key in pairs(db.links) do if type(key) == "string" then keys[#keys + 1] = key end end
	table.sort(keys)
	for _, key in ipairs(keys) do
		local edge = db.links[key]
		if type(edge) == "table" and edge.a ~= edge.b and Pair(edge.a, edge.b) == key then
			local a, b = Point(edge.a), Point(edge.b)
			if Compatible(a, b) and not OneWay(edge.a, edge.b)
				and (not Custom(edge.a) or out.nodes[edge.a]) and (not Custom(edge.b) or out.nodes[edge.b]) then
				out.links[#out.links + 1] = { a = edge.a, b = edge.b }
				if #out.links == LINK_LIMIT then break end
			end
		end
	end
	snapshot = out
	return out
end

function mod.GPSRoadEditing() return editing end

function mod.GPSRoadSelected()
	Database()
	if selected and not Point(selected) then selected = nil end
	return editing and selected or nil
end

function mod.GPSSetRoadEditing(on)
	Database()
	editing = on and true or false
	if not editing then selected = nil end
	if mod.CloseLocationMenu then mod.CloseLocationMenu() end
	if editing and mod.GPSSetRoadsShown then mod.GPSSetRoadsShown(true) end
	Refresh()
	return true
end

function mod.GPSRoadEditSelect(ref)
	if ref ~= nil and not Known(Point(ref)) then return nil, L["Choose a road node on a known floor."] end
	selected = ref
	Refresh()
	return true
end

function mod.GPSRoadEditNearest(map, x, y, radius)
	local target = mod.GPSRecordedPoint({ map, x, y })
	if not Known(target) then return end
	radius = math.max(0, math.min(Number(radius) or 25, 100))
	local nearest, found, distance
	local function Offer(ref, p)
		if Compatible(target, p) then
			local d = (p.wx - target.wx) ^ 2 + (p.wy - target.wy) ^ 2
			if d <= radius * radius and (not distance or d < distance or d == distance and ref < nearest) then
				nearest, found, distance = ref, p, d
			end
		end
	end
	for ref, p in pairs(mod.GPSRoadEditSnapshot().nodes) do Offer(ref, p) end
	local network = ns.GPSRoadData and ns.GPSRoadData.networks and ns.GPSRoadData.networks[target.cont]
	for id in pairs(network and network.nodes or {}) do
		if Number(id) and id >= 1 and id % 1 == 0 then
			local ref = "b:" .. target.cont .. ":" .. id
			Offer(ref, Point(ref))
		end
	end
	return nearest, found
end

function mod.GPSRoadEditLinked(a, b)
	local db = Database()
	local key = Pair(a, b)
	return db and key and type(db.links[key]) == "table" or false
end

function mod.GPSRoadEditAdd(map, x, y, connectFrom)
	local db = Database()
	local p = mod.GPSRecordedPoint({ map, x, y })
	if not db or not p then return nil, L["GPS cannot place a road node here."] end
	if not Known(p) then return nil, L["Choose a road node on a known floor."] end
	local from = connectFrom and Point(connectFrom)
	if connectFrom and not Compatible(from, p) then return nil, L["Road nodes must be on the same continent and floor."] end
	if Count(db.nodes) >= NODE_LIMIT or connectFrom and Count(db.links) >= LINK_LIMIT then return nil, L["The road editor limit has been reached."] end
	local id = Number(db.nextID) or 1
	if id < 1 or id % 1 ~= 0 or id > 2147483647 then id = 1 end
	while db.nodes["m:" .. id] do id = id + 1 end
	local ref = "m:" .. id
	db.nextID = id + 1
	db.nodes[ref] = { p.map, p.x, p.y, piece = p.piece, layer = p.layer }
	if connectFrom then
		local key, a, b = Pair(connectFrom, ref)
		db.links[key] = { a = a, b = b }
	end
	selected = ref
	Changed()
	return ref
end

function mod.GPSRoadEditConnect(a, b)
	local db = Database()
	if not db or a == b then return nil, L["Select two different road nodes."] end
	if not Compatible(Point(a), Point(b)) then return nil, L["Road nodes must be on the same continent and floor."] end
	if OneWay(a, b) then return nil, L["This connection would bypass a one-way road."] end
	local key, first, last = Pair(a, b)
	if db.links[key] then return true end
	if Count(db.links) >= LINK_LIMIT then return nil, L["The road editor limit has been reached."] end
	db.links[key] = { a = first, b = last }
	Changed()
	return true
end

function mod.GPSRoadEditDisconnect(a, b)
	local db, key = Database(), Pair(a, b)
	if not db or not key or not db.links[key] then return nil, L["This road connection was not added by you."] end
	db.links[key] = nil
	Changed()
	return true
end

function mod.GPSRoadEditDelete(ref)
	local db = Database()
	if not db or not Custom(ref) or not db.nodes[ref] then return nil, L["Only your own road nodes can be deleted."] end
	db.nodes[ref] = nil
	for key, edge in pairs(db.links) do
		if type(edge) == "table" and (edge.a == ref or edge.b == ref) then db.links[key] = nil end
	end
	if selected == ref then selected = nil end
	Changed()
	return true
end
