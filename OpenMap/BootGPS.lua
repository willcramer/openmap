-- Loaded first only by the separately packaged OpenMapGPS addon. The packager
-- leaves this file's identifiers intact: "OpenMap" here means the original.
local _, ns = ...
local L = setmetatable({}, { __index = function(_, key) return ns.L and ns.L[key] or key end })
local function Print(text) DEFAULT_CHAT_FRAME:AddMessage("|cffe6b85cOpenMap GPS|r: " .. text) end
local addons = C_AddOns
local originalLoaded = addons and addons.IsAddOnLoaded and addons.IsAddOnLoaded("OpenMap")
ns.variantDormant = originalLoaded and true or false
local dispatch

local function Switch(target)
	if InCombatLockdown and InCombatLockdown() then
		Print(L["Leave combat before switching map addons."])
		return
	end
	if not addons or not addons.EnableAddOn or not addons.DisableAddOn or not ReloadUI then
		Print(L["Use the AddOns list to enable one map addon, then reload."])
		return
	end
	if target == "original" and addons.DoesAddOnExist and not addons.DoesAddOnExist("OpenMap") then
		Print(L["The original OpenMap is not installed. Install it beside OpenMapGPS first."])
		return
	end
	local character = UnitName("player")
	-- Keep the small GPS switch command loaded in standby when using the original.
	-- OptionalDeps in the variant toc makes the original load first in that case.
	local ok = pcall(function()
		addons.EnableAddOn("OpenMapGPS", character)
		if target == "gps" then addons.DisableAddOn("OpenMap", character)
		else addons.EnableAddOn("OpenMap", character) end
	end)
	if not ok then
		Print(L["Use the AddOns list to enable one map addon, then reload."])
		return
	end
	ReloadUI()
end

local function Command(text)
	local command = (text or ""):match("^%s*(.-)%s*$"):lower()
	if command == "use gps" then Switch("gps")
	elseif command == "use original" then Switch("original")
	elseif ns.variantDormant then
		Print(L["Original OpenMap is active. /omgps use gps switches to the GPS build and reloads; /omgps use original switches back."])
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

if ns.variantDormant then
	local boot = CreateFrame("Frame")
	boot:RegisterEvent("PLAYER_LOGIN")
	boot:SetScript("OnEvent", function(self)
		self:UnregisterEvent("PLAYER_LOGIN")
		Command("")
	end)
end
