-- Route marks on native maps outside the stitched canvas (Zephras Isle).
-- Everything drawn belongs to this addon; map layout and other pins stay alone.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local Safe = ns.Safe
local MAX_POINTS = 25000
local STYLE = { color = { 0.15, 1, 0.25 }, thickness = 3, nodeSize = 7, targetSize = 10 }
local NATIVE = { [2521] = 2991, [2665] = 2991 }
local map, root, canvas
local dots, drawn, redraws = {}, 0, 0
local lines, lineDrawn, head, headShown, headUpdates = {}, 0, nil, false, 0
local headTarget, headPoint
local lastRoute, lastIndex, lastMap, lastWidth, lastHeight, lastScale, lastCount
local lastStyle, lastPlayerX, lastPlayerY, lastPlayerCont, lastPlayerLayer, lastPlayerFloor
local nativeJob, spare, requested
local networkRoot, networkCanvas, networkData, networkMap, networkWidth, networkHeight, networkScale
local networkDots, networkDrawn, networkRedraws = {}, 0, 0
local networkNodes, networkNodesDrawn, networkRoutes, networkRevision = {}, 0
local networkEdits, networkEditRevision, networkSelected
local NETWORK_LIMIT, NODE_LIMIT, RECORD_LIMIT = 800, 500, 10000
local NODE_COLOR, RECORD_COLOR = { 1, 0.8, 0.35 }, { 1, 0.45, 0.1 }
local MANUAL_COLOR, SELECTED_COLOR = { 0.25, 0.8, 1 }, { 1, 1, 1 }
local NETWORK_COLORS = {
	default = { 0.72, 0.67, 0.51 }, alliance = { 0.3, 0.5, 0.9 }, horde = { 0.8, 0.3, 0.25 },
	swim = { 0.3, 0.75, 0.8 }, offroad = { 0.5, 0.5, 0.5 },
}

local function Number(value)
	value = Safe.Value(value)
	if type(value) == "number" and value == value and math.abs(value) < math.huge then return value end
end

local function Hide()
	nativeJob, requested = nil, nil
	if spare and spare.root then spare.root:Hide() end
	if root then root:Hide() end
	drawn, lineDrawn, headShown, lastRoute = 0, 0, false, nil
end

local function SaveRouteState()
	return { root = root, canvas = canvas, dots = dots, drawn = drawn, lines = lines, lineDrawn = lineDrawn,
		head = head, headShown = headShown, headTarget = headTarget, headPoint = headPoint,
		route = lastRoute, index = lastIndex, map = lastMap, width = lastWidth, height = lastHeight,
		scale = lastScale, count = lastCount, style = lastStyle,
		px = lastPlayerX, py = lastPlayerY, cont = lastPlayerCont, layer = lastPlayerLayer, floor = lastPlayerFloor }
end

local function LoadRouteState(state)
	root, canvas, dots, lines = state.root, state.canvas, state.dots or {}, state.lines or {}
	drawn, lineDrawn, head, headShown = state.drawn or 0, state.lineDrawn or 0, state.head, state.headShown or false
	headTarget, headPoint = state.headTarget, state.headPoint
	lastRoute, lastIndex, lastMap = state.route, state.index, state.map
	lastWidth, lastHeight, lastScale, lastCount, lastStyle = state.width, state.height, state.scale, state.count, state.style
	lastPlayerX, lastPlayerY, lastPlayerCont, lastPlayerLayer, lastPlayerFloor = state.px, state.py, state.cont, state.layer, state.floor
end

local function HideNetwork()
	if networkRoot then networkRoot:Hide() end
	networkDrawn, networkNodesDrawn, networkData, networkRevision = 0, 0, nil, nil
end

local function HideAll() Hide() HideNetwork() end

