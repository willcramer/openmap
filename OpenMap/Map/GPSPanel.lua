--------------------------------------------------------------------------------
-- GPS controls and guidance stay on screen when the map closes. The green path
-- shares the map's line/pin pools; only its leading anchor moves with the player.
--------------------------------------------------------------------------------

local _, ns = ...
local mod = ns:GetModule("worldmap")
local S, L, Safe = ns.MapStitch, ns.L, ns.Safe
local panel, hud, ticker, trail
local drawnRoute, drawnIndex, drawnActive, drawnCount
local playerPin, playerLine, firstPoint
local MAX_ROUTE_POINTS = 25000 -- the supplied graph plus all permitted recorded samples and stair steps
local mode = "once"
local MODES = { "once", "reverse", "loop", "pingpong" }
local MODE_NAMES = { once = L["Once"], reverse = L["Reverse"], loop = L["Loop"], pingpong = L["Back and forth"] }
local GREEN = { 0.15, 1, 0.25 }
local DOT = { atlas = "WhiteCircle-RaidBlips", texture = "Interface\\Buttons\\WHITE8X8", size = 7, color = GREEN }
local TARGET = { atlas = DOT.atlas, texture = DOT.texture, size = 10, color = GREEN }
mod.GPSRouteStyle = { color = GREEN, thickness = 3, nodeSize = DOT.size, targetSize = TARGET.size }

local function Button(parent, text, width, x, y, fn)
	local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
	b:SetSize(width, 24)
	b:SetPoint("TOPLEFT", x, y)
	b:SetText(text)
	b:SetScript("OnClick", fn)
	return b
end

local function Label(parent, font, x, y, width)
	local text = parent:CreateFontString(nil, "OVERLAY", font)
	text:SetPoint("TOPLEFT", x, y)
	text:SetWidth(width)
	text:SetJustifyH("LEFT")
	return text
end

local function Movable(frame, key, x, y)
	frame:SetMovable(true)
	frame:SetClampedToScreen(true)
	frame:EnableMouse(true)
	frame:RegisterForDrag("LeftButton")
	frame:SetScript("OnDragStart", function(self) self:StartMoving() end)
	frame:SetScript("OnDragStop", function(self)
		self:StopMovingOrSizing()
		local point, _, relative, ox, oy = self:GetPoint(1)
		if point then mod.db[key] = { point, relative, ox, oy } end
	end)
	local saved = mod.db[key]
	if type(saved) == "table" then frame:SetPoint(saved[1], UIParent, saved[2], saved[3], saved[4])
	else frame:SetPoint("CENTER", UIParent, "CENTER", x, y) end
end

local function Result(ok, err)
	if not ok and err then
		ns:Print(err)
		if panel then panel.message:SetText(err) end
	elseif panel then panel.message:SetText("") end
	return ok
end

local function Waypoint()
	local mapID, x, y = mod.WaypointPoint()
	if not mapID then return Result(nil, L["Set a waypoint first, or Alt-click the map to start GPS."]) end
	return Result(mod.GPSStart(mapID, x, y, L["Waypoint"]))
end

local function Distance(yards)
	if type(yards) ~= "number" or yards ~= yards or yards == math.huge or yards == -math.huge then return "" end
	return L["%d yd"]:format(math.floor(yards + 0.5))
end

local function RecordingText(status)
	if status.recordingState == "gap" then return L["Recording paused after a position gap. Save the partial trail or discard it."] end
	if status.recordingState == "full" then return L["The recording is full. Save the partial trail or discard it."] end
	return L["Recording: %s (%d points)"]:format(status.recording, status.recorded or 0)
end

local function StopOrDiscard()
	if mod.GPSStatus().recording then Result(mod.GPSCancelRecording()) else mod.GPSStop() end
end

local function Number(value)
	value = Safe.Value(value)
	return type(value) == "number" and value == value and math.abs(value) < math.huge and value or nil
end

local function Placed(point)
	return type(point) == "table" and Number(point.u) and Number(point.v) and Number(point.cont)
end

local function Line(a, b)
	return S.AddLine(trail, a.u, a.v, b.u, b.v, 3, GREEN[1], GREEN[2], GREEN[3], 1)
