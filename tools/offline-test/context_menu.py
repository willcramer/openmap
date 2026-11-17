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

    def editor(self):
        self.check('''
            NIL_GLOBALS.selected,NIL_GLOBALS.nearest,NIL_GLOBALS.popup=true,true,true
            editing,selected,nearest=false,nil,'b:0:4'
            edits,links={},{}
            mod.db.gpsManualRoads={nodes={},links={}}
            function mod.GPSRoadEditing()return editing end
            function mod.GPSRoadSelected()return selected end
            function mod.GPSSetRoadEditing(on)
                editing=on
                mod.CloseLocationMenu()
                if not on then selected=nil end
                return true
            end
            function mod.GPSRoadEditNearest(map,x,y)return nearest end
            function mod.GPSRoadEditSelect(ref)selected=ref return true end
            function mod.GPSRoadEditAdd(map,x,y,from)
                assert(not currentMenu)
                edits[#edits+1]={kind='add',map=map,x=x,y=y,from=from}
                selected='m:'..#edits
                return selected
            end
            function mod.GPSRoadEditLinked(a,b)return links[a..'>'..b]or false end
            function mod.GPSRoadEditConnect(a,b)
                assert(not currentMenu)
                edits[#edits+1]={kind='connect',a=a,b=b}
                links[a..'>'..b]=true
                return true
            end
            function mod.GPSRoadEditDisconnect(a,b)
                assert(not currentMenu)
                edits[#edits+1]={kind='disconnect',a=a,b=b}
                links[a..'>'..b]=nil
                return true
            end
            function mod.GPSRoadEditDelete(ref)
                edits[#edits+1]={kind='delete',ref=ref}
                return true
            end
            StaticPopup_Show=function(which,_,__,data)popup={which=which,data=data}end
        ''')

    def test_editor_menu_adds_and_connects_at_captured_locations_without_navigation(self):
        self.editor()
        self.check('''
            assert(Open()and #lastMenu.rows==4)
            assert(lastMenu.rows[4].label=='Edit road network')
            Click(4)assert(editing)
            assert(Open()and #lastMenu.rows==8)
            assert(lastMenu.rows[1].label=='Add road node'and lastMenu.rows[2].label=='Add connected node')
            assert(not lastMenu.rows[2].enabled and not lastMenu.rows[4].enabled)
            Click(3)assert(selected=='b:0:4')
            Open()
            chosenMap,mx,my=1430,.9,.9
            mod.FromWorld=function()return .99,.99 end
            selected='m:999'
            Click(2)
            assert(#edits==1 and edits[1].kind=='add'and edits[1].map==1429)
            assert(math.abs(edits[1].x-.3)<1e-8 and edits[1].y==.5 and edits[1].from=='b:0:4')
            assert(selected=='m:1'and #calls==0,'editing changed GPS or a waypoint')
        ''')

    def test_editor_connect_disconnect_and_clear_use_captured_node_references(self):
        self.editor()
        self.check('''
            editing,selected,nearest=true,'m:1','b:0:5'
            Open()selected,nearest='m:999','b:0:999'
            Click(4)
            assert(edits[1].kind=='connect'and edits[1].a=='m:1'and edits[1].b=='b:0:5')
            selected,nearest='m:1','b:0:5'
            Open()assert(not lastMenu.rows[4].enabled and lastMenu.rows[5].enabled)
            Click(5)assert(edits[2].kind=='disconnect'and not links['m:1>b:0:5'])
            Open()Click(7)assert(selected==nil)
            nearest=nil
            Open()
            assert(not lastMenu.rows[3].enabled and not lastMenu.rows[4].enabled and not lastMenu.rows[6].enabled)
            Click(1)assert(edits[3].kind=='add'and edits[3].from==nil)
        ''')

    def test_editor_deletion_is_confirmed_and_cannot_delete_bundled_or_replaced_profile_nodes(self):
        self.editor()
        self.check('''
            editing,selected,nearest=true,'m:1','b:0:5'
            Open()assert(not lastMenu.rows[6].enabled)Click(6)assert(not popup)
            nearest='m:1'
            Open()Click(6)
            assert(popup.which=='OPENMAP_GPS_DELETE_NODE'and popup.data.ref=='m:1'and #edits==0)
            local captured=popup.data
            nearest,selected='m:2','m:2'
            StaticPopupDialogs[popup.which].OnAccept({},captured)
            assert(#edits==1 and edits[1].kind=='delete'and edits[1].ref=='m:1')
            Open()Click(6)
            mod.db.gpsManualRoads={nodes={},links={}}
            StaticPopupDialogs[popup.which].OnAccept({},popup.data)
            assert(#edits==1,'confirmation from an old profile deleted a different node')
        ''')

    def test_editor_callbacks_are_revoked_and_finishing_restores_regular_menu(self):
        self.editor()
        self.check('''
            editing=true
            Open()local escaped=lastMenu.rows[1].callback
            Menu.GetManager():HandleESC()escaped()assert(#edits==0)
            Open()local stale=lastMenu.rows[1].callback
            editing=false stale()assert(#edits==0)
            editing=true mod.db.mapRightClick='zoom'
            Open()Click(8)
            assert(not editing and mod.db.mapRightClick=='zoom')
            Open()assert(lastMenu.rows[1].label=='Place waypoint')
        ''')

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
            assert(mod.defaults.mapRightClick=='menu'and options.mapRightClick.values.menu=='Open location menu')
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

    def test_native_editor_temporarily_overrides_zoom_and_retains_drag_protection(self):
        self.editor()
        self.check('''
            mod.SetupLocationMenu()chosenMap=2521
            mod.db.mapRightClick='zoom'editing=true
            assert(nativeClick(world,'RightButton'))
            assert(lastMenu.rows[1].label=='Add road node'and mod.db.mapRightClick=='zoom')
            Click(1)assert(edits[1].map==2521 and edits[1].x==.2 and edits[1].y==.3)
            cx,cy,held=100,100,true
            GetCursorPosition=function()return cx,cy end
            IsMouseButtonDown=function()return held end
            world.ScrollContainer:GetScript('OnMouseDown')(world.ScrollContainer,'RightButton')
            cx=150 RunOnUpdate(.1)cx=100 RunOnUpdate(.1)held=false
            assert(nativeClick(world,'RightButton')and not currentMenu)
            assert(#edits==1)
            mod.GPSSetRoadEditing(false)
            assert(not nativeClick(world,'RightButton')and mod.db.mapRightClick=='zoom')
        ''')


