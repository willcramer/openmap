-- Route marks on native maps outside the stitched canvas (Zephras Isle).
-- Everything drawn belongs to this addon; map layout and other pins stay alone.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local Safe = ns.Safe
local MAX_DOTS = 300
local NATIVE = { [2521] = 2991, [2665] = 2991 }
local map, root, canvas
local dots, drawn, redraws = {}, 0, 0
local lastRoute, lastIndex, lastMap, lastWidth, lastHeight, lastScale, lastCount
local networkRoot, networkCanvas, networkData, networkMap, networkWidth, networkHeight, networkScale
local networkDots, networkDrawn, networkRedraws = {}, 0, 0
local NETWORK_LIMIT = 800
local NETWORK_COLORS = {
	default = { 0.72, 0.67, 0.51 }, alliance = { 0.3, 0.5, 0.9 }, horde = { 0.8, 0.3, 0.25 },
	swim = { 0.3, 0.75, 0.8 }, offroad = { 0.5, 0.5, 0.5 },
}

local function Number(value)
	value = Safe.Value(value)
	if type(value) == "number" and value == value and math.abs(value) < math.huge then return value end
end

local function Hide()
	if root then root:Hide() end
	drawn, lastRoute = 0, nil
end

local function HideNetwork()
	if networkRoot then networkRoot:Hide() end
	networkDrawn, networkData = 0, nil
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
	end
	if canvas ~= nextCanvas then
		canvas, lastRoute = nextCanvas, nil
		root:SetParent(canvas)
		root:ClearAllPoints()
		root:SetAllPoints(canvas)
		root:SetFrameLevel(canvas:GetFrameLevel() + 10)
	end
end

