"""Vertical GPS progress: real boot and live waypoint/HUD code with position input.

Run: python -P tools/offline-test/gps_vertical.py
Synthetic planned routes isolate live progress; imported floor bounds are audited
separately without executing Forever Maps routing implementation.
"""
import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gps_vertical_boot', HERE / 'gps_bundled_integration.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class GPSVerticalTests(unittest.TestCase):
    def setUp(self):
        base.BundledGPSIntegrationTests.setUp(self)
        self.lua.execute('''
            function Planned(points)
                mod.GPSRoadRoute=function()
                    return points,nil,{source='bundled'}
                end
            end
            function LivePoint(x,y,extra)
                local p={cont=0,world=0,wx=x,wy=y,map=900001,x=x/1000,y=y/1000}
                for k,v in pairs(extra or {})do p[k]=v end
                return p
            end
            function Stairs(first,last,radius)
                local points={}
                local steps=math.floor(math.abs(last-first)*16+.5)
                for i=0,steps do
                    local turn=first+(last-first)*i/steps
                    local angle=turn*2*math.pi
                    local p=LivePoint(100+radius*math.cos(angle),100+radius*math.sin(angle),{
                        kind='stairs',stairOwner=1,stairTurn=turn,
                        stairStartTurn=first,stairAngleSign=1,centerWX=100,centerWY=100
                    })
                    if i>0 then p.stairDirection=last>first and 1 or -1 end
                    points[#points+1]=p
                end
                return points
            end
            function MoveWorld(x,y,z)
                player.x,player.y=x/1000,y/1000
                player.z=z
                TickGPS()
            end
            function RoomFixture()
                ns.GPSBuildingData={cell=256,networks={[0]={
                    buildings={{id=100,bounds={90,90,220,110},pieces={
                        [1]={indoor=true,zmin=0,zmax=5,polygon={{90,90},{220,90},{220,110},{90,110}}},
                        [2]={indoor=true,zmin=20,zmax=25,polygon={{90,90},{220,90},{220,110},{90,110}}}
                    }}},cells={[32896]={1}}
                }}}
                RoadFixture({
                    [1]={wx=100,wy=100,map=900001,piece='100:1',layer=true,links={[2]=true}},
                    [2]={wx=200,wy=100,map=900001,piece='100:2',layer=true,links={[1]=true}}
                })
                mod.GPSResetRoom()
                IsIndoors=function()return true end
            end
        ''')

    def run_lua(self, source):
        self.lua.execute(source)

    def test_upstairs_exact_three_turns_without_an_initial_pause(self):
        self.run_lua('''
            local route=Stairs(0,3,4)
            player.x,player.y,player.z=.104,.1,nil
            Planned(route)
            assert(mod.GPSStart(900001,.104,.1))
            for i=2,#route do MoveWorld(route[i].wx,route[i].wy)end
            for _=1,3 do TickGPS()end
            assert(mod.GPSStatus().state=='arrived',
                'three-turn staircase lost the first movement interval without a pause')
        ''')

    def test_downstairs_exact_two_turns_without_an_initial_pause(self):
        self.run_lua('''
            local route=Stairs(2,0,10)
            player.x,player.y,player.z=.11,.1,nil
            Planned(route)
            assert(mod.GPSStart(900001,.11,.1))
            for i=2,#route do MoveWorld(route[i].wx,route[i].wy)end
            for _=1,3 do TickGPS()end
            assert(mod.GPSStatus().state=='arrived',
                'descending spiral lost winding progress or used the upward comparison')
        ''')

    def test_intermediate_exit_requires_its_winding_level_at_shared_xy(self):
        self.run_lua('''
            local route=Stairs(0,1.5,6)
            player.x,player.y,player.z=.106,.1,nil
            Planned(route)
            assert(mod.GPSStart(900001,route[#route].x,route[#route].y))
            for _=1,5 do TickGPS()end
            assert(mod.GPSStatus().active,'small radius was treated as arrival without climbing')
            for i=2,#route do MoveWorld(route[i].wx,route[i].wy)end
            for _=1,3 do TickGPS()end
            assert(mod.GPSStatus().state=='arrived','intermediate landing could not be reached')
        ''')

    def test_same_floor_rejoin_skips_a_corner_without_returning_to_old_point(self):
        self.run_lua('''
            Planned({LivePoint(100,100),LivePoint(100,130),LivePoint(130,130),
                LivePoint(130,100),LivePoint(160,100)})
            assert(mod.GPSStart(900001,.16,.1))
            MoveWorld(130,100,0)
            assert(mod.GPSStatus().index>=4,
                'standing on a later stretch still directs the player back to the missed corner')
            MoveWorld(160,100,0)TickGPS()
            assert(mod.GPSStatus().state=='arrived')
        ''')

    def test_rejoin_can_recover_after_the_first_road_point_was_missed(self):
        self.run_lua('''
            Planned({LivePoint(100,130),LivePoint(130,130),
                LivePoint(130,100),LivePoint(160,100)})
            assert(mod.GPSStart(900001,.16,.1))
            MoveWorld(130,100,0)
            assert(mod.GPSStatus().index>=3,
                'missing the first road point prevented rejoining a later stretch')
            MoveWorld(160,100,0)TickGPS()
            assert(mod.GPSStatus().state=='arrived')
        ''')

    def test_later_point_on_other_floor_never_causes_rejoin_or_arrival(self):
        self.run_lua('''
            RoomFixture()
            player.x,player.y,player.z=.1,.1,2
            Planned({
                LivePoint(100,100,{piece='100:1',layer=true,minZ=0,maxZ=5}),
                LivePoint(200,100,{piece='100:1',layer=true,minZ=0,maxZ=5}),
                LivePoint(200,100,{piece='100:2',layer=true,minZ=20,maxZ=25}),
                LivePoint(100,100,{piece='100:2',layer=true,minZ=20,maxZ=25})
            })
            assert(mod.GPSStart(900001,.1,.1))
            for _=1,8 do TickGPS()end
            assert(mod.GPSStatus().active and mod.GPSStatus().index<=2,
                'lower floor XY matched a later upper-floor waypoint')
        ''')

    def test_undercity_elevator_waits_for_subzone_floor_change_without_height(self):
        self.run_lua('''
            player.map,player.x,player.y,player.z=1458,.1,.1,nil
            local subzone='Localized Ruins'
            GetSubZoneText=function()return subzone end
            C_Map.GetAreaInfo=function(id)if id==153 then return 'Localized Ruins'end end
            IsIndoors=function()return nil end
            Planned({{cont=0,wx=100,wy=100,map=1458,x=.1,y=.1,layer=1458,kind='elevator'}})
            assert(mod.GPSStart(1458,.1,.1))
            for _=1,4 do TickGPS()end
            assert(mod.GPSStatus().active and mod.GPSStatus().instruction:find('floor'),
                'Ruins above were treated as the underground city')
            subzone='Trade Quarter'
            TickGPS()
            assert(mod.GPSStatus().state=='arrived')
        ''')

    def test_ambiguous_indoor_floor_without_height_cannot_arrive(self):
        self.run_lua('''
            RoomFixture()
            player.x,player.y,player.z=.1,.1,nil
            Planned({LivePoint(100,100,{piece='100:2',layer=true,minZ=20,maxZ=25})})
            assert(mod.GPSStart(900001,.1,.1))
            for _=1,6 do TickGPS()end
            assert(mod.GPSStatus().active,
                'unknown indoor floor was accepted just because both floors share XY')
        ''')

    def test_idle_observation_retains_entered_room_before_starting_navigation(self):
        self.run_lua('''
            RoomFixture()
            player.x,player.y,player.z=.1,.1,2
            local observe=mod.GPSObserveRoom
            local seen={}
            mod.GPSObserveRoom=function(...)
                local context=observe(...)
                seen[#seen+1]=context
                return context
            end
            assert(not mod.GPSStatus().active)
            TickGPS()
            assert(#seen>0 and seen[#seen].piece=='100:1',
                'entering a building while GPS is idle did not establish room membership')
            player.z=nil
            TickGPS()
            assert(seen[#seen].piece=='100:1' and not seen[#seen].ambiguous,
                'the known room was lost when height became unavailable before a journey')
            Planned({LivePoint(100,100,{piece='100:1',layer=true,minZ=0,maxZ=5})})
            assert(mod.GPSStart(900001,.1,.1))
            assert(mod.GPSStatus().state=='arrived',
                'a new journey ignored the room established while GPS was idle')
        ''')

    def test_adjacent_same_floor_room_is_not_reported_as_another_floor(self):
        self.run_lua('''
            RoomFixture()
            local b=ns.GPSBuildingData.networks[0].buildings[1]
            b.pieces[1].polygon={{90,90},{115,90},{115,110},{90,110}}
            b.pieces[2].polygon={{115,90},{140,90},{140,110},{115,110}}
            b.pieces[2].zmin,b.pieces[2].zmax=0,5
            player.x,player.y,player.z=.11,.1,2
            Planned({LivePoint(120,100,{piece='100:2',layer=true,minZ=0,maxZ=5})})
            assert(mod.GPSStart(900001,.12,.1))
            assert(mod.GPSStatus().state=='arrived',
                'an adjacent room with the same height interval was treated as another floor')
        ''')

    def test_adjacent_rooms_with_overlapping_heights_are_not_other_floors(self):
        self.run_lua('''
            assert(type(mod.GPSOtherFloor)=='function')
            local a={cont=0,piece='100:1',minZ=0,maxZ=10}
            local b={cont=0,piece='100:2',minZ=0,maxZ=10}
            local c={cont=0,piece='100:3',minZ=20,maxZ=30}
            assert(not mod.GPSOtherFloor(a,b) and mod.GPSOtherFloor(a,c))
            assert(not mod.GPSOtherFloor(a,{cont=0,piece='200:1',minZ=20,maxZ=30}))
            assert(not mod.GPSOtherFloor(a,{cont=0,piece='100:999'}))
        ''')

    def test_all_imported_same_building_piece_pairs_follow_height_overlap_contract(self):
        if self.lua.eval("rawget(_G,'realBuildings') == nil"):
            self.skipTest('Forever-only imported room geometry')
        self.run_lua('''
            ns.GPSBuildingData=realBuildings
            ns.GPSRoadData=realRoads
            local checked=0
            for cont,network in pairs(realBuildings.networks)do
                for _,building in pairs(network.buildings)do
                    for ag,a in pairs(building.pieces)do
                        for bg,b in pairs(building.pieces)do
                            local expected=ag~=bg and math.min(a.zmax,b.zmax)-math.max(a.zmin,b.zmin)<.5
                            local actual=mod.GPSOtherFloor({cont=cont,piece=building.id..':'..ag},
                                {cont=cont,piece=building.id..':'..bg})
                            assert(actual==expected,'imported floor contract mismatch at '..building.id..':'..ag..'/'..bg)
                            checked=checked+1
                        end
                    end
                end
            end
            assert(checked>1000)
        ''')


if __name__ == '__main__':
    unittest.main()
