-- Interpret imported room geometry without joining rooms or floors by proximity.
-- Coordinates here are C_Map world X/Y, already swapped once by the importer.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local Safe = ns.Safe
local cache, buildingSource, roadSource = {}, nil, nil
local EPSILON = 0.001
local observed, crossing, samples, eventOwner = nil, nil, {}, nil

local function Number(value)
	value = Safe.Value(value)
	if type(value) == "number" and value == value and value > -math.huge and value < math.huge then return value end
end

local function Index(continent)
	if buildingSource ~= ns.GPSBuildingData or roadSource ~= ns.GPSRoadData then
		buildingSource, roadSource, cache = ns.GPSBuildingData, ns.GPSRoadData, {}
	end
	if cache[continent] then return cache[continent] end
	local network = buildingSource and buildingSource.networks and buildingSource.networks[continent]
	local indexed = { pieces = {}, network = network }
	cache[continent] = indexed
	if not network then return indexed end
	local layers = {}
	local roads = roadSource and roadSource.networks and roadSource.networks[continent]
	for _, node in pairs(roads and roads.nodes or {}) do
		if node.piece then
			local layer = node.layer or false
			if not layers[node.piece] then layers[node.piece] = { value = layer }
			elseif layers[node.piece].value ~= layer then layers[node.piece].mixed = true end
		end
	end
	for _, building in pairs(network.buildings or {}) do
		for group, room in pairs(building.pieces or {}) do
			local key = tostring(building.id) .. ":" .. tostring(group)
			local hint = layers[key]
			local layer = room.indoor and true or nil
			if hint and not hint.mixed then layer = hint.value or nil end
			indexed.pieces[key] = { piece = key, building = building.id, group = group,
				room = room, layer = layer, layerAmbiguous = hint and hint.mixed or false }
		end
	end
	return indexed
end

local function OnEdge(x, y, ax, ay, bx, by)
	local dx, dy = bx - ax, by - ay
	local length = dx * dx + dy * dy
	if length == 0 then return (x - ax) ^ 2 + (y - ay) ^ 2 <= EPSILON ^ 2 end
	local t = ((x - ax) * dx + (y - ay) * dy) / length
	if t < 0 or t > 1 then return false end
	return (x - ax - t * dx) ^ 2 + (y - ay - t * dy) ^ 2 <= EPSILON ^ 2
end

