-- A location is captured before the cursor moves into the menu. Blizzard's
-- context-menu framework owns Escape, outside clicks and owner visibility.
local _, ns = ...
local mod = ns:GetModule("worldmap")
local S, Safe, L = ns.MapStitch, ns.Safe, ns.L
mod.defaults.mapRightClick = "menu"
mod.defaults.gpsRightClickMenuDefault = true

local migrate = mod.Migrate
function mod.Migrate(db)
	if migrate then migrate(db) end
	-- Earlier builds saved zoom as their filled default. Adopt the new default
	-- once, then retain any later explicit zoom choice across reloads/imports.
	if not db.gpsRightClickMenuDefault then
		db.mapRightClick, db.gpsRightClickMenuDefault = "menu", true
	end
end

local activeMenu, activeTarget
local nativeMap
local nativePress, nativeWatch
local NATIVE_MAPS = { [2521] = true, [2665] = true }

local function Editing()
	return mod.GPSRoadEditing and mod.GPSRoadEditing() or false
end

local function Result(ok, err)
	if not ok and err then ns:Print(err) end
	return ok
end

StaticPopupDialogs.OPENMAP_GPS_DELETE_NODE = {
	text = L["Delete this road node and its connections?"],
	button1 = L["Delete"], button2 = CANCEL,
	OnAccept = function(_, data)
		if Editing() and data and mod.db and mod.db.gpsManualRoads == data.roads and mod.GPSRoadEditDelete then
			Result(mod.GPSRoadEditDelete(data.ref))
		end
	end,
	timeout = 0, whileDead = true, hideOnEscape = true,
}

local function Number(value)
	value = Safe.Value(value)
	return type(value) == "number" and value == value and math.abs(value) < math.huge and value or nil
end

local function Location(mapID, x, y)
	mapID, x, y = Number(mapID), Number(x), Number(y)
	if not mapID or mapID < 1 or mapID % 1 ~= 0 or not x or not y
		or x < 0 or x > 1 or y < 0 or y > 1 then return end
	return { map = mapID, x = x, y = y }
end

function mod.CloseLocationMenu()
	local menu = activeMenu
	activeMenu, activeTarget = nil, nil
	local framework = _G.Menu
	local manager = menu and framework and framework.GetManager and framework.GetManager()
	if manager and manager.CloseMenu then manager:CloseMenu(menu) end
end

local function Open(target, owner)
	local map, util = _G.WorldMapFrame, _G.MenuUtil
	if not target or not map or not map:IsShown() or mod.instanceWorldHidden
		or (mod.DungeonViewShown and mod.DungeonViewShown())
		or not util or type(util.CreateContextMenu) ~= "function" then return false end
	mod.CloseLocationMenu()
	activeTarget = target
	local function Action(callback)
		return function()
			if activeTarget ~= target then return end
			mod.CloseLocationMenu()
			callback()
		end
	end
	local menu = util.CreateContextMenu(owner or map, function(_, root)
		if Editing() then
			local selected = mod.GPSRoadSelected and mod.GPSRoadSelected()
			local nearest
			if mod.GPSRoadEditNearest then nearest = mod.GPSRoadEditNearest(target.map, target.x, target.y) end
			local linked = selected and nearest and mod.GPSRoadEditLinked and mod.GPSRoadEditLinked(selected, nearest)
			local function Edit(label, enabled, callback)
				local row = root:CreateButton(label, Action(function()
					if Editing() then callback() end
				end))
				row:SetEnabled(enabled and true or false)
			end
			Edit(L["Add road node"], mod.GPSRoadEditAdd, function()
				Result(mod.GPSRoadEditAdd(target.map, target.x, target.y))
			end)
			Edit(L["Add connected node"], selected and mod.GPSRoadEditAdd, function()
				Result(mod.GPSRoadEditAdd(target.map, target.x, target.y, selected))
			end)
			Edit(L["Select road node"], nearest and mod.GPSRoadEditSelect, function()
				Result(mod.GPSRoadEditSelect(nearest))
			end)
			Edit(L["Connect selected node"], selected and nearest and selected ~= nearest and not linked and mod.GPSRoadEditConnect, function()
				Result(mod.GPSRoadEditConnect(selected, nearest))
			end)
			Edit(L["Disconnect selected node"], linked and mod.GPSRoadEditDisconnect, function()
				Result(mod.GPSRoadEditDisconnect(selected, nearest))
			end)
			Edit(L["Delete road node"], type(nearest) == "string" and nearest:match("^m:") and mod.GPSRoadEditDelete, function()
				StaticPopup_Show("OPENMAP_GPS_DELETE_NODE", nil, nil, { ref = nearest, roads = mod.db.gpsManualRoads })
			end)
			Edit(L["Clear selection"], selected and mod.GPSRoadEditSelect, function()
				Result(mod.GPSRoadEditSelect(nil))
			end)
			Edit(L["Finish editing"], mod.GPSSetRoadEditing, function() Result(mod.GPSSetRoadEditing(false)) end)
			return
		end
		local waypoint = root:CreateButton(L["Place waypoint"], Action(function()
			mod.TrackPoint(target.map, target.x, target.y, L["Waypoint"])
		end))
		waypoint:SetEnabled(type(mod.TrackPoint) == "function")
		local note = root:CreateButton(L["Add note"], Action(function()
			-- A note should not replace an active navigation destination.
			mod.AddPin(target.map, target.x, target.y, false)
		end))
		note:SetEnabled(type(mod.AddPin) == "function")
		local gps = root:CreateButton(L["Go Here"], Action(function()
			local ok, err = mod.GPSStart(target.map, target.x, target.y)
			if not ok and err then ns:Print(err) end
		end))
		gps:SetEnabled(type(mod.GPSStart) == "function")
		if mod.GPSSetRoadEditing then
			root:CreateButton(L["Edit road network"], Action(function() Result(mod.GPSSetRoadEditing(true)) end))
		end
	end)
	if not menu then activeTarget = nil return false end
	activeMenu = menu
	menu:SetClosedCallback(function()
		if activeMenu == menu then activeMenu, activeTarget = nil, nil end
	end)
	return true
