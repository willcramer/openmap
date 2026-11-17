-- Passive minimap guidance. Blizzard's minimap and its mask stay untouched.
-- GetViewRadius/IsRotateMinimapIgnored: Blizzard_APIDocumentationGenerated/MinimapDocumentation.lua
-- (Gethe/wow-ui-source, forever). Map transforms determine the world axes.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local Safe = ns.Safe
mod.defaults.gpsShowMinimap = true

local MAX_POINTS, MAX_LINES, BLOCK = 25000, 256, 24
local INTERVAL, INSET = 0.05, 3
local COLOR = { 0.15, 1, 0.25 }
local observed, route, count, tree, indexing, drawing, latest, shown
local front, spare, axes, nextRead = nil, nil, {}, 0
local stats = { indexBuilds = 0, redraws = 0, queryNodes = 0, querySegments = 0, maxSliceMS = 0 }

local function Number(value)
	value = Safe.Value(value)
	return type(value) == "number" and value == value and math.abs(value) < math.huge and value or nil
end

local function Read(fn, ...)
	if type(fn) ~= "function" then return end
	local ok, value = pcall(fn, ...)
	if ok then return Safe.Value(value) end
end

local function Clock()
	return Number(Read(_G.debugprofilestop)) or (Number(Read(_G.GetTime)) or 0) * 1000
end

local function Checkpoint()
	if mod.GPSPlanningCheckpoint then mod.GPSPlanningCheckpoint() end
end

local function Hide()
	if front then front.frame:Hide() end
	if spare then spare.frame:Hide() end
	drawing, latest, shown = nil, nil, nil
	stats.drawn = 0
end

local function World(mapID, x, y)
	if not C_Map.GetWorldPosFromMapPos or type(CreateVector2D) ~= "function" then return end
	local ok, continent, pos = pcall(C_Map.GetWorldPosFromMapPos, mapID, CreateVector2D(x, y))
	continent, pos = Number(continent), Safe.Value(pos)
	if not ok or not continent or not pos then return end
	local wx, wy = Safe.XY(pos)
	wx, wy = Number(wx), Number(wy)
	if wx and wy then return continent, wx, wy end
end

local function Axes(mapID, continent)
	local cached = axes[mapID]
	if cached and cached.convert == C_Map.GetWorldPosFromMapPos and cached.cont == continent then return cached end
	local c, x, y = World(mapID, 0.5, 0.5)
	local ce, xe, ye = World(mapID, 0.51, 0.5)
	local cn, xn, yn = World(mapID, 0.5, 0.49)
	if c ~= continent or ce ~= continent or cn ~= continent then return end
	local ex, ey, nx, ny = xe - x, ye - y, xn - x, yn - y
	local e, n = math.sqrt(ex * ex + ey * ey), math.sqrt(nx * nx + ny * ny)
	if e <= 0 or n <= 0 then return end
	ex, ey, nx, ny = ex / e, ey / e, nx / n, ny / n
	if math.abs(ex * nx + ey * ny) > 0.01 then return end
	cached = { ex = ex, ey = ey, nx = nx, ny = ny, cont = continent, convert = C_Map.GetWorldPosFromMapPos }
	axes[mapID] = cached
	return cached
end

local function Placed(point)
	return type(point) == "table" and Number(point.wx) and Number(point.wy) and Number(point.cont)
end

local function Floor(point, player)
	if not Placed(point) or point.cont ~= player.cont or point.unknown
		or point.ambiguous and not point.floorResolved then return false end
	if point.layer ~= nil and point.layer ~= (player.layer or false) then return false end
	if mod.GPSOtherFloor and mod.GPSOtherFloor(player, point) then return false end
	return true
end

local function Bound(box, point)
	if not Placed(point) then return end
	box.x1, box.y1 = math.min(box.x1 or point.wx, point.wx), math.min(box.y1 or point.wy, point.wy)
	box.x2, box.y2 = math.max(box.x2 or point.wx, point.wx), math.max(box.y2 or point.wy, point.wy)
end