local function DrawNetwork(nextCanvas, host, continent, width, height, scale)
	local data = ns.GPSRoadData
	local network = data and data.networks and data.networks[continent]
	if not network then HideNetwork() return end
	if data == networkData and nextCanvas == networkCanvas and host == networkMap
		and width == networkWidth and height == networkHeight and scale == networkScale then
		if networkRoot then networkRoot:SetShown(networkDrawn > 0) end
		return
	end
	if not networkRoot then
		networkRoot = CreateFrame("Frame", nil, nextCanvas)
		networkRoot:EnableMouse(false)
	end
	if networkCanvas ~= nextCanvas then
		networkRoot:SetParent(nextCanvas)
		networkRoot:ClearAllPoints()
		networkRoot:SetAllPoints(nextCanvas)
		networkRoot:SetFrameLevel(nextCanvas:GetFrameLevel() + 9)
	end
	networkData, networkCanvas, networkMap = data, nextCanvas, host
	networkWidth, networkHeight, networkScale = width, height, scale
	networkRedraws = networkRedraws + 1
	local points, ids = {}, {}
	for id, node in pairs(network.nodes or {}) do
		if Number(id) then
			local projected = Project({ cont = continent, wx = node.wx, wy = node.wy, layer = node.layer }, host, continent)
			if projected then points[id], ids[#ids + 1] = projected, id end
		end
	end
	table.sort(ids)
	local segments, total = {}, 0
	for _, id in ipairs(ids) do
		local a = network.nodes[id]
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
				local first, last = Clip(points[id], points[target])
				if first then
					local distance = math.sqrt(((last[1] - first[1]) * width) ^ 2 + ((last[2] - first[2]) * height) ^ 2)
					if distance > 0 then
						segments[#segments + 1] = { first, last, distance, NETWORK_COLORS[a.type or b.type] or NETWORK_COLORS.default }
						total = total + distance
					end
				end
			end
		end
	end
	networkDrawn = 0
	local spacing, carry = math.max(7 / scale, total / (NETWORK_LIMIT - 1)), 0
	for _, segment in ipairs(segments) do
		local first, last, distance, color = segment[1], segment[2], segment[3], segment[4]
		local along = carry
		while along <= distance and networkDrawn < NETWORK_LIMIT do
			local fraction = along / distance
			networkDrawn = networkDrawn + 1
			local dot = networkDots[networkDrawn]
			if not dot then
				dot = networkRoot:CreateTexture(nil, "ARTWORK")
				dot:SetTexture("Interface\\Buttons\\WHITE8X8")
				networkDots[networkDrawn] = dot
			end
			dot:ClearAllPoints()
			dot:SetPoint("CENTER", networkRoot, "TOPLEFT", (first[1] + (last[1] - first[1]) * fraction) * width,
				-(first[2] + (last[2] - first[2]) * fraction) * height)
			dot:SetSize(3 / scale, 3 / scale)
			dot:SetVertexColor(color[1], color[2], color[3], 0.8)
			dot:Show()
			along = along + spacing
		end
		carry = along - distance
	end
	for i = networkDrawn + 1, #networkDots do networkDots[i]:Hide() end
	networkRoot:SetShown(networkDrawn > 0)
end

function mod:SetupGPSNative(worldMap)
	if map then return end
	map = worldMap or _G.WorldMapFrame
	if map and map.HookScript then map:HookScript("OnHide", HideAll) end
end

function mod.GPSDrawNative(status)
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
	local index = math.max(1, math.floor(Number(status.index) or 1) - 1)
	if status.route == lastRoute and index == lastIndex and host == lastMap and width == lastWidth
		and height == lastHeight and scale == lastScale and #status.route == lastCount then
		root:SetShown(drawn > 0)
		return
	end
	lastRoute, lastIndex, lastMap = status.route, index, host
	lastWidth, lastHeight, lastScale, lastCount = width, height, scale, #status.route
	redraws = redraws + 1
	local segments, previous, first, final, length = {}, nil, nil, nil, 0
	for i = index, #status.route do
		local point = Project(status.route[i], host, continent)
		if point and point[1] >= 0 and point[1] <= 1 and point[2] >= 0 and point[2] <= 1 then
			first, final = first or point, point
		end
		if previous and point then
			local a, b = Clip(previous, point)
			if a then
				local distance = math.sqrt(((b[1] - a[1]) * width) ^ 2 + ((b[2] - a[2]) * height) ^ 2)
				segments[#segments + 1] = { a, b, distance }
				first, final, length = first or a, b, length + distance
			end
		end
		previous = point
	end
	drawn = 0
	local function Dot(point)
		if not point or drawn >= MAX_DOTS then return end
		drawn = drawn + 1
		local dot = dots[drawn]
		if not dot then
			dot = root:CreateTexture(nil, "ARTWORK")
			dot:SetTexture("Interface\\Buttons\\WHITE8X8")
			dot:SetVertexColor(1, 0.75, 0.15, 0.95)
			dots[drawn] = dot
		end
		dot:ClearAllPoints()
		dot:SetPoint("CENTER", root, "TOPLEFT", point[1] * width, -point[2] * height)
		dot:SetSize(5 / scale, 5 / scale)
		dot:Show()
	end
	Dot(first)
	local spacing = math.max(9 / scale, length / (MAX_DOTS - 2))
	local carry = spacing
	for _, segment in ipairs(segments) do
		local a, b, distance = segment[1], segment[2], segment[3]
		local along = carry
		while along < distance and drawn < MAX_DOTS - 1 do
			local t = along / distance
			Dot({ a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t })
			along = along + spacing
		end
		carry = along - distance
	end
	if final and final ~= first then Dot(final) end
	for i = drawn + 1, #dots do dots[i]:Hide() end
	root:SetShown(drawn > 0)
end

function mod.GPSNativeStats()
	return { drawn = drawn, pooled = #dots, redraws = redraws, map = lastMap,
		shown = root and root:IsShown() or false, networkDrawn = networkDrawn,
		networkPooled = #networkDots, networkRedraws = networkRedraws,
		networkShown = networkRoot and networkRoot:IsShown() or false }
end
