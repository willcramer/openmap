"""Exact attachment reuse and cooperative planning without changing road policy."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute('''
            mod={}
            ns={Safe={Value=function(v)return v end}}
            function ns:GetModule()return mod end
            function Fixture(nodes)
                ns.GPSRoadData={version='planner-test',networks={[0]={nodes=nodes}}}
                mod.GPSInvalidateRoads()
            end
            function Point(x,y,id)return {cont=0,wx=x,wy=y,nodeID=id}end
            function EqualRoute(a,b)
                assert(#a==#b,'route point count changed')
                for i,p in ipairs(a)do
                    for _,k in ipairs({'wx','wy','piece','layer','kind','source','onewayDrop','connector','stairTurn'})do
                        assert(p[k]==b[i][k],k..' changed at route point '..i)
                    end
                end
            end
        ''')
        lua.execute((ROOT / 'OpenMap/Map/GPSRoads.lua').read_text(), 'OpenMap', lua.globals().ns)

    def test_reusing_destination_preserves_cost_route_and_owned_data(self):
        self.lua.execute('''
            Fixture({[1]={wx=0,wy=0,links={[2]=true}},[2]={wx=100,wy=0,links={[1]=true,[3]=true}},
                [3]={wx=100,wy=100,links={[2]=true}}})
            local cache={}
            for _,x in ipairs({-10,5,20,40})do
                local plain,reason,plainStats=mod.GPSRoadRoute(Point(x,5),Point(100,90),{})
                assert(plain,reason)
                local cached,why,cachedStats=mod.GPSRoadRoute(Point(x,5),Point(100,90),{destinationCache=cache})
                assert(cached,why)EqualRoute(plain,cached)
                assert(math.abs(plainStats.cost-cachedStats.cost)<1e-9)
            end
            assert(cache.misses==1 and cache.hits==3)
            assert(not ns.GPSRoadData.networks[0].nodes[1].onewayDrop)
        ''')

    def test_cached_one_way_finish_does_not_leak_origin_specific_flags(self):
        self.lua.execute('''
            Fixture({[1]={wx=0,wy=0,oneway={[2]=true},links={[2]=true,[3]=true}},
                [2]={wx=100,wy=0,links={[1]=true}},[3]={wx=0,wy=1000,links={[1]=true}}})
            local cache={}
            local direct=assert(mod.GPSRoadRoute(Point(20,2),Point(80,2),{destinationCache=cache,entrySlack=0}))
            assert(direct[#direct-1].onewayDrop)
            assert(not cache.result.point.onewayDrop,'solve mutated the reusable attachment')
            local plain,reason,stats=mod.GPSRoadRoute(Point(0,1000,3),Point(80,2),{entrySlack=0})
            assert(plain,reason)
            local cached,why,cost=mod.GPSRoadRoute(Point(0,1000,3),Point(80,2),{destinationCache=cache,entrySlack=0})
            assert(cached,why)EqualRoute(plain,cached)
            assert(math.abs(stats.cost-cost.cost)<1e-9 and cache.hits==1)
            assert(not cached[#cached-1].onewayDrop)
        ''')

    def test_target_preferences_and_graph_revisions_invalidate_reuse(self):
        self.lua.execute('''
            Fixture({[1]={wx=0,wy=0,links={[2]=true}},[2]={wx=100,wy=0,links={[1]=true}}})
            local cache={}local context={destinationCache=cache,faction='Horde',offroad='avoid'}
            local function Plan(x)return mod.GPSRoadRoute(Point(-5,2),Point(x or 80,2),context)end
            assert(Plan())assert(Plan())assert(cache.hits==1 and cache.misses==1)
            assert(Plan(70))assert(cache.misses==2)
            context.faction='Alliance'assert(Plan(70))assert(cache.misses==3)
            context.ghost=true assert(Plan(70))assert(cache.misses==4)
            context.offroad='deny'assert(Plan(70))assert(cache.misses==5)
            local before=mod.GPSRoadGraphRevision()
            mod.GPSInvalidateRoads()assert(mod.GPSRoadGraphRevision()==before+1)
            assert(Plan(70))assert(cache.misses==6)
            context.extraRoutes={walk={points={Point(0,0),Point(100,0)}}}context.extraRevision=1
            assert(Plan(70))assert(cache.misses==7)
            assert(Plan(70))assert(cache.hits==2)
            context.extraRevision=2 assert(Plan(70))assert(cache.misses==8)
        ''')

    def test_mutating_floor_membership_invalidates_destination(self):
        self.lua.execute('''
            mod.GPSOtherFloor=function()return false end
            Fixture({[1]={wx=0,wy=0,piece='a',layer=true,links={[2]=true}},
                [2]={wx=100,wy=0,piece='a',layer=true,links={[1]=true}},
                [3]={wx=0,wy=5,piece='b',layer=true,links={[4]=true}},
                [4]={wx=100,wy=5,piece='b',layer=true,links={[3]=true}}})
            local cache={}local target=Point(80,2)
            target.layer,target.floorResolved,target.pieces=true,true,{a=true}
            local from=Point(-5,0)from.layer,from.floorResolved=true,true
            assert(mod.GPSRoadRoute(from,target,{destinationCache=cache}))
            assert(cache.result.point.piece=='a')
            target.pieces.a,target.pieces.b=nil,true
            assert(mod.GPSRoadRoute(from,target,{destinationCache=cache}))
            assert(cache.misses==2 and cache.result.point.piece=='b')
        ''')

    def test_level_callbacks_need_a_revision_and_are_memoized_per_query(self):
        self.lua.execute('''
            Fixture({[1]={wx=0,wy=0,type='offroad',links={[2]=true}},
                [2]={wx=100,wy=0,type='offroad',links={[1]=true}}})
            local cache,counts={},{}
            local context={destinationCache=cache,playerLevel=30,offroad='avoid',aboveLevel='avoid',
                minLevel=function(p)counts[p.nodeID]=(counts[p.nodeID]or 0)+1 return 20 end}
            assert(mod.GPSRoadRoute(Point(-5,2),Point(80,2),context))
            assert(cache.hits==nil and cache.misses==nil)
            assert(counts[1]==1 and counts[2]==1,'level lookup repeated for the same node in a query')
            context.cacheRevision={}
            assert(mod.GPSRoadRoute(Point(-5,2),Point(80,2),context))
            assert(mod.GPSRoadRoute(Point(-5,2),Point(80,2),context))
            assert(cache.hits==1 and cache.misses==1)
            context.cacheRevision={}assert(mod.GPSRoadRoute(Point(-5,2),Point(80,2),context))
            assert(cache.misses==2)
        ''')

    def test_distant_components_are_kept_without_a_fixed_radius_cutoff(self):
        self.lua.execute('''
            Fixture({[1]={wx=0,wy=0,links={[2]=true}},[2]={wx=100,wy=0,links={[1]=true}},
                [3]={wx=5000,wy=0,links={[4]=true}},[4]={wx=5100,wy=0,links={[3]=true}}})
            local entries=assert(mod.GPSRoadEntries(Point(5,1),{}))
            assert(#entries==2)
            local near,far=false,false
            for _,entry in ipairs(entries)do near=near or entry.distance<=100 far=far or entry.distance>4900 end
            assert(near and far,'distant disconnected component lost its nearest entry')
        ''')

    def test_cold_and_warm_plans_can_yield_without_partial_results_or_route_changes(self):
        self.lua.execute('''
            local nodes={}
            for i=1,500 do nodes[i]={wx=i*10,wy=0,links={}}
                if i>1 then nodes[i].links[i-1]=true end
                if i<500 then nodes[i].links[i+1]=true end
            end
            Fixture(nodes)
            local yielded=0
            local function Slice()yielded=yielded+1 coroutine.yield()end
            local result,reason,stats
            local co=coroutine.create(function()
                result,reason,stats=mod.GPSRoadRoute(Point(10,2),Point(5000,2),{checkpoint=Slice,destinationCache={}})
            end)
            local frames=0
            repeat
                local ok,err=coroutine.resume(co)assert(ok,err)frames=frames+1
                if coroutine.status(co)~='dead'then assert(result==nil,'partial route escaped')end
            until coroutine.status(co)=='dead'
            assert(result,reason)assert(frames>50 and yielded>50,'planning did not yield across its expensive stages')
            local plain,why,cost=mod.GPSRoadRoute(Point(10,2),Point(5000,2),{})
            assert(plain,why)EqualRoute(plain,result)assert(math.abs(stats.cost-cost.cost)<1e-9)
        ''')


if __name__ == '__main__':
    unittest.main()
