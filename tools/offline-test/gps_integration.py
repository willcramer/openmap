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
            assert(gpsmod.GPSStatus().player and gpsmod.GPSStatus().player.x == PX)
            assert(WAYPOINT.uiMapID == 900001 and WAYPOINT.position.x == .3)
            TickGPS()
            assert(OpenMapGPSGuide:IsShown())
            PX = .3
            TickGPS()
            assert(not gpsmod.GPSStatus().active and not OpenMapGPSGuide:IsShown())
            assert(gpsmod.GPSStatus().player == nil)
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
            assert(gpsmod.GPSStatus().player == nil, 'a stale route-head position survived position loss')
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

    def test_hiding_tracker_keeps_tomtom_waypoints_route_progress_and_arrival(self):
        self.lua.execute(r'''
            -- Only map drawing regions are simulated. Core, GPS, Nav and the
            -- tracker callbacks still run through the complete addon.
            DRAW={}
            local S=testns.MapStitch
            S.IsBuilt=function()return true end
            S.PinSet=function(key)
                if not DRAW[key]then DRAW[key]={frame=CreateFrame('Frame'),pins={},lines={}}end
                return DRAW[key]
            end
            S.ClearPinSet=function(set)
                for _,pin in ipairs(set.pins)do pin:Hide()end
                for _,line in ipairs(set.lines)do line:Hide()end
                set.pins,set.lines={},{}
            end
            S.AddPin=function(set,u,v,look)
                local pin=CreateFrame('Button',nil,set.frame)
                pin.u,pin.v,pin.look=u,v,look
                set.pins[#set.pins+1]=pin
                return pin
            end
            S.MovePin=function(_,pin,u,v)pin.u,pin.v=u,v end
            S.AddLine=function(set)
                local line=set.frame:CreateLine(nil,'ARTWORK')
                set.lines[#set.lines+1]=line
                return line
            end
            local added,removed={},{}
            TomTom={}
            function TomTom:AddWaypoint(map,x,y,options)
                local handle={map=map,x=x,y=y,title=options.title}
                added[#added+1]=handle
                return handle
            end
            function TomTom:RemoveWaypoint(handle)removed[#removed+1]=handle end
            gpsmod.db.gpsRoutes['Tracker road']={points={
                {900001,.2,.2},{900001,.3,.2},{900001,.4,.2}
            }}
            assert(gpsmod.GPSPlay('Tracker road','once'))
            TickGPS()
            assert(OpenMapGPSGuide:IsShown()and WAYPOINT.position.x==.3)
            local route,waypoint,updates,lines=gpsmod.GPSStatus().route,WAYPOINT,#added,DRAW.gps.lines
            assert(#DRAW.gps.lines>0,'active GPS route was not drawn')
            local hide
            for _,frame in ipairs(FRAMES)do
                if frame:GetParent()==OpenMapGPSGuide and frame:GetText()=='Hide'and frame:GetScript('OnClick')then hide=frame end
            end
            assert(hide,'tracker has no Hide control')
            -- The frame stub preserves SetPoint's short-form arguments.
            local _,hx,hy=hide:GetPoint()
            local _,sx,sy=OpenMapGPSGuide.stop:GetPoint()
            assert(hx+hide:GetWidth()<sx and hy==sy,'Hide and Stop overlap')
            hide:GetScript('OnClick')(hide)
            assert(not OpenMapGPSGuide:IsShown()and not gpsmod.GPSTrackerEnabled())
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().route==route)
            assert(WAYPOINT==waypoint and #added==updates and DRAW.gps.lines==lines and #lines>0)
            PX=.3 TickGPS()
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().index==3)
            assert(WAYPOINT.position.x==.4 and added[#added].x==.4 and #added>updates)
            assert(not OpenMapGPSGuide:IsShown()and #DRAW.gps.lines>0)
            PX=.4 TickGPS()
            assert(gpsmod.GPSStatus().state=='arrived'and WAYPOINT==nil)
            assert(#removed==#added and #DRAW.gps.lines==0)
            assert(#gpsmod.db.gpsRoutes['Tracker road'].points==3)
        ''')

    def test_tracker_commands_and_options_restore_without_changing_navigation(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP('gps go 900001 40 20')
            local route,waypoint=gpsmod.GPSStatus().route,WAYPOINT
            local notifications,refreshes=0,0
            local notify,refresh=testns.NotifyOptions,gpsmod.RefreshPanel
            testns.NotifyOptions=function(...)notifications=notifications+1 if notify then notify(...)end end
            gpsmod.RefreshPanel=function(self,...)refreshes=refreshes+1 if refresh then refresh(self,...)end end
            SlashCmdList.OPENMAP('gps tracker OFF')
            assert(not OpenMapGPSGuide:IsShown()and gpsmod.db.gpsShowTracker==false)
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().route==route and WAYPOINT==waypoint)
            TickGPS()assert(not OpenMapGPSGuide:IsShown())
            SlashCmdList.OPENMAP('gps tracker ON')
            assert(OpenMapGPSGuide:IsShown()and gpsmod.GPSStatus().active and WAYPOINT==waypoint)
            SlashCmdList.OPENMAP('gps tracker')
            assert(not OpenMapGPSGuide:IsShown())
            local options=gpsmod:Options()
            assert(options.gpsShowTracker.name=='GPS tracker'and not options.gpsShowTracker.get({'gpsShowTracker'}))
            options.gpsShowTracker.set({'gpsShowTracker'},true)
            assert(OpenMapGPSGuide:IsShown()and gpsmod.GPSStatus().route==route and WAYPOINT==waypoint)
            assert(notifications==4 and refreshes==4,'visibility changes did not refresh settings controls')
            OpenMapGPSGuide.stop:GetScript('OnClick')(OpenMapGPSGuide.stop)
            assert(not gpsmod.GPSStatus().active and gpsmod.GPSStatus().state=='stopped'and WAYPOINT==nil)
        ''')

    def test_hidden_preference_survives_new_journeys_recording_and_profile_initialization(self):
        self.lua.execute(r'''
            SlashCmdList.OPENMAP('gps tracker off')
            gpsmod.db.gpsUseRoads=false
            gpsmod.db.gpsRoutes['Reroute road']={points={
                {900001,.2,.2},{900001,.3,.2},{900001,.4,.2}
            }}
            assert(gpsmod.GPSStart(900001,.4,.2))
            TickGPS()assert(not OpenMapGPSGuide:IsShown()and gpsmod.GPSStatus().active)
            MISSING=true TickGPS()
            assert(gpsmod.GPSStatus().state=='waiting'and not OpenMapGPSGuide:IsShown())
            MISSING=false
            gpsmod.GPSStop()
            assert(gpsmod.GPSStart(900001,.5,.2))
            assert(not OpenMapGPSGuide:IsShown())
            gpsmod.GPSStop()
            assert(gpsmod.GPSStart(900001,.4,.2))
            local road=gpsmod.GPSStatus().route
            assert(gpsmod.GPSStatus().state=='recorded')
            PY=.28 TickGPS()
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().route~=road)
            assert(not OpenMapGPSGuide:IsShown(),'rerouting restored a hidden tracker')
            gpsmod.GPSStop()
            PY=.2
            SlashCmdList.OPENMAP('gps record Hidden walk')
            PX=.22 TickGPS()
            assert(gpsmod.GPSStatus().recording=='Hidden walk'and gpsmod.GPSStatus().recorded==2)
            assert(not OpenMapGPSGuide:IsShown())
            SlashCmdList.OPENMAP('gps tracker on')
            assert(OpenMapGPSGuide:IsShown()and gpsmod.GPSStatus().recording=='Hidden walk')
            OpenMapGPSGuide.hide:GetScript('OnClick')(OpenMapGPSGuide.hide)
            assert(not OpenMapGPSGuide:IsShown()and gpsmod.GPSStatus().recording=='Hidden walk')
            SlashCmdList.OPENMAP('gps save')
            assert(#gpsmod.db.gpsRoutes['Hidden walk'].points==2)
            -- InitDB is the real profile-load/default-fill path used after reload.
            local saved=OpenMapDB.worldmap
            testns:InitDB()
            assert(gpsmod.db==saved and gpsmod.defaults.gpsShowTracker==true and gpsmod.db.gpsShowTracker==false)
            assert(gpsmod.GPSStart(900001,.5,.2))
            assert(not OpenMapGPSGuide:IsShown())
        ''')

    def test_map_menu_and_panel_manage_roads_recording_and_saved_routes_without_commands(self):
        self.lua.execute(r'''
            -- Exercise the real map menu using its classic slider fallback;
            -- the general frame stub does not model Blizzard template mixins.
            NIL_GLOBALS.MinimalSliderWithSteppersMixin=true
            MinimalSliderWithSteppersMixin=nil
            gpsmod:SetupPanel(WorldMapFrame)
            local action
            for _,frame in ipairs(FRAMES)do
                if frame:GetParent()==OpenMapMenu and frame.entry and frame.entry.id=='gps'then action=frame end
            end
            assert(action and action.label:GetText()=='GPS navigation','map menu has no GPS action')
            action:GetScript('OnClick')(action,'LeftButton')
            assert(OpenMapGPSPanel:IsShown())
            local panel=OpenMapGPSPanel
            local function Click(button)
                assert(button.uiEnabled~=false,'clicked a disabled GPS control')
                button:GetScript('OnClick')(button,'LeftButton')
            end
            local function Name(text)
                panel.name:SetText(text)
                panel.name:GetScript('OnTextChanged')(panel.name,true)
            end
            for _,control in ipairs({panel.roads,panel.tracker,panel.record,panel.save,panel.follow,panel.delete,panel.routes,panel.mode,panel.stop,panel.guide})do
                control.SetEnabled=function(self,on)self.uiEnabled=on and true or false end
                if control==panel.roads or control==panel.tracker then
                    control.SetChecked=function(self,on)self.checked=on and true or false end
                    control.GetChecked=function(self)return self.checked end
                end
            end
            gpsmod.GPSRefreshPanel()
            assert(panel.nameLabel:GetText()=='Route name'and panel.playbackLabel:GetText()=='Playback')
            assert(not panel.save.uiEnabled and not panel.record.uiEnabled and not panel.follow.uiEnabled)
            panel.roads:SetChecked(true)Click(panel.roads)
            assert(gpsmod.GPSRoadsShown())
            panel.tracker:SetChecked(false)Click(panel.tracker)
            Name('  UI road  ')Click(panel.record)
            assert(gpsmod.GPSStatus().recording=='UI road'and panel.name:GetText()=='UI road')
            assert(panel.save.uiEnabled and not panel.record.uiEnabled and not panel.routes.uiEnabled)
            PX=.22 TickGPS()PX=.24 TickGPS()
            assert(not OpenMapGPSGuide:IsShown())
            Click(panel.save)
            assert(#gpsmod.db.gpsRoutes['UI road'].points==3 and not gpsmod.GPSStatus().recording)
            assert(panel.follow.uiEnabled and panel.delete.uiEnabled and panel.routes.uiEnabled)
            MenuUtil={CreateContextMenu=function(owner,generate)
                routeChoices={}
                generate(owner,{CreateButton=function(_,label,callback)
                    routeChoices[#routeChoices+1]={label=label,callback=callback}
                end})
            end}
            Name('Another name')Click(panel.routes)
            assert(#routeChoices==1 and routeChoices[1].label=='UI road')
            routeChoices[1].callback()
            assert(panel.name:GetText()=='UI road')
            Name('  UI road  ')
            Click(panel.mode)assert(panel.mode:GetText()=='Reverse')
            Click(panel.follow)
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().route[1].x==.24)
            assert(not OpenMapGPSGuide:IsShown(),'opening or following from the panel reset tracker visibility')
            local route,waypoint=gpsmod.GPSStatus().route,WAYPOINT
            panel.roads:SetChecked(false)Click(panel.roads)
            panel.tracker:SetChecked(true)Click(panel.tracker)
            assert(not gpsmod.GPSRoadsShown()and OpenMapGPSGuide:IsShown())
            assert(gpsmod.GPSStatus().route==route and WAYPOINT==waypoint)
            Click(panel.stop)assert(not gpsmod.GPSStatus().active)
            StaticPopup_Show=function(which,name,_,data)popup={which=which,name=name,data=data}end
            Click(panel.delete)
            assert(popup.which=='OPENMAP_GPS_DELETE'and popup.name=='UI road'and popup.data=='UI road')
            assert(gpsmod.db.gpsRoutes['UI road'],'opening deletion confirmation deleted a route')
            -- The dialog captures its selected route instead of a later edit-box value.
            gpsmod.db.gpsRoutes.Other={points={{900001,.2,.2},{900001,.22,.2}}}
            Name('Other')
            StaticPopupDialogs[popup.which].OnAccept({},popup.data)
            assert(not gpsmod.db.gpsRoutes['UI road']and gpsmod.db.gpsRoutes.Other)
            assert(panel.name:GetText()=='Other')
            assert(#ERRORS==0,ERRORS[1])
        ''')

    def test_panel_editor_toggle_preserves_guidance_tracker_and_right_click_preference(self):
        self.lua.execute(r'''
            gpsmod.db.mapRightClick='zoom'
            gpsmod.GPSSetTrackerShown(false)
            assert(gpsmod.GPSStart(900001,.4,.2))
            local route,waypoint=gpsmod.GPSStatus().route,WAYPOINT
            gpsmod:ToggleGPS(true)
            local panel=OpenMapGPSPanel
            assert(panel.edit:GetText()=='Edit road network')
            panel.edit:GetScript('OnClick')(panel.edit)
            assert(gpsmod.GPSRoadEditing()and gpsmod.GPSRoadsShown())
            assert(panel.edit:GetText()=='Finish editing')
            assert(panel.help:GetText():find('Right%-click'))
            assert(gpsmod.GPSStatus().active and gpsmod.GPSStatus().route==route and WAYPOINT==waypoint)
            assert(not OpenMapGPSGuide:IsShown()and gpsmod.db.mapRightClick=='zoom')
            panel.edit:GetScript('OnClick')(panel.edit)
            assert(not gpsmod.GPSRoadEditing()and panel.edit:GetText()=='Edit road network')
            assert(gpsmod.GPSStatus().active and WAYPOINT==waypoint and gpsmod.db.mapRightClick=='zoom')
            assert(#ERRORS==0,ERRORS[1])
        ''')

    def test_panel_saves_partial_recordings_and_discards_false_starts(self):
        self.lua.execute(r'''
            gpsmod:ToggleGPS(true)
            local panel=OpenMapGPSPanel
            local function Click(button)button:GetScript('OnClick')(button,'LeftButton')end
            panel.name:SetText('Partial UI road')Click(panel.record)
            PX=.22 TickGPS()
            PX=.5 TickGPS()
            assert(gpsmod.GPSStatus().recordingState=='gap'and panel.save:GetText()=='Save partial')
            Click(panel.save)
            assert(not gpsmod.GPSStatus().recording and #gpsmod.db.gpsRoutes['Partial UI road'].points==2)
            panel.name:SetText('False start')Click(panel.record)
            assert(panel.stop:GetText()=='Discard recording')
            Click(panel.stop)
            assert(not gpsmod.GPSStatus().recording and not gpsmod.db.gpsRoutes['False start'])
            assert(#ERRORS==0,ERRORS[1])
        ''')


if __name__ == "__main__":
    unittest.main()