-- A hierarchy of route blocks avoids scanning a long journey at every movement
-- update. Large segments remain whole and are clipped, never shortcut or dropped.
local function Index(points, total)
	local level = {}
	for first = 2, total, BLOCK do
		local node = { first = first, last = math.min(total, first + BLOCK - 1) }
		for i = node.first, node.last do
			Checkpoint()
			Bound(node, points[i - 1])
			Bound(node, points[i])
		end
		level[#level + 1] = node
	end
	while #level > 1 do
		local parents = {}
		for i = 1, #level, 2 do
			Checkpoint()
			local a, b = level[i], level[i + 1]
			if not b then parents[#parents + 1] = a
			else
				local node = { first = a.first, last = b.last, left = a, right = b }
				for _, child in ipairs({ a, b }) do
					if child.x1 then
						node.x1, node.y1 = math.min(node.x1 or child.x1, child.x1), math.min(node.y1 or child.y1, child.y1)
						node.x2, node.y2 = math.max(node.x2 or child.x2, child.x2), math.max(node.y2 or child.y2, child.y2)
					end
				end
				parents[#parents + 1] = node
			end
		end
		level = parents
	end
	return level[1]
end

local function Context(status)
	local host = _G.Minimap
	local player = status and status.player
	if not host or type(host.IsShown) ~= "function" or not host:IsShown()
		or not mod.db or mod.db.gpsShowMinimap == false or not status.active or not Placed(player)
		or player.unknown or player.ambiguous and not player.floorResolved or Read(_G.IsInInstance) then return end
	if mod.GPSRoomsReady and not mod.GPSRoomsReady(player.cont) then return end
	local width, height = Number(host:GetWidth()), Number(host:GetHeight())
	local radius = C_Minimap and Number(Read(C_Minimap.GetViewRadius))
	if not width or not height or width <= INSET * 2 or height <= INSET * 2
		or not radius or radius <= 0 or radius > 10000 then return end
	local mapID, _, _, _, _, continent, wx, wy, z = mod.GPSPlayer()
	mapID, continent, wx, wy, z = Number(mapID), Number(continent), Number(wx), Number(wy), Number(z)
	if not mapID or not wx or not wy or continent ~= player.cont or mapID ~= player.map then return end
	if player.z and z and math.abs(player.z - z) > 8 then return end
	local basis = Axes(mapID, continent)
	if not basis then return end
	local rotating = Read(_G.GetCVarBool, "rotateMinimap")
	if rotating == nil and C_CVar then rotating = Read(C_CVar.GetCVarBool, "rotateMinimap") end
	if rotating == nil then rotating = Read(_G.GetCVar, "rotateMinimap") == "1" end
	if C_Minimap and Read(C_Minimap.IsRotateMinimapIgnored) then rotating = false end
	local angle = rotating and Number(Read(_G.GetPlayerFacing)) or 0
	if angle == nil then return end
	local snapshot = {}
	for key, value in pairs(player) do snapshot[key] = value end
	return { host = host, route = status.route, index = math.max(1, math.floor(Number(status.index) or 1)),
		count = #status.route, player = snapshot, cont = continent, map = mapID, wx = wx, wy = wy,
		width = width, height = height, radius = radius, basis = basis, angle = angle,
		rotating = rotating and true or false, square = Read(_G.GetMinimapShape) == "SQUARE",
		cosine = math.cos(angle), sine = math.sin(angle) }
end

local function SameFloor(a, b)
	return a and b and a.cont == b.cont and a.map == b.map and a.player.layer == b.player.layer
		and a.player.piece == b.player.piece
end

local function Same(a, b)
	return SameFloor(a, b) and a.host == b.host and a.route == b.route and a.index == b.index
		and a.count == b.count and a.wx == b.wx and a.wy == b.wy and a.radius == b.radius
		and a.width == b.width and a.height == b.height and a.angle == b.angle and a.square == b.square
		and a.basis == b.basis
end

local function Project(point, request)
	local dx, dy = point.wx - request.wx, point.wy - request.wy
	local east = (dx * request.basis.ex + dy * request.basis.ey) / request.radius
	local north = (dx * request.basis.nx + dy * request.basis.ny) / request.radius
	-- GetPlayerFacing is counterclockwise from north; turning west moves north
	-- rightward on a rotating minimap.
	return east * request.cosine + north * request.sine, north * request.cosine - east * request.sine
end

local function Clip(ax, ay, bx, by, square, limitX, limitY)
	ax, ay, bx, by = ax / limitX, ay / limitY, bx / limitX, by / limitY
	local dx, dy, low, high = bx - ax, by - ay, 0, 1
	if square then
		local function edge(p, q)
			if p == 0 then return q >= 0 end
			local t = q / p
			if p < 0 then if t > high then return false end low = math.max(low, t)
			else if t < low then return false end high = math.min(high, t) end
			return true
		end
		if not edge(-dx, ax + 1) or not edge(dx, 1 - ax) or not edge(-dy, ay + 1) or not edge(dy, 1 - ay) then return end
	else
		local a = dx * dx + dy * dy
		if a <= 0 then return end
		local b, c = 2 * (ax * dx + ay * dy), ax * ax + ay * ay - 1
		local discriminant = b * b - 4 * a * c
		if discriminant < 0 then return end
		local distance = math.sqrt(discriminant)
		low, high = math.max(0, (-b - distance) / (2 * a)), math.min(1, (-b + distance) / (2 * a))
		if low > high then return end
	end
	return (ax + low * dx) * limitX, (ay + low * dy) * limitY,
		(ax + high * dx) * limitX, (ay + high * dy) * limitY
end

local function Bag(host)
	local bag = { frame = CreateFrame("Frame", nil, host), lines = {} }
	bag.frame:SetAllPoints(host)
	bag.frame:SetFrameLevel((Number(host:GetFrameLevel()) or 1) + 1)
	bag.frame:EnableMouse(false)
	bag.frame:SetClipsChildren(true)
	bag.frame:Hide()
	return bag
end

local function Attach(bag, host)
	if bag.frame:GetParent() == host then return end
	bag.frame:SetParent(host)
	bag.frame:ClearAllPoints()
	bag.frame:SetAllPoints(host)
	bag.frame:SetFrameLevel((Number(host:GetFrameLevel()) or 1) + 1)
end

local function Draw(job)
	local request, bag = job.request, job.bag
	local used, visited, segments = 0, 0, 0
	local function segment(a, b)
		if used >= MAX_LINES or not Floor(a, request.player) or not Floor(b, request.player) then return end
		local ax, ay = Project(a, request)
		local bx, by = Project(b, request)
		ax, ay, bx, by = Clip(ax, ay, bx, by, request.square,
			1 - INSET * 2 / request.width, 1 - INSET * 2 / request.height)
		if not ax or (ax - bx) ^ 2 + (ay - by) ^ 2 < 0.00000001 then return end
		used = used + 1
		local line = bag.lines[used]
		if not line then line = bag.frame:CreateLine(nil, "ARTWORK") bag.lines[used] = line end
		line:ClearAllPoints()
		line:SetStartPoint("CENTER", bag.frame, ax * request.width / 2, ay * request.height / 2)
		line:SetEndPoint("CENTER", bag.frame, bx * request.width / 2, by * request.height / 2)
		line:SetThickness(2)
		line:SetColorTexture(1, 1, 1, 1)
		line:SetVertexColor(COLOR[1], COLOR[2], COLOR[3], 1)
		line:Show()
	end
	local target = request.route[request.index]
	if target then
		segment({ wx = request.wx, wy = request.wy, cont = request.cont, layer = request.player.layer,
			piece = request.player.piece }, target)
		Checkpoint()
	end
	local reach = request.radius * (request.square and math.sqrt(2) or 1)
	local function visit(node)
		Checkpoint()
		visited = visited + 1
		if not node or not node.x1 or node.last <= request.index or used >= MAX_LINES
			or node.x2 < request.wx - reach or node.x1 > request.wx + reach
			or node.y2 < request.wy - reach or node.y1 > request.wy + reach then return end
		if node.left then visit(node.left) visit(node.right)
		else
			for i = math.max(node.first, request.index + 1), node.last do
				Checkpoint()
				segments = segments + 1
				segment(request.route[i - 1], request.route[i])
				if used >= MAX_LINES then break end
			end
		end
	end
	if tree then visit(tree) end
	for i = used + 1, #bag.lines do bag.lines[i]:Hide() Checkpoint() end
	job.used, job.visited, job.segments = used, visited, segments
end

local function Current(request)
	local status = observed
	return status and status.active and status.route == request.route and status.index == request.index
		and status.player and not status.player.unknown and not (status.player.ambiguous and not status.player.floorResolved)
		and SameFloor(request, { cont = status.player.cont, map = status.player.map, player = status.player })
		and #request.route == request.count and mod.db and mod.db.gpsShowMinimap ~= false
		and request.host == _G.Minimap and request.host:IsShown() and latest and SameFloor(request, latest)
		and request.radius == latest.radius and request.width == latest.width and request.height == latest.height
		and request.square == latest.square and request.rotating == latest.rotating
		and math.abs((request.angle - latest.angle + math.pi) % (2 * math.pi) - math.pi) <= math.pi / 3
		and (request.wx - latest.wx) ^ 2 + (request.wy - latest.wy) ^ 2 <= 10000
end

function mod.GPSMinimapEnabled() return mod.db and mod.db.gpsShowMinimap ~= false or false end

function mod.GPSSetMinimapShown(value)
	if not mod.db then return end
	mod.db.gpsShowMinimap = value and true or false
	nextRead = 0
	if not value then indexing = nil Hide() end
	if mod.GPSRefreshPanel then mod.GPSRefreshPanel() end
end

function mod.GPSDrawMinimap(status)
	observed = status
	if not status or not status.active or type(status.route) ~= "table" or not mod.GPSMinimapEnabled() then
		indexing = nil
		Hide()
		return
	end
	if latest and (not status.player or status.player.unknown or status.player.ambiguous and not status.player.floorResolved
		or not SameFloor(latest, { cont = status.player.cont, map = status.player.map, player = status.player })) then
		Hide()
		nextRead = 0
	end
	if route ~= status.route or count ~= #status.route or not tree and not indexing and #status.route > 1 then
		Hide()
		route, count, tree = status.route, #status.route, nil
		indexing = { route = route, count = count }
		local job = indexing
		job.co = coroutine.create(function() return Index(job.route, math.min(job.count, MAX_POINTS)) end)
		stats.indexBuilds = stats.indexBuilds + 1
		nextRead = 0
	end
end

function mod.GPSRunMinimapDrawing(budget)
	if not observed or not observed.active or not mod.GPSMinimapEnabled() then Hide() return 0 end
	if not mod.GPSRunBudgetedWork or not budget or budget <= 0 then return 0 end
	local started = Clock()
	local now = Number(Read(_G.GetTime)) or 0
	if now >= nextRead or not latest then
		nextRead = now + INTERVAL
		local request = Context(observed)
		if not request then indexing = nil Hide() return math.max(0, Clock() - started) end
		if latest and (not SameFloor(request, latest) or request.host ~= latest.host
			or request.radius ~= latest.radius or request.width ~= latest.width or request.height ~= latest.height
			or request.square ~= latest.square or request.rotating ~= latest.rotating
			or (request.wx - latest.wx) ^ 2 + (request.wy - latest.wy) ^ 2 > 10000) then Hide() end
		latest = request
	end
	if not tree and not indexing and count > 1 then mod.GPSDrawMinimap(observed) end
	if indexing then
		local job = indexing
		local done, _, ok, result = mod.GPSRunBudgetedWork(job, math.max(0, budget - (Clock() - started)))
		stats.maxSliceMS = math.max(stats.maxSliceMS, job.maxSliceMS or 0)
		if done then
			indexing = nil
			if not ok then if type(geterrorhandler) == "function" then geterrorhandler()(result) end
			elseif route == job.route and count == job.count then tree = result end
		end
	end
	if not indexing and latest and not drawing and not Same(shown, latest) then
		if not spare then spare = Bag(latest.host) else Attach(spare, latest.host) end
		spare.frame:Hide()
		drawing = { request = latest, bag = spare }
		local job = drawing
		job.co = coroutine.create(function() Draw(job) end)
	end
	if drawing then
		local job = drawing
		if not Current(job.request) then drawing = nil
		else
			local done, _, ok, err = mod.GPSRunBudgetedWork(job, math.max(0, budget - (Clock() - started)))
			stats.maxSliceMS = math.max(stats.maxSliceMS, job.maxSliceMS or 0)
			if done then
				drawing = nil
				if not ok then if type(geterrorhandler) == "function" then geterrorhandler()(err) end
				elseif Current(job.request) then
					if front then front.frame:Hide() end
					front, spare, shown = job.bag, front, job.request
					front.frame:Show()
					stats.redraws, stats.drawn = stats.redraws + 1, job.used
					stats.queryNodes, stats.querySegments = job.visited, job.segments
				end
			end
		end
	end
	return math.max(0, Clock() - started)
end

function mod.GPSMinimapDrawingPending() return indexing ~= nil or drawing ~= nil end

function mod.GPSMinimapStats()
	local result = { pending = mod.GPSMinimapDrawingPending(), limit = MAX_LINES,
		allocated = (front and #front.lines or 0) + (spare and #spare.lines or 0) }
	for key, value in pairs(stats) do result[key] = value end
	return result
end
