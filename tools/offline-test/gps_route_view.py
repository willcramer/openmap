"""The real GPS panel draws a continuous green remaining path with actual nodes.

Run: python -P tools/offline-test/gps_route_view.py
Only the map's region/pool API is simulated; GPSPanel.lua is loaded in full.
"""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]


class GPSRouteViewTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute("""
            mod={defaults={},db={}}
            ns={L=setmetatable({},{__index=function(_,key)return key end}),Safe={}}
            function ns:GetModule()return mod end
            function ns.Safe.Value(v)
                if type(v)=='table'and v.secret then return nil end
                return v
            end
            ns.MapStitch={}
            S=ns.MapStitch
            built=true
            function S.IsBuilt()return built end
            sets={}
            allocations,clears,moves=0,0,0
            local function Region(pool)
                local region=table.remove(pool)
                if not region then
                    region={} allocations=allocations+1
                    function region:Hide()self.shown=false end
                    function region:Show()self.shown=true end
                    function region:EnableMouse(on)self.mouse=on end
                    function region:SetStartPoint(corner,pin)self.startPin=pin end
                end
                return region
            end
            function S.PinSet(key,minZoom,level)
                local s=sets[key]
                if not s then
                    s={pins={},lines={},pinPool={},linePool={},key=key,on=true}
                    sets[key]=s
                end
                s.level,s.minZoom=level,minZoom
                return s
            end
            function S.ClearPinSet(s)
                clears=clears+1
                for _,p in ipairs(s.pins)do p:Hide()s.pinPool[#s.pinPool+1]=p end
                for _,p in ipairs(s.lines)do p:Hide()s.linePool[#s.linePool+1]=p end
                s.pins,s.lines={},{}
            end
            function S.AddPin(s,u,v,look)
                local p=Region(s.pinPool)
                p.u,p.v,p.look,p.shown=u,v,look,true
                s.pins[#s.pins+1]=p
                return p
            end
            function S.MovePin(s,p,u,v)p.u,p.v=u,v moves=moves+1 end
            function S.AddLine(s,u1,v1,u2,v2,width,r,g,b,a)
                local p=Region(s.linePool)
                p.u1,p.v1,p.u2,p.v2,p.width=u1,v1,u2,v2,width
                p.color,p.shown,p.startPin={r,g,b,a},true,nil
                s.lines[#s.lines+1]=p
                return p
            end
            function Point(u,v,cont)return {u=u,v=v,cont=cont or 0}end
            status={active=true,index=1,player=Point(.1,.2),route={
                Point(.2,.2),Point(.2,.8),Point(.8,.8)
            }}
            function Draw()mod.GPSDrawRoute(status)end
            function Shown(items)
                local n=0 for _,p in ipairs(items)do if p.shown then n=n+1 end end
                return n
            end
        """)
        lua.execute((ROOT / 'OpenMap/Map/GPSPanel.lua').read_text(), 'OpenMap', lua.globals().ns)

    def check(self, code):
        self.lua.execute(code)

    def test_solid_green_lines_preserve_the_road_bend_and_waypoint_nodes(self):
        self.check("""
            Draw()
            local s=sets.gps
            assert(s.minZoom==0 and s.level==4)
            assert(#s.pins==4 and #s.lines==3)
            assert(s.lines[1].u1==.2 and s.lines[1].v1==.2 and s.lines[1].u2==.2 and s.lines[1].v2==.8)
            assert(s.lines[2].u1==.2 and s.lines[2].v1==.8 and s.lines[2].u2==.8 and s.lines[2].v2==.8)
            for _,line in ipairs(s.lines)do
                assert(line.width==3 and line.color[1]==.15 and line.color[2]==1 and line.color[3]==.25 and line.color[4]==1)
            end
            for i,pin in ipairs(s.pins)do
                assert(pin.mouse==false and pin.look.color[2]==1)
                if i<3 then assert(pin.look.size==7)end
            end
            assert(s.pins[3].look.size==10,'destination should be distinct')
            assert(s.lines[3].startPin==s.pins[4])
        """)

    def test_player_connector_tracks_motion_without_rebuilding_the_road(self):
        self.check("""
            Draw()
            local s,first,head,created,rebuilt=sets.gps,sets.gps.lines[1],sets.gps.lines[3],allocations,clears
            status.player=Point(.12,.24)
            Draw()
            assert(allocations==created and clears==rebuilt and s.lines[1]==first and s.lines[3]==head)
            assert(head.startPin.u==.12 and head.startPin.v==.24 and moves==1)
            assert(head.u2==.2 and head.v2==.2)
        """)

    def test_progress_and_rerouting_remove_completed_geometry_and_reuse_pools(self):
        self.check("""
            Draw()
            local before=allocations
            status.index=2 status.player=Point(.2,.3)
            Draw()
            local s=sets.gps
            assert(#s.lines==2 and #s.pins==3 and allocations==before)
            assert(s.lines[1].u1==.2 and s.lines[1].v1==.8)
            status.route={Point(.3,.3),Point(.6,.3)}status.index=1
            Draw()
            assert(#s.lines==2 and #s.pins==3 and allocations==before)
            assert(s.lines[1].u1==.3 and s.lines[1].u2==.6)
            status.active=false Draw()
            assert(#s.lines==0 and #s.pins==0)
            status.active=true Draw()
            assert(allocations==before and #s.lines==2)
        """)

    def test_unprojectable_points_and_continents_break_the_path(self):
        self.check("""
            status.route={Point(.2,.2),{},Point(.4,.4),Point(.6,.4,1),Point(.8,.4,1)}
            Draw()
            local s=sets.gps
            assert(#s.lines==2,'a gap or continent change became a straight shortcut')
            assert(s.lines[1].u1==.6 and s.lines[1].u2==.8)
            status.route={{},Point(.4,.4)} Draw()
            assert(#s.lines==0 and #s.pins==1,'player skipped an unprojectable current waypoint')
        """)

    def test_missing_secret_or_wrong_floor_player_hides_the_live_connector(self):
        self.check("""
            Draw()
            local head=sets.gps.lines[3]
            status.player=nil Draw()assert(not head.shown and Shown(sets.gps.lines)==2)
            status.player=Point({secret=true},.2) Draw()assert(not head.shown)
            status.player=Point(.1,.2,1) Draw()assert(not head.shown)
            status.player=Point(.1,.2)status.player.ambiguous=true Draw()assert(not head.shown)
            status.player=Point(.1,.2)status.player.layer=1458 status.route[1].layer=false
            Draw()assert(not head.shown)
            status.player=Point(.1,.2)mod.GPSOtherFloor=function()return true end
            Draw()assert(not head.shown)
            mod.GPSOtherFloor=nil status.route[1].layer=nil
            Draw()assert(head.shown and head.startPin.shown)
        """)

    def test_a_single_destination_still_draws_a_continuous_player_connector(self):
        self.check("""
            status.route={Point(.8,.8)}
            Draw()
            assert(#sets.gps.lines==1 and #sets.gps.pins==2)
            assert(sets.gps.pins[1].look.size==10)
            status.player=nil Draw()
            assert(Shown(sets.gps.lines)==0 and Shown(sets.gps.pins)==1)
        """)

    def test_large_valid_routes_keep_every_bend_and_the_pool_is_bounded(self):
        self.check("""
            status.route={}
            for i=1,12000 do status.route[i]=Point(i/12001,(i%2==0)and .4 or .6)end
            Draw()
            assert(#sets.gps.lines==12000 and #sets.gps.pins==12001)
            for i=1,11999 do
                assert(sets.gps.lines[i].v1==status.route[i].v and sets.gps.lines[i].v2==status.route[i+1].v)
            end
            local before=allocations
            status.index=6000 Draw()assert(allocations==before)
            status.route={}
            for i=1,26000 do status.route[i]=Point(i/26001,.5)end
            status.index=1 Draw()
            assert(#sets.gps.lines<=25000 and #sets.gps.pins<=25001)
            assert(sets.gps.pins[25000].u==status.route[25000].u,'drawing skipped to the target across an over-budget gap')
        """)

    def test_build_waits_for_stitched_world_and_controller_uses_the_same_layer(self):
        self.check("""
            built=false Draw()assert(sets.gps==nil)
            built=true mod.PadViewOn=function()return true end
            Draw()assert(#sets.gps.lines==3)
            status.active=false mod.GPSStatus=function()return status end
            mod.BuildGPSPanel(mod)
            assert(#sets.gps.lines==0,'inactive GPS panel refresh retained the old route')
        """)


if __name__ == '__main__':
    unittest.main()