local function Project(point, host, continent)
	if type(point) ~= "table" then return end
	if Number(point.cont) ~= continent or (Number(point.layer) and point.layer ~= host)
		or not Number(point.wx) or not Number(point.wy) then return end
	if not C_Map.GetMapPosFromWorldPos or not CreateVector2D then return end
	local ok, mapID, position = pcall(C_Map.GetMapPosFromWorldPos, continent, CreateVector2D(point.wx, point.wy), host)
	mapID, position = Number(mapID), Safe.Value(position)
	if not ok or mapID ~= host or not position then return end
	local x, y = Safe.XY(position)
	x, y = Number(x), Number(y)
	if x and y then return { x, y } end
end

-- Keep only the part of a road inside this map, including one whose endpoints
-- both lie outside it. Native map canvases do not clip their own children.
local function Clip(a, b)
	local dx, dy = b[1] - a[1], b[2] - a[2]
	local low, high = 0, 1
	local function edge(p, q)
		if p == 0 then return q >= 0 end
		local t = q / p
		if p < 0 then if t > high then return false end low = math.max(low, t)
		else if t < low then return false end high = math.min(high, t) end
		return true
	end
	if not edge(-dx, a[1]) or not edge(dx, 1 - a[1]) or not edge(-dy, a[2]) or not edge(dy, 1 - a[2]) then return end
	return { a[1] + low * dx, a[2] + low * dy }, { a[1] + high * dx, a[2] + high * dy }
end

local function Attach(nextCanvas)
	if not root then
		root = CreateFrame("Frame", nil, nextCanvas)
		root:EnableMouse(false)
		root:SetClipsChildren(true)
	end
	if canvas ~= nextCanvas then
		canvas, lastRoute = nextCanvas, nil
		root:SetParent(canvas)
		root:ClearAllPoints()
		root:SetAllPoints(canvas)
		root:SetFrameLevel(canvas:GetFrameLevel() + 10)
	end
end

local function RouteLine(line, first, last, width, height, scale, style)
	line:ClearAllPoints()
	line:SetStartPoint("TOPLEFT", root, first[1] * width, -first[2] * height)
	line:SetEndPoint("TOPLEFT", root, last[1] * width, -last[2] * height)
	line:SetThickness(style.thickness / scale)
	line:SetColorTexture(1, 1, 1, 1)
	line:SetVertexColor(style.color[1], style.color[2], style.color[3], 1)
	line:Show()
end

local function Nonzero(first, last)
	return first and last and (math.abs(first[1] - last[1]) > 0.0000001 or math.abs(first[2] - last[2]) > 0.0000001)
end

local function RouteNode(point, target, width, height, scale, style)
	if not point or point[1] < 0 or point[1] > 1 or point[2] < 0 or point[2] > 1 then return end
	drawn = drawn + 1
	local dot = dots[drawn]
	if not dot then
		dot = root:CreateTexture(nil, "OVERLAY", nil, 1)
		if C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo("WhiteCircle-RaidBlips") then
			dot:SetAtlas("WhiteCircle-RaidBlips")
		else dot:SetTexture("Interface\\Buttons\\WHITE8X8") end
		dots[drawn] = dot
	end
	dot:ClearAllPoints()
	dot:SetPoint("CENTER", root, "TOPLEFT", point[1] * width, -point[2] * height)
	local size = (target and style.targetSize or style.nodeSize) / scale
	dot:SetSize(size, size)
	dot:SetVertexColor(style.color[1], style.color[2], style.color[3], 1)
	dot:Show()
end

local function Head(status, host, continent, width, height, scale, style, changed)
	local player = type(status.player) == "table" and status.player
	local wx, wy = Number(player and player.wx), Number(player and player.wy)
	local cont = Number(player and player.cont)
	local layer = player and Safe.Value(player.layer)
	if type(layer) ~= "number" and type(layer) ~= "boolean" then layer = nil end
	local floor = player and headTarget and (player.unknown or player.ambiguous
		or layer ~= nil and headTarget.layer ~= nil and layer ~= headTarget.layer
		or mod.GPSOtherFloor and mod.GPSOtherFloor(player, headTarget)) or false
	if not changed and wx == lastPlayerX and wy == lastPlayerY and cont == lastPlayerCont
		and layer == lastPlayerLayer and floor == lastPlayerFloor then return end
	lastPlayerX, lastPlayerY, lastPlayerCont, lastPlayerLayer, lastPlayerFloor = wx, wy, cont, layer, floor
	headUpdates, headShown = headUpdates + 1, false
	local point = not floor and player and Project(player, host, continent)
	if Nonzero(point, headPoint) then
		local first, last = Clip(point, headPoint)
		if Nonzero(first, last) then
			head = head or root:CreateLine(nil, "ARTWORK")
			RouteLine(head, first, last, width, height, scale, style)
			headShown = true
		end
	end
	if head and not headShown then head:Hide() end
