"""Flight masters' learned state (Map/Flights.lua), against a stubbed client; run with
python -P tools/offline-test/flights.py. Needs lupa.

Whose flight paths count as learned: the game's own "found" list until the character has opened a
flight master's map, then the paths that map listed as learned (#274: a new character was shown another
character's; #301: a learned one read as not found)."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2] / "OpenMap"

STUB = r"""
local function Frame()
	local f = { shown = true }
	function f:SetShown(on) self.shown = on and true or false end
	function f:IsShown() return self.shown end
	function f:Show() self.shown = true end
	function f:Hide() self.shown = false end
	function f:CreateTexture()
		local t = Frame()
		for _, k in ipairs({ "SetPoint", "ClearAllPoints", "SetSize", "SetVertexColor", "SetDesaturated", "SetAlpha" }) do t[k] = function() end end
		return t
	end
	for _, k in ipairs({ "SetSize", "SetScript", "SetPoint", "ClearAllPoints" }) do f[k] = function() end end
	return f
end
S = {}
function S.IsBuilt() return true end
function S.PinSet(key) return { key = key, pins = {} } end
function S.AddPin(set, u, v, look) local p = Frame() p.Icon = p:CreateTexture() set.pins[#set.pins + 1] = p return p end
function S.FromYards(c, x, y) return 0.5, 0.5 end
function S.Look() end
setmetatable(S, { __index = function() return function() end end })
mod = { defaults = {}, db = { flight = true, foundOnly = false }, char = { flightsKnownV = 2 } }
ns = { MapStitch = S, MapFlights = {
	nodes = { [1] = { "Crossroads, The Barrens", 1, 0, 0, 3 }, [2] = { "Orgrimmar, Durotar", 1, 0, 0, 3 } },
	paths = {} },
	L = setmetatable({}, { __index = function(_, k) return k end }), Safe = { Call = function(f, ...) return f(...) end } }
function ns:GetModule() return mod end
function ns.RegisterEvent(_, e, fn) events[e] = fn end
function ns:Print() end
events = {}
-- the game's list: node 1 undiscovered, node 2 found (another character's, #274's case)
taxi = { { nodeID = 1, isUndiscovered = true, name = "Crossroads, The Barrens" }, { nodeID = 2, isUndiscovered = false, name = "Orgrimmar, Durotar" } }
C_TaxiMap = { GetTaxiNodesForMap = function() return taxi end }
C_Timer = { After = function() end }
function UnitFactionGroup() return "Horde" end
function UnitClass() return "Warrior", "WARRIOR" end
function hooksecurefunc() end
GameTooltip_Hide = function() end
bit = { band = function(a, b) local r, p = 0, 1 while a > 0 and b > 0 do if a % 2 == 1 and b % 2 == 1 then r = r + p end a, b, p = math.floor(a / 2), math.floor(b / 2), p * 2 end return r end }
tinsert, wipe = table.insert, function(t) for k in pairs(t) do t[k] = nil end return t end
"""


class FlightTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB)
        self.lua.execute("local f = assert(loadstring(...)) f('OpenMap', ns)", (ROOT / "Map/Flights.lua").read_text(encoding="utf-8"))
        self.lua.execute("mod:BuildFlights()")

    def learned(self):
        return self.lua.eval("mod.FlightStatus()")

    def test_the_game_s_list_until_a_flight_master_s_map_is_opened(self):
        self.assertIn("1 learned", self.learned())

    def test_then_what_that_map_listed_for_this_character(self):
        # (a flight master's map listed only the Crossroads as learned: Orgrimmar, "found" by the game for
        # another character, no longer counts, and the Crossroads does)
        self.lua.execute("mod.char.flightsKnown = { ['Crossroads, The Barrens'] = true } mod.RefreshFlightsFound()")
        status = self.learned()
        self.assertIn("1 learned", status)
        self.lua.execute("""
            local n = 0
            mod.char.flightsKnown = { ['Crossroads, The Barrens'] = true, ['Orgrimmar, Durotar'] = true }
            mod.RefreshFlightsFound()
        """)
        self.assertIn("2 learned", self.learned())


if __name__ == "__main__":
    unittest.main()
