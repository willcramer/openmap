"""Native Zephras route marks: own regions, projection, clipping and bounded reuse.

Run: python -P tools/offline-test/gps_native.py
"""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]


class NativeGPSRouteTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((Path(__file__).with_name('stub.lua')).read_text())
        self.lua.execute('''
            mod = { db = {} }
            ns = { GetModule=function() return mod end, Safe={
                Value=function(v) if issecretvalue and issecretvalue(v) then return nil end return v end,
                XY=function(p) return p.x,p.y end,
                Call=function(fn,...) if type(fn)~='function' then return end local ok,v=pcall(fn,...) if ok then return v end end
            } }
            stitched = false
            mod.IsStitched = function() return stitched end
            host, scale, projections = 2521, 1, 0
            map = CreateFrame('Frame')
            canvas = CreateFrame('Frame',nil,map)
            canvas:SetSize(1000,500)
            map.GetMapID=function() return host end
            map.GetCanvas=function() return canvas end
            map.GetCanvasScale=function() return scale end
            WorldMapFrame=map
            CreateVector2D=function(x,y) return {x=x,y=y} end
            C_Map.GetMapPosFromWorldPos=function(cont,point,override)
                assert(cont==2991 and override==host,'node map replaced native host override')
                projections=projections+1
                local shift=host==2665 and .1 or 0
                return override,{x=point.x/1000+shift,y=point.y/1000}
            end
            status={active=true,index=1,route={
                {cont=2991,map=2665,wx=100,wy=200},
                {cont=2991,map=2521,wx=800,wy=200}
            }}
            foreign=CreateFrame('Frame',nil,canvas)
            foreign:SetSize(37,41)
            hiddenCallbacks=0
            map:SetScript('OnHide',function() hiddenCallbacks=hiddenCallbacks+1 end)
            function nativeRoot()
                for _, frame in ipairs(FRAMES) do
                    if frame:GetParent()==canvas and frame~=foreign and frame:GetObjectType()=='Frame' then return frame end
                end
            end
            function shownDots()
                local out={}
                local owner=nativeRoot()
                for _, frame in ipairs(FRAMES) do
                    if frame:GetParent()==owner and frame:GetObjectType()=='Texture' and frame:IsShown() then out[#out+1]=frame end
                end
                return out
            end
        ''')
        self.lua.execute((ROOT / 'OpenMap/Map/GPSNative.lua').read_text(), 'OpenMap', self.lua.globals().ns)

    def check(self, source):
        self.lua.execute(source)

    def test_native_projection_uses_host_canvas_coordinates_without_stitched_world(self):
        self.check('''
            mod.GPSDrawNative(status)
            local stats=mod.GPSNativeStats()
            assert(stats.shown and stats.drawn>2)
            local owner=nativeRoot()
            assert(owner and owner:GetParent()==canvas)
            local first=shownDots()[1]
            local point,relative,corner,x,y=first:GetPoint()
            assert(point=='CENTER' and relative==owner and corner=='TOPLEFT' and x==100 and y==-100)
            assert(foreign:GetWidth()==37 and foreign:GetHeight()==41,'another addon frame was changed')
            host=2665 mod.GPSDrawNative(status)
            local _,_,_,nx,ny=shownDots()[1]:GetPoint()
            assert(math.abs(nx-200)<1e-8 and ny==-100,'host override did not reproject points')
        ''')

    def test_unchanged_route_is_lazy_and_zoom_resizes_existing_marks(self):
        self.check('''
            mod.GPSDrawNative(status)
            local before=#FRAMES
            local initial=mod.GPSNativeStats()
            local count=projections
            mod.GPSDrawNative(status)
            assert(projections==count and #FRAMES==before)
            assert(mod.GPSNativeStats().redraws==initial.redraws)
            scale=2 mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().redraws==initial.redraws+1)
            assert(shownDots()[1]:GetWidth()==2.5,'marks grew with native canvas zoom')
            canvas:SetSize(1200,600) mod.GPSDrawNative(status)
            local _,_,_,x,y=shownDots()[1]:GetPoint()
            assert(x==120 and y==-120)
        ''')

    def test_region_count_is_bounded_and_reused_for_long_routes(self):
        self.check('''
            status.route={}
            for i=1,1000 do
                status.route[i]={cont=2991,map=2521,wx=(i%2==0 and 950 or 50),wy=200+(i%5)}
            end
            mod.GPSDrawNative(status)
            local initial=mod.GPSNativeStats()
            assert(initial.drawn<=300 and initial.pooled<=300 and initial.drawn>200)
            local allocated=#FRAMES
            status.index=500 mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().pooled<=300 and #FRAMES==allocated)
            status.route={{cont=2991,map=2521,wx=100,wy=200}}
            status.index=1 mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().drawn==1 and #shownDots()==1)
            assert(#FRAMES==allocated,'route edits leaked drawing regions')
        ''')

    def test_world_stopped_closed_and_instance_filtered_routes_hide(self):
        self.check('''
            mod.GPSDrawNative(status)
            map:Hide()
            assert(hiddenCallbacks==1,'existing OnHide callback was replaced')
            assert(not mod.GPSNativeStats().shown)
            map:Show() mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().shown)
            host=947 mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown)
            host=2521 stitched=true mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown)
            stitched=false status.active=false mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown)
            status.active=true mod.instanceWorldHidden=true mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown)
            mod.instanceWorldHidden=false mod.instancePinsHidden=true mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown)
        ''')

    def test_crossing_segment_is_clipped_and_other_continents_layers_are_not_drawn(self):
        self.check('''
            status.route={
                {cont=2991,map=2521,wx=-500,wy=250},
                {cont=2991,map=2521,wx=1500,wy=250}
            }
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().drawn>2)
            for _,dot in ipairs(shownDots()) do
                local _,_,_,x,y=dot:GetPoint()
                assert(x>=0 and x<=1000 and y<=0 and y>=-500,'native marks escaped map bounds')
            end
            status.route={
                {cont=0,map=2521,wx=100,wy=200},
                {cont=2991,map=2521,wx=800,wy=200,layer=1458}
            }
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown and mod.GPSNativeStats().drawn==0)
        ''')

    def test_short_segments_sample_the_whole_path_and_projection_failures_do_not_bridge(self):
        self.check('''
            status.route={}
            for i=1,100 do status.route[i]={cont=2991,map=2521,wx=100+i,wy=200} end
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().drawn>5,'short road segments lost all intermediate marks')
            C_Map.GetMapPosFromWorldPos=function() return 2665,{x=.5,y=.5} end
            status.route={{cont=2991,map=2521,wx=100,wy=200}}
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown,'a point projected onto another map was drawn')
        ''')

    def test_secret_positions_are_not_used_and_new_canvas_reuses_own_regions(self):
        self.check('''
            mod.GPSDrawNative(status)
            local owner=shownDots()[1]:GetParent()
            local pooled=mod.GPSNativeStats().pooled
            canvas=CreateFrame('Frame',nil,map)
            canvas:SetSize(1000,500)
            mod.GPSDrawNative(status)
            assert(owner:GetParent()==canvas and mod.GPSNativeStats().pooled==pooled)
            assert(foreign:GetWidth()==37 and foreign:GetHeight()==41)
            ENABLE_SECRETS()
            status.route={{cont=2991,map=2521,wx=Secret(100),wy=200}}
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown)
            C_Map.GetMapPosFromWorldPos=function() return host,{x=Secret(.5),y=.5} end
            status.route={{cont=2991,map=2521,wx=100,wy=200}}
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown and #ERRORS==0)
        ''')

    def test_network_toggle_draws_without_active_route_and_uses_only_explicit_surface_edges(self):
        self.check('''
            networkOn=true
            mod.GPSRoadsShown=function() return networkOn end
            ns.GPSRoadData={networks={[2991]={nodes={
                [1]={wx=100,wy=100,links={[2]=true}},
                [2]={wx=900,wy=100,links={[1]=true}},
                [3]={wx=100,wy=300,piece='a',links={[4]=true}},
                [4]={wx=900,wy=300,piece='b',links={[3]=true}},
                [5]={wx=100,wy=500,tower={top=6},links={[6]=true}},
                [6]={wx=900,wy=500,links={[5]=true}},
                [7]={wx=-500,wy=200,links={[8]=true}},
                [8]={wx=1500,wy=200,links={[7]=true}}
            }}}}
            status.active=false
            local before=#FRAMES
            mod.GPSDrawNative(status)
            local network=FRAMES[before+1]
            local stats=mod.GPSNativeStats()
            assert(stats.networkShown and stats.networkDrawn>10 and not stats.shown and stats.drawn==0)
            assert(network:GetParent()==canvas)
            for _,region in ipairs(FRAMES) do
                if region:GetParent()==network and region:GetObjectType()=='Texture' and region:IsShown() then
                    local _,_,_,x,y=region:GetPoint()
                    assert(x>=0 and x<=1000 and (y==-50 or y==-100),
                        'native network invented a floor/stair link or escaped the map')
                end
            end
            local projected=projections
            mod.GPSDrawNative(status)
            assert(projections==projected and mod.GPSNativeStats().networkRedraws==stats.networkRedraws)
            networkOn=false mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().networkShown)
            networkOn=true mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().networkShown)
            map:Hide()
            assert(not mod.GPSNativeStats().networkShown,'network remained after map closed')
        ''')

    def test_large_network_has_separate_bounded_pool_and_does_not_replace_active_route(self):
        self.check('''
            networkOn=true
            mod.GPSRoadsShown=function() return networkOn end
            local nodes={}
            for i=1,1000 do
                nodes[i]={wx=(i%2==0 and 950 or 50),wy=100+(i%500),links={}}
                if i>1 then nodes[i].links[i-1]=true nodes[i-1].links[i]=true end
            end
            ns.GPSRoadData={networks={[2991]={nodes=nodes}}}
            mod.GPSDrawNative(status)
            local stats=mod.GPSNativeStats()
            assert(stats.shown and stats.drawn>2 and stats.pooled<=300)
            assert(stats.networkShown and stats.networkDrawn>600 and stats.networkPooled<=800)
            local allocated=#FRAMES
            status.index=2 mod.GPSDrawNative(status)
            assert(#FRAMES==allocated,'native network allocated regions on route-step change')
            networkOn=false mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().shown and not mod.GPSNativeStats().networkShown,
                'turning off network removed the active route')
            networkOn=true mod.GPSDrawNative(status)
            assert(#FRAMES==allocated)
            host=947 mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown and not mod.GPSNativeStats().networkShown)
        ''')


if __name__ == '__main__':
    unittest.main()
