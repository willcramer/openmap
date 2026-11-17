"""Budgeted GPS replanning, stale result guards and deferred map publication.

Run: python -P tools/offline-test/gps_async.py
CPU time is controlled explicitly so these checks do not depend on host speed.
The planner, ownership rules and production ticker are the addon implementations.
"""
import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def fixture(name):
    spec = importlib.util.spec_from_file_location('gps_async_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core, integration, view = (fixture(name) for name in ('gps', 'gps_integration', 'gps_route_view'))


class GPSAsyncTests(unittest.TestCase):
    setUp = core.GPS.setUp

    def begin(self):
        self.lua.execute('''
            CPU, PLANS, UNITS = 0, 0, 1000
            function debugprofilestop()return CPU end
            function P(x,y)return {map=1,x=x,y=y,u=x,v=y,cont=1,wx=x*1000,wy=y*1000}end
            CACHES={}
            mod.GPSRoadRoute=function(from,to,context)
                PLANS=PLANS+1 CACHES[#CACHES+1]=context.destinationCache
                for _=1,UNITS do CPU=CPU+.05 context.checkpoint()end
                if PLANS==1 then return {from,P(.2,.1),P(.4,.1),to},nil,{}end
                return {from,P(.25,.25),to},nil,{}
            end
            assert(mod.GPSStart(1,.7,.1,'Target'))
            OLD,OWNED=mod.GPSStatus().route,waypoint
            NOW=10 move(.15,.25)
            assert(mod.GPSPlanningStats().active and mod.GPSStatus().route==OLD)
            assert(waypoint==OWNED,'queuing changed the owned waypoint')
            function Finish()
                for _=1,200 do
                    mod.GPSRunPlanning(1)
                    if not mod.GPSPlanningStats().active then return end
                    NOW=NOW+1/120
                end
                error('planner did not finish')
            end
        ''')

    def test_budget_preserves_route_and_waypoint_until_atomic_completion(self):
        self.begin()
        self.lua.execute('''
            local frames,notifications,tracked=0,0,tracks
            mod.OnGPSChanged=function()
                notifications=notifications+1
                assert(mod.GPSStatus().route~=OLD and mod.GPSStatus().index==2,
                    'publication observed an intermediate route index')
            end
            while mod.GPSPlanningStats().active do
                local before=CPU
                mod.GPSRunPlanning(1)
                frames=frames+1
                assert(CPU-before<=1.051,'planner exceeded its budget plus one bounded operation')
                if mod.GPSPlanningStats().active then
                    assert(mod.GPSStatus().route==OLD and waypoint==OWNED,'partial route leaked')
                end
            end
            local stats=mod.GPSPlanningStats()
            assert(frames>20 and stats.completed==1 and stats.lastFrames==frames)
            assert(mod.GPSStatus().route~=OLD and waypoint~=OWNED)
            assert(notifications==1 and tracks==tracked+1,'replan published the origin before the final guidance step')
            assert(CACHES[1]==CACHES[2],'same destination did not reuse its attachment cache')
            assert(stats.maxSliceMS<=1.051 and math.abs(stats.lastTotalMS-50)<.001)
        ''')

    def test_fallback_bounds_work_when_profiling_clock_is_static_or_missing(self):
        self.begin()
        self.lua.execute('''
            debugprofilestop=nil
            local before=CPU
            mod.GPSRunPlanning(1)
            assert(mod.GPSPlanningStats().active and CPU-before<=256*.05+.001)
            assert(mod.GPSStatus().route==OLD and waypoint==OWNED)
            Finish()
            assert(mod.GPSPlanningStats().completed==1)
        ''')

    def test_stop_and_external_waypoint_takeover_cancel_without_overwrite(self):
        for takeover in (False, True):
            with self.subTest(takeover=takeover):
                self.setUp()
                self.begin()
                self.lua.execute('''
                    mod.GPSRunPlanning(1)
                ''' + ('''
                    waypoint={map=1,x=.9,y=.9}
                    local external=waypoint
                    mod.GPSRunPlanning(1)
                    assert(waypoint==external and not mod.GPSStatus().active)
                ''' if takeover else '''
                    mod.GPSStop()
                    mod.GPSRunPlanning(1)
                    assert(not waypoint and not mod.GPSStatus().active)
                ''') + '''
                    assert(not mod.GPSPlanningStats().active and mod.GPSPlanningStats().completed==0)
                ''')

    def test_new_destination_discards_the_old_job_and_uses_a_fresh_cache(self):
        self.begin()
        self.lua.execute('''
            mod.GPSRunPlanning(1)
            assert(mod.GPSStart(1,.8,.3,'New destination'))
            local newRoute,newWaypoint=mod.GPSStatus().route,waypoint
            for _=1,100 do mod.GPSRunPlanning(1)end
            assert(not mod.GPSPlanningStats().active and mod.GPSStatus().route==newRoute and waypoint==newWaypoint)
            assert(CACHES[1]~=CACHES[3] and mod.GPSStatus().title=='New destination')
        ''')

    def test_settings_topology_source_and_player_state_invalidate_pending_results(self):
        cases = {
            'routing preference': 'mod.db.gpsOffroad="allow"',
            'saved routes identity': 'mod.db.gpsRoutes={}',
            'source data identity': 'ns.GPSRoadData={}',
            'graph revision': 'mod.GPSRoadGraphRevision=function()return 1 end',
            'missing position': 'player=nil mod.GPSUpdate()',
            'taxi': 'TAXI=true',
            'continent': 'player.map=2 mod.GPSUpdate()',
            'teleport': 'move(.9,.9)',
            'floor': 'mod.GPSStatus().player.layer="upstairs"',
        }
        for name, change in cases.items():
            with self.subTest(reason=name):
                self.setUp()
                self.begin()
                self.lua.execute('''
                    mod.GPSRunPlanning(1)
                ''' + change + '''
                    mod.GPSRunPlanning(1)
                    assert(not mod.GPSPlanningStats().active,'stale planning survived invalidation')
                    assert(mod.GPSPlanningStats().completed==0 and mod.GPSStatus().route==OLD)
                    assert(waypoint==OWNED,'stale result rewrote the waypoint')
                ''')

    def test_planner_error_keeps_the_previous_route_and_reports_once(self):
        self.begin()
        self.lua.execute('''
            local checks=0
            mod.GPSPlanningCheckpoint=function()
                checks=checks+1
                if checks==5 then error('test planner failure')end
            end
            local errors={}
            geterrorhandler=function()return function(message)errors[#errors+1]=message end end
            mod.GPSRunPlanning(1)
            assert(not mod.GPSPlanningStats().active and mod.GPSPlanningStats().failed==1)
            assert(#errors==1 and errors[1]:find('test planner failure',1,true))
            assert(mod.GPSStatus().route==OLD and waypoint==OWNED)
        ''')

    def test_recorded_sample_projection_is_reused_and_invalidated_on_changes(self):
        self.lua.execute('''
            local project=C_Map.GetWorldPosFromMapPos
            SAMPLE_PROJECTIONS=0
            C_Map.GetWorldPosFromMapPos=function(map,p)
                if p.x==.4 and p.y==.1 then SAMPLE_PROJECTIONS=SAMPLE_PROJECTIONS+1 end
                return project(map,p)
            end
            local points={}
            for i=0,12 do points[#points+1]={1,.1+i*.05,.1}end
            -- Use an exactly represented coordinate to distinguish this sample
            -- from the player's and target's independently projected points.
            points[7]={1,.4,.1}
            mod.db.gpsRoutes.road={points=points}
            assert(mod.GPSStart(1,.7,.1))
            assert(SAMPLE_PROJECTIONS==1)
            NOW=10 move(.15,.18)
            for _=1,200 do mod.GPSRunPlanning(1)end
            assert(SAMPLE_PROJECTIONS==1,'warm replanning projected the saved samples again')
            mod.GPSStop()
            mod.db.gpsRoutes={road={points=points}}
            assert(mod.GPSStart(1,.7,.1))
            assert(SAMPLE_PROJECTIONS==2,'replacing saved data kept the old sample cache')
            assert(mod.GPSDelete('road'))
            mod.db.gpsRoutes.road={points=points}
            assert(mod.GPSStart(1,.7,.1))
            assert(SAMPLE_PROJECTIONS==3,'recorded road revision kept the old sample cache')
        ''')

    def test_cancelled_level_lookup_does_not_publish_a_partial_restriction_cache(self):
        self.lua.execute('''
            CPU,CALLS,LOOKUPS=0,0,0
            debugprofilestop=function()return CPU end
            ns.GPSRoadLevels={areas={[1]=11,[2]=22,[3]=33}}
            C_Map.GetAreaInfo=function(id)
                CPU=CPU+.7 LOOKUPS=LOOKUPS+1
                return 'Area'..id
            end
            mod.GPSRoadRoute=function(from,to,context)
                CALLS=CALLS+1
                if CALLS>1 then FOUND_LEVEL=context.minLevel({area='Area3'})end
                return {from,to},nil,{}
            end
            assert(mod.GPSStart(1,.7,.1))
            NOW=10 move(.15,.25)
            mod.GPSRunPlanning(1)
            assert(mod.GPSPlanningStats().active and LOOKUPS==2 and not FOUND_LEVEL)
            mod.GPSStop()
            assert(mod.GPSStart(1,.7,.1))
            assert(FOUND_LEVEL==33 and LOOKUPS==5,'a cancelled partial area cache lost a level restriction')
        ''')

    def test_recorded_only_cached_samples_keep_unprojectable_gaps_disconnected(self):
        self.lua.execute('''
            local project=C_Map.GetWorldPosFromMapPos
            C_Map.GetWorldPosFromMapPos=function(map,p)
                if p.x==.18 then return nil end
                return project(map,p)
            end
            mod.db.gpsRoutes.broken={points={
                {1,.1,.1},{1,.14,.1},{1,.18,.1},{1,.22,.1},{1,.26,.1}
            }}
            assert(mod.GPSStart(1,.26,.1))
            assert(mod.GPSStatus().state=='direct','cached sample conversion bridged a missing projection')
        ''')


class GPSAsyncTickerTests(unittest.TestCase):
    setUp = integration.GPSIntegrationTests.setUp

    def test_production_ticker_resumes_between_guidance_polls_with_tracker_hidden(self):
        self.lua.execute('''
            CPU,UNITS,PLANS=0,1000,0
            debugprofilestop=function()return CPU end
            gpsmod.GPSRoadRoute=function(from,to,context)
                PLANS=PLANS+1
                for _=1,UNITS do CPU=CPU+.05 context.checkpoint()end
                local p={}
                for k,v in pairs(to)do p[k]=v end
                p.x,p.y,p.wx,p.wy=.3,.2,800,700
                return {from,p,to},nil,{}
            end
            gpsmod.GPSSetTrackerShown(false)
            assert(gpsmod.GPSStart(900001,.7,.2))
            local old=gpsmod.GPSStatus().route
            PY=.28 NOW=10
            TickGPS()
            assert(gpsmod.GPSPlanningStats().active and not OpenMapGPSGuide:IsShown())
            local before=CPU
            NOW=NOW+1/120 RunOnUpdate(1/120)
            assert(CPU>before,'worker waited for the next .2 second guidance poll')
            assert(gpsmod.GPSStatus().route==old)
            for _=1,200 do
                before=CPU
                NOW=NOW+1/120 RunOnUpdate(1/120)
                assert(CPU-before<=1.051)
                if not gpsmod.GPSPlanningStats().active then break end
            end
            assert(gpsmod.GPSPlanningStats().completed==1 and gpsmod.GPSStatus().route~=old)
            assert(not OpenMapGPSGuide:IsShown()and not WorldMapFrame:IsShown()and #ERRORS==0)
        ''')


class GPSAsyncDrawingTests(unittest.TestCase):
    def setUp(self):
        view.GPSRouteViewTests.setUp(self)
        self.lua.execute('''
            mod.db.gpsRoutes={}
            C_Map={}
            NOW,CPU=0,0
            function GetTime()return NOW end
            function debugprofilestop()return CPU end
            function ns.Safe.Call(fn,...)if type(fn)=='function'then return fn(...)end end
            function ns.Safe.XY(v)return v.x,v.y end
            local pin,line=S.AddPin,S.AddLine
            S.AddPin=function(...)CPU=CPU+.05 return pin(...)end
            S.AddLine=function(...)CPU=CPU+.05 return line(...)end
            S.SetPinSetOn=function(set,on)set.on=on end
            local clear=S.ClearPinSet
            S.ClearPinSet=function(set,checkpoint)
                clear(set)
                if checkpoint then checkpoint()end
            end
            VISIBLE=true
            WorldMapFrame={IsShown=function()return VISIBLE end}
        ''')
        self.lua.execute((ROOT / 'OpenMap/Map/GPS.lua').read_text(), 'OpenMap', self.lua.globals().ns)

    def test_closed_map_allocates_nothing_then_catches_up_with_atomic_visible_path(self):
        self.lua.execute('''
            VISIBLE=false
            status.route={}
            for i=1,100 do status.route[i]=Point(i/200,.2)end
            local before=allocations
            mod.GPSDrawRoute(status,true)
            assert(allocations==before and not mod.GPSRouteDrawingPending())
            VISIBLE=true
            mod.GPSDrawRoute(status,true)
            assert(mod.GPSRouteDrawingPending()and sets.gps.on and not sets.gpsnext.on)
            while mod.GPSRouteDrawingPending()do
                local cpu=CPU
                mod.GPSRunRouteDrawing(1)
                assert(CPU-cpu<=1.201)
                if mod.GPSRouteDrawingPending()then assert(not sets.gpsnext.on)end
            end
            assert(not sets.gps.on and sets.gpsnext.on and #sets.gpsnext.pins==101)
            assert(#sets.gpsnext.lines==100)
        ''')

    def test_replacement_cancels_partial_geometry_and_keeps_previous_front_visible(self):
        self.lua.execute('''
            Draw()
            local previous=sets.gps
            status.route={}
            for i=1,100 do status.route[i]=Point(i/200,.3)end
            mod.GPSDrawRoute(status,true)
            mod.GPSRunRouteDrawing(1)
            assert(previous.on and not sets.gpsnext.on and mod.GPSRouteDrawingPending())
            status.route={Point(.2,.7),Point(.8,.7)}
            mod.GPSDrawRoute(status,true)
            for _=1,10 do mod.GPSRunRouteDrawing(1)end
            assert(not mod.GPSRouteDrawingPending()and sets.gpsnext.on and not previous.on)
            assert(#sets.gpsnext.pins==3 and #sets.gpsnext.lines==2)
            status.active=false mod.GPSDrawRoute(status,true)
            assert(not sets.gpsnext.on and not previous.on)
        ''')


if __name__ == '__main__':
    unittest.main()