local function Contains(polygon, x, y)
	if type(polygon) ~= "table" or #polygon < 3 then return false end
	local inside = false
	local previous = polygon[#polygon]
	for _, current in ipairs(polygon) do
		local ax, ay, bx, by = previous[1], previous[2], current[1], current[2]
		if OnEdge(x, y, ax, ay, bx, by) then return true end
		if (ay > y) ~= (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay) then inside = not inside end
		previous = current
	end
	return inside
end

local function Bounds(context, room)
	context.zmin, context.zmax = room.zmin, room.zmax
	context.minZ, context.maxZ = room.zmin, room.zmax
	-- An enclosing WMO group's middle is not the height of a walkable floor.
	if room.zmin == room.zmax then context.z = room.zmin end
	return context
end

-- Explicit road piece metadata is authoritative. Do not infer a midpoint height
-- for rooms whose bounds can span several stair landings or an entire building.
function mod.GPSRoadNodeContext(continent, node)
	continent = Number(continent)
	if not continent or type(node) ~= "table" then return end
	local context = { world = continent, map = node.map or node[3], piece = node.piece, layer = node.layer }
	local found = node.piece and Index(continent).pieces[node.piece]
	if not found then return context end
	context.building, context.group = found.building, found.group
	context.inside = found.room.indoor and true or false
	if context.layer == nil then context.layer = found.layer end
	context.pieces = { [node.piece] = true }
	return Bounds(context, found.room)
end

-- Different rooms can share a floor. Only compare known vertical intervals in
-- one building; an unknown piece is not evidence for rejecting a route point.
function mod.GPSOtherFloor(a, b, margin)
	if type(a) ~= "table" or type(b) ~= "table" or type(a.piece) ~= "string" or type(b.piece) ~= "string"
		or a.piece == b.piece then return false end
	local building = a.piece:match("^(%d+):%d+$")
	if not building or building ~= b.piece:match("^(%d+):%d+$") then return false end
	local ac, bc = Number(a.cont or a.world), Number(b.cont or b.world)
	if ac and bc and ac ~= bc then return false end
	local continent = ac or bc
	local function Interval(point)
		local low, high = Number(point.minZ or point.zmin), Number(point.maxZ or point.zmax)
		if (not low or not high) and continent then
			local room = mod.GPSRoadNodeContext(continent, point)
			low, high = room and Number(room.minZ), room and Number(room.maxZ)
		end
		if low and high and low <= high then return low, high end
	end
	local alo, ahi = Interval(a)
	local blo, bhi = Interval(b)
	if not alo or not blo then return false end
	local tolerance = math.max(0, Number(margin) or 0.5)
	local overlap = math.min(ahi, bhi) - math.max(alo, blo)
	return overlap < tolerance
end

-- Unknown Z never chooses one of overlapping floors. Callers can inspect the
-- candidate set for diagnostics, but must not treat ambiguity as outdoor ground.
function mod.GPSRoomContext(continent, wx, wy, z, mapID)
	continent, wx, wy = Number(continent), Number(wx), Number(wy)
	z, mapID = Number(z), Number(mapID)
	if not continent or not wx or not wy then return { unknown = true, ambiguous = true, reason = "position" } end
	local context = { world = continent, map = mapID, z = z, pieces = {}, candidates = {}, inside = false, ambiguous = false }
	local indexed = Index(continent)
	local network = indexed.network
	if not network then return context end
	local cell = buildingSource.cell or 256
	-- The source cell encoding uses HBD's old Y/X ordering; geometry does not.
	local key = (math.floor(wy / cell) + 128) * 256 + math.floor(wx / cell) + 128
	for _, index in ipairs(network.cells and network.cells[key] or {}) do
		local building = network.buildings[index]
		local box = building and building.bounds
		if box and wx >= box[1] - EPSILON and wx <= box[3] + EPSILON
			and wy >= box[2] - EPSILON and wy <= box[4] + EPSILON then
			for group, room in pairs(building.pieces or {}) do
				if (not z or z >= room.zmin - EPSILON and z <= room.zmax + EPSILON) and Contains(room.polygon, wx, wy) then
					local piece = tostring(building.id) .. ":" .. tostring(group)
					if not context.pieces[piece] then
						context.pieces[piece] = true
						local found = indexed.pieces[piece]
						context.candidates[#context.candidates + 1] = Bounds({ piece = piece,
							building = building.id, group = group, inside = room.indoor and true or false,
							layer = found and found.layer }, room)
					end
				end
			end
		end
	end
	table.sort(context.candidates, function(a, b) return a.piece < b.piece end)
	local count = #context.candidates
	if count == 0 then return context end
	local first = context.candidates[1]
	context.inside = first.inside
	context.layer = first.layer
	for i = 2, count do
		local other = context.candidates[i]
		if context.inside ~= other.inside then context.inside = nil end
		if context.layer ~= other.layer then context.layer = nil end
	end
	context.ambiguous = count > 1
	if count == 1 then
		context.piece, context.building, context.group = first.piece, first.building, first.group
		context.zmin, context.zmax, context.minZ, context.maxZ = first.zmin, first.zmax, first.zmin, first.zmax
	end
	return context
end

local function Read(fn, ...)
	if type(fn) ~= "function" then return end
	local ok, value = pcall(fn, ...)
	if ok then return Safe.Value(value) end
end

