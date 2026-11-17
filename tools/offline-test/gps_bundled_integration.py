"""Bundled roads through the full toc, live GPS, Nav waypoint and HUD.

Run: python -P tools/offline-test/gps_bundled_integration.py
The source dataset is tested separately from synthetic restriction/transition cases.
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
import warnings


HERE = Path(__file__).resolve().parent


class BundledGPSIntegrationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('openmap_bundled_boot', HERE / 'run.py')
        module = importlib.util.module_from_spec(spec)
        argv = sys.argv
        try:
            sys.argv = [str(HERE / 'run.py'), 'plain']
            with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
                warnings.simplefilter('ignore', ResourceWarning)
                try:
                    spec.loader.exec_module(module)
                except SystemExit as result:
                    self.assertEqual(result.code, 0)
        finally:
            sys.argv = argv
        self.lua = module.L
        self.lua.globals().ns = module.ns
        self.lua.execute('''
            mod = ns:GetModule('worldmap')
            assert(type(mod.GPSRoadRoute) == 'function', 'bundled router missing from toc')
            realRoads, realBuildings = ns.GPSRoadData, ns.GPSBuildingData
            realLevels, realAreas = ns.GPSRoadLevels, ns.GPSRoadAreas
            realAnchors = ns.GPSRoadAnchors
            ns.GPSBuildingData = { cell = 256, networks = {} }
            ns.GPSRoadLevels, ns.GPSRoadAreas = {}, {}
            SCALE, OFFSET = 1000, 0
            NATIVE = nil
            MAP_CONT = { [900001] = 0, [2521] = 2991 }
            player = { map = 900001, x = .1, y = .1, z = 0 }
            CreateVector2D = function(x,y) return { x=x,y=y } end
            C_Map.GetBestMapForUnit = function() return player.map end
            C_Map.GetPlayerMapPosition = function(map)
                if map == player.map then return CreateVector2D(player.x, player.y) end
            end
            C_Map.GetWorldPosFromMapPos = function(map, p)
                return MAP_CONT[map] or 0, CreateVector2D(p.x * SCALE + OFFSET, p.y * SCALE + OFFSET)
            end
            C_Map.GetMapPosFromWorldPos = function(cont, p, map)
                return map, CreateVector2D((p.x - OFFSET) / SCALE, (p.y - OFFSET) / SCALE)
            end
            C_Map.GetMapInfo = function(map) return { mapID = map, name = 'Integration map' } end
            C_Map.GetAreaInfo = function() return nil end
            UnitPosition = function()
                return player.x * SCALE + OFFSET, player.y * SCALE + OFFSET, player.z, MAP_CONT[player.map] or 0
            end
            UnitFactionGroup = function() return 'Alliance' end
            UnitLevel = function() return 10 end
            UnitOnTaxi = function() return false end
            UnitIsGhost = function() return false end
            GetPlayerFacing = function() return 0 end
            ns.MapStitch.Rect = function(map) if map ~= NATIVE then return 0, 1, 0, 1 end end
            ns.MapStitch.IsBuilt = function() return false end
            ns.MapStitch.FromYards = function(cont, wx, wy)
                if NATIVE and cont == 2991 then return end
                return (wx - OFFSET) / SCALE, (wy - OFFSET) / SCALE
            end
            WAYPOINT = nil
            C_Map.HasUserWaypoint = function() return WAYPOINT ~= nil end
            C_Map.GetUserWaypoint = function() return WAYPOINT end
            C_Map.CanSetUserWaypointOnMap = function() return true end
            C_Map.SetUserWaypoint = function(p) WAYPOINT = p end
            C_Map.ClearUserWaypoint = function() WAYPOINT = nil end
            UiMapPoint = { CreateFromCoordinates = function(map, x, y)
                return { uiMapID = map, position = { x = x, y = y } }
            end }
            WorldMapFrame:Hide()
            function TickGPS()
                NOW = NOW + .21
                RunOnUpdate(.21)
                assert(#ERRORS == 0, ERRORS[1])
            end
            function RoadFixture(nodes, continent)
                ns.GPSRoadData = { version = 'integration', networks = { [continent or 0] = { nodes = nodes } } }
                mod.GPSInvalidateRoads()
            end
        ''')
        self.lua.execute((HERE / 'gps_wait.lua').read_text(), self.lua.globals().mod)

    def run_lua(self, source):
        self.lua.execute(source)

    def test_bundled_road_navigation_arrives_with_map_closed_and_yields_waypoints(self):
        self.run_lua('''
            RoadFixture({
                [1] = {wx=100,wy=100,map=900001,links={[2]=true}},
                [2] = {wx=300,wy=100,map=900001,links={[1]=true,[3]=true}},
                [3] = {wx=500,wy=100,map=900001,links={[2]=true}}
            })
            SlashCmdList.OPENMAP('gps go 900001 50 10')
            assert(mod.GPSStatus().planning and not mod.GPSStatus().active)
            assert(DrainGPS())
            assert(mod.GPSStatus().active and mod.GPSStatus().roadSource == 'bundled')
            assert(not WorldMapFrame:IsShown() and OpenMapGPSGuide:IsShown())
            local other = UiMapPoint.CreateFromCoordinates(900001,.8,.8)
            C_Map.SetUserWaypoint(other)
            TickGPS()
            assert(not mod.GPSStatus().active and WAYPOINT == other)
            assert(PlanGPS(900001,.5,.1))
            player.x = .3 TickGPS()
            player.x = .5 TickGPS()
            TickGPS()
            assert(mod.GPSStatus().state == 'arrived' and WAYPOINT == nil)
            assert(not WorldMapFrame:IsShown() and not OpenMapGPSGuide:IsShown())
        ''')

    def test_saved_road_bridge_and_delete_update_bundled_plan_without_stale_graph(self):
        self.run_lua('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,piece='fixture:0',layer=true,links={[2]=true}},
                [2]={wx=100,wy=200,map=900001,piece='fixture:0',layer=true,links={[1]=true}},
                [3]={wx=100,wy=400,map=900001,piece='fixture:0',layer=true,links={[4]=true}},
                [4]={wx=100,wy=500,map=900001,piece='fixture:0',layer=true,links={[3]=true}}
            })
            mod.GPSRoomContext = function()
                return { piece='fixture:0',layer=true,pieces={['fixture:0']=true},zmin=0,zmax=10 }
            end
            assert(PlanGPS(900001,.1,.5))
            assert(mod.GPSStatus().roadSource == 'bundled')
            local originalCost = mod.GPSStatus().roadStats.cost
            mod.GPSStop()
            player.y, player.z = .2, 8
            assert(mod.GPSRecord('Road bridge'))
            for _, y in ipairs({.25,.3,.35,.4}) do player.y=y TickGPS() end
            assert(mod.GPSSave())
            local saved = mod.db.gpsRoutes['Road bridge'].points
            assert(saved[1].z == 8 and saved[1].piece == 'fixture:0' and saved[1].layer)
            player.y = .1
            assert(PlanGPS(900001,.1,.5))
            assert(mod.GPSStatus().roadSource == 'bundled')
            local used = false
            for _, p in ipairs(mod.GPSStatus().route) do if p.source == 'recorded' then used=true end end
            assert(used, 'planner ignored the saved bridge')
            assert(mod.GPSStatus().roadStats.cost < originalCost, 'saved bridge did not improve the route')
            mod.GPSStop()
            assert(mod.GPSDelete('Road bridge'))
            assert(PlanGPS(900001,.1,.5))
            assert(math.abs(mod.GPSStatus().roadStats.cost - originalCost) < 1e-6)
            for _, point in ipairs(mod.GPSStatus().route) do
                assert(point.source ~= 'recorded', 'deleted bridge stayed in graph cache')
            end
        ''')

    def test_enemy_start_without_safe_prefix_and_strict_offroad_do_not_become_direct(self):
        self.run_lua('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,type='horde',links={[2]=true}},
                [2]={wx=500,wy=100,map=900001,type='horde',links={[1]=true}}
            })
            local ok, err = PlanGPS(900001,.5,.1)
            assert(not ok and err and not mod.GPSStatus().active)
            mod.db.gpsAllowEnemy = true
            assert(PlanGPS(900001,.5,.1))
            assert(mod.GPSStatus().roadStats.enemy and mod.GPSStatus().instruction:find('faction'))
            mod.GPSStop()
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,links={[2]=true}},
                [2]={wx=300,wy=100,map=900001,type='offroad',links={[1]=true,[3]=true}},
                [3]={wx=500,wy=100,map=900001,links={[2]=true}}
            })
            mod.db.gpsOffroad = 'deny'
            assert(not PlanGPS(900001,.5,.1))
            assert(not mod.GPSStatus().active)
            mod.db.gpsOffroad = 'allow'
            assert(PlanGPS(900001,.5,.1))
            assert(mod.GPSStatus().roadSource == 'bundled')
        ''')

    def test_mixed_faction_route_stops_before_border_then_permission_resumes_goal(self):
        self.run_lua('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,type='alliance',links={[2]=true}},
                [2]={wx=200,wy=100,map=900001,type='alliance',links={[1]=true,[3]=true}},
                [3]={wx=300,wy=100,map=900001,type='horde',links={[2]=true,[4]=true}},
                [4]={wx=400,wy=100,map=900001,type='horde',links={[3]=true,[5]=true}},
                [5]={wx=500,wy=100,map=900001,links={[4]=true}}
            })
            assert(mod.db.gpsAllowEnemy==false)
            assert(PlanGPS(900001,.5,.1,'Across the border'))
            local status=mod.GPSStatus()
            assert(status.active and status.roadSource=='bundled' and status.roadStats.factionStop)
            assert(status.route[#status.route].nodeID==2 and status.route[#status.route].factionStop,
                'default faction policy entered the enemy road')
            player.x=.2 TickGPS()
            status=mod.GPSStatus()
            assert(not status.active and status.state=='faction-stop')
            assert(status.instruction:find('faction') and status.instruction~='You have arrived.')
            assert(OpenMapGPSGuide:IsShown() and OpenMapGPSGuide.instruction:GetText()==status.instruction,
                'border stop lost its visible explanation with the map closed')
            assert(not OpenMapGPSGuide.arrow:IsShown() and WAYPOINT==nil)
            assert(status.resumeTarget and status.resumeTarget.x==.5)
            assert(RoutingGPS('gpsAllowEnemy',true))
            status=mod.GPSStatus()
            assert(status.active and status.roadSource=='bundled')
            assert(status.roadStats.enemy and status.instruction:find('faction'),
                'continuing through the border lost the enemy-road warning')
            player.x=.3 TickGPS()
            player.x=.4 TickGPS()
            player.x=.5 TickGPS() TickGPS()
            assert(mod.GPSStatus().state=='arrived')
        ''')

    def test_offroad_needed_is_a_cost_policy_while_deny_is_an_extra_strict_option(self):
        self.run_lua('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,links={[2]=true}},
                [2]={wx=300,wy=100,map=900001,type='offroad',links={[1]=true,[3]=true}},
                [3]={wx=500,wy=100,map=900001,links={[2]=true}}
            })
            assert(RoutingGPS('gpsOffroad','needed'))
            assert(PlanGPS(900001,.5,.1))
            local expensive=mod.GPSStatus().roadStats.cost
            assert(mod.GPSStatus().roadSource=='bundled' and expensive>10000,
                'needed off-road mode incorrectly became a hard ban')
            assert(RoutingGPS('gpsOffroad','allow'))
            assert(mod.GPSStatus().active and mod.GPSStatus().roadStats.cost<expensive/100)
            assert(RoutingGPS('gpsOffroad','deny'))
            assert(not mod.GPSStatus().active and mod.GPSStatus().state~='direct')
        ''')

    def test_ghost_ignores_faction_offroad_and_high_level_constraints(self):
        self.run_lua('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,type='horde',links={[2]=true}},
                [2]={wx=300,wy=100,map=900001,type='offroad',links={[1]=true,[3]=true}},
                [3]={wx=500,wy=100,map=900001,type='horde',links={[2]=true}}
            })
            ns.GPSRoadLevels={areas={},zones={[900001]={low=50,high=60}}}
            assert(RoutingGPS('gpsOffroad','deny'))
            assert(RoutingGPS('gpsAboveLevel','never'))
            assert(not PlanGPS(900001,.5,.1))
            UnitIsGhost=function() return true end
            assert(PlanGPS(900001,.5,.1))
            local status=mod.GPSStatus()
            assert(status.active and status.roadSource=='bundled' and not status.roadStats.factionStop)
            for _,point in ipairs(status.route) do
                assert(not point.enemy and not point.highLevel,'ghost received living-character road constraints')
            end
            player.x=.3 TickGPS()
            player.x=.5 TickGPS() TickGPS()
            assert(mod.GPSStatus().state=='arrived' and not OpenMapGPSGuide:IsShown())
        ''')

    def test_above_level_denial_is_a_route_error_without_direct_shortcut(self):
        self.run_lua('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,type='offroad',links={[2]=true}},
                [2]={wx=500,wy=100,map=900001,type='offroad',links={[1]=true}}
            })
            ns.GPSRoadLevels = { areas={},zones={[900001]={low=30,high=40}} }
            mod.db.gpsAboveLevel = 'deny'
            local ok, err = PlanGPS(900001,.5,.1)
            assert(not ok and err and not mod.GPSStatus().active)
            mod.db.gpsAboveLevel = 'allow'
            assert(PlanGPS(900001,.5,.1))
            assert(mod.GPSStatus().roadSource == 'bundled')
        ''')

    def test_native_zephras_route_works_without_stitched_map_rectangle(self):
        self.run_lua('''
            NATIVE, player.map = 2521, 2521
            RoadFixture({
                [1]={wx=100,wy=100,map=2521,links={[2]=true}},
                [2]={wx=500,wy=100,map=2521,links={[1]=true}}
            },2991)
            assert(ns.MapStitch.Rect(2521) == nil)
            assert(PlanGPS(2521,.5,.1))
            local status = mod.GPSStatus()
            assert(status.active and status.roadSource == 'bundled' and status.u == nil)
            assert(status.map == 2521 and status.distance and status.bearing)
            assert(WAYPOINT.uiMapID == 2521)
            TickGPS()
            assert(OpenMapGPSGuide:IsShown())
            player.x=.5 TickGPS() TickGPS()
            assert(mod.GPSStatus().state == 'arrived')
        ''')

    def test_spiral_stairs_require_angular_traversal_at_overlapping_coordinates(self):
        self.run_lua('''
            player.x=.11
            mod.GPSRoadRoute = function()
                return {
                    {cont=0,wx=110,wy=100,map=900001,x=.11,y=.1,stairOwner=1,stairTurn=0,centerWX=100,centerWY=100,kind='stairs'},
                    {cont=0,wx=110,wy=100,map=900001,x=.11,y=.1,stairOwner=1,stairTurn=1,stairStartTurn=0,
                     stairDirection=1,stairAngleSign=1,centerWX=100,centerWY=100,kind='stairs'}
                },nil,{source='bundled'}
            end
            assert(PlanGPS(900001,.11,.1))
            for _=1,12 do TickGPS() end
            assert(mod.GPSStatus().active and mod.GPSStatus().index == 2,
                'overlapping stair top advanced without walking the spiral')
            for i=1,16 do
                local a=i*2*math.pi/16
                player.x,player.y=(100+10*math.cos(a))/1000,(100+10*math.sin(a))/1000
                TickGPS()
            end
            assert(mod.GPSStatus().state == 'arrived')
        ''')

    def test_live_progress_does_not_arrive_on_the_wrong_floor(self):
        self.run_lua('''
            player.x,player.y,player.z=.5,.5,0
            mod.GPSRoadRoute = function()
                return {{cont=0,wx=500,wy=500,map=900001,x=.5,y=.5,minZ=95,maxZ=105}},nil,{source='bundled'}
            end
            assert(PlanGPS(900001,.5,.5))
            for _=1,5 do TickGPS() end
            assert(mod.GPSStatus().active and mod.GPSStatus().instruction:find('floor'))
            player.z=100 TickGPS()
            assert(mod.GPSStatus().state == 'arrived')
        ''')

    def test_actual_imported_outdoor_edge_plans_through_full_gps(self):
        if self.lua.eval("rawget(_G, 'realRoads') == nil"):
            self.skipTest('Forever-only bundled data is intentionally absent from Retail')
        self.run_lua('''
            ns.GPSRoadData,ns.GPSBuildingData=realRoads,realBuildings
            ns.GPSRoadLevels,ns.GPSRoadAreas=realLevels,realAreas
            mod.GPSInvalidateRoads()
            SCALE,OFFSET=40000,-20000
            mod.db.gpsAboveLevel,mod.db.gpsOffroad='allow','allow'
            local nodes=realRoads.networks[0].nodes
            local first,last
            for _, id in ipairs((function()
                local ids={} for id in pairs(nodes) do ids[#ids+1]=id end table.sort(ids) return ids
            end)()) do
                local a=nodes[id]
                if not a.type and not a.piece and not a.layer and not a.oneway then
                    local ca=mod.GPSRoomContext(0,a.wx,a.wy,nil,a.map)
                    if not ca.inside and not ca.ambiguous then
                        for nextID in pairs(a.links) do
                            local b=nodes[nextID]
                            local distance=((a.wx-b.wx)^2+(a.wy-b.wy)^2)^.5
                            local cb=mod.GPSRoomContext(0,b.wx,b.wy,nil,b.map)
                            if not b.type and not b.piece and not b.layer and not b.oneway and distance>30
                                and not cb.inside and not cb.ambiguous then first,last=a,b break end
                        end
                    end
                end
                if first then break end
            end
            assert(first and last,'source dataset has no neutral outdoor test edge')
            player.map,player.x,player.y=first.map,(first.wx-OFFSET)/SCALE,(first.wy-OFFSET)/SCALE
            assert(PlanGPS(last.map,(last.wx-OFFSET)/SCALE,(last.wy-OFFSET)/SCALE))
            local status=mod.GPSStatus()
            assert(status.roadSource=='bundled' and status.roadStats.nodes==4467)
            assert(status.route[1].source=='bundled' and not WorldMapFrame:IsShown())
            player.map,player.x,player.y=last.map,(last.wx-OFFSET)/SCALE,(last.wy-OFFSET)/SCALE
            for _=1,#status.route+2 do TickGPS() end
            assert(mod.GPSStatus().state=='arrived')
        ''')

    def test_actual_brill_passenger_platform_starts_at_top_and_descends_stairs(self):
        if self.lua.eval("rawget(_G, 'realRoads') == nil"):
            self.skipTest('Forever-only bundled data is intentionally absent from Retail')
        self.run_lua('''
            assert(type(realAnchors)=='table','platform anchor data missing from full toc')
            ns.GPSRoadData,ns.GPSBuildingData=realRoads,realBuildings
            ns.GPSRoadLevels,ns.GPSRoadAreas=realLevels,realAreas
            ns.GPSRoadAnchors=realAnchors
            mod.GPSInvalidateRoads()
            SCALE,OFFSET=40000,-20000
            UnitFactionGroup=function() return 'Horde' end
            mod.db.gpsAboveLevel,mod.db.gpsOffroad='allow','allow'
            local anchor
            for _, candidate in ipairs(realAnchors.networks[0]) do
                if candidate.node==4452 and candidate.positionOverride then anchor=candidate break end
            end
            assert(anchor,'Brill platform position override missing')
            local destination=realRoads.networks[0].nodes[4455]
            player.map,player.x,player.y=anchor.zone,(anchor.wx-OFFSET)/SCALE,(anchor.wy-OFFSET)/SCALE
            assert(PlanGPS(destination.map,(destination.wx-OFFSET)/SCALE,(destination.wy-OFFSET)/SCALE))
            local status=mod.GPSStatus()
            assert(status.active and status.roadSource=='bundled')
            assert(status.route[1].nodeID==4452,'passenger platform snapped to the stair foot or road below')
            assert(status.route[1].stairOwner==4451 and status.route[1].stairTurnsConfigured==1.75)
            assert(status.route[1].stairTurn>1,'platform lost its winding above the ground')
            assert(status.route[2].stairOwner==4451 and status.route[2].stairDirection==-1,
                'platform start did not enter the descending stair arc')
            assert(status.route[2].stairTurn < status.route[1].stairTurn)
            assert(not WorldMapFrame:IsShown() and OpenMapGPSGuide:IsShown())
        ''')


if __name__ == '__main__':
    unittest.main()
