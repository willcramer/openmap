"""Location-menu actions capture their target and use the native menu lifecycle.

Run: python -P tools/offline-test/context_menu.py
The complete addon module is loaded; only Blizzard's Menu framework is modeled.
"""
import importlib.util
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


class LocationMenuTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute((HERE / 'stub.lua').read_text())
        lua.execute('''
            for _,key in ipairs({'currentMenu','lastMenu','chosenMap','MenuUtil'})do NIL_GLOBALS[key]=true end
            registrations,mapChanged=0,0
            mod={defaults={},db={enabled=true,mapRightClick='menu'}}
            ns={L=setmetatable({},{__index=function(_,key)return key end}),Safe={}}
            function ns:GetModule()return mod end
            function ns.Safe.Value(v)if type(v)=='table'and v.secret then return nil end return v end
            function ns.Safe.Call(fn,...)if type(fn)~='function'then return end local ok,v=pcall(fn,...)if ok then return ns.Safe.Value(v)end end
            function ns:Print(text)message=text end
            events={}
            function ns.RegisterEvent(owner,event,fn)events[event]=fn end
            S={WORLD=947}
            ns.MapStitch=S
            built,chosenMap,mx,my=true,1429,.2,.3
            function S.IsBuilt()return built end
            function S.ChainAt()return chosenMap and {947,chosenMap}or{}end
            function S.Rect(id)return id==1429 and 0 end
            function mod.FromWorld(_,u,v)return u+.1,v+.2 end
            calls={}
            local function Capture(kind,map,x,y,extra)
                assert(not currentMenu or not currentMenu.shown,'menu stayed open during the action')
                calls[#calls+1]={kind=kind,map=map,x=x,y=y,extra=extra}
            end
            function mod.TrackPoint(...)Capture('waypoint',...)end
            function mod.AddPin(...)Capture('note',...)end
            function mod.GPSStart(...)Capture('gps',...)return true end
            world=CreateFrame('Frame')world:Show()
            world.ScrollContainer=CreateFrame('Frame',nil,world)
            world.GetMapID=function()return chosenMap end
            world.GetNormalizedCursorPosition=function()return mx,my end
            world.AddCanvasClickHandler=function(_,fn,priority)nativeClick=fn registrations=(registrations or 0)+1 assert(priority==1001)end
            world.OnMapChanged=function()mapChanged=(mapChanged or 0)+1 end
            WorldMapFrame=world
            local manager={}
            function manager:CloseMenu(menu)
                menu.shown=false
                if currentMenu==menu then currentMenu=nil end
                if menu.onClose then menu.onClose(menu)end
            end
            function manager:HandleESC()if currentMenu then self:CloseMenu(currentMenu)end end
            function manager:OutsideClick()if currentMenu then self:CloseMenu(currentMenu)end end
            Menu={GetManager=function()return manager end}
            MenuUtil={}
            function MenuUtil.CreateContextMenu(owner,generator)
                if currentMenu then manager:CloseMenu(currentMenu)end
                local menu={rows={},shown=true,owner=owner}
                function menu:SetClosedCallback(fn)self.onClose=fn end
                local root={}
                function root:CreateButton(label,callback)
                    local row={label=label,callback=callback,enabled=true}
                    function row:SetEnabled(value)self.enabled=value end
                    menu.rows[#menu.rows+1]=row
                    return row
                end
                generator(owner,root)
                owner:HookScript('OnHide',function()manager:CloseMenu(menu)end)
                currentMenu,lastMenu=menu,menu
                return menu
            end
            function Open()return mod.OpenLocationMenu(.2,.3,world)end
            function Click(i)
                local row=lastMenu.rows[i]
                if row.enabled then row.callback()end
            end
        ''')
        lua.execute((ROOT / 'OpenMap/Map/ContextMenu.lua').read_text(), 'OpenMap', lua.globals().ns)

    def check(self, code):
        self.lua.execute(code)

    def test_three_actions_use_the_location_captured_when_menu_opened(self):
        self.check('''
            assert(Open())
            assert(#lastMenu.rows==3)
            assert(lastMenu.rows[1].label=='Place waypoint'and lastMenu.rows[2].label=='Add note'and lastMenu.rows[3].label=='Go Here')
            chosenMap,mx,my=1430,.8,.9
            mod.FromWorld=function()return .99,.99 end
            Click(1)
            assert(#calls==1 and calls[1].kind=='waypoint'and calls[1].map==1429)
            assert(math.abs(calls[1].x-.3)<1e-8 and calls[1].y==.5)
            Click(1)assert(#calls==1,'closed menu callback ran twice')
        ''')

    def test_note_is_a_persistent_pin_without_changing_navigation(self):
        self.check('''
            assert(Open())Click(2)
            assert(#calls==1 and calls[1].kind=='note'and calls[1].extra==false)
        ''')

    def test_gps_reports_planner_failure_after_dismissing_menu(self):
        self.check('''
            mod.GPSStart=function(map,x,y)
                assert(not currentMenu)
                assert(map==1429 and y==.5)
                return nil,'No connected road'
            end
            assert(Open())Click(3)
            assert(message=='No connected road'and not currentMenu)
        ''')

    def test_invalid_unprojectable_secret_or_out_of_bounds_positions_do_not_open(self):
        self.check('''
            built=false assert(not Open())built=true
            chosenMap=nil assert(not Open())
            chosenMap=947 assert(not Open())
            chosenMap=1429
            assert(not mod.OpenLocationMenu(-.1,.5))
            assert(not mod.OpenLocationMenu(.2,math.huge))
            assert(not mod.OpenLocationMenu({secret=true},.5))
            mod.FromWorld=function()return {secret=true},.5 end assert(not Open())
            mod.FromWorld=function()return 1.01,.5 end assert(not Open())
            assert(not lastMenu)
        ''')

    def test_escape_outside_click_and_owner_hide_revoke_old_actions(self):
        self.check('''
            Open()local escaped=lastMenu.rows[1].callback
            Menu.GetManager():HandleESC()escaped()assert(#calls==0)
            Open()local outside=lastMenu.rows[2].callback
            Menu.GetManager():OutsideClick()outside()assert(#calls==0)
            Open()local hidden=lastMenu.rows[3].callback
            world:Hide()hidden()assert(#calls==0 and not currentMenu)
            assert(not Open(),'closed map still offered a location')
        ''')

    def test_new_menu_and_option_change_revoke_previous_actions(self):
        self.check('''
            Open()local old=lastMenu.rows[3].callback
            Open()old()assert(#calls==0)
            local options={}
            mod:ContextMenuOptions(options,function()end,function(info,v)mod.db[info[#info]]=v end,function()end)
            assert(mod.defaults.mapRightClick=='zoom'and options.mapRightClick.values.menu=='Open location menu')
            options.mapRightClick.set({'mapRightClick'},'zoom')
            assert(not currentMenu and mod.db.mapRightClick=='zoom')
            options.mapRightClick.set({'mapRightClick'},'invalid')assert(mod.db.mapRightClick=='zoom')
        ''')

    def test_missing_feature_functions_are_disabled_and_missing_framework_falls_back(self):
        self.check('''
            mod.TrackPoint,mod.AddPin,mod.GPSStart=nil,nil,nil
            assert(Open())
            for i,row in ipairs(lastMenu.rows)do assert(not row.enabled)Click(i)end
            assert(#calls==0)
            mod.CloseLocationMenu()
            MenuUtil=nil assert(not Open())
        ''')

    def test_native_zephras_handler_captures_normalized_coordinates_and_map_change_closes(self):
        self.check('''
            mod.SetupLocationMenu()mod.SetupLocationMenu()assert(registrations==1)
            chosenMap=2521
            assert(nativeClick(world,'RightButton'))
            chosenMap=2665 mx,my=.9,.9
            Click(3)
            assert(calls[1].map==2521 and calls[1].x==.2 and calls[1].y==.3)
            assert(nativeClick(world,'RightButton'))
            local stale=lastMenu.rows[1].callback
            world:OnMapChanged()stale()
            assert(mapChanged==1 and #calls==1 and not currentMenu)
        ''')

    def test_native_mode_and_active_map_tools_do_not_intercept_other_clicks(self):
        self.check('''
            mod.SetupLocationMenu()chosenMap=2521
            assert(not nativeClick(world,'LeftButton'))
            mod.db.mapRightClick='zoom'assert(not nativeClick(world,'RightButton'))mod.db.mapRightClick='menu'
            mod.IsStitched=function()return true end assert(not nativeClick(world,'RightButton'))mod.IsStitched=nil
            mod.PadViewOn=function()return true end assert(not nativeClick(world,'RightButton'))mod.PadViewOn=nil
            mod.IsSketching=function()return true end assert(not nativeClick(world,'RightButton'))mod.IsSketching=nil
            mod.PinMode=function()return true end assert(not nativeClick(world,'RightButton'))mod.PinMode=nil
            mod.db.enabled=false assert(not nativeClick(world,'RightButton'))mod.db.enabled=true
            chosenMap=999 assert(not nativeClick(world,'RightButton'))
            chosenMap=2521 mx=-.1 assert(not nativeClick(world,'RightButton'))
            assert(not lastMenu)
        ''')

    def test_native_right_drag_out_and_back_does_not_open_or_zoom(self):
        self.check('''
            mod.SetupLocationMenu()chosenMap=2521
            cx,cy,held=100,100,true
            GetCursorPosition=function()return cx,cy end
            IsMouseButtonDown=function(button)return button=='RightButton'and held end
            world.ScrollContainer:GetScript('OnMouseDown')(world.ScrollContainer,'RightButton')
            cx=150 RunOnUpdate(.1)
            cx=100 RunOnUpdate(.1)
            held=false
            assert(nativeClick(world,'RightButton')and not lastMenu)
            held=true
            world.ScrollContainer:GetScript('OnMouseDown')(world.ScrollContainer,'RightButton')
            held=false
            assert(nativeClick(world,'RightButton')and lastMenu)
        ''')


class NotePinTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('menu_pin_boot', HERE / 'gps_integration.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.GPSIntegrationTests.setUp(self)
        self.lua.execute('''
            local create=CreateFrame
            CreateFrame=function(...)
                local frame=create(...)
                if frame:GetObjectType()=='EditBox'then frame.HighlightText=function()end end
                return frame
            end
            gpsmod:SetupPins(WorldMapFrame)
            gpsmod.db.pins={list={},nextId=1,migrated=true}
            gpsmod.db.pinsFollowNew=true
            gpsmod.TrackPoint(900001,.8,.8,'Existing target')
            oldWaypoint=WAYPOINT
        ''')

    def test_note_only_pin_keeps_existing_waypoint_and_opens_editor(self):
        self.lua.execute('''
            gpsmod.AddPin(900001,.3,.4,false)
            assert(WAYPOINT==oldWaypoint,'adding a note replaced the GPS destination')
            assert(#gpsmod.db.pins.list==1 and gpsmod.db.pins.list[1].x==.3)
            assert(OpenMapPinEditor:IsShown()and OpenMapPinEditor.box:GetText()=='')
        ''')

    def test_ordinary_pin_still_follows_new_pin_preference(self):
        self.lua.execute('''
            gpsmod.AddPin(900001,.3,.4)
            assert(WAYPOINT~=oldWaypoint and WAYPOINT.position.x==.3)
            gpsmod.db.pinsFollowNew=false
            local followed=WAYPOINT
            gpsmod.AddPin(900001,.5,.6,true)
            assert(WAYPOINT.uiMapID==followed.uiMapID and WAYPOINT.position.x==followed.position.x
                and WAYPOINT.position.y==followed.position.y,'explicit follow bypassed the saved follow-new-pins preference')
        ''')


if __name__ == '__main__':
    unittest.main()
