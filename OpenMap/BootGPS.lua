-- Loaded first only by the separately packaged OpenMapGPS addon. The packager
-- leaves this file's identifiers intact: "OpenMap" here means the original.
local _, ns = ...
local L = setmetatable({}, { __index = function(_, key) return ns.L and ns.L[key] or key end })
local function Print(text) DEFAULT_CHAT_FRAME:AddMessage("|cffe6b85cOpenMap - GPS|r: " .. text) end
local addons = C_AddOns
local originalLoaded = addons and addons.IsAddOnLoaded and addons.IsAddOnLoaded("OpenMap")
ns.variantDormant = originalLoaded and true or false
local dispatch

local function Switch(target)
	if InCombatLockdown and InCombatLockdown() then
		Print(L["Leave combat before switching map addons."])
		return false
	end
	if not addons or not addons.EnableAddOn or not addons.DisableAddOn or not addons.SaveAddOns or not ReloadUI then
		Print(L["Use the AddOns list to enable one map addon, then reload."])
		return false
	end
	if target == "original" and addons.DoesAddOnExist and not addons.DoesAddOnExist("OpenMap") then
		Print(L["The original OpenMap is not installed. Install it beside OpenMapGPS first."])
		return false
	end
	-- The Forever/retail AddOns list keys per-character overrides by GUID.
	-- A display name can be accepted without changing the current character.
	local character = UnitGUID("player")
	if type(character) ~= "string" or character == "" then
		Print(L["Use the AddOns list to enable one map addon, then reload."])
		return false
	end
	-- This handoff is private to the explicit settings-import round trip.
	-- Ordinary addon selection is controlled through the game's AddOns list.
	local ok = pcall(function()
		addons.EnableAddOn("OpenMapGPS", character)
		if target == "gps" then addons.DisableAddOn("OpenMap", character)
		else addons.EnableAddOn("OpenMap", character) end
		-- Commit the changed enable list before reloading, as the AddOns UI does.
		addons.SaveAddOns()
	end)
	if not ok then
		Print(L["Use the AddOns list to enable one map addon, then reload."])
		return false
	end
	ReloadUI()
	return true
end

-- Import through the original's live saved tables, never by sharing their
-- SavedVariables names or loading its map code while GPS controls the map.
local function Copy(value, seen)
	local kind = type(value)
	if kind ~= "table" then
		if kind == "string" or kind == "number" or kind == "boolean" then return value end
		return
	end
	seen = seen or {}
	if seen[value] then return seen[value] end
	local result = {}
	seen[value] = result
	for key, item in pairs(value) do
		if type(key) == "string" or type(key) == "number" then result[key] = Copy(item, seen) end
	end
	return result
end

local function GPSCharacter()
	if type(rawget(_G, "OpenMapGPSCharDB")) ~= "table" then OpenMapGPSCharDB = {} end
	return OpenMapGPSCharDB
end

local function ImportSettings()
	local original = rawget(_G, "OpenMap")
	local mod = type(original) == "table" and original.modules and original.modules.worldmap
	local account, character = rawget(_G, "OpenMapDB"), rawget(_G, "OpenMapCharDB")
	if not mod or type(mod.defaults) ~= "table" or type(account) ~= "table"
		or type(account.worldmap) ~= "table" or type(character) ~= "table"
		or type(character.worldmap) ~= "table" then return false end
	local target = Copy(rawget(_G, "OpenMapGPSDB")) or {}
	local targetChar = Copy(rawget(_G, "OpenMapGPSCharDB")) or {}
	target.worldmap = type(target.worldmap) == "table" and target.worldmap or {}
	targetChar.worldmap = type(targetChar.worldmap) == "table" and targetChar.worldmap or {}
	-- Pins, drawings, measurements and history are user data, not preferences.
	local excluded = { enabled = true, pins = true, paint = true, flightTimes = true, newsSeen = true }
	for key in pairs(mod.defaults) do
		if type(key) == "string" and not excluded[key] and key:sub(1, 3):lower() ~= "gps" then
			local value = account.worldmap[key]
			if key == "sketch" then
				local sketch = type(target.worldmap.sketch) == "table" and target.worldmap.sketch or {}
				for _, setting in ipairs({ "tool", "ink", "size", "mark" }) do
					if type(value) == "table" and value[setting] ~= nil then sketch[setting] = Copy(value[setting]) end
				end
				target.worldmap.sketch = sketch
			elseif value ~= nil then target.worldmap[key] = Copy(value) end
		end
	end
	-- Other character fields hold waypoints, CVar restoration, caches or reports.
	for _, key in ipairs({ "unexplored", "unexploredOwn" }) do
		targetChar.worldmap[key] = Copy(character.worldmap[key])
	end
	targetChar.gpsSettingsSyncResult = true
	OpenMapGPSDB, OpenMapGPSCharDB = target, targetChar
	return true
end

local function CompleteImport()
	local ok, copied = pcall(ImportSettings)
	if not ok or not copied then Print(L["Map settings could not be copied."]) return false end
	if not Switch("gps") then
		GPSCharacter().gpsSettingsSyncResult = nil
		Print(L["Map settings copied to GPS."])
	end
	return true
end

local function SyncSettings()
	if InCombatLockdown and InCombatLockdown() then
		Print(L["Leave combat before switching map addons."])
		return
	end
	if addons and addons.DoesAddOnExist and not addons.DoesAddOnExist("OpenMap") then
		Print(L["The original OpenMap is not installed. Install it beside OpenMapGPS first."])
		return
	end
	local character = GPSCharacter()
	character.gpsSettingsSyncRequest, character.gpsSettingsSyncResult = nil, nil
	if ns.variantDormant then CompleteImport()
	else
		character.gpsSettingsSyncRequest = true
		if not Switch("original") then character.gpsSettingsSyncRequest = nil end
	end
end

local function Command(text)
	local command = (text or ""):match("^%s*(.-)%s*$"):lower()
	if command == "sync settings" then SyncSettings()
	elseif ns.variantDormant then
		Print(L["Original OpenMap is active. Disable it in the AddOns list and enable OpenMap - GPS, then reload."])
	elseif dispatch then dispatch(text)
	else Print(L["OpenMap GPS is still loading."]) end
end

SLASH_OPENMAPGPS1, SLASH_OPENMAPGPS2 = "/openmapgps", "/omgps"
SlashCmdList.OPENMAPGPS = Command
function ns.ConfigureSlash(handler) dispatch = handler end

-- The compartment can still call the variant's entry while its map is dormant.
OpenMapGPS_OnAddonCompartmentClick = function() Command("") end
OpenMapGPS_OnAddonCompartmentEnter = function() end
OpenMapGPS_OnAddonCompartmentLeave = function() end

local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
	self:UnregisterEvent("PLAYER_LOGIN")
	local character = rawget(_G, "OpenMapGPSCharDB")
	if type(character) == "table" and character.gpsSettingsSyncRequest then
		-- Clear before either handoff: a failed import/switch must not loop at login.
		character.gpsSettingsSyncRequest = nil
		if ns.variantDormant then CompleteImport()
		else Print(L["Map settings could not be copied."]) end
	elseif type(character) == "table" and character.gpsSettingsSyncResult then
		character.gpsSettingsSyncResult = nil
		Print(L["Map settings copied to GPS."])
	elseif ns.variantDormant then Command("") end
end)