end

function mod.GPSDrawRoute(status)
	if not S.IsBuilt() then return end
	if not trail then trail = S.PinSet("gps", 0, 4) end
	status = status or {}
	local route = type(status.route) == "table" and status.route or nil
	local index = math.max(1, math.floor(Number(status.index) or 1))
	local count = route and #route or 0
	if drawnRoute ~= route or drawnIndex ~= index or drawnActive ~= status.active or drawnCount ~= count then
		drawnRoute, drawnIndex, drawnActive, drawnCount = route, index, status.active, count
		S.ClearPinSet(trail)
		playerPin, playerLine, firstPoint = nil, nil, nil
		if status.active and route then
			local previous
			for i = index, math.min(count, index + MAX_ROUTE_POINTS - 1) do
				local point = route[i]
				if Placed(point) then
					local pin = S.AddPin(trail, point.u, point.v, i == count and TARGET or DOT)
					pin:EnableMouse(false)
					if i == index then firstPoint = point end
					if previous and previous.cont == point.cont then Line(previous, point) end
					previous = point
				else
					-- An unprojectable waypoint is a break, not permission to join
					-- its neighbours across a different map or hidden floor.
					previous = nil
				end
			end
		end
	end
	if not status.active or not firstPoint then return end
	local player = status.player
	local u, v, continent
	if Placed(player) and not player.unknown and not player.ambiguous
		and (player.layer == nil or firstPoint.layer == nil or player.layer == firstPoint.layer)
		and not (mod.GPSOtherFloor and mod.GPSOtherFloor(player, firstPoint)) then
		u, v, continent = player.u, player.v, player.cont
	end
	if not u or continent ~= firstPoint.cont then
		if playerLine then playerLine:Hide() playerPin:Hide() end
		return
	end
	if not playerPin then
		playerPin = S.AddPin(trail, u, v, DOT)
		playerPin:EnableMouse(false)
		playerLine = Line({ u = u, v = v }, firstPoint)
		-- Lines remain screen-sized on the view. Move only this pin's existing
		-- world anchor as the player walks; the remaining road never rebuilds.
		playerLine:SetStartPoint("CENTER", playerPin)
	else
		S.MovePin(trail, playerPin, u, v)
	end
	playerPin:Show()
	playerLine:Show()
end

local function Refresh()
	if not mod.GPSStatus then return end
	local status = mod.GPSStatus()
	mod.GPSDrawRoute(status)
	if mod.GPSDrawNative then mod.GPSDrawNative(status) end
	if mod.GPSRefreshRoadView then mod.GPSRefreshRoadView() end
	if hud then
		hud:SetShown(status.active or status.state == "faction-stop" or status.recording ~= nil and status.recording ~= false)
		hud.title:SetText(status.recording and L["Recording: %s"]:format(status.recording) or status.title or L["GPS"])
		hud.instruction:SetText(status.recording and RecordingText(status) or status.instruction or "")
		hud.stop:SetText(status.recording and L["Discard"] or L["Stop"])
		local distance = Distance(status.distance)
		if status.active and status.total and status.total > 1 then
			distance = L["%s · step %d/%d"]:format(distance, status.index or 1, status.total)
		elseif status.recording then distance = L["%d points recorded"]:format(status.recorded or 0) end
		hud.distance:SetText(distance)
		local facing = Safe.Call(GetPlayerFacing)
		local arrow = status.active and type(status.bearing) == "number" and type(facing) == "number"
		hud.arrow:SetShown(arrow and true or false)
		if arrow then hud.arrow:SetRotation(status.bearing - facing) end
	end
	if panel and panel:IsShown() then
		local text = status.instruction or L["Choose a waypoint or a saved route."]
		if status.recording then text = RecordingText(status) end
		panel.status:SetText(text)
		panel.save:SetEnabled(status.recording and true or false)
		panel.save:SetText((status.recordingState == "gap" or status.recordingState == "full") and L["Save partial"] or L["Save route"])
		panel.stop:SetText(status.recording and L["Discard recording"] or L["Stop GPS"])
	end
end