class RoadEditorMenuIntegrationTests(unittest.TestCase):
    """Place and connect a road using real menu/model/router code without moving."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location('road_editor_menu_boot', HERE / 'gps_bundled_integration.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.BundledGPSIntegrationTests.setUp(self)
        self.lua.execute('''
            -- The loader has no actual stitched canvas. Only drawing regions
            -- are simulated; menu actions, stored edits and planning are real.
            ns.MapStitch.PinSet=function()return {frame=CreateFrame('Frame')}end
            ns.MapStitch.ClearPinSet=function()end
            ns.MapStitch.SetPinSetOn=function()end
            ns.MapStitch.AddPin=function()return CreateFrame('Button')end
            ns.MapStitch.MovePin=function()end
            ns.MapStitch.AddLine=function()return CreateFrame('Frame'):CreateLine()end
            ns.MapStitch.IsBuilt=function()return true end
            ns.MapStitch.ChainAt=function()return {947,900001}end
            mod.ToWorld=function(_,x,y)return x,y end
            mod.FromWorld=function(_,u,v)return u,v end
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,links={[2]=true}},
                [2]={wx=100,wy=200,map=900001,links={[1]=true}},
                [3]={wx=900,wy=800,map=900001,links={[4]=true}},
                [4]={wx=900,wy=900,map=900001,links={[3]=true}}
            })
            local manager={}
            function manager:CloseMenu(menu)
                if menu.onClose then menu.onClose(menu)end
            end
            Menu={GetManager=function()return manager end}
            MenuUtil={CreateContextMenu=function(owner,generate)
                local menu={rows={}}
                function menu:SetClosedCallback(fn)self.onClose=fn end
                generate(owner,{CreateButton=function(_,label,callback)
                    local row={label=label,callback=callback,enabled=true}
                    function row:SetEnabled(value)self.enabled=value end
                    menu.rows[#menu.rows+1]=row
                    return row
                end})
                editorMenu=menu
                return menu
            end}
            function OpenAt(x,y)
                assert(mod.OpenLocationMenu(x,y,WorldMapFrame))
            end
            function Choose(label)
                for _,row in ipairs(editorMenu.rows)do
                    if row.label==label then
                        assert(row.enabled,'disabled editor action: '..label)
                        row.callback()return
                    end
                end
                error('missing editor action: '..label)
            end
            WorldMapFrame:Show()
        ''')

    def test_context_menu_places_and_connects_a_new_route_without_walking(self):
        self.lua.execute('''
            OpenAt(.1,.2)Choose('Edit road network')
            assert(mod.GPSRoadEditing())
            OpenAt(.1,.2)Choose('Select road node')
            assert(mod.GPSRoadSelected()=='b:0:2')
            OpenAt(.5,.2)Choose('Add connected node')
            local first=mod.GPSRoadSelected()
            OpenAt(.5,.8)Choose('Add connected node')
            local second=mod.GPSRoadSelected()
            assert(first~=second and mod.GPSRoadEditLinked(first,second))
            OpenAt(.9,.8)Choose('Connect selected node')
            assert(mod.GPSRoadEditLinked(second,'b:0:3'))
            assert(player.x==.1 and player.y==.1,'placing a road needed player movement')
            assert(PlanGPS(900001,.9,.9))
            local a,b=false,false
            for _,point in ipairs(mod.GPSStatus().route)do
                a=a or point.source=='manual'and point.wx==500 and point.wy==200
                b=b or point.source=='manual'and point.wx==500 and point.wy==800
            end
            assert(a and b,'navigation ignored the manually connected road bend')
            assert(not ns.GPSRoadData.networks[0].nodes[2].links[3],'editing mutated bundled road data')
            local saved=mod.db.gpsManualRoads
            ns:InitDB()
            assert(mod.db.gpsManualRoads==saved and mod.GPSRoadEditLinked(first,second))
            OpenAt(.9,.8)Choose('Finish editing')
            assert(not mod.GPSRoadEditing()and mod.GPSStatus().active)
            assert(#ERRORS==0,ERRORS[1])
        ''')


class LocationMenuDefaultsTests(unittest.TestCase):
    """Use the complete addon and real Core.InitDB migration/default filling."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location('menu_defaults_boot', HERE / 'gps_integration.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.GPSIntegrationTests.setUp(self)

    def test_fresh_profile_defaults_to_location_menu_and_records_adoption(self):
        self.lua.execute('''
            assert(gpsmod.defaults.mapRightClick=='menu')
            assert(gpsmod.db.mapRightClick=='menu'and gpsmod.db.gpsRightClickMenuDefault==true)
            gpsmod.db.mapRightClick='zoom'
            testns:InitDB()
            assert(gpsmod.db.mapRightClick=='zoom','fresh profile lost its later explicit choice')
        ''')

    def test_existing_zoom_default_migrates_once_without_losing_other_settings(self):
        self.lua.execute('''
            OpenMapDB={worldmap={mapRightClick='zoom',icons=false,brightness=.7,
                gpsUseRoads=false,gpsRoutes={Walk={points={{1429,.2,.3},{1429,.3,.4}}}}}}
            local saved=OpenMapDB.worldmap
            local routes=saved.gpsRoutes
            OpenMapCharDB={worldmap={pin={1429,.4,.5}}}
            local char=OpenMapCharDB.worldmap
            testns:InitDB()
            assert(gpsmod.db==saved and gpsmod.char==char)
            assert(saved.mapRightClick=='menu'and saved.gpsRightClickMenuDefault==true)
            assert(saved.brightness==.7 and saved.gpsUseRoads==false and saved.gpsRoutes==routes)
            assert(char.pin[2]==.4 and char.pin[3]==.5)
            assert(saved.boats==false and saved.zeppelins==false and saved.zoomHidePinsOff==true,
                'the existing world-map migration was not chained')
            local options=gpsmod:Options()
            options.mapRightClick.set({'mapRightClick'},'zoom')
            assert(saved.mapRightClick=='zoom')
            testns:InitDB()
            assert(saved.mapRightClick=='zoom','migration repeated after an explicit zoom choice')
        ''')

    def test_existing_menu_and_adopted_zoom_profiles_keep_their_choices(self):
        self.lua.execute('''
            OpenMapDB={worldmap={mapRightClick='menu'}}
            testns:InitDB()
            assert(gpsmod.db.mapRightClick=='menu'and gpsmod.db.gpsRightClickMenuDefault==true)
            OpenMapDB={worldmap={mapRightClick='zoom',gpsRightClickMenuDefault=true}}
            testns:InitDB()
            assert(gpsmod.db.mapRightClick=='zoom')
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
