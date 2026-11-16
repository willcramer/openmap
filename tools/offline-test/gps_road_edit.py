"""Persistent explicit road edits through the full addon and real road planner."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('road_edit_fixture', HERE / 'gps_bundled_integration.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class RoadEditorTests(unittest.TestCase):
    def setUp(self):
        fixture.BundledGPSIntegrationTests.setUp(self)
        self.lua.execute('''
            ns.GPSRoadData=nil
            mod.GPSInvalidateRoads()
            function EditedPoint(ref)
                local p=mod.GPSRoadEditPoint(ref)
                -- Known editor endpoints request node-attachment semantics;
                -- arbitrary coordinate pins may use a labeled direct approach.
                p.nodeID=p.nodeID or ref
                return p
            end
            function EditedPlan(a,b,opts)
                opts=opts or {}
                opts.manualRoads=mod.GPSRoadEditSnapshot()
                opts.entrySlack,opts.attachLimit=0,1
                return mod.GPSRoadRoute(EditedPoint(a),EditedPoint(b),opts)
            end
            function Uses(route,ref)
                for _,p in ipairs(route or {})do if p.editRef==ref then return true end end
                return false
            end
        ''')

    def test_manual_only_explicit_route_works_without_bundled_data_or_walking(self):
        self.lua.execute('''
            mod.GPSSetRoadEditing(true)
            local a=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            local b=assert(mod.GPSRoadEditAdd(900001,.1,.4,a))
            local c=assert(mod.GPSRoadEditAdd(900001,.4,.4,b))
            assert(mod.GPSRoadSelected()==c and mod.GPSRoadEditing())
            local route,reason,stats=EditedPlan(a,c)
            assert(route,reason)
            assert(Uses(route,b)and math.abs(stats.length-600)<.001)
            assert(mod.GPSStart(900001,.4,.4))
            assert(mod.GPSStatus().active and Uses(mod.GPSStatus().route,b))
            assert(mod.GPSRoadEditDisconnect(b,c))
            route,reason=EditedPlan(a,c)
            assert(not route and (reason=='disconnected'or reason=='no-coverage'),reason)
            assert(not mod.GPSRoadEditLinked(b,c))
        ''')

    def test_proximity_and_saved_walks_never_create_manual_junctions(self):
        self.lua.execute('''
            local a=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            local b=assert(mod.GPSRoadEditAdd(900001,.5,.1))
            local near=assert(mod.GPSRoadEditAdd(900001,.101,.1))
            assert(#mod.GPSRoadEditSnapshot().links==0)
            local route,reason=EditedPlan(a,b)
            assert(not route and (reason=='disconnected'or reason=='no-coverage'),reason)
            mod.db.gpsRoutes['Nearby walk']={points={{900001,.1,.1},{900001,.5,.1}}}
            local extra={walk={points={EditedPoint(a),EditedPoint(b)}}}
            route,reason=EditedPlan(near,b,{extraRoutes=extra})
            assert(not route and (reason=='disconnected'or reason=='no-coverage'),'a nearby recording joined an unlinked manual node')
            assert(mod.GPSRoadEditConnect(a,b))
            assert(EditedPlan(a,b))
            assert(#mod.GPSRoadEditSnapshot().links==1)
        ''')

    def test_custom_links_bridge_bundled_components_without_mutating_source(self):
        self.lua.execute('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,links={[2]=true}},
                [2]={wx=100,wy=200,map=900001,links={[1]=true}},
                [3]={wx=500,wy=100,map=900001,links={[4]=true}},
                [4]={wx=500,wy=200,map=900001,links={[3]=true}}
            })
            local nodes=ns.GPSRoadData.networks[0].nodes
            local a='b:0:1' local b='b:0:3'
            local middle=assert(mod.GPSRoadEditAdd(900001,.3,.1,a))
            assert(mod.GPSRoadEditConnect(middle,b))
            local route,reason,stats=EditedPlan(a,b)
            assert(route,reason)
            assert(Uses(route,middle)and math.abs(stats.length-400)<.001)
            assert(not nodes[1].links[3]and nodes[1].links[2]and nodes[3].links[4])
            assert(not mod.GPSRoadEditDelete(a))
            assert(not mod.GPSRoadEditDisconnect('b:0:1','b:0:2'))
            assert(mod.GPSRoadEditDelete(middle))
            assert(#mod.GPSRoadEditSnapshot().links==0 and nodes[1].links[2])
            route,reason=EditedPlan(a,b)
            assert(not route and (reason=='disconnected'or reason=='no-coverage'),reason)
        ''')

    def test_link_rejections_and_add_connected_failure_are_atomic(self):
        self.lua.execute('''
            local a=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            local b=assert(mod.GPSRoadEditAdd(2521,.2,.1))
            assert(not mod.GPSRoadEditConnect(a,a))
            assert(not mod.GPSRoadEditConnect(a,b))
            local before=mod.GPSRoadEditSnapshot()
            local nextID=mod.db.gpsManualRoads.nextID
            assert(not mod.GPSRoadEditAdd(2521,.3,.1,a))
            assert(mod.db.gpsManualRoads.nextID==nextID and mod.GPSRoadEditSnapshot()==before)
            assert(not mod.GPSRoadEditConnect(a,'m:99999'))
            assert(not mod.GPSRoadEditAdd(900001,0/0,.2))
            assert(not mod.GPSRoadEditAdd(900001,1.1,.2))
            assert(not mod.GPSRoadEditAdd(900001,.2,.2,'b:0:99999'))
            assert(#mod.GPSRoadEditSnapshot().links==0)
        ''')

    def test_ambiguous_rooms_and_cross_floor_connections_are_rejected(self):
        self.lua.execute('''
            mod.GPSRoomContext=function(_,x)
                if x>600 then return {ambiguous=true,inside=true}end
                return {piece=x<300 and '7:0'or '7:1',layer=true,minZ=x<300 and 0 or 20,maxZ=x<300 and 10 or 30}
            end
            local a=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            local b=assert(mod.GPSRoadEditAdd(900001,.4,.1))
            assert(not mod.GPSRoadEditConnect(a,b),'different floors were joined')
            assert(not mod.GPSRoadEditAdd(900001,.7,.1),'ambiguous map click chose a floor')
            assert(not mod.GPSRoadEditNearest(900001,.7,.1))
            assert(not mod.GPSRoadEditAdd(900001,.4,.2,a))
            local same=assert(mod.GPSRoadEditAdd(900001,.15,.1,a))
            assert(mod.GPSRoadEditLinked(a,same))
        ''')

    def test_selection_and_edit_mode_preserve_gps_tracker_and_waypoint(self):
        self.lua.execute('''
            local a=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            local b=assert(mod.GPSRoadEditAdd(900001,.5,.1,a))
            mod.GPSSetTrackerShown(false)
            assert(mod.GPSStart(900001,.5,.1))
            local route,waypoint=mod.GPSStatus().route,WAYPOINT
            mod.GPSSetRoadEditing(true)
            assert(mod.GPSRoadsShown()and mod.GPSStatus().route==route and WAYPOINT==waypoint)
            assert(mod.GPSRoadEditSelect(a))
            assert(mod.GPSRoadSelected()==a and not mod.db.gpsShowTracker)
            mod.GPSSetRoadEditing(false)
            assert(not mod.GPSRoadEditing()and not mod.GPSRoadSelected()and mod.GPSRoadsShown())
            assert(mod.GPSStatus().route==route and WAYPOINT==waypoint and not mod.db.gpsShowTracker)
        ''')

    def test_saved_graph_survives_profile_initialization_and_editor_reload(self):
        self.lua.execute('''
            mod.GPSSetRoadEditing(true)
            savedA=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            savedB=assert(mod.GPSRoadEditAdd(900001,.5,.1,savedA))
            savedGraph=mod.db.gpsManualRoads
            ns:InitDB()
            assert(mod.db.gpsManualRoads==savedGraph)
        ''')
        self.lua.execute((ROOT / 'OpenMap/Map/GPSRoadEdit.lua').read_text(), 'OpenMap', self.lua.globals().ns)
        self.lua.execute('''
            assert(not mod.GPSRoadEditing()and not mod.GPSRoadSelected())
            assert(mod.GPSRoadEditLinked(savedA,savedB))
            assert(EditedPlan(savedA,savedB))
            local next=assert(mod.GPSRoadEditAdd(900001,.6,.1))
            assert(next~=savedA and next~=savedB and mod.db.gpsManualRoads==savedGraph)
        ''')

    def test_manual_graph_routes_with_bundled_roads_disabled_and_replans_after_edits(self):
        self.lua.execute('''
            RoadFixture({[1]={wx=100,wy=100,map=900001,links={[2]=true}},[2]={wx=500,wy=100,map=900001,links={[1]=true}}})
            local a=assert(mod.GPSRoadEditAdd(900001,.1,.1))
            local b=assert(mod.GPSRoadEditAdd(900001,.1,.4,a))
            local c=assert(mod.GPSRoadEditAdd(900001,.5,.4,b))
            assert(mod.GPSSetRoutingOption('gpsUseRoads',false))
            assert(mod.GPSStart(900001,.5,.4))
            assert(Uses(mod.GPSStatus().route,b))
            assert(mod.GPSStatus().roadStats.nodes==3,'bundled nodes remained in the disabled graph')
            local old=mod.GPSStatus().route
            local revision=mod.GPSRoadsRevision()
            assert(mod.GPSRoadEditConnect(a,c))
            assert(mod.GPSRoadsRevision()>revision and mod.GPSStatus().active)
            assert(mod.GPSStatus().route~=old and not Uses(mod.GPSStatus().route,b))
        ''')

    def test_manual_link_cannot_reverse_a_shipped_one_way_road(self):
        self.lua.execute('''
            RoadFixture({
                [1]={wx=100,wy=100,map=900001,oneway={[2]=true},links={[2]=true}},
                [2]={wx=500,wy=100,map=900001,links={[1]=true}}
            })
            local a,b='b:0:1','b:0:2'
            assert(not mod.GPSRoadEditConnect(a,b))
            assert(not mod.GPSRoadEditConnect(b,a))
            assert(#mod.GPSRoadEditSnapshot().links==0)
            assert(mod.GPSRoadCanWalk(0,1,2)and not mod.GPSRoadCanWalk(0,2,1))
        ''')

    def test_loaded_graph_limits_and_invalid_next_id_fail_without_partial_edits(self):
        self.lua.execute('''
            local db=mod.db.gpsManualRoads
            for i=1,2000 do db.nodes['m:'..i]={900001,.1,.1}end
            assert(not mod.GPSRoadEditAdd(900001,.2,.1),'node budget was exceeded')
            db.nodes={['m:1']={900001,.1,.1},['m:2']={900001,.5,.1}}
            db.nextID=1e100
            assert(mod.GPSRoadEditAdd(900001,.2,.1)=='m:3','invalid next ID was not safely recovered')
            for i=1,4000 do db.links['loaded:'..i]={a='m:1',b='m:2'}end
            assert(not mod.GPSRoadEditConnect('m:1','m:3'),'link budget was exceeded')
            local nextID=db.nextID
            assert(not mod.GPSRoadEditAdd(900001,.3,.1,'m:1'))
            assert(db.nextID==nextID and not db.nodes['m:4'],'failed add-and-connect left a partial node')
        ''')


if __name__ == '__main__':
    unittest.main()