end

local function NetworkMark(pool, index, point, size, color, width, height, scale, node)
	local dot = pool[index]
	if not dot then
		dot = networkRoot:CreateTexture(nil, node and "OVERLAY" or "ARTWORK")
		if node and C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo("WhiteCircle-RaidBlips") then
			dot:SetAtlas("WhiteCircle-RaidBlips")
		else dot:SetTexture("Interface\\Buttons\\WHITE8X8") end
		pool[index] = dot
	end
	dot:ClearAllPoints()
	dot:SetPoint("CENTER", networkRoot, "TOPLEFT", point[1] * width, -point[2] * height)
	dot:SetSize(size / scale, size / scale)
	dot:SetVertexColor(color[1], color[2], color[3], node and 1 or 0.8)
	dot:Show()
end

local function DrawNetwork(nextCanvas, host, continent, width, height, scale)
	local data = ns.GPSRoadData
	local network = data and data.networks and data.networks[continent]
	local routes = mod.db and mod.db.gpsRoutes
	local revision = mod.GPSRoadsRevision and mod.GPSRoadsRevision() or 0
	local manual = mod.GPSRoadEditSnapshot and mod.GPSRoadEditSnapshot()
	local manualRevision = manual and manual.revision
	local selected = mod.GPSRoadSelected and mod.GPSRoadSelected()
	if data == networkData and nextCanvas == networkCanvas and host == networkMap
		and width == networkWidth and height == networkHeight and scale == networkScale
		and routes == networkRoutes and revision == networkRevision
		and manual == networkEdits and manualRevision == networkEditRevision and selected == networkSelected then
		if networkRoot then networkRoot:SetShown(networkDrawn > 0 or networkNodesDrawn > 0) end
		return
	end
	if not networkRoot then
		networkRoot = CreateFrame("Frame", nil, nextCanvas)
		networkRoot:EnableMouse(false)
		networkRoot:SetClipsChildren(true)
	end
	if networkCanvas ~= nextCanvas then
		networkRoot:SetParent(nextCanvas)
		networkRoot:ClearAllPoints()
		networkRoot:SetAllPoints(nextCanvas)
		networkRoot:SetFrameLevel(nextCanvas:GetFrameLevel() + 9)
	end
	networkData, networkCanvas, networkMap = data, nextCanvas, host
	networkWidth, networkHeight, networkScale = width, height, scale
	networkRoutes, networkRevision = routes, revision
	networkEdits, networkEditRevision, networkSelected = manual, manualRevision, selected
	networkRedraws = networkRedraws + 1
	local points, ids, markers = {}, {}, {}
	local function marker(point, size, color, ref)
		if (not selected or ref ~= selected) and point[1] >= 0 and point[1] <= 1 and point[2] >= 0 and point[2] <= 1 then
			markers[#markers + 1] = { point, size, color }
		end
	end
	for id, node in pairs(network and network.nodes or {}) do
		if Number(id) then
			local projected = Project({ cont = continent, wx = node.wx, wy = node.wy, layer = node.layer }, host, continent)
			if projected then points[id], ids[#ids + 1] = projected, id end
		end
	end
	table.sort(ids)
	local segments, total = {}, 0
	local function segment(a, b, color)
		local first, last = Clip(a, b)
		if not first then return end
		local distance = math.sqrt(((last[1] - first[1]) * width) ^ 2 + ((last[2] - first[2]) * height) ^ 2)
		if distance > 0 then
			segments[#segments + 1] = { first, last, distance, color }
			total = total + distance
		end
	end
	for _, id in ipairs(ids) do
		local a = network.nodes[id]
		marker(points[id], 6, NODE_COLOR, "b:" .. continent .. ":" .. id)
		local links = {}
		for target, linked in pairs(a.links or {}) do if linked and points[target] then links[#links + 1] = target end end
		table.sort(links)
		for _, target in ipairs(links) do
			local b = network.nodes[target]
			local reciprocal = b.links and b.links[id]
			-- Only explicit surface links are drawn. A stair/elevator's vertical
			-- connection must not become a straight line across another floor.
			if (not reciprocal or id < target) and a.piece == b.piece and a.layer == b.layer
				and not a.tower and not b.tower and not a.towerOf and not b.towerOf and not a.elevator and not b.elevator then
				segment(points[id], points[target], NETWORK_COLORS[a.type or b.type] or NETWORK_COLORS.default)
			end
		end
	end
	-- Saved trails are separate data. Show their actual samples and only the
	-- walked links; projecting them never adds links to the navigation graph.
	local names, sampled = {}, 0
	for name in pairs(type(routes) == "table" and routes or {}) do
		if type(name) == "string" then names[#names + 1] = name end
	end
	table.sort(names)
	for _, name in ipairs(names) do
		local trail, previous, previousPoint = routes[name]
		for _, sample in ipairs(type(trail) == "table" and type(trail.points) == "table" and trail.points or {}) do
			if sampled >= RECORD_LIMIT then break end
			sampled = sampled + 1
			local p = mod.GPSRecordedPoint and mod.GPSRecordedPoint(sample)
			local point = p and Project(p, host, continent)
			if point then
				marker(point, 7, RECORD_COLOR)
				if previous and p.cont == previous.cont and p.piece == previous.piece and p.layer == previous.layer
					and (p.wx - previous.wx) ^ 2 + (p.wy - previous.wy) ^ 2 <= 10000 then
					segment(previousPoint, point, RECORD_COLOR)
				end
			end
			previous, previousPoint = point and p or nil, point
		end
		if sampled >= RECORD_LIMIT then break end
	end
	local manualPoints = {}
	local function manualPoint(ref)
		if manualPoints[ref] then return manualPoints[ref][1], manualPoints[ref][2] end
		local raw = mod.GPSRoadEditPoint and mod.GPSRoadEditPoint(ref)
		local point = raw and Project(raw, host, continent)
		if point then manualPoints[ref] = { raw, point } return raw, point end
	end
	for ref in pairs(manual and manual.nodes or {}) do
		local _, point = manualPoint(ref)
		if point then marker(point, 7, MANUAL_COLOR, ref) end
	end
	for _, link in ipairs(manual and manual.links or {}) do
		local a, first = manualPoint(link.a)
		local b, last = manualPoint(link.b)
		if first and last and a.cont == b.cont and not a.ambiguous and not b.ambiguous
			and not (a.layer ~= nil and b.layer ~= nil and a.layer ~= b.layer)
			and not (mod.GPSOtherFloor and mod.GPSOtherFloor(a, b)) then segment(first, last, MANUAL_COLOR) end
	end
	local selectedPoint
	if selected then
		local _, point = manualPoint(selected)
		if point and point[1] >= 0 and point[1] <= 1 and point[2] >= 0 and point[2] <= 1 then selectedPoint = point end
	end
	networkDrawn = 0
	local spacing, carry = math.max(7 / scale, total / (NETWORK_LIMIT - 1)), 0
	for _, segment in ipairs(segments) do
		local first, last, distance, color = segment[1], segment[2], segment[3], segment[4]
		local along = carry
		while along <= distance and networkDrawn < NETWORK_LIMIT do
			local fraction = along / distance
			networkDrawn = networkDrawn + 1
			NetworkMark(networkDots, networkDrawn,
				{ first[1] + (last[1] - first[1]) * fraction, first[2] + (last[2] - first[2]) * fraction },
				3, color, width, height, scale)
			along = along + spacing
		end
		carry = along - distance
	end
	for i = networkDrawn + 1, #networkDots do networkDots[i]:Hide() end
	networkNodesDrawn = math.min(NODE_LIMIT - (selectedPoint and 1 or 0), #markers)
	for i = 1, networkNodesDrawn do
		-- At wide views thin the markers across the whole network, always using
		-- a real node position rather than creating another interpolated dot.
		local item = markers[math.floor((i - 0.5) * #markers / networkNodesDrawn) + 1]
		NetworkMark(networkNodes, i, item[1], item[2], item[3], width, height, scale, true)
	end
	if selectedPoint then
		-- Keep the selected endpoint visible even when the wider network is thinned.
		networkNodesDrawn = networkNodesDrawn + 1
		NetworkMark(networkNodes, networkNodesDrawn, selectedPoint, 10, SELECTED_COLOR, width, height, scale, true)
	end
	for i = networkNodesDrawn + 1, #networkNodes do networkNodes[i]:Hide() end
	networkRoot:SetShown(networkDrawn > 0 or networkNodesDrawn > 0)
end

local function BuildRoute(request, checkpoint)
	local status, host, continent = request.status, request.host, request.continent
	local width, height, scale, style = request.width, request.height, request.scale, request.style
	local route, index = request.route, request.index
	Attach(request.canvas)
	if checkpoint then root:Hide() end
	lastRoute, lastIndex, lastMap, lastStyle = route, index, host, style
	lastWidth, lastHeight, lastScale, lastCount = width, height, scale, request.count
	lastPlayerX, lastPlayerY = nil, nil
	redraws, drawn, lineDrawn = redraws + 1, 0, 0
	headTarget, headPoint = route[index], nil
	local previous
	-- Staging remains hidden until every bend and endpoint has been built.
	for i = index, math.min(request.count, index + MAX_POINTS - 1) do
		local point = Project(route[i], host, continent)
		if i == index then headPoint = point end
		RouteNode(point, i == request.count, width, height, scale, style)
		if Nonzero(previous, point) then
			local first, last = Clip(previous, point)
			if Nonzero(first, last) then
				lineDrawn = lineDrawn + 1
				local line = lines[lineDrawn] or root:CreateLine(nil, "ARTWORK")
				lines[lineDrawn] = line
				RouteLine(line, first, last, width, height, scale, style)
			end
		end
		previous = point
		if checkpoint then checkpoint() end
	end
	for i = drawn + 1, #dots do dots[i]:Hide() if checkpoint then checkpoint() end end
	for i = lineDrawn + 1, #lines do lines[i]:Hide() if checkpoint then checkpoint() end end
	if head then head:Hide() end
	headShown = false
end

local function SameRequest(a, b)
	return a and b and a.route == b.route and a.index == b.index and a.count == b.count
		and a.host == b.host and a.canvas == b.canvas and a.width == b.width and a.height == b.height
		and a.scale == b.scale and a.style == b.style
end

local function CurrentRequest(request)
	if not request or requested ~= request or not map or not map:IsShown() or mod.instanceWorldHidden
		or (mod.instancePinsHidden and not mod.instanceWorldBrowsing)
		or (mod.IsStitched and mod.IsStitched()) then return false end
	local status = mod.GPSStatus and mod.GPSStatus() or request.status
	return status.active and status.route == request.route and (status.index or 1) == request.index
		and #request.route == request.count and Safe.Call(map.GetMapID, map) == request.host
		and Safe.Call(map.GetCanvas, map) == request.canvas
		and Safe.Call(request.canvas.GetWidth, request.canvas) == request.width
		and Safe.Call(request.canvas.GetHeight, request.canvas) == request.height
		and (Number(Safe.Call(map.GetCanvasScale, map)) or 1) == request.scale
end

function mod.GPSRunNativeDrawing(budget)
	local job = nativeJob
	if not job or not mod.GPSRunBudgetedWork then return 0 end
	if not CurrentRequest(job.request) then nativeJob = nil return 0 end
	local front = SaveRouteState()
	LoadRouteState(spare or {})
	local done, spent, ok, err = mod.GPSRunBudgetedWork(job, budget)
	spare = SaveRouteState()
	LoadRouteState(front)
	if not ok then
		nativeJob = nil
		if spare.root then spare.root:Hide() end
		geterrorhandler()(err)
	elseif done then
		nativeJob = nil
		if CurrentRequest(job.request) then
			if root then root:Hide() end
			LoadRouteState(spare)
			spare = front
			local request = job.request
			local status = mod.GPSStatus and mod.GPSStatus() or request.status
			Head(status, request.host, request.continent, request.width, request.height, request.scale, request.style, true)
			root:SetShown(drawn > 0 or lineDrawn > 0 or headShown)
		end
	end
	return spent or 0
end

function mod.GPSNativeDrawingPending() return nativeJob ~= nil end

function mod:SetupGPSNative(worldMap)
	if map then return end
	map = worldMap or _G.WorldMapFrame
	if map and map.HookScript then map:HookScript("OnHide", HideAll) end
end

function mod.GPSDrawNative(status, budgeted)
	if not map then mod:SetupGPSNative() end
	local active = status and status.active and type(status.route) == "table"
	local showNetwork = mod.GPSRoadsShown and mod.GPSRoadsShown()
	if not map or not map:IsShown() or (not active and not showNetwork)
		or mod.instanceWorldHidden or (mod.instancePinsHidden and not mod.instanceWorldBrowsing)
		or (mod.IsStitched and mod.IsStitched()) then HideAll() return end
	local host = Number(Safe.Call(map.GetMapID, map))
	local continent = host and NATIVE[host]
	if not continent then HideAll() return end
	local nextCanvas = Safe.Call(map.GetCanvas, map)
	if not nextCanvas then HideAll() return end
	local width, height = Number(Safe.Call(nextCanvas.GetWidth, nextCanvas)), Number(Safe.Call(nextCanvas.GetHeight, nextCanvas))
	local scale = Number(Safe.Call(map.GetCanvasScale, map)) or 1
	if not width or not height or width <= 0 or height <= 0 or scale <= 0 then HideAll() return end
	if showNetwork then DrawNetwork(nextCanvas, host, continent, width, height, scale) else HideNetwork() end
	if not active then Hide() return end
	Attach(nextCanvas)
	local style = mod.GPSRouteStyle or STYLE
	local index = math.max(1, math.floor(Number(status.index) or 1))
	local changed = status.route ~= lastRoute or index ~= lastIndex or host ~= lastMap or width ~= lastWidth
		or height ~= lastHeight or scale ~= lastScale or #status.route ~= lastCount or style ~= lastStyle
	if changed then
		local request = { status = status, route = status.route, index = index, count = #status.route,
			host = host, continent = continent, canvas = nextCanvas, width = width, height = height, scale = scale, style = style }
		if budgeted and mod.GPSRunBudgetedWork and mod.GPSPlanningCheckpoint then
			if not SameRequest(requested, request) or not nativeJob then
				requested = request
				nativeJob = { request = request }
				nativeJob.co = coroutine.create(function() BuildRoute(request, mod.GPSPlanningCheckpoint) end)
			end
			if lastMap ~= host then root:Hide() end
			return
		end
		nativeJob, requested = nil, nil
		BuildRoute(request)
	end
	Head(status, host, continent, width, height, scale, style, changed)
	root:SetShown(drawn > 0 or lineDrawn > 0 or headShown)
end

function mod.GPSNativeStats()
	return { drawn = drawn, pooled = #dots, redraws = redraws, map = lastMap,
		lines = lineDrawn + (headShown and 1 or 0), linePooled = #lines + (head and 1 or 0),
		headShown = headShown, headUpdates = headUpdates, pointLimit = MAX_POINTS,
		shown = root and root:IsShown() or false, networkDrawn = networkDrawn,
		drawingPending = nativeJob ~= nil,
		networkPooled = #networkDots, networkRedraws = networkRedraws,
		networkNodesDrawn = networkNodesDrawn, networkNodesPooled = #networkNodes,
		networkShown = networkRoot and networkRoot:IsShown() or false }
end
