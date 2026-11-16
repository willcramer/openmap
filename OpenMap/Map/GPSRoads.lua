-- Route only over the bundled network's explicit links. Spatial proximity never
-- creates a road: opposite banks, rooms and overlapping floors can be adjacent.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local Safe = ns.Safe
local cachedData, cachedNetworks
local extraCache = {}

local function Number(value)
	value = Safe.Value(value)
	return type(value) == "number" and value == value and math.abs(value) < math.huge and value or nil
end

local function Distance(a, b)
	return math.sqrt((a.wx - b.wx) ^ 2 + (a.wy - b.wy) ^ 2)
end

local function Network(continent)
	local data = ns.GPSRoadData
	if data ~= cachedData then cachedData, cachedNetworks = data, {} end
	if not data or not data.networks or not data.networks[continent] then return end
	if cachedNetworks[continent] then return cachedNetworks[continent] end
	local source = data.networks[continent].nodes or {}
	local graph = { nodes = {}, list = {}, links = {}, edgeCount = 0, source = source }
	for id, raw in pairs(source) do
		if Number(id) and Number(raw.wx) and Number(raw.wy) then
			local p = mod.GPSRoadPoint and mod.GPSRoadPoint(raw, continent)
			if not p then p = { wx = raw.wx, wy = raw.wy, cont = continent, map = raw.map } end
			-- Keep the imported table read-only, including its floor and travel metadata.
			local point = {}
			for key, value in pairs(p) do point[key] = value end
			for key, value in pairs(raw) do if key ~= "links" and key ~= "map" then point[key] = value end end
			point.map, point.sourceMap = p.map or raw.map, raw.map
			point.cont, point.nodeID, point.source = continent, id, "bundled"
			graph.nodes[id], graph.list[#graph.list + 1], graph.links[id] = point, id, {}
		end
	end
	table.sort(graph.list)
	for _, id in ipairs(graph.list) do
		local p = graph.nodes[id]
		local tower = p.tower
		if tower and Number(tower.x) and Number(tower.y) and Number(tower.r) and Number(tower.turns) then
			local angle0 = math.atan2(p.wy - tower.x, p.wx - tower.y)
			local sign = tower.cw and -1 or 1
			local function mark(node, turn)
				if not node or not Number(turn) then return end
				local configured = turn
				if node ~= p then
					-- The authored winding level is coarse; the endpoint's actual
					-- bearing sets its last fraction of a turn, including side exits.
					local angle = math.atan2(node.wy - tower.x, node.wx - tower.y)
					local fraction = ((angle - angle0) * sign / (2 * math.pi)) % 1
					if Distance(node, { wx = tower.y, wy = tower.x }) > tower.r * 0.7 then
						turn = fraction + math.max(0, math.floor(math.max(configured, 0.25) - fraction + 0.5))
					else turn = math.max(configured, 0.25) end
				end
				node.stairOwner, node.stairTurn = id, turn
				node.stairTurnsConfigured = configured
				node.centerWX, node.centerWY, node.stairRadius = tower.y, tower.x, tower.r
				node.stairCW, node.stairAngleSign, node.stairAngle0 = tower.cw and true or false, sign, angle0
			end
			mark(p, 0)
			mark(graph.nodes[tower.top], tower.turns)
			for exit, turn in pairs(tower.exits or {}) do mark(graph.nodes[exit], turn) end
		end
	end
	for _, id in ipairs(graph.list) do
		local raw = source[id]
		for nextID, linked in pairs(raw.links or {}) do
			local target = source[nextID]
			-- An arrow stored on target->id forbids this reverse direction, even
			-- though the editable network retains reciprocal adjacency entries.
			local reverseOnly = target and target.oneway and target.oneway[id]
			if linked and graph.nodes[nextID] and not reverseOnly then
				graph.links[id][#graph.links[id] + 1] = nextID
				graph.edgeCount = graph.edgeCount + 1
			end
		end
		table.sort(graph.links[id])
	end
	cachedNetworks[continent] = graph
	return graph
end

local function Enemy(p, context)
	if p.type ~= "alliance" and p.type ~= "horde" then return false end
	local own = type(context.faction) == "string" and context.faction:lower()
	return p.type ~= own
end

local function High(p, context)
	if p.type ~= "offroad" or not context.minLevel or not context.playerLevel then return false end
	local minimum = context.minLevel(p)
	return minimum and minimum > context.playerLevel or false
end

local function Allowed(p, context)
	if context.ghost then return true end
	if Enemy(p, context) and not context.allowEnemy then return false end
	if p.type == "swim" and context.swim == "deny" then return false end
	if p.type == "offroad" and context.offroad == "deny" then return false end
	if High(p, context) and (context.aboveLevel == "deny" or context.aboveLevel == "never") then return false end
	return true
end

local function EndpointAllowed(p, at, starting, context)
	if not Allowed(p, context) or (starting and p.nostart) then return false end
	if starting and context.tops and context.tops[p.nodeID] then return true end
	if at.piece and p.piece and at.piece ~= p.piece
		and (not mod.GPSOtherFloor or mod.GPSOtherFloor(at, p)) then return false end
	if not at.piece and at.pieces and next(at.pieces) and p.piece and not at.pieces[p.piece] then return false end
	if at.layer ~= nil and p.layer ~= nil and at.layer ~= p.layer then return false end
	-- A map click without a room cannot choose an overlapping indoor floor.
	if not at.piece and p.layer and not at.floorResolved and not context.allowUnknownFloor
		and not (type(p.layer) == "number" and at.layer == p.layer) then return false end
	if at.z and p.z and math.abs(at.z - p.z) > (context.floorTolerance or 8) then return false end
	if at.z and p.minZ and p.maxZ and (at.z < p.minZ - 2 or at.z > p.maxZ + 2) then return false end
	return true
end

local function Projection(at, a, b)
	local dx, dy = b.wx - a.wx, b.wy - a.wy
	local length = dx * dx + dy * dy
	local t = length > 0 and math.max(0, math.min(1, ((at.wx - a.wx) * dx + (at.wy - a.wy) * dy) / length)) or 0
	local wx, wy = a.wx + dx * t, a.wy + dy * t
	return math.sqrt((at.wx - wx) ^ 2 + (at.wy - wy) ^ 2), t, wx, wy
end

local function GeometryCompatible(a, b)
	-- Inter-floor and spiral links are traversable graph edges, not surfaces to
	-- which a nearby point may attach halfway up from outside the building.
	return not (a.stairOwner and a.stairOwner == b.stairOwner)
		and (a.layer == b.layer or (type(a.layer) ~= "number" and type(b.layer) ~= "number" and not a.elevator and not b.elevator))
		and not (mod.GPSOtherFloor and mod.GPSOtherFloor(a, b))
end

local function Attachment(graph, at, starting, context)
	local nearest, distance, blocked, floor
	local pin = not starting and not at.nodeID
	local edge, edgeDistance, preferredEdge, preferredDistance, preferredRank
	local limit = context.attachLimit or math.huge
	for _, id in ipairs(graph.list) do
		local p = graph.nodes[id]
		local d = Distance(at, p)
		if d <= limit and not Allowed(p, context) then blocked = true end
		if d <= limit and not EndpointAllowed(p, at, starting, context) and Allowed(p, context) and not p.nostart then floor = true end
		if EndpointAllowed(p, at, starting, context) then
			if not distance or d < distance then nearest, distance = { node = id, point = p }, d end
		end
	end
	-- Choose one nearest piece of road rather than connecting to every point in
	-- a radius, which would cut across hairpins and jump over missing bridges.
	for _, id in ipairs(graph.list) do
		local a = graph.nodes[id]
		if EndpointAllowed(a, at, starting, context) then
			for _, nextID in ipairs(graph.links[id]) do
				local b = graph.nodes[nextID]
				if GeometryCompatible(a, b) and EndpointAllowed(b, at, starting, context) then
					local d, t, wx, wy = Projection(at, a, b)
					local candidate = { a = id, b = nextID, t = t, point = { wx = wx, wy = wy, cont = at.cont,
						map = a.map, piece = a.piece, layer = a.layer, source = "bundled",
						roadEnemy = Enemy(a, context) or Enemy(b, context), roadHigh = High(a, context) or High(b, context),
						roadOffroad = a.type == "offroad" or b.type == "offroad", roadSwim = a.type == "swim" or b.type == "swim" } }
					if pin then
						if not edgeDistance or d < edgeDistance - 0.00001 then edge, edgeDistance = candidate, d end
						local room = at.piece and a.piece == at.piece and b.piece == at.piece
						local layer = at.layer and a.layer and b.layer and (at.layer == true or (a.layer == at.layer and b.layer == at.layer))
						local rank = room and 0 or layer and 1 or nil
						if rank and d <= (context.entryRadius or 100) and (not preferredRank or rank < preferredRank
							or (rank == preferredRank and d < preferredDistance - 0.00001)) then
							preferredEdge, preferredDistance, preferredRank = candidate, d, rank
						end
					elseif t > 0.00001 and t < 0.99999 and (not distance or d < distance - 0.00001) then
						nearest, distance = candidate, d
					end
				end
			end
		end
	end
	if pin and edge then nearest, distance = preferredEdge or edge, preferredDistance or edgeDistance end
	if not nearest or distance > limit then return nil, blocked and "blocked" or floor and "floor" or "no-coverage" end
	nearest.distance = distance
	return nearest
end

local function Parts(graph)
	if graph.parts then return graph.parts end
	local roots = {}
	for _, id in ipairs(graph.list) do roots[id] = id end
	local function root(id)
		while roots[id] ~= id do roots[id] = roots[roots[id]] id = roots[id] end
		return id
	end
	for _, id in ipairs(graph.list) do
		for other in pairs(graph.source[id] and graph.source[id].links or {}) do
			if roots[other] then roots[root(other)] = root(id) end
		end
		for _, other in ipairs(graph.links[id]) do roots[root(other)] = root(id) end
	end
	for _, id in ipairs(graph.list) do roots[id] = root(id) end
	graph.parts = roots
	return roots
end

local function StartAttachments(graph, at, context)
	local candidates, nearest, blocked, floor = {}, nil, false, false
	local limit, radius = context.attachLimit or math.huge, context.entryRadius or 100
	local parts = Parts(graph)
	local function offer(entry, distance)
		if distance > limit then return end
		entry.distance, entry.part = distance, parts[entry.node or entry.a]
		candidates[#candidates + 1] = entry
		if not nearest or distance < nearest then nearest = distance end
	end
	local function eligible(p)
		if not EndpointAllowed(p, at, true, context) then return false end
		if context.tops and next(context.tops) then return context.tops[p.nodeID] and true or false end
		if p.stairOwner and p.stairTurn ~= 0 and not at.stairOwner then return false end
		if p.stairOwner and p.stairTurn > 0 and not at.stairOwner
			and not (context.tops and context.tops[p.nodeID])
			and not (at.piece and at.piece == p.piece)
			and not (at.z and p.minZ and p.maxZ and at.z >= p.minZ - 2 and at.z <= p.maxZ + 2) then return false end
		return true
	end
	for _, id in ipairs(graph.list) do
		local p = graph.nodes[id]
		local distance = Distance(at, p)
		if distance <= limit then
			if not Allowed(p, context) then blocked = true
			elseif not eligible(p) and not p.nostart then floor = true end
		end
		if eligible(p) and (not next(graph.source[id] and graph.source[id].links or {})
			or (context.tops and context.tops[id]) or p.stairOwner) then offer({ node = id, point = p }, distance) end
	end
	local seen = {}
	for _, id in ipairs(graph.list) do
		local a = graph.nodes[id]
		if eligible(a) then
			for _, other in ipairs(graph.links[id]) do
				local key = math.min(id, other) .. ":" .. math.max(id, other)
				local b = graph.nodes[other]
				if not seen[key] and eligible(b) and GeometryCompatible(a, b) then
					seen[key] = true
					local distance, t, wx, wy = Projection(at, a, b)
					offer({ a = id, b = other, t = t, point = { wx = wx, wy = wy, cont = at.cont,
							map = a.map, piece = a.piece, layer = a.layer, source = "bundled",
							roadOffroad = a.type == "offroad" or b.type == "offroad",
							roadSwim = a.type == "swim" or b.type == "swim",
							roadHigh = High(a, context) or High(b, context),
							roadEnemy = Enemy(a, context) or Enemy(b, context) } }, distance)
				elseif not seen[key] and a.layer ~= b.layer then
					-- A doorway or lift is entered at the end on your level,
					-- never halfway through its vertical transition.
					offer({ node = id, point = a }, Distance(at, a))
				end
			end
		end
	end
	if not nearest then return nil, blocked and "blocked" or floor and "floor" or "no-coverage" end
	local function entryHas(entry, key, value)
		local a = graph.nodes[entry.node or entry.a]
		local b = entry.b and graph.nodes[entry.b]
		return a[key] == value or (b and b[key] == value) or false
	end
	local function adjusted(entry, key, value)
		if entry.node or not key then return entry end
		local a, b = graph.nodes[entry.a], graph.nodes[entry.b]
		local afit, bfit = a[key] == value, b[key] == value
		if afit == bfit then return entry end
		local copy, point = {}, {}
		for k, v in pairs(entry) do copy[k] = v end
		for k, v in pairs(afit and a or b) do point[k] = v end
		point.roadOffroad, point.roadSwim, point.roadHigh = entry.point.roadOffroad, entry.point.roadSwim, entry.point.roadHigh
		copy.point, copy.distance, copy.t = point, Distance(at, point), afit and 0 or 1
		return copy
	end
	local preferred, preferredValue
	local function nearestWith(key, value)
		local distance
		for _, entry in ipairs(candidates) do
			if entryHas(entry, key, value) then
				local candidate = adjusted(entry, key, value)
				if candidate.distance <= radius and (not distance or candidate.distance < distance) then distance = candidate.distance end
			end
		end
		return distance
	end
	if at.layer ~= nil then
		local desired = at.layer
		if desired == false then desired = nil end
		local distance = nearestWith("layer", desired)
		if distance then preferred, preferredValue, nearest = "layer", desired, distance end
	end
	local pieceDistance = at.piece and nearestWith("piece", at.piece)
	local areaDistance = at.area and nearestWith("area", at.area)
	if pieceDistance and pieceDistance <= nearest + 20 then preferred, preferredValue, nearest = "piece", at.piece, pieceDistance
	elseif areaDistance and areaDistance <= nearest + 40 then preferred, preferredValue, nearest = "area", at.area, areaDistance end
	local slack = context.entrySlack or ((at.layer ~= nil and at.layer ~= false) and 20 or 15)
	for _, id in ipairs(graph.list) do
		local p = graph.nodes[id]
		for lowerID in pairs(p.oneway or {}) do
			local lower = graph.nodes[lowerID]
			if lower and Distance(at, lower) <= 50 and Distance(at, lower) < Distance(at, p) then slack = math.min(slack, 10) end
		end
	end
	local out, closest = {}, {}
	for _, entry in ipairs(candidates) do
		if not closest[entry.part] or entry.distance < closest[entry.part].distance then closest[entry.part] = entry end
		if not preferred or entryHas(entry, preferred, preferredValue) then
			local candidate = adjusted(entry, preferred, preferredValue)
			if candidate.distance <= math.min(radius, nearest + slack) + 0.00001 then out[#out + 1] = candidate end
		end
	end
	for _, entry in pairs(closest) do if entry.distance > radius then out[#out + 1] = entry end end
	return out
end

local function EdgeLength(a, b)
	if a.stairOwner and a.stairOwner == b.stairOwner then
		local radius, sweep = a.stairRadius, math.abs(b.stairTurn - a.stairTurn) * 2 * math.pi
		local steps = math.max(1, math.ceil(sweep / (math.pi / 6) - 1e-9))
		local circumference = 2 * radius * math.sin(sweep / (2 * steps)) * steps
		local angle0 = a.stairAngle0
		local function landing(p)
			local angle = angle0 + a.stairAngleSign * p.stairTurn * 2 * math.pi
			return { wx = a.centerWX + radius * math.cos(angle), wy = a.centerWY + radius * math.sin(angle) }
		end
		return (a.towerOf == a.stairOwner and 0 or Distance(a, landing(a))) + circumference
			+ (b.towerOf == b.stairOwner and 0 or Distance(b, landing(b)))
	end
	return Distance(a, b)
end

local function OffroadMultiplier(context)
	if context.ghost then return 1 end
	if context.offroad == "needed" then return context.neededMultiplier or 1000 end
	if context.offroad == "avoid" then return context.offroadMultiplier or 4 end
	return 1
end

local function Cost(a, b, context)
	local distance = EdgeLength(a, b)
	if a.type == "swim" or b.type == "swim" or a.roadSwim or b.roadSwim then distance = distance * (context.swimMultiplier or 1.5) end
	if a.type == "offroad" or b.type == "offroad" or a.roadOffroad or b.roadOffroad then
		distance = distance * OffroadMultiplier(context)
	end
	if not context.ghost then
		local caution = 1
		if (High(a, context) or High(b, context) or a.roadHigh or b.roadHigh) and context.aboveLevel == "avoid" then caution = context.levelMultiplier or 1000 end
		if Enemy(a, context) or Enemy(b, context) or a.roadEnemy or b.roadEnemy then caution = math.max(caution, context.enemyMultiplier or 1000) end
		distance = distance * caution
	end
	return distance
end

local function CopyPoint(point)
	local copy = {}
	for key, value in pairs(point) do copy[key] = value end
	return copy
end

local function Augmented(graph, continent, context)
	local extra = context.extraRoutes
	if type(extra) ~= "table" or not next(extra) then return graph end
	local cached = extraCache[continent]
	if cached and cached.base == graph and cached.revision == context.extraRevision
		and (cached.extra == extra or context.extraRevision ~= nil) then return cached.graph end
	local out = { nodes = {}, list = {}, links = {}, edgeCount = graph.edgeCount, source = graph.source }
	local cells = {}
	local function cellKey(x, y) return x .. ":" .. y end
	local function index(id, p)
		local key = cellKey(math.floor(p.wx / 10), math.floor(p.wy / 10))
		cells[key] = cells[key] or {}
		cells[key][#cells[key] + 1] = id
	end
	for _, id in ipairs(graph.list) do
		out.nodes[id], out.list[#out.list + 1], out.links[id] = graph.nodes[id], id, {}
		for _, other in ipairs(graph.links[id]) do out.links[id][#out.links[id] + 1] = other end
		index(id, graph.nodes[id])
	end
	local nextID = #graph.list > 0 and graph.list[#graph.list] + 1 or 1
	local function link(a, b)
		out.links[a][#out.links[a] + 1], out.links[b][#out.links[b] + 1] = b, a
		out.edgeCount = out.edgeCount + 2
	end
	local names = {}
	for name in pairs(extra) do names[#names + 1] = name end
	table.sort(names)
	for _, name in ipairs(names) do
		local trail = extra[name]
		local previous
		for _, raw in ipairs(type(trail) == "table" and trail.points or {}) do
			if raw.cont == continent and Number(raw.wx) and Number(raw.wy) then
				local id, p = nextID, CopyPoint(raw)
				nextID = nextID + 1
				p.nodeID, p.source = id, "recorded"
				out.nodes[id], out.links[id] = p, {}
				local cx, cy = math.floor(p.wx / 10), math.floor(p.wy / 10)
				for dx = -1, 1 do for dy = -1, 1 do
					for _, other in ipairs(cells[cellKey(cx + dx, cy + dy)] or {}) do
						local q = out.nodes[other]
						if p.piece == q.piece and p.layer == q.layer and Distance(p, q) <= 10
							and (not p.z or not q.minZ or not q.maxZ or (p.z >= q.minZ - 2 and p.z <= q.maxZ + 2)) then link(id, other) end
					end
				end end
				out.list[#out.list + 1] = id
				index(id, p)
				if previous and Distance(p, out.nodes[previous]) <= 100 then link(previous, id) end
				previous = id
			else previous = nil end
		end
	end
	extraCache[continent] = { base = graph, extra = extra, revision = context.extraRevision, graph = out }
	return out
end

local function AddPoint(route, p, context)
	p = CopyPoint(p)
	p.enemy = not context.ghost and (Enemy(p, context) or p.roadEnemy) and true or nil
	p.highLevel = not context.ghost and (High(p, context) or p.roadHigh) and true or nil
	p.kind = p.connector and "offroad" or p.stairOwner and "stairs" or p.onewayDrop and "drop" or p.elevator and "elevator" or p.type == "swim" and "swim" or "road"
	if not p.x and mod.GPSRoadPoint then
		local converted = mod.GPSRoadPoint(p, p.cont)
		if converted then for key, value in pairs(converted) do p[key] = value end end
	end
	local previous = route[#route]
	if previous and Distance(previous, p) < 0.001 and previous.piece == p.piece and previous.layer == p.layer then
		if previous.kind ~= "road" and p.kind == "road" then p.kind = previous.kind end
		for key, value in pairs(p) do previous[key] = value end
	else route[#route + 1] = p end
end

local function AddSegment(route, graph, a, b, context)
	if a and a.oneway and a.oneway[b.nodeID] then
		b = CopyPoint(b)
		b.onewayDrop = true
	end
	if a and a.stairOwner and a.stairOwner == b.stairOwner then
		local anchor = graph.nodes[a.stairOwner]
		local delta = b.stairTurn - a.stairTurn
		local steps = math.max(1, math.ceil(math.abs(delta) * 16))
		local angle0 = math.atan2(anchor.wy - a.centerWY, anchor.wx - a.centerWX)
		for i = 1, steps - 1 do
			local fraction = i / steps
			local turn = a.stairTurn + delta * fraction
			local angle = angle0 + a.stairAngleSign * turn * 2 * math.pi
			local p = CopyPoint(a)
			p.wx, p.wy = a.centerWX + a.stairRadius * math.cos(angle), a.centerWY + a.stairRadius * math.sin(angle)
			p.x, p.y, p.u, p.v, p.nodeID, p.tower = nil, nil, nil, nil, nil, nil
			p.stairTurn, p.stairStartTurn, p.stairDirection = turn, a.stairTurn, delta > 0 and 1 or -1
			p.piece, p.layer = nil, nil
			if a.z and b.z then p.z = a.z + (b.z - a.z) * fraction else p.z = nil end
			p.zmin, p.zmax, p.minZ, p.maxZ = nil, nil, nil, nil
			AddPoint(route, p, context)
		end
		b = CopyPoint(b)
		b.stairStartTurn, b.stairDirection = a.stairTurn, delta > 0 and 1 or -1
	end
	AddPoint(route, b, context)
end

-- A small binary heap; no graph-sized quadratic scans while planning a journey.
local function Solve(graph, from, to, context)
	local entries, startReason = StartAttachments(graph, from, context)
	local finish, finishReason = Attachment(graph, to, false, context)
	if not entries or not finish then return nil, startReason or finishReason end
	local function approach(distance)
		local radius, factor = context.entryRadius or 100, context.offroadFactor or 2
		local extra = math.max(0, distance - radius)
		return factor * (math.min(distance, radius) + extra * OffroadMultiplier(context))
	end
	local function reverse(a, b)
		for _, id in ipairs(graph.links[b]) do if id == a then return true end end
		return false
	end
	local heap, distances, previous, origins = {}, {}, {}, {}
	local function push(id, cost)
		if distances[id] and distances[id] <= cost then return end
		distances[id] = cost
		local i = #heap + 1
		while i > 1 do
			local parent = math.floor(i / 2)
			if heap[parent][2] <= cost then break end
			heap[i], i = heap[parent], parent
		end
		heap[i] = { id, cost }
	end
	local function seed(id, cost, entry)
		if not distances[id] or cost < distances[id] then
			origins[id], previous[id] = entry, nil
			push(id, cost)
		end
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
	local ends = {}
	local pin = not to.nodeID
	local tail = pin and (finish.distance > 1 and approach(finish.distance) or 0) or finish.distance
	local function finalLeg(p)
		return pin and Distance(p, finish.point) or Cost(p, finish.point, context)
	end
	if finish.node then ends[finish.node] = pin and Distance(graph.nodes[finish.node], to) or finish.distance
	else
		ends[finish.a] = tail + finalLeg(graph.nodes[finish.a])
		if reverse(finish.a, finish.b) then ends[finish.b] = tail + finalLeg(graph.nodes[finish.b]) end
	end
	local direct, best, reverseDrop
	for _, entry in ipairs(entries) do
		local walked = approach(entry.distance)
		if entry.node then seed(entry.node, walked, entry)
		else
			seed(entry.b, walked + Cost(entry.point, graph.nodes[entry.b], context), entry)
			if reverse(entry.a, entry.b) then seed(entry.a, walked + Cost(entry.point, graph.nodes[entry.a], context), entry) end
			local sameEdge = entry.a == finish.a and entry.b == finish.b
			local oneWay = not reverse(entry.a, entry.b)
			if sameEdge and oneWay and finish.t < entry.t then reverseDrop = true end
			if (not pin or oneWay) and sameEdge
				and (finish.t >= entry.t or not oneWay) then
				local cost = walked + Cost(entry.point, finish.point, context) + finish.distance
				if not best or cost < best then direct, best = entry, cost end
			end
		end
	end
	local winner, visited = nil, 0
	while #heap > 0 do
		local id, cost = pop()
		if best and cost >= best then break end
		if distances[id] == cost then
			visited = visited + 1
			if ends[id] and (not best or cost + ends[id] < best) then winner, best = id, cost + ends[id] end
			for _, nextID in ipairs(graph.links[id]) do
				if Allowed(graph.nodes[nextID], context) then
					local nextCost = cost + Cost(graph.nodes[id], graph.nodes[nextID], context)
					if not distances[nextID] or nextCost < distances[nextID] then
						previous[nextID], origins[nextID] = id, origins[id]
						push(nextID, nextCost)
					end
				end
			end
		end
	end
	-- Pins may be walked to directly when they are nearer than any usable road
	-- node, or when no road route is possible. This is a visible end connector,
	-- never a fabricated edge joining two interior parts of the road graph.
	local straight = Distance(from, to)
	local nearNode
	if pin and not reverseDrop and not (context.tops and next(context.tops)) then
		for _, id in ipairs(graph.list) do
			local p = graph.nodes[id]
			if EndpointAllowed(p, from, true, context) then
				local d = Distance(from, p)
				if not nearNode or d < nearNode then nearNode = d end
			end
		end
		local sameFloor = not mod.GPSOtherFloor or not mod.GPSOtherFloor(from, to)
		local sameLayer = from.layer == nil or to.layer == nil or to.layer == true or from.layer == to.layer
		if sameFloor and sameLayer and (not best or not nearNode or straight <= nearNode) and (not best or approach(straight) < best) then
			local target = CopyPoint(to)
			target.connector, target.connectorRole = true, "finish"
			local route = {}
			AddPoint(route, target, context)
			return route, nil, { source = "bundled", length = straight, cost = approach(straight), visited = visited,
				nodes = #graph.list, edges = graph.edgeCount, startDistance = 0, finishDistance = straight,
				connectorDistance = straight, direct = true, version = ns.GPSRoadData.version }
		end
	end
	if not winner and not direct then return nil, "disconnected" end
	local start = winner and origins[winner] or direct
	local route = {}
	local function entryPoint()
		local p = CopyPoint(start.point)
		p.onewayDrop = start.a and graph.nodes[start.a].oneway and graph.nodes[start.a].oneway[start.b] or nil
		p.connector = start.distance > 0.01 or nil
		p.connectorRole = p.connector and "start" or nil
		AddPoint(route, p, context)
	end
	if winner then
		local ids = {}
		while winner do ids[#ids + 1], winner = winner, previous[winner] end
		if not start.node then entryPoint() end
		local previousNode
		for i = #ids, 1, -1 do
			local p = graph.nodes[ids[i]]
			if i == #ids and start.a and p.nodeID == start.b and graph.nodes[start.a].oneway and graph.nodes[start.a].oneway[start.b] then
				p = CopyPoint(p)
				p.onewayDrop = true
			end
			if i == #ids and start.node and start.distance > 0.01 then p = CopyPoint(p) p.connector, p.connectorRole = true, "start" end
			AddSegment(route, graph, previousNode, p, context)
			previousNode = p
		end
	else entryPoint() end
	if not finish.node then
		if start == direct and start.a and graph.nodes[start.a].oneway and graph.nodes[start.a].oneway[start.b] then
			finish.point.onewayDrop = true
		end
		AddPoint(route, finish.point, context)
	end
	local target = CopyPoint(to)
	target.connector = finish.distance > 0.01 or nil
	target.connectorRole = target.connector and "finish" or nil
	AddPoint(route, target, context)
	local length, enemy, firstEnemy = start.distance, false, nil
	for i, p in ipairs(route) do
		if i > 1 then length = length + Distance(route[i - 1], p) end
		if p.enemy then enemy, firstEnemy = true, firstEnemy or i end
	end
	return route, nil, { source = "bundled", length = length, cost = best, visited = visited,
		nodes = #graph.list, edges = graph.edgeCount, enemy = enemy, firstEnemy = firstEnemy, startDistance = start.distance,
		finishDistance = finish.distance, connectorDistance = start.distance + finish.distance,
		version = ns.GPSRoadData.version }
end

-- A click can overlap adjacent room boxes on one known floor. Preserve the
-- whole candidate set; a common vertical interval proves the floor without
-- inventing a preferred room. Disjoint floors and missing height bounds remain
-- unresolved, even when their two-dimensional boxes happen to overlap.
local function ResolveFloor(point)
	if not point.ambiguous or point.unknown then return point end
	local candidates = point.candidates
	if type(candidates) ~= "table" or #candidates < 2 then return point end
	local low, high, first = -math.huge, math.huge, candidates[1]
	for _, candidate in ipairs(candidates) do
		local bottom, top = Number(candidate.minZ or candidate.zmin), Number(candidate.maxZ or candidate.zmax)
		if not bottom or not top or candidate.layer ~= first.layer or candidate.inside ~= first.inside
			or (first.building and candidate.building ~= first.building) then return point end
		low, high = math.max(low, bottom), math.min(high, top)
	end
	if high - low < 0.5 then return point end
	local copy = CopyPoint(point)
	copy.floorResolved, copy.layer = true, first.layer
	return copy
end

function mod.GPSRoadRoute(from, to, context)
	if type(from) ~= "table" or type(to) ~= "table" or not Number(from.cont) or not Number(to.cont)
		or not Number(from.wx) or not Number(from.wy) or not Number(to.wx) or not Number(to.wy) then return nil, "position" end
	if from.cont ~= to.cont then return nil, "continent" end
	local graph = Network(from.cont)
	if not graph or #graph.list == 0 then return nil, "no-data" end
	context = context or {}
	from, to = ResolveFloor(from), ResolveFloor(to)
	if not context.allowUnknownFloor then
		if to.unknown or (to.ambiguous and not to.floorResolved) then return nil, "floor" end
		if (from.unknown or (from.ambiguous and not from.floorResolved)) and not (context.tops and next(context.tops)) then return nil, "floor" end
	end
	graph = Augmented(graph, from.cont, context)
	return Solve(graph, from, to, context)
end

function mod.GPSInvalidateRoads()
	cachedData, cachedNetworks, extraCache = nil, nil, {}
end

-- Read-only diagnostics used by the offline parity audit.
function mod.GPSRoadEntries(at, context)
	local graph = Network(at.cont)
	return graph and StartAttachments(graph, at, context or {}) or nil
end

function mod.GPSRoadCanWalk(continent, fromID, toID)
	local graph = Network(continent)
	if not graph or not graph.links[fromID] then return false end
	for _, id in ipairs(graph.links[fromID]) do if id == toID then return true end end
	return false
end

function mod.GPSRoadNode(continent, id)
	local graph = Network(continent)
	return graph and graph.nodes[id] and CopyPoint(graph.nodes[id]) or nil
end

function mod.GPSRoadTopsAt(at)
	local data = ns.GPSRoadAnchors
	local anchors = data and data.networks and data.networks[at.cont]
	local graph = Network(at.cont)
	local tops
	for _, anchor in ipairs(anchors or {}) do
		local p = graph and graph.nodes[anchor.node]
		if p and p.stairOwner and p.stairTurn > 0 and Distance(at, anchor) <= 15 then
			tops = tops or {}
			tops[anchor.node] = true
		end
	end
	return tops
end

function mod.GPSRoadStats()
	local data = ns.GPSRoadData
	local out = { nodes = 0, edges = 0, networks = {}, version = data and data.version }
	for continent in pairs(data and data.networks or {}) do
		local graph = Network(continent)
		out.networks[continent] = { nodes = #graph.list, edges = graph.edgeCount }
		out.nodes, out.edges = out.nodes + #graph.list, out.edges + graph.edgeCount
	end
	return out
end
