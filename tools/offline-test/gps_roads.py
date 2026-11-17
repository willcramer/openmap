"""Bundled graph topology, travel constraints and generated Forever road coverage.

Run: python -P tools/offline-test/gps_roads.py
"""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]


class GPSRoadTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            mod = {}
            ns = { Safe = { Value = function(v) return v end } }
            function ns:GetModule() return mod end
            function mod.GPSRoadPoint(raw, cont)
                local p = {}
                for k,v in pairs(raw) do p[k]=v end
                p.cont,p.map = cont,raw.map or 1
                p.x,p.y,p.u,p.v = raw.wx/10000,raw.wy/10000,raw.wx/10000,raw.wy/10000
                return p
            end
            function network(nodes)
                ns.GPSRoadData={version='test',networks={[0]={nodes=nodes}}}
            end
            function point(x,y,piece,layer)
                return {wx=x,wy=y,cont=0,map=1,piece=piece,layer=layer}
            end
            function at(id)
                local p = {}
                for k,v in pairs(ns.GPSRoadData.networks[0].nodes[id]) do p[k]=v end
                p.cont,p.nodeID=0,id
                return p
            end
            function has(route,id)
                for _,p in ipairs(route) do if p.nodeID==id then return true end end
                return false
            end
        """)
        self.lua.execute((ROOT / "OpenMap/Map/GPSRoads.lua").read_text(), "OpenMap", self.lua.globals().ns)

    def test_hairpin_stays_on_the_explicit_detour(self):
        self.lua.execute("""
            network({
                [1]={wx=0,wy=0,links={[2]=true}},
                [2]={wx=0,wy=100,links={[1]=true,[3]=true}},
                [3]={wx=20,wy=100,links={[2]=true,[4]=true}},
                [4]={wx=20,wy=0,links={[3]=true}},
            })
            local route,reason,stats=mod.GPSRoadRoute(at(1),at(4))
            assert(route,reason)
            assert(has(route,2) and has(route,3))
            assert(math.abs(stats.length-220)<.001,stats.length)
        """)

    def test_close_unconnected_banks_are_not_joined(self):
        self.lua.execute("""
            network({
                [1]={wx=0,wy=0,links={[2]=true}},[2]={wx=0,wy=100,links={[1]=true}},
                [3]={wx=10,wy=0,links={[4]=true}},[4]={wx=10,wy=100,links={[3]=true}},
            })
            local route,reason,stats=mod.GPSRoadRoute(at(1),at(4))
            assert(route,reason)
            assert(route[1].connector and stats.startDistance==10 and stats.cost==120)
            assert(not mod.GPSRoadCanWalk(0,1,3),'approach was stored as a graph bridge')
            route,reason=mod.GPSRoadRoute(at(1),at(4),{entrySlack=0})
            assert(not route and reason=='disconnected',reason)
        """)

    def test_one_way_and_partial_segment_attachments(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,links={[2]=true},oneway={[2]=true}},
                [2]={wx=100,wy=0,links={[1]=true}}})
            local route,reason,stats=mod.GPSRoadRoute(point(20,2),point(80,2))
            assert(route,reason)
            assert(math.abs(stats.length-64)<.001,stats.length)
            assert(route[#route-1].onewayDrop and route[#route-1].kind=='drop')
            route,reason=mod.GPSRoadRoute(point(80,2),point(20,2))
            assert(not route and reason=='disconnected',reason)
            assert(mod.GPSRoadStats().edges==1)
            route=mod.GPSRoadRoute(at(1),at(2))
            assert(route[#route].onewayDrop and route[#route].kind=='drop')
        """)

    def test_arbitrary_pin_tail_is_weighted_without_a_coverage_cap(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,links={[2]=true}},[2]={wx=10000,wy=0,links={[1]=true}}})
            for _,distance in ipairs({199,201,600,1000,1500}) do
                local route,reason,stats=mod.GPSRoadRoute(at(1),point(5000,distance),{offroad='avoid'})
                assert(route,reason)
                local tail=2*(100+(distance-100)*4)
                assert(math.abs(stats.cost-(5000+tail))<1e-7,stats.cost)
                assert(stats.finishDistance==distance and stats.connectorDistance==distance)
                assert(route[#route].connector and route[#route].kind=='offroad')
            end
        """)

    def test_same_floor_overlapping_room_boxes_resolve_without_choosing_a_room(self):
        self.lua.execute("""
            mod.GPSOtherFloor=function() return false end
            network({[1]={wx=0,wy=0,piece='7:1',layer=true,links={[2]=true}},
                [2]={wx=100,wy=0,piece='7:2',layer=true,links={[1]=true}}})
            local target=point(50,10)
            target.ambiguous,target.pieces=true,{['7:1']=true,['7:2']=true}
            target.candidates={
                {piece='7:1',building=7,inside=true,layer=true,minZ=0,maxZ=10},
                {piece='7:2',building=7,inside=true,layer=true,minZ=2,maxZ=12},
            }
            local route,reason=mod.GPSRoadRoute(at(1),target)
            assert(route,reason)
            assert(route[#route].floorResolved and not route[#route].piece)
            assert(not target.floorResolved,'caller context mutated')
            target.candidates[2].minZ,target.candidates[2].maxZ=20,30
            route,reason=mod.GPSRoadRoute(at(1),target)
            assert(not route and reason=='floor',reason)
            target.candidates[2].minZ,target.candidates[2].maxZ=nil,nil
            route,reason=mod.GPSRoadRoute(at(1),target)
            assert(not route and reason=='floor',reason)
        """)

    def test_pin_prefers_its_room_road_inside_entry_radius(self):
        self.lua.execute("""
            mod.GPSOtherFloor=function() return false end
            network({[1]={wx=80,wy=0,piece='roomA',layer=true,links={[2]=true}},
                [2]={wx=100,wy=0,piece='roomA',layer=true,links={[1]=true}},
                [3]={wx=0,wy=0,piece='roomB',layer=true,links={[4]=true}},
                [4]={wx=20,wy=0,piece='roomB',layer=true,links={[3]=true}}})
            local route,reason,stats=mod.GPSRoadRoute(at(1),point(0,0,'roomA',true))
            assert(route,reason)
            assert(math.abs(stats.cost-160)<1e-7,stats.cost)
            assert(not has(route,3) and not has(route,4))
        """)

    def test_enemy_roads_are_filtered_and_warning_mode_is_explicit(self):
        self.lua.execute("""
            network({
                [1]={wx=0,wy=0,links={[2]=true,[3]=true}},
                [2]={wx=100,wy=0,type='horde',links={[1]=true,[4]=true}},
                [3]={wx=100,wy=100,links={[1]=true,[4]=true}},
                [4]={wx=200,wy=0,links={[2]=true,[3]=true}},
            })
            local route,reason=mod.GPSRoadRoute(at(1),at(4),{faction='Alliance'})
            assert(route and has(route,3) and not has(route,2),reason)
            network({[1]={wx=0,wy=0,links={[2]=true}},
                [2]={wx=100,wy=0,type='horde',links={[1]=true,[3]=true}},
                [3]={wx=200,wy=0,links={[2]=true}}})
            route,reason=mod.GPSRoadRoute(at(1),at(3),{faction='Alliance'})
            assert(not route and reason=='blocked',reason)
            local stats
            route,reason,stats=mod.GPSRoadRoute(at(1),at(3),{faction='Alliance',allowEnemy=true})
            assert(route and stats.enemy and route[2].enemy,reason)
        """)

    def test_offroad_level_and_swimming_constraints(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,links={[2]=true}},
                [2]={wx=100,wy=0,type='offroad',links={[1]=true,[3]=true}},
                [3]={wx=200,wy=0,links={[2]=true}}})
            local route,reason=mod.GPSRoadRoute(at(1),at(3),{offroad='deny'})
            assert(not route and reason=='blocked',reason)
            route,reason=mod.GPSRoadRoute(at(1),at(3),{playerLevel=10,aboveLevel='deny',
                minLevel=function(p) return p.type=='offroad' and 20 or nil end})
            assert(not route and reason=='blocked',reason)
            ns.GPSRoadData.networks[0].nodes[2].type='swim'
            mod.GPSInvalidateRoads()
            route,reason=mod.GPSRoadRoute(at(1),at(3))
            assert(route and route[2].kind=='swim',reason)
            route,reason=mod.GPSRoadRoute(at(1),at(3),{swim='deny'})
            assert(not route and reason=='blocked',reason)
        """)

    def test_no_start_is_traversable_but_not_an_attachment(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,links={[2]=true,[5]=true}},
                [2]={wx=100,wy=0,nostart=true,links={[1]=true,[3]=true}},
                [3]={wx=200,wy=0,links={[2]=true}},
                [5]={wx=-100,wy=0,links={[1]=true}}})
            local route,reason=mod.GPSRoadRoute(at(1),at(3),{attachLimit=10})
            assert(route and has(route,2),reason)
            route,reason=mod.GPSRoadRoute(at(2),at(3),{attachLimit=10})
            assert(not route and reason=='no-coverage',reason)
        """)

    def test_overlapping_floors_and_unknown_height_do_not_shortcut(self):
        self.lua.execute("""
            network({
                [1]={wx=0,wy=0,piece='lower',layer=true,minZ=0,maxZ=5,links={[2]=true}},
                [2]={wx=100,wy=0,piece='lower',layer=true,minZ=0,maxZ=5,links={[1]=true}},
                [3]={wx=0,wy=0,piece='upper',layer=true,minZ=20,maxZ=25,links={[4]=true}},
                [4]={wx=100,wy=0,piece='upper',layer=true,minZ=20,maxZ=25,links={[3]=true}},
            })
            local route,reason=mod.GPSRoadRoute(at(1),at(4))
            assert(not route and reason=='disconnected',reason)
            local start=point(0,0)
            start.ambiguous=true
            route,reason=mod.GPSRoadRoute(start,at(4))
            assert(not route and reason=='floor',reason)
            start=point(0,0,'lower',true) start.z=23
            route,reason=mod.GPSRoadRoute(start,at(2),{attachLimit=20})
            assert(not route and reason=='floor',reason)
        """)

    def test_spiral_and_side_exit_turns_expand_in_both_directions(self):
        self.lua.execute("""
            network({
                [1]={wx=10,wy=0,piece='bottom',minZ=0,maxZ=5,links={[2]=true},tower={x=0,y=0,r=10,top=2,turns=1,exits={[3]=2}}},
                [2]={wx=10,wy=0,piece='middle',layer=true,links={[1]=true,[3]=true}},
                [3]={wx=10,wy=0,piece='top',layer=true,towerOf=1,links={[2]=true}},
            })
            local route,reason,stats=mod.GPSRoadRoute(at(1),at(3))
            assert(route and #route>25,reason)
            assert(stats.length>120,stats.length)
            for i=2,#route do
                if route[i].stairTurn then
                    assert(route[i].stairTurn>=route[i-1].stairTurn)
                    assert(route[i].stairAngleSign==1 and route[i].kind=='stairs')
                    if not route[i].nodeID then assert(not route[i].minZ and not route[i].maxZ,'spiral inherited the foot room height') end
                end
            end
            route,reason=mod.GPSRoadRoute(at(3),at(1),{tops={[3]=true}})
            assert(route and #route>25,reason)
            for i=2,#route do
                assert(route[i].stairTurn<=route[i-1].stairTurn)
            end
        """)

    def test_one_way_drop_cannot_be_entered_from_its_lower_end(self):
        self.lua.execute("""
            network({
                [1]={wx=0,wy=0,links={[2]=true},oneway={[2]=true},nostart=true},
                [2]={wx=20,wy=0,links={[1]=true,[3]=true}},
                [3]={wx=40,wy=0,links={[2]=true}},
            })
            local route,reason=mod.GPSRoadRoute(at(2),at(1),{attachLimit=30})
            assert(not route and reason=='disconnected',reason)
            route,reason=mod.GPSRoadRoute(point(15,1),at(1),{attachLimit=30})
            assert(not route and reason=='disconnected',reason)
        """)

    def test_elevator_warning_survives_faction_annotation(self):
        self.lua.execute("""
            network({
                [1]={wx=0,wy=0,type='horde',links={[2]=true}},
                [2]={wx=100,wy=0,type='horde',elevator=true,links={[1]=true,[3]=true}},
                [3]={wx=200,wy=0,type='horde',links={[2]=true}},
            })
            local route,reason=mod.GPSRoadRoute(at(1),at(3),{faction='Horde'})
            assert(route,reason)
            assert(route[2].kind=='elevator' and route[2].type=='horde')
            route,reason=mod.GPSRoadRoute(at(1),at(3),{faction='Alliance'})
            assert(not route and reason=='blocked',reason)
        """)

    def test_coarse_stair_winding_uses_the_exit_actual_bearing(self):
        self.lua.execute("""
            network({
                [1]={wx=10,wy=0,piece='bottom',links={[2]=true},tower={x=0,y=0,r=10,top=2,turns=1.75,cw=true}},
                [2]={wx=-10,wy=0,piece='top',layer=true,links={[1]=true}},
            })
            local route,reason=mod.GPSRoadRoute(at(1),at(2))
            assert(route,reason)
            local last,previous=route[#route],route[#route-1]
            assert(math.abs(last.stairTurn-1.5)<.001,last.stairTurn)
            assert(last.stairAngleSign==-1 and last.stairTurnsConfigured==1.75)
            assert(math.sqrt((last.wx-previous.wx)^2+(last.wy-previous.wy)^2)<5,
                'the last fractional turn jumped to the real exit')
        """)

    def test_user_trails_bridge_a_gap_without_joining_another_floor(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,links={[2]=true}},[2]={wx=100,wy=0,links={[1]=true}},
                [3]={wx=200,wy=0,links={[4]=true}},[4]={wx=300,wy=0,links={[3]=true}}})
            local extra={bridge={points={point(100,0),point(150,0),point(200,0)}}}
            local route,reason=mod.GPSRoadRoute(at(1),at(4),{extraRoutes=extra,attachLimit=20})
            assert(route,reason)
            assert(mod.GPSRoadStats().nodes==4,'extra routes changed bundled data')
            for _,p in ipairs(extra.bridge.points) do p.piece='upper' p.layer=true end
            route,reason=mod.GPSRoadRoute(at(1),at(4),{extraRoutes=extra,extraRevision=1,attachLimit=20})
            assert(not route and reason=='disconnected',reason)
        """)

    def test_all_shipped_nodes_are_retained_and_real_continents_route(self):
        self.lua.execute((ROOT / "OpenMap/Data/Forever/Roads.lua").read_text(), "OpenMap", self.lua.globals().ns)
        self.lua.execute("""
            local stats=mod.GPSRoadStats()
            assert(stats.nodes==8944,stats.nodes)
            assert(stats.networks[0].nodes==4467 and stats.networks[1].nodes==4134)
            assert(stats.networks[2991].nodes==341 and stats.networks[2806].nodes==2)
            local cases={
                {cont=0,fromMap=1434,toMap=1453,faction='Alliance'},
                {cont=1,fromMap=1411,toMap=1454,faction='Horde'},
                {cont=2991,fromMap=2665,toMap=2665,faction='Alliance'},
            }
            for _,case in ipairs(cases) do
                local nodes=ns.GPSRoadData.networks[case.cont].nodes
                local first,last
                for id,p in pairs(nodes) do
                    if p.map==case.fromMap and not p.layer and not p.piece and not p.nostart then first=not first and id or math.min(first,id) end
                    if p.map==case.toMap and not p.layer and not p.piece then last=not last and id or math.max(last,id) end
                end
                assert(first and last,'no real endpoints')
                local from,to={},{}
                for k,v in pairs(nodes[first]) do from[k]=v end
                for k,v in pairs(nodes[last]) do to[k]=v end
                from.cont,to.cont=case.cont,case.cont
                local route,reason,result=mod.GPSRoadRoute(from,to,{faction=case.faction,allowUnknownFloor=true})
                assert(route,case.cont..':'..tostring(reason))
                assert(result.source=='bundled' and result.length>0)
            end
        """)


    def test_numeric_underground_layer_does_not_require_a_building_piece(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,layer=1458,links={[2]=true}},
                [2]={wx=100,wy=0,layer=1458,links={[1]=true}}})
            local route,reason=mod.GPSRoadRoute(at(1),at(2))
            assert(route,reason)
            local outside=point(0,0)
            outside.layer=false
            route,reason=mod.GPSRoadRoute(outside,at(2))
            assert(not route and reason=='floor',reason)
        """)

    def test_unknown_faction_and_conflicting_one_way_flags_are_blocked(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,type='alliance',links={[2]=true}},
                [2]={wx=100,wy=0,type='alliance',links={[1]=true}}})
            local route,reason=mod.GPSRoadRoute(at(1),at(2))
            assert(not route and reason=='blocked',reason)
            network({[1]={wx=0,wy=0,oneway={[2]=true},links={[2]=true}},
                [2]={wx=100,wy=0,oneway={[1]=true},links={[1]=true}}})
            assert(not mod.GPSRoadCanWalk(0,1,2) and not mod.GPSRoadCanWalk(0,2,1))
        """)

    def test_same_floor_rooms_prefer_the_current_piece_only_within_slack(self):
        self.lua.execute("""
            mod.GPSOtherFloor=function() return false end
            network({
                [1]={wx=20,wy=0,piece='roomA',layer=true,links={[2]=true}},
                [2]={wx=100,wy=0,piece='roomA',layer=true,links={[1]=true,[4]=true}},
                [3]={wx=0,wy=0,piece='roomB',layer=true,links={[4]=true}},
                [4]={wx=0,wy=100,piece='roomB',layer=true,links={[2]=true,[3]=true}},
            })
            local route,reason,stats=mod.GPSRoadRoute(point(0,0,'roomA',true),at(4))
            assert(route and stats.startDistance==20,reason)
            ns.GPSRoadData.networks[0].nodes[1].wx=30
            mod.GPSInvalidateRoads()
            route,reason,stats=mod.GPSRoadRoute(point(0,0,'roomA',true),at(4))
            assert(route and stats.startDistance==0,reason)
        """)

    def test_source_preference_factors_and_ghost_override(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,links={[2]=true}},
                [2]={wx=100,wy=0,type='offroad',links={[1]=true,[3]=true}},
                [3]={wx=200,wy=0,links={[2]=true}}})
            for mode,expected in pairs({shortest=200,avoid=800,needed=200000}) do
                local route,reason,stats=mod.GPSRoadRoute(at(1),at(3),{offroad=mode})
                assert(route and math.abs(stats.cost-expected)<.001,mode..':'..tostring(reason))
            end
            local level=function() return 99 end
            local route,reason,stats=mod.GPSRoadRoute(at(1),at(3),{offroad='shortest',aboveLevel='avoid',minLevel=level,playerLevel=1})
            assert(route and stats.cost==200000 and route[2].highLevel,reason)
            route,reason=mod.GPSRoadRoute(at(1),at(3),{aboveLevel='never',minLevel=level,playerLevel=1})
            assert(not route and reason=='blocked',reason)
            route,reason,stats=mod.GPSRoadRoute(at(1),at(3),{offroad='deny',aboveLevel='never',minLevel=level,playerLevel=1,ghost=true})
            assert(route and stats.cost==200 and not route[2].highLevel,reason)
            ns.GPSRoadData.networks[0].nodes[2].type='horde'
            mod.GPSInvalidateRoads()
            route,reason,stats=mod.GPSRoadRoute(at(1),at(3),{faction='Alliance',allowEnemy=true})
            assert(route and stats.cost==200000 and stats.firstEnemy,reason)
            route,reason,stats=mod.GPSRoadRoute(at(1),at(3),{faction='Alliance',ghost=true})
            assert(route and stats.cost==200 and not stats.enemy and not route[2].enemy,reason)
        """)

    def test_empty_room_candidates_do_not_reject_outdoor_piece_nodes(self):
        self.lua.execute("""
            network({[1]={wx=0,wy=0,piece='outdoor',links={[2]=true}},
                [2]={wx=100,wy=0,piece='outdoor',links={[1]=true}}})
            local from=point(0,0)
            from.pieces={}
            local route,reason=mod.GPSRoadRoute(from,at(2))
            assert(route,reason)
        """)

    def test_authored_top_anchor_proves_an_ambiguous_start_landing(self):
        self.lua.execute("""
            network({
                [1]={wx=10,wy=0,piece='bottom',links={[2]=true},tower={x=0,y=0,r=10,top=2,turns=1.5}},
                [2]={wx=-10,wy=0,piece='top',layer=true,links={[1]=true,[3]=true}},
                [3]={wx=-100,wy=0,piece='top',layer=true,links={[2]=true}},
            })
            ns.GPSRoadAnchors={networks={[0]={{node=2,wx=-10,wy=0}}}}
            local from=point(-10,0)
            from.ambiguous=true
            local tops=mod.GPSRoadTopsAt(from)
            assert(tops and tops[2] and not tops[1])
            local route,reason=mod.GPSRoadRoute(from,at(3),{tops=tops})
            assert(route and route[1].nodeID==2,reason)
            assert(not mod.GPSRoadTopsAt(point(-10,16)))
        """)


if __name__ == "__main__":
    unittest.main()