local function BuildHUD()
	hud = CreateFrame("Frame", "OpenMapGPSGuide", UIParent)
	hud:SetSize(330, 124)
	hud:SetFrameStrata("MEDIUM")
	ns.Look:Panel(hud, { alpha = 0.92 })
	Movable(hud, "gpsGuideAt", 0, 210)
	hud.arrow = hud:CreateTexture(nil, "ARTWORK")
	hud.arrow:SetTexture("Interface\\Minimap\\MinimapArrow")
	hud.arrow:SetSize(48, 48)
	hud.arrow:SetPoint("TOPLEFT", 12, -28)
	hud.title = Label(hud, "GameFontNormal", 14, -10, 260)
	hud.title:SetWordWrap(false)
	hud.instruction = Label(hud, "GameFontHighlightSmall", 72, -35, 242)
	hud.distance = Label(hud, "GameFontNormalSmall", 72, -82, 242)
	hud.stop = Button(hud, L["Stop"], 66, 252, -94, function() StopOrDiscard() Refresh() end)
	hud:Hide()
end

local function CycleRoute()
	local names = mod.GPSList()
	if #names == 0 then return Result(nil, L["No saved GPS routes. Record a route first."]) end
	local current = panel.name:GetText()
	local nextIndex = 1
	for i, name in ipairs(names) do if name == current then nextIndex = i % #names + 1 break end end
	panel.name:SetText(names[nextIndex])
	panel.name:ClearFocus()
end