end

function mod.OpenLocationMenu(u, v, owner)
	u, v = Number(u), Number(v)
	if not u or not v or u < 0 or u > 1 or v < 0 or v > 1 or not S.IsBuilt() then return false end
	local chain = S.ChainAt(u, v)
	local mapID = chain and chain[#chain]
	if not mapID or mapID == S.WORLD or not S.Rect(mapID) then return false end
	local x, y = mod.FromWorld(mapID, u, v)
	return Open(Location(mapID, x, y), owner)
end

function mod:ContextMenuOptions(opts, get, set, off)
	opts.mapRightClick = { type = "select", name = L["Right-click on the map"], order = 35,
		values = { zoom = L["Zoom out"], menu = L["Open location menu"] }, sorting = { "zoom", "menu" },
		get = get, disabled = off,
		set = function(info, value)
			if value ~= "zoom" and value ~= "menu" then return end
			mod.CloseLocationMenu()
			set(info, value)
		end,
		desc = L["Choose whether right-click zooms out or opens waypoint, note and GPS actions."] }
end

local function NativeClick(map, button)
	if button ~= "RightButton" or not mod.db or mod.db.enabled == false or (mod.db.mapRightClick ~= "menu" and not Editing())
		or (mod.IsStitched and mod.IsStitched()) or (mod.PadViewOn and mod.PadViewOn())
		or (mod.IsSketching and mod:IsSketching()) or (mod.PinMode and mod.PinMode()) then return false end
	local mapID = Number(Safe.Call(map.GetMapID, map))
	if not NATIVE_MAPS[mapID] or type(map.GetNormalizedCursorPosition) ~= "function" then return false end
	if nativeWatch then nativeWatch:Hide() end
	local moved = nativePress and nativePress.moved
	nativePress = nil
	if moved then return true end
	local ok, x, y = pcall(map.GetNormalizedCursorPosition, map)
	if not ok then return false end
	return Open(Location(mapID, x, y), map)
end

function mod.SetupLocationMenu()
	local map = _G.WorldMapFrame
	if not map or nativeMap == map or type(map.AddCanvasClickHandler) ~= "function" then return end
	nativeMap = map
	map:AddCanvasClickHandler(NativeClick, 1001)
	map:HookScript("OnHide", mod.CloseLocationMenu)
	if type(map.OnMapChanged) == "function" then hooksecurefunc(map, "OnMapChanged", mod.CloseLocationMenu) end
	-- The native canvas's own drag test compares only its start/end positions.
	-- Remember movement during the press too, as the stitched/controller views do.
	local sc = map.ScrollContainer
	if sc and sc.HookScript then
		nativeWatch = CreateFrame("Frame", nil, map)
		nativeWatch:Hide()
		nativeWatch:SetScript("OnUpdate", function()
			if not nativePress or not IsMouseButtonDown("RightButton") then nativeWatch:Hide() return end
			local x, y = GetCursorPosition()
			x, y = Number(x), Number(y)
			if x and y then
				local dx, dy = x - nativePress.x, y - nativePress.y
				if dx * dx + dy * dy > 20 then nativePress.moved = true end
			end
		end)
		sc:HookScript("OnMouseDown", function(_, button)
			if button ~= "RightButton" then return end
			local mapID = Number(Safe.Call(map.GetMapID, map))
			if not mod.db or (mod.db.mapRightClick ~= "menu" and not Editing()) or not NATIVE_MAPS[mapID] then return end
			local x, y = GetCursorPosition()
			x, y = Number(x), Number(y)
			if x and y then nativePress = { x = x, y = y } nativeWatch:Show() end
		end)
		map:HookScript("OnHide", function() nativePress = nil nativeWatch:Hide() end)
	end
end

local owner = {}
ns.RegisterEvent(owner, "PLAYER_LOGIN", function()
	mod.SetupLocationMenu()
	if not nativeMap and EventUtil and EventUtil.ContinueOnAddOnLoaded then
		EventUtil.ContinueOnAddOnLoaded("Blizzard_WorldMap", mod.SetupLocationMenu)
	end
end)
