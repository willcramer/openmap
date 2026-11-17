"""Room/floor interpretation: no shortcuts between overlapping WMO groups.

Run: python -P tools/offline-test/gps_rooms.py
"""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]


class GPSRooms(unittest.TestCase):
    def setUp(self):
        self.lua = lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
            mod = {}
            ns = { Safe = { Value = function(v)
                if type(v) == 'table' and v.secret then return nil end
                return v
            end } }
            function ns:GetModule() return mod end
            NOW=0
            function GetTime() return NOW end
            function GetSubZoneText() return SUBZONE end
            function IsIndoors() return INDOORS end
            C_Map={GetAreaInfo=function(id) if id==153 then return 'Localized Ruins' end end}
            handlers={}
            function ns.RegisterEvent(owner,event,fn)
                handlers[event]=function()fn(owner,event)end
            end
            function fire(event) assert(handlers[event],event) handlers[event]() end
            function square(x,y,size)
                return {{x,y},{x+size,y},{x+size,y+size},{x,y+size}}
            end
            ns.GPSBuildingData = {cell=256, networks={[0]={buildings={
                [1]={id=100,bounds={0,0,20,20},pieces={
                    [1]={indoor=true,zmin=0,zmax=5,polygon=square(0,0,10)},
                    [2]={indoor=true,zmin=10,zmax=15,polygon=square(0,0,10)},
                    [3]={indoor=false,zmin=0,zmax=5,polygon=square(10,0,10)}
                }}
            },cells={[32896]={1}}}}}
            ns.GPSRoadData = {networks={[0]={nodes={
                [1]={piece='100:1',layer=1458},
                [2]={piece='100:2',layer=true},
                [3]={piece='100:3'}
            }}}}
        """)
        lua.execute((ROOT / 'OpenMap/Map/GPSRooms.lua').read_text(), 'OpenMap', lua.globals().ns)

    def test_known_height_selects_exact_floor_and_source_layer(self):
        self.lua.execute("""
            local a=mod.GPSRoomContext(0,5,5,2,1458)
            assert(a.piece=='100:1' and a.layer==1458 and a.inside and not a.ambiguous)
            assert(a.z==2 and a.minZ==0 and a.maxZ==5)
            local b=mod.GPSRoomContext(0,5,5,12,1458)
            assert(b.piece=='100:2' and b.layer==true and b.inside and not b.ambiguous)
        """)

    def test_unknown_height_preserves_ambiguity_instead_of_guessing_floor(self):
        self.lua.execute("""
            local a=mod.GPSRoomContext(0,5,5,nil,1458)
            assert(a.ambiguous and not a.piece and not a.layer)
            assert(a.pieces['100:1'] and a.pieces['100:2'] and #a.candidates==2)
        """)

    def test_cancelled_cold_index_is_not_published_and_rebuilds_completely(self):
        self.lua.execute("""
            local nodes=ns.GPSRoadData.networks[0].nodes
            for i=4,80 do nodes[i]={piece='100:'..i,layer=i}end
            local rooms=ns.GPSBuildingData.networks[0].buildings[1].pieces
            for i=4,80 do rooms[i]={indoor=true,zmin=i*10,zmax=i*10+5,polygon=square(0,0,10)}end
            assert(not mod.GPSRoomsReady(0))
            mod.GPSPlanningCheckpoint=function()coroutine.yield()end
            local pending=coroutine.create(function()return mod.GPSRoadNodeContext(0,{piece='100:80'})end)
            assert(coroutine.resume(pending))
            assert(coroutine.status(pending)=='suspended'and not mod.GPSRoomsReady(0))
            -- Abandon the first worker, then build with the ordinary synchronous API.
            mod.GPSPlanningCheckpoint=nil
            for i=4,80 do
                local room=mod.GPSRoadNodeContext(0,{piece='100:'..i})
                assert(room.layer==i and room.minZ==i*10 and room.maxZ==i*10+5)
            end
            assert(mod.GPSRoomsReady(0))
            ns.GPSRoadData={networks={[0]={nodes={}}}}
            assert(not mod.GPSRoomsReady(0),'source replacement kept the old ready flag')
            local rebuilt=mod.GPSRoadNodeContext(0,{piece='100:80'})
            assert(rebuilt.layer==true and mod.GPSRoomsReady(0))
        """)

    def test_boundary_is_included_and_shared_wall_remains_ambiguous(self):
        self.lua.execute("""
            assert(mod.GPSRoomContext(0,0,5,2).piece=='100:1')
            local wall=mod.GPSRoomContext(0,10,5,2)
            assert(wall.ambiguous and not wall.piece)
            assert(wall.pieces['100:1'] and wall.pieces['100:3'])
            assert(wall.inside==nil)
        """)

    def test_outdoor_and_vertical_gaps_do_not_become_rooms(self):
        self.lua.execute("""
            local a=mod.GPSRoomContext(0,15,5,2)
            assert(a.piece=='100:3' and a.inside==false and not a.layer)
            local b=mod.GPSRoomContext(0,5,5,8)
            assert(not b.piece and not b.ambiguous and b.inside==false)
            local c=mod.GPSRoomContext(0,1000,1000,2)
            assert(not c.piece and c.inside==false)
        """)

    def test_node_piece_is_exact_without_inventing_a_floor_height(self):
        self.lua.execute("""
            local a=mod.GPSRoadNodeContext(0,{piece='100:1',layer=1458,[3]=1458})
            assert(a.piece=='100:1' and a.layer==1458 and a.minZ==0 and a.maxZ==5)
            assert(not a.z, 'a room box midpoint was reported as its walkable floor')
            local b=mod.GPSRoadNodeContext(0,{piece='unknown:4',layer=true})
            assert(b.piece=='unknown:4' and b.layer==true and not b.minZ)
        """)

    def test_source_grid_axes_are_not_swapped_twice(self):
        self.lua.execute("""
            local net=ns.GPSBuildingData.networks[0]
            net.buildings[2]={id=200,bounds={300,600,310,610},pieces={
                [0]={indoor=true,zmin=1,zmax=2,polygon=square(300,600,10)}
            }}
            net.cells[(2+128)*256+1+128]={2}
            local a=mod.GPSRoomContext(0,305,605,1.5)
            assert(a.piece=='200:0')
            assert(not mod.GPSRoomContext(0,605,305,1.5).piece)
        """)

    def test_secret_or_nonfinite_values_never_take_part_in_geometry(self):
        self.lua.execute("""
            local a=mod.GPSRoomContext(0,{secret=true},5,2)
            assert(a.unknown and a.ambiguous and a.inside==nil)
            assert(mod.GPSRoomContext(0,math.huge,5,2).unknown)
            local b=mod.GPSRoomContext(0,5,5,{secret=true})
            assert(b.ambiguous and not b.piece)
        """)

    def test_imported_piece_lookup_matches_authoritative_data(self):
        source = ROOT / 'OpenMap/Data/Forever/RoadBuildings.lua'
        if not source.exists():
            self.skipTest('imported room data is not available')
        self.lua.execute(source.read_text(), 'OpenMap', self.lua.globals().ns)
        self.lua.execute("""
            local found=0
            for continent,network in pairs(ns.GPSBuildingData.networks) do
                for _,building in pairs(network.buildings) do
                    for group,room in pairs(building.pieces) do
                        local piece=building.id..':'..group
                        local got=mod.GPSRoadNodeContext(continent,{piece=piece,layer=true})
                        assert(got.minZ==room.zmin and got.maxZ==room.zmax and got.piece==piece)
                        assert(got.inside==room.indoor)
                        found=found+1
                        break
                    end
                    break
                end
            end
            assert(found>0)
        """)

    def test_temporal_membership_survives_unknown_height_but_resets_after_loading(self):
        self.lua.execute("""
            mod:SetupGPSRooms()
            assert(mod.GPSObserveRoom(0,5,5,nil,2).piece=='100:1')
            NOW=.2
            local same=mod.GPSObserveRoom(0,5,5)
            assert(same.piece=='100:1' and same.evidence=='continuity')
            fire('PLAYER_ENTERING_WORLD')
            local reset=mod.GPSObserveRoom(0,5,5)
            assert(reset.ambiguous and not reset.piece)
        """)

    def test_portal_event_and_motion_identify_room_in_overlapping_boxes(self):
        self.lua.execute("""
            local b=ns.GPSBuildingData.networks[0].buildings[1]
            b.pieces[2].zmin,b.pieces[2].zmax=0,5
            b.pieces[2].polygon=square(5,0,10)
            b.portals={{from=2,to=1,nx=1,ny=0,zmin=0,zmax=5,polygon={{7,2},{7,8}}}}
            mod:SetupGPSRooms()
            assert(mod.GPSObserveRoom(0,2,5).piece=='100:1')
            NOW=.2 assert(mod.GPSObserveRoom(0,6,5).piece=='100:1')
            fire('NEW_WMO_CHUNK')
            NOW=.4
            local entered=mod.GPSObserveRoom(0,8,5)
            assert(entered.piece=='100:2' and entered.evidence=='portal')
            fire('NEW_WMO_CHUNK')
            NOW=.6 assert(mod.GPSObserveRoom(0,6,5).piece=='100:1')
        """)

    def test_leaving_previous_box_invalidates_room_without_a_portal_event(self):
        self.lua.execute("""
            local b=ns.GPSBuildingData.networks[0].buildings[1]
            b.pieces[2].zmin,b.pieces[2].zmax=0,5
            b.pieces[2].polygon=square(5,0,10)
            b.pieces[3]=nil
            assert(mod.GPSObserveRoom(0,2,5).piece=='100:1')
            NOW=.2 assert(mod.GPSObserveRoom(0,8,5).piece=='100:1')
            NOW=.4 assert(mod.GPSObserveRoom(0,11,5).piece=='100:2')
        """)

    def test_delayed_chunk_event_uses_recent_motion_even_after_stopping(self):
        self.lua.execute("""
            local b=ns.GPSBuildingData.networks[0].buildings[1]
            b.pieces[2].zmin,b.pieces[2].zmax=0,5
            b.pieces[2].polygon=square(5,0,10)
            b.portals={{from=2,to=1,nx=1,ny=0,zmin=0,zmax=5,polygon={{7,2},{7,8}}}}
            mod:SetupGPSRooms()
            assert(mod.GPSObserveRoom(0,2,5).piece=='100:1')
            NOW=.2 assert(mod.GPSObserveRoom(0,6,5).piece=='100:1')
            NOW=.4 assert(mod.GPSObserveRoom(0,8,5).piece=='100:1')
            fire('NEW_WMO_CHUNK')
            NOW=.6 local current=mod.GPSObserveRoom(0,8,5)
            assert(current.piece=='100:2' and current.evidence=='portal')
        """)

    def test_floor_hole_uses_prior_membership_and_keeps_unknown_start_ambiguous(self):
        self.lua.execute("""
            local b=ns.GPSBuildingData.networks[0].buildings[1]
            b.portals={{from=1,to=2,nx=0,ny=0,zmin=0,zmax=15,polygon=square(0,0,10)}}
            mod:SetupGPSRooms()
            assert(mod.GPSObserveRoom(0,5,5,nil,2).piece=='100:1')
            fire('NEW_WMO_CHUNK')
            NOW=.2 assert(mod.GPSObserveRoom(0,5,5).piece=='100:2')
            mod.GPSResetRoom()
            assert(mod.GPSObserveRoom(0,5,5).ambiguous)
            fire('NEW_WMO_CHUNK')
            NOW=.4 assert(mod.GPSObserveRoom(0,5,5).ambiguous)
        """)

    def test_teleports_and_secret_position_loss_clear_temporal_membership(self):
        self.lua.execute("""
            assert(mod.GPSObserveRoom(0,5,5,nil,2).piece=='100:1')
            NOW=.2 mod.GPSObserveRoom(0,500,500)
            NOW=.4 assert(mod.GPSObserveRoom(0,5,5).ambiguous)
            assert(mod.GPSObserveRoom(0,5,5,nil,2).piece=='100:1')
            local hidden=mod.GPSObserveRoom(0,{secret=true},5)
            assert(hidden.unknown and hidden.ambiguous)
            NOW=.6 assert(mod.GPSObserveRoom(0,5,5).ambiguous)
        """)

    def test_unique_indoor_piece_beats_overlapping_exterior_envelope(self):
        self.lua.execute("""
            ns.GPSBuildingData.networks[0].buildings[1].pieces[1].indoor=false
            local got=mod.GPSObserveRoom(0,5,5)
            assert(got.piece=='100:2' and got.inside and got.evidence=='unique-indoor')
        """)

    def test_localized_undercity_subzone_separates_ruins_from_underground(self):
        self.lua.execute("""
            SUBZONE='Localized Ruins'
            local above=mod.GPSObserveRoom(0,5,5,1458)
            assert(above.cityLayer==false and above.layer~=1458 and above.piece=='100:2')
            SUBZONE='Trade Quarter'
            NOW=.2
            local below=mod.GPSObserveRoom(0,5,5,1458)
            assert(below.layer==1458 and below.piece=='100:1')
            mod.GPSResetRoom() SUBZONE=nil
            assert(mod.GPSObserveRoom(0,5,5,1458).ambiguous)
        """)

    def test_unique_supplied_context_and_idempotent_event_setup(self):
        self.lua.execute("""
            mod.GPSRoomContext=function()return {piece='known:1',layer=true}end
            mod:SetupGPSRooms()local callback=handlers.NEW_WMO_CHUNK
            mod:SetupGPSRooms()assert(handlers.NEW_WMO_CHUNK==callback)
            local got=mod.GPSObserveRoom(0,5,5)
            assert(got.piece=='known:1' and got.layer==true and not got.ambiguous)
        """)


if __name__ == '__main__':
    unittest.main()
