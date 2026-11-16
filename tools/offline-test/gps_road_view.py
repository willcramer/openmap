"""The optional road layer stays bounded, view-culled and separate from navigation."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]


class RoadViewTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
            mod={defaults={},db={gpsShowRoads=true,gpsRoutes={}}}
            roadsRevision=0
            function mod.GPSRoadsRevision()return roadsRevision end
            function mod.GPSRecordedPoint(sample)
                if sample[1]~=900001 then return end
                return {cont=0,wx=sample[2],wy=sample[3],piece=sample.piece,layer=sample.layer}
            end
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

    def test_source_nodes_are_exact_positions_not_interpolated_road_dots(self):
        self.lua.execute("""
            mod.GPSRefreshRoadView()
            local nodes=sets.gpsroadnodes
            assert(nodes.on and #nodes.pins==2)
            assert(nodes.pins[1].u==0 and nodes.pins[2].u==1)
            for _,pin in ipairs(nodes.pins)do
                assert(pin.v==.5 and pin.look.size==6 and pin.mouse==false)
            end
            assert(#sets.gpsroads.pins==100)
            local n=ns.GPSRoadData.networks[0].nodes
            assert(n[1].u==nil and n[2].u==nil,'view modified source coordinates')
            local pins,clears=nodes.pins,nodes.clears
            mod.GPSRefreshRoadView()
            assert(nodes.pins==pins and nodes.clears==clears)
            viewU=5.5 mod.GPSRefreshRoadView()
            assert(#nodes.pins==2 and nodes.pins[1].u==5 and nodes.pins[2].u==6)
        """)

    def test_isolated_and_special_nodes_remain_visible_without_invented_links(self):
        self.lua.execute("""
            ns.GPSRoadData={networks={[0]={nodes={
                [1]={wx=.1,wy=.2,links={}},
                [2]={wx=.3,wy=.2,tower={top=3},links={[3]=true}},
                [3]={wx=.4,wy=.2,links={[2]=true}},
                [4]={wx=.5,wy=.2,layer=true,links={[5]=true}},
                [5]={wx=.6,wy=.2,links={[4]=true}}
            }}}}
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroadnodes.pins==5 and #sets.gpsroads.pins==0)
        """)

    def test_saved_trails_refresh_on_save_delete_and_profile_change(self):
        self.lua.execute("""
            mod.GPSRefreshRoadView()
            local s=sets.gpsroadnodes local clears=s.clears
            mod.db.gpsRoutes['New road']={points={{900001,.2,.3},{900001,.4,.3}}}
            roadsRevision=roadsRevision+1
            mod.GPSRefreshRoadView()
            assert(s.clears==clears+1 and #s.pins==4)
            local recorded=0
            for _,pin in ipairs(s.pins)do
                if pin.look.size==7 then
                    recorded=recorded+1
                    assert(pin.v==.3 and (pin.u==.2 or pin.u==.4))
                    assert(pin.look.color[1]==1 and pin.look.color[2]==.45)
                end
            end
            assert(recorded==2)
            local orange=0
            for _,pin in ipairs(sets.gpsroads.pins)do
                if pin.look.color[2]==.45 then orange=orange+1 assert(pin.v==.3)end
            end
            assert(orange>0,'saved links were not displayed')
            local raw=mod.db.gpsRoutes['New road'].points
            assert(raw[1].wx==nil and raw[2].u==nil,'view modified saved samples')
            mod.db.gpsRoutes['New road']=nil roadsRevision=roadsRevision+1
            mod.GPSRefreshRoadView()assert(#s.pins==2)
            mod.db.gpsRoutes={['Profile road']={points={{900001,.6,.7},{900001,.8,.7}}}}
            mod.GPSRefreshRoadView()assert(#s.pins==4)
        """)

    def test_recorded_floor_changes_invalid_points_and_large_gaps_do_not_make_links(self):
        self.lua.execute("""
            ns.GPSRoadData={networks={}}
            mod.db.gpsRoutes={
                floor={points={{900001,.1,.2,piece='a:0'},{900001,.2,.2,piece='a:1'}}},
                layer={points={{900001,.1,.3,layer=true},{900001,.2,.3}}},
                invalid={points={{900001,.1,.4},{-1,.2,.4},{900001,.3,.4}}},
                gap={points={{900001,.1,.5},{900001,201,.5}}}
            }
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroads.pins==0,'unwalked or cross-floor connection was drawn')
            assert(#sets.gpsroadnodes.pins==7)
        """)

    def test_manual_links_selected_nodes_and_deletion_refresh_without_navigation_changes(self):
        self.lua.execute("""
            ns.MapStitch.FromYards=function(cont,x,y)if cont==0 then return x/1000,y/1000 end end
            local base={cont=0,wx=100,wy=500,links={}}
            ns.GPSRoadData={networks={[0]={nodes={[1]=base}}}}
            local a,b={cont=0,wx=500,wy=500},{cont=0,wx=900,wy=500}
            manual={nodes={['m:1']=a,['m:2']=b},links={
                {a='b:0:1',b='m:1'},{a='m:1',b='m:2'}},revision=1}
            selected='m:1'
            function mod.GPSRoadEditSnapshot()return manual end
            function mod.GPSRoadEditPoint(ref)return ref=='b:0:1'and base or manual.nodes[ref]end
            function mod.GPSRoadSelected()return selected end
            sets.gps={sentinel=true}
            mod.GPSRefreshRoadView()
            local layer=sets.gpsroadnodes
            assert(#layer.pins==3 and sets.gps.sentinel)
            local cyan,white,gold=0,0,0
            for _,pin in ipairs(layer.pins)do
                assert(pin.mouse==false and pin.v==.5)
                if pin.look.size==10 then
                    white=white+1 assert(pin.u==.5 and pin.look.color[1]==1 and pin.look.color[2]==1)
                elseif pin.look.color[1]==.25 then cyan=cyan+1 assert(pin.u==.9)
                else gold=gold+1 assert(pin.u==.1)end
            end
            assert(cyan==1 and white==1 and gold==1)
            local links=0
            for _,pin in ipairs(sets.gpsroads.pins)do
                if pin.look.color[1]==.25 then
                    links=links+1 assert(pin.v==.5 and pin.u>=.1 and pin.u<=.9)
                end
            end
            assert(links>50,'explicit long manual links were clipped by recording gap limits')
            local pins,clears=layer.pins,layer.clears
            mod.GPSRefreshRoadView()assert(layer.pins==pins and layer.clears==clears)
            selected='b:0:1' mod.GPSRefreshRoadView()
            assert(layer.clears==clears+1 and #layer.pins==3)
            assert(layer.pins[#layer.pins].look.size==10 and layer.pins[#layer.pins].u==.1)
            manual.nodes['m:1']=nil manual.links={} manual.revision=2 selected=nil
            mod.GPSRefreshRoadView()
            assert(#layer.pins==2 and #sets.gpsroads.pins==0 and sets.gps.sentinel)
            assert(base.u==nil and a.u==nil and b.u==nil,'road display mutated stored positions')
        """)

    def test_manual_display_rejects_missing_cross_continent_and_known_floor_links(self):
        self.lua.execute("""
            ns.GPSRoadData={networks={}}
            manual={nodes={
                ['m:1']={cont=0,wx=.1,wy=.3,layer=1},
                ['m:2']={cont=0,wx=.9,wy=.3,layer=2},
                ['m:3']={cont=1,wx=.5,wy=.3},
                ['m:4']={cont=0,wx=.8,wy=.3,layer=1,ambiguous=true}
            },links={{a='m:1',b='m:2'},{a='m:1',b='m:3'},
                {a='m:1',b='missing'},{a='m:1',b='m:4'}},revision=1}
            function mod.GPSRoadEditSnapshot()return manual end
            function mod.GPSRoadEditPoint(ref)return manual.nodes[ref]end
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroadnodes.pins==3 and #sets.gpsroads.pins==0)
            manual={nodes={},links={},revision=0}
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroadnodes.pins==0,'profile replacement retained manual nodes')
        """)

    def test_selected_manual_node_survives_dense_budget_and_hiding_finishes_editing(self):
        self.lua.execute("""
            ns.GPSRoadData={networks={}}
            manual={nodes={},links={},revision=1}
            for i=1,1500 do manual.nodes['m:'..i]={cont=0,wx=i/1501,wy=.5}end
            local selected='m:1499'
            local editing=true
            function mod.GPSRoadEditSnapshot()return manual end
            function mod.GPSRoadEditPoint(ref)return manual.nodes[ref]end
            function mod.GPSRoadSelected()return selected end
            function mod.GPSRoadEditing()return editing end
            function mod.GPSSetRoadEditing(on)editing=on selected=nil end
            mod.GPSRefreshRoadView()
            local nodes=sets.gpsroadnodes.pins
            assert(#nodes==500 and nodes[#nodes].look.size==10 and nodes[#nodes].u==1499/1501)
            mod.GPSSetRoadsShown(false)
            assert(not editing and selected==nil and not sets.gpsroadnodes.on)
            mod.GPSSetRoadsShown(true)
            assert(#sets.gpsroadnodes.pins==500)
            for _,pin in ipairs(sets.gpsroadnodes.pins)do assert(pin.look.size==7)end
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
            local nodes=sets.gpsroadnodes.pins
            assert(#nodes==500)
            low,high=false,false
            for _,p in ipairs(nodes)do
                assert(p.u==0 or p.u==1,'node display interpolated a position')
                low=low or p.v<.2 high=high or p.v>.8
            end
            assert(low and high,'node budget only showed one end of the network')
            halfU=.01 halfV=.01 viewU=0
            mod.GPSRefreshRoadView()
            assert(#sets.gpsroadnodes.pins>0 and #sets.gpsroadnodes.pins<500)
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
            local nodes=sets.gpsroadnodes
            shown=false mod.GPSRefreshRoadView()assert(not s.on and not nodes.on)
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

    def test_preference_changes_refresh_ui_without_altering_navigation(self):
        self.lua.execute("""
            local gps,panel,options=0,0,0
            function mod.GPSRefreshPanel()gps=gps+1 mod.GPSRefreshRoadView()end
            function mod:RefreshPanel()panel=panel+1 end
            function ns.NotifyOptions()options=options+1 end
            mod.GPSStatus=function()return {active=true,route='unchanged'}end
            sets.gps={sentinel=true}
            mod.GPSSetRoadsShown(false)
            mod.GPSSetRoadsShown(true)
            assert(gps==2 and panel==2 and options==2)
            assert(mod.GPSStatus().active and mod.GPSStatus().route=='unchanged'and sets.gps.sentinel)
        """)


if __name__ == '__main__':
    unittest.main()