local function Choose(context, pieces, evidence)
	local result = {}
	for key, value in pairs(context) do result[key] = value end
	result.piece, result.building, result.group = nil, nil, nil
	result.zmin, result.zmax, result.minZ, result.maxZ = nil, nil, nil, nil
	result.candidates, result.pieces = {}, {}
	for _, candidate in ipairs(context.candidates or {}) do
		if pieces[candidate.piece] then
			result.candidates[#result.candidates + 1] = candidate
			result.pieces[candidate.piece] = true
		end
	end
	if #result.candidates == 0 then return end
	local first = result.candidates[1]
	result.inside, result.layer = first.inside, first.layer
	for i = 2, #result.candidates do
		local candidate = result.candidates[i]
		if result.inside ~= candidate.inside then result.inside = nil end
		if result.layer ~= candidate.layer then result.layer = nil end
	end
	result.ambiguous = #result.candidates ~= 1
	result.evidence = evidence
	if not result.ambiguous then
		result.piece, result.building, result.group = first.piece, first.building, first.group
		result.zmin, result.zmax, result.minZ, result.maxZ = first.zmin, first.zmax, first.zmin, first.zmax
	end
	if context.cityLayer == 1458 then result.layer = 1458 end
	return result
end

-- A city map alone does not tell the Ruins of Lordaeron from Undercity below.
-- Area 153 supplies the client's localized surface name; unknown text is not
-- evidence for either floor.
local function CityLayer(mapID)
	if mapID ~= 1458 then return end
	local subzone = Read(_G.GetSubZoneText)
	if type(subzone) ~= "string" or subzone == "" then return end
	local maps = _G.C_Map
	local surface = maps and Read(maps.GetAreaInfo, 153) or Read(_G.GetAreaInfo, 153)
	if type(surface) ~= "string" or surface == "" then return end
	if subzone == surface then return false end
	return 1458
end

local function FilterLive(context, mapID)
	context.candidates, context.pieces = context.candidates or {}, context.pieces or {}
	if context.piece and #context.candidates == 0 then
		context.pieces[context.piece] = true
		context.candidates[1] = { piece = context.piece, layer = context.layer, inside = context.inside,
			zmin = context.zmin or context.minZ, zmax = context.zmax or context.maxZ }
	end
	local layer = CityLayer(mapID)
	local indoors = Read(_G.IsIndoors)
	local allowed = {}
	local hasCityFloor = false
	if layer == 1458 then
		for _, candidate in ipairs(context.candidates) do if candidate.layer == 1458 then hasCityFloor = true break end end
	end
	for _, candidate in ipairs(context.candidates) do
		if (layer ~= false or candidate.layer ~= 1458)
			and (not hasCityFloor or candidate.layer == 1458)
			and (indoors == nil or candidate.inside == indoors) then allowed[candidate.piece] = true end
	end
	local filtered = Choose(context, allowed, "geometry")
	if filtered then context = filtered
	elseif next(allowed) == nil and (#context.candidates > 0 or indoors ~= nil) then
		context = { world = context.world, map = context.map, z = context.z, candidates = {}, pieces = {},
			inside = indoors == true, ambiguous = indoors == true, unknown = indoors == true }
	end
	if layer ~= nil then
		context.cityLayer, context.layerEvidence = layer, "subzone"
		if layer == 1458 then context.layer, context.inside = 1458, true
		elseif context.layer == 1458 then context.layer = nil end
	end
	return context
end

local function NearPortal(portal, x, y)
	local polygon = portal.polygon
	if not polygon or #polygon < 2 then return false end
	if #polygon > 2 and Contains(polygon, x, y) then return true end
	for i = 1, #polygon - 1 do
		local a, b = polygon[i], polygon[i + 1]
		local dx, dy = b[1] - a[1], b[2] - a[2]
		local length = dx * dx + dy * dy
		local t = length > 0 and math.max(0, math.min(1, ((x - a[1]) * dx + (y - a[2]) * dy) / length)) or 0
		if (x - a[1] - t * dx) ^ 2 + (y - a[2] - t * dy) ^ 2 <= 64 then return true end
	end
	return false
end

local function CrossedPieces(context, previous, x, y, z)
	local network = Index(context.world).network
	if not network or not previous or previous.world ~= context.world then return end
	local found, seen = {}, {}
	local cell = buildingSource.cell or 256
	local cx, cy = math.floor(y / cell), math.floor(x / cell)
	for ox = -1, 1 do for oy = -1, 1 do
		local key = (cx + ox + 128) * 256 + cy + oy + 128
		for _, index in ipairs(network.cells and network.cells[key] or {}) do
			if not seen[index] then
				seen[index] = true
				local building = network.buildings[index]
				for _, portal in ipairs(building and building.portals or {}) do
					if (not z or z >= portal.zmin - EPSILON and z <= portal.zmax + EPSILON) and NearPortal(portal, x, y) then
						local plus = tostring(building.id) .. ":" .. tostring(portal.from)
						local minus = tostring(building.id) .. ":" .. tostring(portal.to)
						local hadPlus, hadMinus = previous.pieces[plus], previous.pieces[minus]
						local target
						local nx, ny = portal.nx or 0, portal.ny or 0
						local direction = (x - previous.x) * nx + (y - previous.y) * ny
						if nx == 0 and ny == 0 then
							-- A horizontal hole has no XY direction. Prior membership
							-- can identify its other side; without it both remain possible.
							if hadPlus and not hadMinus then target = minus
							elseif hadMinus and not hadPlus then target = plus end
						elseif math.abs(direction) > 0.05 then
							local p = portal.polygon[1]
							local side = (x - p[1]) * nx + (y - p[2]) * ny
							local priorSide = (previous.x - p[1]) * nx + (previous.y - p[2]) * ny
							if side * priorSide <= EPSILON ^ 2 and side * direction >= -EPSILON then
								target = direction > 0 and plus or minus
							end
						end
						-- A known room can leave only through one of its own portals.
						if target and (not previous.piece or hadPlus or hadMinus) and context.pieces[target] then
							if not previous.piece or target ~= previous.piece then found[target] = true end
						elseif not target and nx == 0 and ny == 0 and not previous.piece then
							if context.pieces[plus] then found[plus] = true end
							if context.pieces[minus] then found[minus] = true end
						end
					end
				end
			end
		end
	end end
	if next(found) then return found end
end

function mod.GPSResetRoom()
	observed, crossing, samples = nil, nil, {}
end

-- Live-only inference. A NEW_WMO_CHUNK event names no room; combine it with
-- imported portal sides and recent movement, retaining uncertainty when the
-- evidence still allows more than one floor. Map-click targets stay static.
function mod.GPSObserveRoom(continent, wx, wy, mapID, z)
	continent, wx, wy, mapID, z = Number(continent), Number(wx), Number(wy), Number(mapID), Number(z)
	if not continent or not wx or not wy then
		mod.GPSResetRoom()
		return { unknown = true, ambiguous = true, reason = "position" }
	end
	local now = Number(Read(_G.GetTime)) or 0
	if observed and (observed.world ~= continent or now - observed.time > 5
		or (wx - observed.x) ^ 2 + (wy - observed.y) ^ 2 > 10000) then mod.GPSResetRoom() end
	local context = mod.GPSRoomContext(continent, wx, wy, z, mapID)
	context.world, context.map = continent, mapID
	context = FilterLive(context, mapID)
	if observed and context.cityLayer ~= nil and observed.cityLayer ~= nil and context.cityLayer ~= observed.cityLayer then
		mod.GPSResetRoom()
	end
	if crossing and now - crossing.time > 1 then crossing = nil end
	local entered
	if crossing then
		local anchor = crossing.anchor
		if not anchor or (anchor.x - wx) ^ 2 + (anchor.y - wy) ^ 2 < 0.01 then
			for i = #samples, 1, -1 do
				local sample = samples[i]
				if sample.world == continent and now - sample.time <= 0.8
					and (sample.x - wx) ^ 2 + (sample.y - wy) ^ 2 >= 0.01 then
					local membership = anchor or sample
					anchor = { world = continent, x = sample.x, y = sample.y,
						piece = membership.piece, pieces = membership.pieces }
					break
				end
			end
		end
		local candidates = CrossedPieces(context, anchor, wx, wy, z)
		if candidates then entered = Choose(context, candidates, "portal") end
		if entered then context, crossing = entered, nil end
	end
	if not entered and observed then
		local retained = Choose(context, observed.pieces, "continuity")
		if retained then context = retained end
	end
	if context.ambiguous and not entered then
		local indoor, count = {}, 0
		for _, candidate in ipairs(context.candidates) do
			if candidate.inside then indoor[candidate.piece], count = true, count + 1 end
		end
		if count == 1 then context = Choose(context, indoor, "unique-indoor") end
	end
	observed = { world = continent, x = wx, y = wy, time = now, piece = context.piece,
		pieces = context.pieces or {}, cityLayer = context.cityLayer }
	samples[#samples + 1] = observed
	while #samples > 8 or samples[1] and now - samples[1].time > 1 do table.remove(samples, 1) end
	return context
end

function mod:SetupGPSRooms()
	if eventOwner or not ns.RegisterEvent then return end
	eventOwner = {}
	ns.RegisterEvent(eventOwner, "NEW_WMO_CHUNK", function()
		crossing = { time = Number(Read(_G.GetTime)) or 0, anchor = observed }
	end)
	for _, event in ipairs({ "PLAYER_ENTERING_WORLD", "PLAYER_LEAVING_WORLD", "LOADING_SCREEN_ENABLED", "ZONE_CHANGED_NEW_AREA" }) do
		ns.RegisterEvent(eventOwner, event, mod.GPSResetRoom)
	end
end
