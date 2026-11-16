"""The optional road layer stays bounded, view-culled and separate from navigation."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]


class RoadViewTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
            mod={defaults={},db={gpsShowRoads=true}}
            ns={Safe={Value=function(v)return v end,Call=function(fn,...)if type(fn)=='function'then return fn(...)end end}}
            function ns:GetModule()return mod end
            shown,stitched,built=true,true,true
            WorldMapFrame={IsShown=function()return shown end}
            IsInInstance=function()return instance end
            function mod.IsStitched()return stitched end
            viewU,viewV,halfU,halfV=.5,.5,.5,.5
            function mod.ViewNow()return viewU,viewV,1 end
            function mod.ViewHalfExtents()return halfU,halfV end
            local clears=0
            sets={}
            ns.MapStitch={}
            local S=ns.MapStitch
            function S.IsBuilt()return built end
            function S.FromYards(cont,x,y)if cont==0 then return x,y end end
            function S.PinSet(key)sets[key]={pins={},clears=0}return sets[key]end
            function S.SetPinSetOn(s,on)s.on=on end
            function S.ClearPinSet(s)s.pins={}s.clears=s.clears+1 end
            function S.AddPin(s,u,v,look)
                local pin={u=u,v=v,look=look,EnableMouse=function(self,on)self.mouse=on end}
                s.pins[#s.pins+1]=pin
                return pin
            end
            ns.GPSRoadData={networks={[0]={nodes={
                [1]={wx=0,wy=.5,links={[2]=true}},
                [2]={wx=1,wy=.5,links={[1]=true}},
                [3]={wx=5,wy=.5,links={[4]=true}},
                [4]={wx=6,wy=.5,links={[3]=true}}
            }}}}
        """)
        lua.execute((ROOT / 'OpenMap/Map/GPSRoadView.lua').read_text(), 'OpenMap', lua.globals().ns)

    def test_view_culling_and_unchanged_view_reuses_pins(self):
        self.lua.execute("""
            mod.GPSRefreshRoadView()
            local s=sets.gpsroads
            assert(s.on and #s.pins==100)
            for _,p in ipairs(s.pins)do assert(p.u>=0 and p.u<=1 and p.mouse==false)end
            local pins,clears=s.pins,s.clears
            mod.GPSRefreshRoadView()
            assert(s.pins==pins and s.clears==clears)
            viewU=5.5 mod.GPSRefreshRoadView()
            assert(s.clears==clears+1 and #s.pins==100)
            for _,p in ipairs(s.pins)do assert(p.u>=5 and p.u<=6)end
        """)

    def test_reciprocal_edges_are_drawn_once_without_mutating_data(self):
        self.lua.execute("""
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroads.pins==100)
            local n=ns.GPSRoadData.networks[0].nodes
            assert(n[1].links[2] and n[2].links[1] and n[1].u==nil)
        """)

    def test_controller_stitched_view_uses_the_same_road_layer(self):
        self.lua.execute("""
            stitched=false
            mod.PadViewOn=function()return true end
            mod.PadViewHalfExtents=function()return .5,.5 end
            mod.ViewHalfExtents=function()error('used the inactive keyboard map geometry')end
            mod.GPSRefreshRoadView()
            assert(sets.gpsroads.on and #sets.gpsroads.pins>0)
        """)

    def test_dense_world_is_bounded_and_samples_the_whole_view(self):
        self.lua.execute("""
            local nodes={}
            for i=1,3000 do
                local y=(i-.5)/3000
                nodes[i*2]={wx=0,wy=y,links={[i*2+1]=true}}
                nodes[i*2+1]={wx=1,wy=y,links={[i*2]=true}}
            end
            ns.GPSRoadData={networks={[0]={nodes=nodes}}}
            mod.GPSRefreshRoadView()
            local pins=sets.gpsroads.pins
            assert(#pins>0 and #pins<=800)
            local low,high=false,false
            for _,p in ipairs(pins)do low=low or p.v<.2 high=high or p.v>.8 end
            assert(low and high,'the budget only showed one end of the network')
        """)

    def test_floor_changes_towers_and_unmapped_continents_are_not_straight_lines(self):
        self.lua.execute("""
            ns.GPSRoadData={networks={
                [0]={nodes={
                    [1]={wx=0,wy=.5,layer=true,links={[2]=true}},
                    [2]={wx=1,wy=.5,links={[1]=true}},
                    [3]={wx=0,wy=.4,piece='a:0',links={[4]=true}},
                    [4]={wx=1,wy=.4,piece='a:1',links={[3]=true}},
                    [5]={wx=0,wy=.3,tower={top=6},links={[6]=true}},
                    [6]={wx=1,wy=.3,links={[5]=true}}
                }},
                [1]={nodes={[1]={wx=0,wy=.1,links={[2]=true}},[2]={wx=1,wy=.1,links={[1]=true}}}}
            }}
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroads.pins==0)
        """)

    def test_hidden_native_instance_and_preference_filters_do_not_clear_routes(self):
        self.lua.execute("""
            sets.gps={sentinel=true}
            mod.GPSRefreshRoadView()
            local s=sets.gpsroads local clears=s.clears
            shown=false mod.GPSRefreshRoadView()assert(not s.on)
            shown=true stitched=false mod.GPSRefreshRoadView()assert(not s.on)
            stitched=true mod.instanceWorldHidden=true mod.GPSRefreshRoadView()assert(not s.on)
            mod.instanceWorldHidden=false mod.db.hideWorldPinsInInstances=true instance=true
            mod.GPSRefreshRoadView()assert(not s.on)
            mod.instanceWorldBrowsing=true
            mod.GPSRefreshRoadView()assert(s.on)
            mod.instanceWorldBrowsing=false
            mod.GPSRefreshRoadView()assert(not s.on)
            instance=false mod.GPSRefreshRoadView()assert(s.on)
            mod.GPSSetRoadsShown(false)assert(not s.on and not mod.GPSRoadsShown())
            mod.GPSSetRoadsShown(true)assert(s.on and mod.GPSRoadsShown())
            assert(s.clears==clears and sets.gps.sentinel)
        """)


if __name__ == '__main__':
    unittest.main()
