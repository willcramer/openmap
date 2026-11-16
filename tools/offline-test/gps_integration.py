"""GPS commands, HUD and waypoint ownership against the complete addon in Lua 5.1.

Run: python -P tools/offline-test/gps_integration.py
The existing loader supplies real Core/Nav/Init code; only the game's position APIs
are simulated. No world-map window needs to be open for guidance or recording.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
import warnings


HERE = Path(__file__).resolve().parent


class GPSIntegrationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("openmap_gps_load", HERE / "run.py")
        module = importlib.util.module_from_spec(spec)
        argv = sys.argv
        try:
            sys.argv = [str(HERE / "run.py"), "plain"]
            with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                try:
                    spec.loader.exec_module(module)
                except SystemExit as result:
                    self.assertEqual(result.code, 0, "the complete addon failed to load")
        finally:
            sys.argv = argv
        self.lua = module.L
        self.lua.globals().testns = module.ns
        self.lua.execute(r'''
            gpsmod = testns.modules.worldmap
            testns.MapStitch.Rect = function(id)
                if id == 900001 then return 0, 1, 0, 1 end
            end
            gpsmod.ToWorld = function(_, x, y) return x, y end
            gpsmod.FromWorld = function(_, u, v) return u, v end
            PX, PY = .2, .2
            MISSING = false
            CreateVector2D = function(x, y) return { x = x, y = y } end
            C_Map.GetBestMapForUnit = function() return 900001 end
            C_Map.GetPlayerMapPosition = function()
                if not MISSING then return { x = PX, y = PY } end
            end
            C_Map.GetWorldPosFromMapPos = function(_, p)
                -- Keep this synthetic map outside any real imported continent.
                return 900001, { x = 1000 - p.y * 1000, y = 1000 - p.x * 1000 }
            end
            C_Map.GetMapInfo = function(id) return { mapID = id, name = "Test road" } end
            WAYPOINT = nil
            C_Map.HasUserWaypoint = function() return WAYPOINT ~= nil end
            C_Map.GetUserWaypoint = function() return WAYPOINT end
            C_Map.CanSetUserWaypointOnMap = function() return true end
            C_Map.SetUserWaypoint = function(p) WAYPOINT = p end
            C_Map.ClearUserWaypoint = function() WAYPOINT = nil end
            UiMapPoint = { CreateFromCoordinates = function(id, x, y)
                return { uiMapID = id, position = { x = x, y = y } }
            end }
            GetPlayerFacing = function() return 0 end
            WorldMapFrame:Hide()
            function TickGPS()
                NOW = NOW + .21
                RunOnUpdate(.21)
                assert(#ERRORS == 0, ERRORS[1])
            end
        ''')

    def test_commands_and_live_arrival_with_map_closed(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP("gps go 900001 30 20")
            assert(gpsmod.GPSStatus().active and not WorldMapFrame:IsShown())
            assert(WAYPOINT.uiMapID == 900001 and WAYPOINT.position.x == .3)
            TickGPS()
            assert(OpenMapGPSGuide:IsShown())
            PX = .3
            TickGPS()
            assert(not gpsmod.GPSStatus().active and not OpenMapGPSGuide:IsShown())
            assert(WAYPOINT == nil)
        ''')

    def test_recording_saved_by_command_preserves_name_and_plays(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP("gps record Evening Walk")
            assert(gpsmod.GPSStatus().recording == "Evening Walk")
            PX = .22
            TickGPS()
            PX = .24
            TickGPS()
            SlashCmdList.OPENMAP("gps save")
            assert(not gpsmod.GPSStatus().recording)
            assert(gpsmod.db.gpsRoutes["Evening Walk"])
            assert(#gpsmod.GPSList() == 1)
            PX = .2
            SlashCmdList.OPENMAP("gps follow Evening Walk")
            assert(gpsmod.GPSStatus().active)
            SlashCmdList.OPENMAP("gps stop")
            assert(not gpsmod.GPSStatus().active)
            assert(gpsmod.GPSStatus().state == "stopped")
            assert(gpsmod.GPSStatus().instruction == testns.L["GPS stopped."])
            SlashCmdList.OPENMAP("gps delete Evening Walk")
            assert(#gpsmod.GPSList() == 0)
        ''')

    def test_external_waypoint_takes_over_and_survives_stop(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP("gps go 900001 40 20")
            local other = UiMapPoint.CreateFromCoordinates(900001, .8, .6)
            C_Map.SetUserWaypoint(other)
            TickGPS()
            assert(not gpsmod.GPSStatus().active)
            assert(WAYPOINT == other)
            SlashCmdList.OPENMAP("gps stop")
            assert(WAYPOINT == other)
        ''')

    def test_position_gaps_suspend_guidance_without_arrival(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP("gps go 900001 40 20")
            MISSING = true
            TickGPS()
            assert(gpsmod.GPSStatus().active)
            assert(gpsmod.GPSStatus().bearing == nil,
                "a stale arrow remained while the player position was unavailable")
            MISSING = false
            TickGPS()
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().bearing ~= nil)
        ''')

    def test_secret_positions_do_not_reach_guidance_arithmetic(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP("gps go 900001 40 20")
            ENABLE_SECRETS()
            C_Map.GetPlayerMapPosition = function()
                return { x = Secret(.2), y = Secret(.2) }
            end
            TickGPS()
            assert(gpsmod.GPSStatus().active)
        ''')

    def test_panel_builds_and_setup_is_idempotent(self):
        self.lua.execute(r'''
            local frames = #FRAMES
            gpsmod:SetupGPSPanel()
            gpsmod:SetupGPSPanel()
            assert(#FRAMES == frames, "setup allocated duplicate tickers or HUDs")
            SlashCmdList.OPENMAP("gps")
            assert(OpenMapGPSPanel:IsShown())
            SlashCmdList.OPENMAP("gps")
            assert(not OpenMapGPSPanel:IsShown())
            assert(#ERRORS == 0, ERRORS[1])
        ''')

    def test_single_point_recording_can_be_discarded_from_hud(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP("gps record False Start")
            TickGPS()
            assert(OpenMapGPSGuide:IsShown())
            local stop
            for _, child in ipairs(FRAMES) do
                if child:GetParent() == OpenMapGPSGuide and child:GetScript("OnClick") then stop = child end
            end
            assert(stop, "guidance has no stop/discard button")
            stop:GetScript("OnClick")(stop)
            assert(not gpsmod.GPSStatus().recording and not OpenMapGPSGuide:IsShown())
            assert(#gpsmod.GPSList() == 0)
            SlashCmdList.OPENMAP("gps record Real Start")
            assert(gpsmod.GPSStatus().recording == "Real Start")
            SlashCmdList.OPENMAP("gps cancelrecord")
            assert(not gpsmod.GPSStatus().recording)
        ''')


if __name__ == "__main__":
    unittest.main()
