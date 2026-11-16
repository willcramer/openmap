"""A left press that wandered isn't a click (#37, #64), and a Ctrl-click with OpenMap's pins off is
another addon's (#19): python -P tools/offline-test/press.py."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


SOURCE = (Path(__file__).resolve().parents[2] / 'OpenMap/Map/WorldMap.lua').read_text(encoding='utf-8')


class PressTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            cx, cy = 100, 100
            sc = { mouseButtonInfo = { LeftButton = { down = false }, RightButton = { down = false } } }
            function sc:GetCursorPosition() return cx, cy end
            function Down() sc.mouseButtonInfo.LeftButton.down = true PressDown(nil, 'LeftButton') end
            function RightDown() sc.mouseButtonInfo.RightButton.down = true PressDown(nil, 'RightButton') end
            function MoveTo(x, y) cx, cy = x, y PressTrack() end
        """)
        helpers = SOURCE[SOURCE.index('local press = {'):SOURCE.index('local function OnCanvasClick(')]
        self.lua.execute(helpers + '\n_G.PressDown, _G.PressTrack, _G.WasDrag = PressDown, PressTrack, WasDrag\n')

    def check(self, code):
        self.lua.execute(code)

    def test_still_press_is_a_click(self):
        self.check("Down() MoveTo(101, 102) assert(not WasDrag())")

    def test_drag_out_and_back_is_not_a_click(self):
        self.check("Down() MoveTo(160, 100) MoveTo(101, 100) assert(WasDrag(), 'a drag back to the start counted as a click')")

    def test_next_press_starts_fresh(self):
        self.check("Down() MoveTo(160, 100) sc.mouseButtonInfo.LeftButton.down = false Down() assert(not WasDrag())")

    def test_right_button_leaves_left_press_alone(self):
        self.check("Down() MoveTo(160, 100) PressDown(nil, 'RightButton') assert(WasDrag())")

    def test_no_tracking_after_release(self):
        self.check("Down() sc.mouseButtonInfo.LeftButton.down = false MoveTo(300, 300) assert(not WasDrag())")

    def test_right_drag_out_and_back_is_not_a_context_click(self):
        self.check("RightDown() MoveTo(160,100) MoveTo(100,100) assert(WasDrag('RightButton')) assert(not WasDrag('LeftButton'))")

    def test_each_button_has_independent_press_tracking(self):
        self.check("Down() MoveTo(160,100) RightDown() MoveTo(161,101) assert(WasDrag()) assert(not WasDrag('RightButton'))")


class CtrlClickTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            ctrl, shift, alt = false, false, false
            function IsControlKeyDown() return ctrl end
            function IsShiftKeyDown() return shift end
            function IsAltKeyDown() return alt end
            active, dropped, glided = true, 0, 0
            mod = { db = {}, DropWaypoint = function() dropped = dropped + 1 end,
                CursorWorld = function() return 0.5, 0.5 end }
            sc = { mouseButtonInfo = { LeftButton = { down = false }, RightButton = { down = false } } }
            function sc:GetCursorPosition() return 0, 0 end
            ns = {}
            WORLD = 947
            S = { ChainAt = function() return { WORLD, 1 } end, Rect = function() return 0, 1, 0, 1 end }
            function View() return 0, 0, 1 end
            function Stitchable() return true end
            function FitZoom() return 2 end
            function GlideTo() glided = glided + 1 end
        """)
        chunk = SOURCE[SOURCE.index('local function Dropping('):SOURCE.index('-- our icons: a press')]
        self.lua.execute(chunk + '\n_G.OnCanvasClick, _G.PressDown, _G.PressTrack = OnCanvasClick, PressDown, PressTrack\n')

    def check(self, code):
        self.lua.execute(code)

    def test_ctrl_click_drops_a_pin_by_default(self):
        self.check("ctrl = true assert(OnCanvasClick(true, 'LeftButton') == true) assert(dropped == 1 and glided == 0)")

    def test_ctrl_click_passes_on_when_turned_off(self):
        self.check("ctrl = true mod.db.ctrlClickPin = false "
                   "assert(OnCanvasClick(true, 'LeftButton') == false, 'the Ctrl-click was kept from other addons') "
                   "assert(dropped == 0 and glided == 0)")

    def test_plain_click_still_zooms_when_turned_off(self):
        self.check("mod.db.ctrlClickPin = false assert(OnCanvasClick(true, 'LeftButton') == true) assert(glided == 1)")

    def test_alt_click_navigates_without_zooming_or_dropping_a_pin(self):
        self.check("""
            local navigated = 0
            mod.GPSGoWorld = function(u, v)
                assert(u == .5 and v == .5)
                navigated = navigated + 1
            end
            alt = true
            assert(OnCanvasClick(true, 'LeftButton') == true)
            assert(navigated == 1 and dropped == 0 and glided == 0)
        """)

    def test_alt_drag_does_not_start_navigation(self):
        self.check("""
            mod.GPSGoWorld = function() error('a drag started GPS') end
            alt = true
            sc.GetCursorPosition = function() return 0, 0 end
            PressDown(nil, 'LeftButton')
            sc.mouseButtonInfo.LeftButton.down = true
            sc.GetCursorPosition = function() return 100, 0 end
            PressTrack()
            assert(OnCanvasClick(true, 'LeftButton') == true)
            assert(dropped == 0 and glided == 0)
        """)

    def test_right_click_defaults_to_zoom_without_opening_a_menu(self):
        self.check("""
            mod.OpenLocationMenu=function()error('default right-click opened a menu')end
            assert(OnCanvasClick(true,'RightButton')==true)
            assert(glided==1 and dropped==0)
        """)

    def test_right_click_menu_captures_both_world_coordinates_and_owner(self):
        self.check("""
            mod.db.mapRightClick='menu'
            local opened=0
            mod.OpenLocationMenu=function(u,v,owner)
                assert(u==.5 and v==.5 and owner==sc)
                opened=opened+1
                return true
            end
            assert(OnCanvasClick(true,'RightButton')==true)
            assert(opened==1 and glided==0 and dropped==0)
        """)

    def test_right_drag_suppresses_the_menu_and_zoom(self):
        self.check("""
            mod.db.mapRightClick='menu'
            mod.OpenLocationMenu=function()error('right drag opened a menu')end
            PressDown(nil,'RightButton')
            sc.mouseButtonInfo.RightButton.down=true
            sc.GetCursorPosition=function()return 100,0 end
            PressTrack()
            sc.GetCursorPosition=function()return 0,0 end
            PressTrack()
            assert(OnCanvasClick(true,'RightButton')==true)
            assert(glided==0 and dropped==0)
        """)

    def test_gamepad_parent_navigation_still_zooms_with_menu_mode(self):
        self.check("""
            mod.db.mapRightClick='menu'
            mod.OpenLocationMenu=function()error('controller X opened a mouse menu')end
            assert(OnCanvasClick(nil,'RightButton')==true)
            assert(glided==1)
        """)

    def test_tools_and_dungeon_overlay_do_not_open_the_menu(self):
        self.check("""
            mod.db.mapRightClick='menu'
            mod.OpenLocationMenu=function()error('a tool or hidden dungeon opened a menu')end
            mod.IsSketching=function()return true end
            OnCanvasClick(true,'RightButton')assert(glided==1)
            mod.IsSketching=nil mod.PinMode=function()return true end
            OnCanvasClick(true,'RightButton')assert(glided==2)
            mod.PinMode=nil mod.DungeonViewShown=function()return true end
            OnCanvasClick(true,'RightButton')assert(glided==3)
            mod.DungeonViewShown=nil mod.instanceWorldHidden=true
            OnCanvasClick(true,'RightButton')assert(glided==3)
        """)

    def test_failed_menu_resolution_is_consumed_without_unexpected_zoom(self):
        self.check("""
            mod.db.mapRightClick='menu'
            mod.OpenLocationMenu=function()return false end
            assert(OnCanvasClick(true,'RightButton')==true)
            assert(glided==0)
        """)


if __name__ == '__main__':
    unittest.main()