local function BuildPanel()
	panel = CreateFrame("Frame", "OpenMapGPSPanel", UIParent)
	panel:SetFrameStrata("DIALOG")
	local top = ns.Look:Window(panel, L["GPS navigation"])
	panel:SetSize(360, 262 + top)
	Movable(panel, "gpsPanelAt", 0, 0)
	local y = -math.max(top, 24) - 12
	local help = Label(panel, "GameFontHighlightSmall", 18, y, 324)
	help:SetText(L["Alt-click the map for GPS. Record roads you walk to use them for future journeys."])
	Button(panel, L["Guide to waypoint"], 158, 18, y - 42, function() Waypoint() Refresh() end)
	panel.stop = Button(panel, L["Stop GPS"], 158, 184, y - 42, function() StopOrDiscard() Refresh() end)
	panel.name = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
	panel.name:SetSize(242, 24)
	panel.name:SetPoint("TOPLEFT", 24, y - 80)
	panel.name:SetAutoFocus(false)
	panel.name:SetMaxLetters(64)
	panel.name:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
	panel.name:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
	Button(panel, L["Routes"], 66, 276, y - 80, CycleRoute)
	Button(panel, L["Record"], 100, 18, y - 114, function()
		Result(mod.GPSRecord(panel.name:GetText()))
		panel.name:ClearFocus()
		Refresh()
	end)
	panel.save = Button(panel, L["Save route"], 100, 130, y - 114, function()
		local state = mod.GPSStatus().recordingState
		Result(mod.GPSSave(state == "gap" or state == "full"))
		Refresh()
	end)
	panel.mode = Button(panel, MODE_NAMES[mode], 100, 242, y - 114, function()
		for i, value in ipairs(MODES) do if value == mode then mode = MODES[i % #MODES + 1] break end end
		panel.mode:SetText(MODE_NAMES[mode])
	end)
	Button(panel, L["Follow saved route"], 324, 18, y - 146, function()
		Result(mod.GPSPlay(panel.name:GetText(), mode))
		panel.name:ClearFocus()
		Refresh()
	end)
	panel.status = Label(panel, "GameFontHighlightSmall", 18, y - 182, 324)
	panel.message = Label(panel, "GameFontRedSmall", 18, y - 210, 324)
	panel:Hide()
	if mod.padRoots then mod.padRoots[#mod.padRoots + 1] = panel end
end

function mod:ToggleGPS(on)
	self:SetupGPSPanel()
	if not panel then BuildPanel() end
	if on == nil then on = not panel:IsShown() end
	panel:SetShown(on)
	Refresh()
end

function mod.GPSShown() return panel and panel:IsShown() or false end

function mod.GPSGoWorld(u, v, title)
	u, v = Safe.Value(u), Safe.Value(v)
	if type(u) ~= "number" or type(v) ~= "number" or u ~= u or v ~= v
		or u < 0 or u > 1 or v < 0 or v > 1 or not S.IsBuilt() then return false end
	local chain = S.ChainAt(u, v)
	local mapID = chain and chain[#chain]
	if not mapID or mapID == S.WORLD or not S.Rect(mapID) then return false end
	local x, y = mod.FromWorld(mapID, u, v)
	if not x or not y or x < 0 or x > 1 or y < 0 or y > 1 then return false end
	return Result(mod.GPSStart(mapID, x, y, title)) and true or false
end

function mod:BuildGPSPanel()
	drawnRoute, drawnIndex, drawnActive, drawnCount = nil, nil, nil, nil
	Refresh()
end

function mod:SetupGPSPanel()
	if ticker or not mod.GPSUpdate then return end
	BuildHUD()
	if mod.SetupGPSRooms then mod:SetupGPSRooms() end
	if mod.SetupGPSNative then mod:SetupGPSNative() end
	ticker = CreateFrame("Frame", nil, UIParent)
	local elapsed = 0
	ticker:SetScript("OnUpdate", function(_, dt)
		elapsed = elapsed + dt
		if elapsed < 0.2 then return end
		elapsed = 0
		mod.GPSUpdate()
		Refresh()
	end)
	local previous = mod.OnGPSChanged
	mod.OnGPSChanged = function()
		if previous then previous() end
		Refresh()
	end
end

function mod:GPSCommand(rest)
	self:SetupGPSPanel()
	rest = (rest or ""):match("^%s*(.-)%s*$")
	local command, args = rest:match("^(%S+)%s*(.*)$")
	command = command and command:lower() or "panel"
	if command == "panel" then self:ToggleGPS()
	elseif command == "roads" and mod.GPSSetRoadsShown then
		mod.GPSSetRoadsShown(args == "on" or args ~= "off" and not mod.GPSRoadsShown())
	elseif command == "waypoint" then Waypoint()
	elseif command == "stop" then mod.GPSStop()
	elseif command == "record" then Result(mod.GPSRecord(args))
	elseif command == "save" then Result(mod.GPSSave())
	elseif command == "savepartial" then Result(mod.GPSSave(true))
	elseif command == "cancelrecord" then Result(mod.GPSCancelRecording())
	elseif command == "follow" then
		local first, name = args:match("^(%S+)%s+(.+)$")
		if MODE_NAMES[first] then Result(mod.GPSPlay(name, first)) else Result(mod.GPSPlay(args, "once")) end
	elseif command == "delete" then Result(mod.GPSDelete(args))
	elseif command == "list" then
		local names = mod.GPSList()
		ns:Print(#names > 0 and table.concat(names, ", ") or L["No saved GPS routes. Record a route first."])
	elseif command == "go" then
		local mapID, x, y = args:match("^(%d+)%s+([%d%.]+)%s+([%d%.]+)$")
		mapID, x, y = tonumber(mapID), tonumber(x), tonumber(y)
		if mapID and x and y then Result(mod.GPSStart(mapID, x / 100, y / 100))
		else Result(nil, L["Usage: /openmap gps go <mapID> <x 0-100> <y 0-100>"]) end
	elseif command == "status" then
		local status = mod.GPSStatus()
		ns:Print(status.recording and RecordingText(status) or (status.active or status.state == "faction-stop")
			and status.instruction or L["GPS is stopped."])
		if status.active then ns:Print(L["Remaining: %s"]:format(Distance(status.remaining))) end
		if mod.GPSRoadStats then
			local roads = mod.GPSRoadStats()
			if roads.nodes > 0 then ns:Print(L["Road network: %d nodes (%s)"]:format(roads.nodes, roads.version or "")) end
		end
	else
		ns:Print(L["GPS: waypoint, go <mapID> <x> <y>, stop, record <name>, save, savepartial, cancelrecord, follow [once/reverse/loop/pingpong] <name>, list, delete <name>, status."])
	end
	Refresh()
end
