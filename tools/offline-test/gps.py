"""Exercise GPS road routing, trail recording, playback and waypoint ownership in Lua 5.1."""
from pathlib import Path
import unittest
import lupa.lua51 as lupa

ROOT = Path(__file__).resolve().parents[2]


class GPS(unittest.TestCase):
    def setUp(self):
        self.lua = lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
            NOW, TAXI = 0, false
            player = {map=1, x=.1, y=.1}
            mod = {defaults={}, db={gpsRoutes={}}, char={}}
            ns = {L=setmetatable({}, {__index=function(_, k) return k end})}
            function ns:GetModule() return mod end
            ns.Safe = {}
            function ns.Safe.Value(v) if type(v)=='table' and v.secret then return nil end return v end
            function ns.Safe.Call(fn, ...)
                if type(fn) ~= 'function' then return end
                local ok,v=pcall(fn,...)
                if ok then return ns.Safe.Value(v) end
            end
            function ns.Safe.XY(v) return v.x,v.y end
            ns.MapStitch = {Rect=function(id) if id==1 or id==2 then return 0,1,0,1 end end}
            function mod.ToWorld(_, x, y) return x,y end
            function CreateVector2D(x,y) return {x=x,y=y} end
            C_Map = {}
            function C_Map.GetBestMapForUnit() return player and player.map end
            function C_Map.GetPlayerMapPosition() return player and {x=player.x,y=player.y} end
            function C_Map.GetWorldPosFromMapPos(id,p) return id,{x=p.x*1000,y=p.y*1000} end
            function UnitOnTaxi() return TAXI end
            function GetTime() return NOW end
            function mod.TrackPoint(map,x,y,title) waypoint={map=map,x=x,y=y} tracks=(tracks or 0)+1 end
            function mod.WaypointPoint() if waypoint then return waypoint.map,waypoint.x,waypoint.y end end
            function mod.ClearPin() waypoint=nil clears=(clears or 0)+1 end
            function move(x,y,map) player={map=map or 1,x=x,y=y} NOW=NOW+.2 mod.GPSUpdate() end
        """)
        lua.execute((ROOT / "OpenMap/Map/GPS.lua").read_text(), "OpenMap", lua.globals().ns)

    def run_lua(self, source):
        self.lua.execute(source)

    def test_direct_arrival_and_external_waypoint_ownership(self):
        self.run_lua("""
            assert(mod.GPSStart(1,.5,.1,'Destination'))
            assert(mod.GPSStatus().state=='direct' and mod.GPSStatus().distance==400)
            local n=tracks
            mod.GPSUpdate() mod.GPSUpdate()
            assert(tracks==n, 'ticker repeatedly rewrote waypoint')
            waypoint={map=1,x=.8,y=.8}
            mod.GPSUpdate()
            assert(not mod.GPSStatus().active and waypoint.x==.8 and not clears)
            assert(mod.GPSStart(1,.5,.1))
            move(.5,.1)
            assert(mod.GPSStatus().state=='arrived' and not waypoint)
            assert(mod.GPSStatus().instruction=='You have arrived.')
        """)

    def test_record_save_and_reverse_without_overwriting(self):
        self.run_lua("""
            assert(mod.GPSRecord(' My walk '))
            move(.13,.1) move(.16,.1) move(.19,.1)
            assert(mod.GPSSave())
            assert(#mod.db.gpsRoutes['My walk'].points==4)
            assert(not mod.GPSRecord('My walk'))
            assert(mod.GPSPlay('My walk','reverse'))
            assert(mod.GPSStatus().route[1].x==.19)
            move(.16,.1) move(.13,.1) move(.1,.1)
            assert(mod.GPSStatus().state=='arrived')
            assert(not mod.GPSStatus().active)
            assert(mod.GPSRecord('single'))
            assert(not mod.GPSSave())
            assert(mod.GPSCancelRecording())
            assert(mod.GPSRecord('another'))
        """)

    def test_recording_gap_requires_explicit_partial_save(self):
        self.run_lua("""
            assert(mod.GPSRecord('walk'))
            move(.13,.1) move(.16,.1)
            move(.7,.1)
            assert(mod.GPSStatus().recordingState=='gap')
            move(.73,.1)
            assert(mod.GPSStatus().recorded==3)
            assert(not mod.GPSSave())
            assert(not mod.db.gpsRoutes.walk)
            assert(mod.GPSSave(true))
            assert(#mod.db.gpsRoutes.walk.points==3)
            assert(mod.db.gpsRoutes.walk.points[3][2]==.16)
        """)

    def test_save_detects_a_teleport_before_the_next_ticker(self):
        self.run_lua("""
            assert(mod.GPSRecord('walk'))
            move(.13,.1)
            player.x=.7
            assert(not mod.GPSSave())
            assert(mod.GPSStatus().recordingState=='gap')
            assert(mod.GPSSave(true))
            assert(#mod.db.gpsRoutes.walk.points==2)
        """)

    def test_road_network_preserves_detour_and_joins_trails(self):
        self.run_lua("""
            local a,b={},{}
            for i=1,7 do a[#a+1]={1,.1,.1+(i-1)*.05} end
            for i=1,13 do a[#a+1]={1,.1+(i-1)*.05,.4} end
            for i=1,7 do b[#b+1]={1,.7,.4-(i-1)*.05} end
            mod.db.gpsRoutes={a={points=a},b={points=b}}
            assert(mod.GPSStart(1,.7,.1))
            local s=mod.GPSStatus()
            assert(s.state=='recorded' and #s.route>20)
            assert(s.remaining>1100, 'route cut across the recorded detour')
            local hasCorner=false
            for _,p in ipairs(s.route) do if p.x==.1 and p.y==.4 then hasCorner=true end end
            assert(hasCorner)
        """)

    def test_invalid_locations_and_cross_continent_guidance_are_rejected(self):
        self.run_lua("""
            assert(not mod.GPSStart(1,0/0,.5))
            assert(not mod.GPSStart(1,2,.5))
            assert(not mod.GPSStart(2,.5,.5))
            assert(not mod.GPSStatus().active)
            player.x={secret=true}
            assert(not mod.GPSRecord('secret'))
            assert(not mod.GPSStart(1,.5,.5))
        """)

    def test_position_loss_and_taxi_pause_without_advancing(self):
        self.run_lua("""
            assert(mod.GPSStart(1,.5,.1))
            TAXI=true move(.5,.1)
            assert(mod.GPSStatus().active and mod.GPSStatus().state=='waiting')
            assert(not mod.GPSStatus().distance and not mod.GPSStatus().remaining)
            TAXI=false player=nil mod.GPSUpdate()
            assert(mod.GPSStatus().active and mod.GPSStatus().state=='waiting')
            move(.5,.1,2)
            assert(mod.GPSStatus().active and mod.GPSStatus().state=='waiting')
            assert(not mod.GPSStatus().distance and not mod.GPSStatus().bearing)
            move(.5,.1)
            assert(mod.GPSStatus().state=='arrived')
        """)

    def test_loop_rejects_open_trail_and_pingpong_reverses(self):
        self.run_lua("""
            local points={}
            for i=1,8 do points[#points+1]={1,.1+(i-1)*.05,.1} end
            mod.db.gpsRoutes.long={points=points}
            assert(not mod.GPSPlay('long','loop'))
            assert(mod.GPSPlay('long','pingpong'))
            for i=2,8 do move(.1+(i-1)*.05,.1) end
            local s=mod.GPSStatus()
            assert(s.active and s.index==2 and math.abs(s.route[1].x-.45)<1e-9)
            assert(s.route[#s.route].x==.1)
        """)

    def test_reroute_falls_back_to_explicit_direct_guidance(self):
        self.run_lua("""
            local points={}
            for i=1,13 do points[#points+1]={1,.1+(i-1)*.05,.1} end
            mod.db.gpsRoutes.road={points=points}
            assert(mod.GPSStart(1,.7,.1))
            assert(mod.GPSStatus().state=='recorded')
            NOW=10 move(.15,.4)
            assert(mod.GPSPlanningStats().active and mod.GPSStatus().state=='recorded')
            for _=1,100 do
                mod.GPSRunPlanning(1)
                if not mod.GPSPlanningStats().active then break end
                NOW=NOW+1/120
            end
            assert(mod.GPSStatus().state=='direct')
            assert(#mod.GPSStatus().route==1)
            assert(mod.GPSStatus().instruction:find('terrain is not checked',1,true))
        """)


if __name__ == "__main__":
    unittest.main()
