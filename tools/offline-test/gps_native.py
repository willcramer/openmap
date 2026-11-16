"""Native Zephras GPS lines and waypoint nodes: projection, clipping and reuse.

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
            local factory=CreateFrame
            CreateFrame=function(...)
                local frame=factory(...)
                local lineFactory,textureFactory=frame.CreateLine,frame.CreateTexture
                frame.CreateLine=function(self,...)
                    local line=lineFactory(self,...)
                    line.SetStartPoint=function(self,...) self.start={...} end
                    line.SetEndPoint=function(self,...) self.finish={...} end
                    line.SetThickness=function(self,n) self.thickness=n end
                    line.SetColorTexture=function(self,...) self.solid={...} end
                    line.SetVertexColor=function(self,...) self.color={...} end
                    return line
                end
                frame.CreateTexture=function(self,...)
                    local texture=textureFactory(self,...)
                    texture.SetVertexColor=function(self,...) self.color={...} end
                    return texture
                end
                return frame
            end
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
                    if frame:GetParent()==canvas and frame~=foreign and frame:GetObjectType()=='Frame'
                        and frame:GetFrameLevel()==canvas:GetFrameLevel()+10 then return frame end
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
            function shownLines()
                local out={}
                for _,frame in ipairs(FRAMES) do
                    if frame:GetParent()==nativeRoot() and frame:GetObjectType()=='Line' and frame:IsShown() then
                        out[#out+1]=frame
                    end
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
            assert(stats.shown and stats.drawn==2 and stats.lines==1)
            local owner=nativeRoot()
            assert(owner and owner:GetParent()==canvas)
            local first=shownDots()[1]
            local point,relative,corner,x,y=first:GetPoint()
            assert(point=='CENTER' and relative==owner and corner=='TOPLEFT' and x==100 and y==-100)
            local line=shownLines()[1]
            assert(line.start[3]==100 and line.start[4]==-100)
            assert(line.finish[3]==800 and line.finish[4]==-100)
            assert(line.thickness==3 and line.solid[4]==1)
            assert(line.color[1]==.15 and line.color[2]==1 and line.color[3]==.25)
            assert(first:GetWidth()==7 and shownDots()[2]:GetWidth()==10,'waypoint/target nodes not distinct')
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
            assert(shownDots()[1]:GetWidth()==3.5,'nodes grew with native canvas zoom')
            assert(shownLines()[1].thickness==1.5,'line grew with native canvas zoom')
            canvas:SetSize(1200,600) mod.GPSDrawNative(status)
            local _,_,_,x,y=shownDots()[1]:GetPoint()
            assert(x==120 and y==-120)
        ''')

    def test_continuous_lines_follow_each_bend_and_nodes_mark_real_waypoints(self):
        self.check('''
            status.route={
                {cont=2991,map=2521,wx=100,wy=100},
                {cont=2991,map=2521,wx=400,wy=100},
                {cont=2991,map=2521,wx=400,wy=600},
                {cont=2991,map=2521,wx=800,wy=600}
            }
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().drawn==4 and mod.GPSNativeStats().lines==3)
            local lines=shownLines()
            assert(lines[1].start[3]==100 and lines[1].finish[3]==400)
            assert(lines[1].start[4]==-50 and lines[1].finish[4]==-50)
            assert(lines[2].start[3]==400 and lines[2].finish[3]==400)
            assert(lines[2].start[4]==-50 and lines[2].finish[4]==-300)
            assert(lines[3].start[3]==400 and lines[3].finish[3]==800)
            assert(lines[3].start[4]==-300 and lines[3].finish[4]==-300)
            local dots=shownDots()
            for i,dot in ipairs(dots) do
                local _,_,_,x,y=dot:GetPoint()
                assert(x==status.route[i].wx and y==-status.route[i].wy/2)
                assert(dot:GetWidth()==(i==4 and 10 or 7))
                assert(dot.color[1]==.15 and dot.color[2]==1 and dot.color[3]==.25)
            end
        ''')

    def test_player_head_moves_without_reprojecting_the_tail_and_completed_edges_disappear(self):
        self.check('''
            status.player={cont=2991,map=2521,wx=50,wy=200}
            mod.GPSDrawNative(status)
            local before=mod.GPSNativeStats()
            assert(before.lines==2 and before.headShown)
            local allocated,count=#FRAMES,projections
            status.player.wx=75
            mod.GPSDrawNative(status)
            local after=mod.GPSNativeStats()
            assert(after.redraws==before.redraws and after.headUpdates==before.headUpdates+1)
            assert(projections==count+1 and #FRAMES==allocated,'moving head rebuilt the tail or allocated regions')
            local head=shownLines()[2]
            assert(head.start[3]==75 and head.finish[3]==100)
            mod.GPSDrawNative(status)
            assert(projections==count+1 and mod.GPSNativeStats().headUpdates==after.headUpdates)
            status.index=2
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().lines==1 and mod.GPSNativeStats().drawn==1)
            head=shownLines()[1]
            assert(head.start[3]==75 and head.finish[3]==800,'a completed route edge remained')
            status.player=nil
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().headShown and mod.GPSNativeStats().lines==0)
            assert(mod.GPSNativeStats().drawn==1,'missing player removed the known remaining target')
            assert(#FRAMES==allocated)
        ''')

    def test_head_does_not_join_another_continent_or_unconfirmed_floor(self):
        self.check('''
            status.player={cont=0,wx=50,wy=200}
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().headShown and mod.GPSNativeStats().lines==1)
            status.player.cont=2991
            status.player.ambiguous=true
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().headShown)
            status.player.ambiguous=nil
            mod.GPSOtherFloor=function()return true end
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().headShown)
            mod.GPSOtherFloor=function()return false end
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().headShown)
            status.player.layer=false
            status.route={
                {cont=2991,map=2521,wx=100,wy=200,layer=true},
                {cont=2991,map=2521,wx=800,wy=200,layer=true}
            }
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().headShown and mod.GPSNativeStats().lines==1)
        ''')

    def test_projection_gap_breaks_the_line_and_zero_length_edges_are_skipped(self):
        self.check('''
            status.route={
                {cont=2991,map=2521,wx=100,wy=200},
                {cont=0,map=2521,wx=400,wy=200},
                {cont=2991,map=2521,wx=800,wy=200},
                {cont=2991,map=2521,wx=800,wy=200}
            }
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().lines==0 and mod.GPSNativeStats().drawn==3,
                'projection failure was bridged or zero-length edge was drawn')
            status.player={cont=2991,map=2521,wx=100,wy=200}
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().headShown,'zero-length player connector was drawn')
        ''')

    def test_oversized_input_stops_at_the_bound_without_shortcutting_to_the_target(self):
        self.check('''
            status.route={}
            for i=1,25002 do
                status.route[i]={cont=2991,map=2521,wx=(i%2==0 and 950 or 50),wy=200+(i%5)}
            end
            mod.GPSDrawNative(status)
            local stats=mod.GPSNativeStats()
            assert(stats.pointLimit==25000 and stats.drawn==25000 and stats.lines==24999)
            assert(stats.pooled==25000 and stats.linePooled==24999)
            assert(shownDots()[25000]:GetWidth()==7,'truncated input invented a target shortcut')
        ''')

    def test_region_count_is_bounded_and_reused_for_long_routes(self):
        self.check('''
            status.route={}
            for i=1,1000 do
                status.route[i]={cont=2991,map=2521,wx=(i%2==0 and 950 or 50),wy=200+(i%5)}
            end
            mod.GPSDrawNative(status)
            local initial=mod.GPSNativeStats()
            assert(initial.drawn==1000 and initial.pooled==1000 and initial.lines==999,
                'long route lost waypoint nodes or shortcut its bends')
            local allocated=#FRAMES
            status.index=500 mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().pooled==1000 and mod.GPSNativeStats().lines==500 and #FRAMES==allocated)
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
            assert(mod.GPSNativeStats().drawn==0 and mod.GPSNativeStats().lines==1)
            local line=shownLines()[1]
            assert(line.start[3]==0 and line.finish[3]==1000 and line.start[4]==-125)
            status.route={
                {cont=0,map=2521,wx=100,wy=200},
                {cont=2991,map=2521,wx=800,wy=200,layer=1458}
            }
            mod.GPSDrawNative(status)
            assert(not mod.GPSNativeStats().shown and mod.GPSNativeStats().drawn==0)
        ''')

    def test_short_segments_retain_every_node_and_projection_failures_do_not_bridge(self):
        self.check('''
            status.route={}
            for i=1,100 do status.route[i]={cont=2991,map=2521,wx=100+i,wy=200} end
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().drawn==100 and mod.GPSNativeStats().lines==99,
                'short road segments lost intermediate waypoints')
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
            assert(stats.networkShown and stats.networkDrawn>10 and stats.networkNodesDrawn==6
                and not stats.shown and stats.drawn==0)
            assert(network:GetParent()==canvas)
            for _,region in ipairs(FRAMES) do
                if region:GetParent()==network and region:GetObjectType()=='Texture' and region:IsShown() then
                    local _,_,_,x,y=region:GetPoint()
                    assert(x>=0 and x<=1000,'native network escaped the map')
                    if region:GetWidth()==3 then
                        assert(y==-50 or y==-100,'native network invented a floor/stair link')
                    else
                        assert(region:GetWidth()==6 and (x==100 or x==900),
                            'actual node marker does not match a source node')
                    end
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
            assert(stats.shown and stats.drawn==2 and stats.pooled==2 and stats.lines==1)
            assert(stats.networkShown and stats.networkDrawn>600 and stats.networkPooled<=800)
            assert(stats.networkNodesDrawn==500 and stats.networkNodesPooled==500)
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

    def test_real_network_nodes_include_isolated_points_and_ignore_other_native_layers(self):
        self.check('''
            mod.GPSRoadsShown=function()return true end
            status.active=false
            ns.GPSRoadData={networks={[2991]={nodes={
                [1]={wx=123,wy=247,links={}},
                [2]={wx=321,wy=765,layer=2665,links={}},
                [3]={wx=1500,wy=200,links={}}
            }}}}
            local before=#FRAMES
            mod.GPSDrawNative(status)
            local owner=FRAMES[before+1]
            local stats=mod.GPSNativeStats()
            assert(stats.networkShown and stats.networkDrawn==0 and stats.networkNodesDrawn==1)
            local count=0
            for _,region in ipairs(FRAMES)do
                if region:GetParent()==owner and region:GetObjectType()=='Texture'and region:IsShown()then
                    count=count+1
                    local _,_,_,x,y=region:GetPoint()
                    assert(x==123 and y==-123.5 and region:GetWidth()==6)
                    assert(region.color[1]==1 and region.color[2]==.8 and region.color[3]==.35)
                end
            end
            assert(count==1,'isolated source node did not have an actual marker')
            scale=2 mod.GPSDrawNative(status)
            for _,region in ipairs(FRAMES)do
                if region:GetParent()==owner and region:GetObjectType()=='Texture'and region:IsShown()then
                    assert(region:GetWidth()==3,'source node marker grew with zoom')
                end
            end
        ''')

    def test_saved_trail_nodes_and_links_refresh_after_save_delete_without_touching_navigation(self):
        self.check('''
            mod.GPSRoadsShown=function()return true end
            local revision=0
            mod.GPSRoadsRevision=function()return revision end
            mod.GPSRecordedPoint=function(sample)return sample.valid~=false and sample or nil end
            ns.GPSRoadData={networks={[2991]={nodes={}}}}
            mod.db.gpsRoutes={Trail={points={
                {cont=2991,wx=100,wy=100},
                {cont=2991,wx=150,wy=100},
                {valid=false},
                {cont=2991,wx=200,wy=100},
                {cont=2991,wx=250,wy=100,piece='other floor'},
                {cont=2991,wx=800,wy=100,piece='other floor'},
                {cont=0,wx=500,wy=100},
                {cont=2991,wx=300,wy=100}
            }}}
            mod.GPSDrawNative(status)
            local before=mod.GPSNativeStats()
            assert(before.shown and before.drawn==2 and before.lines==1)
            assert(before.networkNodesDrawn==6 and before.networkDrawn>1)
            local owner
            for _,frame in ipairs(FRAMES)do
                if frame:GetObjectType()=='Frame'and frame:GetParent()==canvas
                    and frame:GetFrameLevel()==canvas:GetFrameLevel()+9 then owner=frame end
            end
            for _,region in ipairs(FRAMES)do
                if region:GetParent()==owner and region:GetObjectType()=='Texture'and region:IsShown()then
                    local _,_,_,x,y=region:GetPoint()
                    if region:GetWidth()==3 then
                        assert(x>=100 and x<=150 and y==-50,'saved display bridged a gap or floor')
                    else
                        assert(region:GetWidth()==7 and region.color[1]==1 and region.color[2]==.45)
                    end
                end
            end
            local projected=projections
            mod.GPSDrawNative(status)
            assert(projections==projected and mod.GPSNativeStats().networkRedraws==before.networkRedraws)
            mod.db.gpsRoutes.Trail=nil revision=revision+1
            mod.GPSDrawNative(status)
            local after=mod.GPSNativeStats()
            assert(not after.networkShown and after.networkNodesDrawn==0 and after.networkDrawn==0)
            assert(after.shown and after.redraws==before.redraws and after.lines==1,
                'deleting a saved road disturbed active navigation')
            mod.db.gpsRoutes={New={points={{cont=2991,wx=200,wy=200},{cont=2991,wx=250,wy=200}}}}
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().networkShown and mod.GPSNativeStats().networkNodesDrawn==2,
                'profile replacement did not invalidate the saved-road display')
        ''')

    def test_manual_nodes_long_links_and_selected_endpoint_refresh_without_route_changes(self):
        self.check('''
            mod.GPSRoadsShown=function()return true end
            local base={cont=2991,wx=100,wy=500,links={}}
            ns.GPSRoadData={networks={[2991]={nodes={[1]=base}}}}
            local a,b={cont=2991,wx=500,wy=500},{cont=2991,wx=900,wy=500}
            manual={nodes={['m:1']=a,['m:2']=b},links={
                {a='b:2991:1',b='m:1'},{a='m:1',b='m:2'}},revision=1}
            selected='m:1'
            function mod.GPSRoadEditSnapshot()return manual end
            function mod.GPSRoadEditPoint(ref)return ref=='b:2991:1'and base or manual.nodes[ref]end
            function mod.GPSRoadSelected()return selected end
            function NetworkMarks()
                local marks={}
                for _,frame in ipairs(FRAMES)do
                    local owner=frame:GetParent()
                    if owner and owner:GetParent()==canvas and owner:GetFrameLevel()==canvas:GetFrameLevel()+9
                        and frame:GetObjectType()=='Texture'and frame:IsShown()then marks[#marks+1]=frame end
                end
                return marks
            end
            mod.GPSDrawNative(status)
            local stats=mod.GPSNativeStats()
            assert(stats.networkNodesDrawn==3 and stats.networkDrawn>50)
            assert(stats.shown and stats.drawn==2 and stats.lines==1)
            local cyan,white,gold,links=0,0,0,0
            for _,mark in ipairs(NetworkMarks())do
                local _,_,_,x,y=mark:GetPoint()
                assert(y==-250)
                if mark:GetWidth()==3 then
                    links=links+1 assert(mark.color[1]==.25 and x>=100 and x<=900)
                elseif mark:GetWidth()==10 then
                    white=white+1 assert(x==500 and mark.color[1]==1 and mark.color[2]==1)
                elseif mark.color[1]==.25 then cyan=cyan+1 assert(x==900)
                else gold=gold+1 assert(x==100)end
            end
            assert(cyan==1 and white==1 and gold==1 and links>50)
            local projected,allocated=projections,#FRAMES
            mod.GPSDrawNative(status)
            assert(projections==projected and #FRAMES==allocated)
            selected='b:2991:1' mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().networkNodesDrawn==3)
            for _,mark in ipairs(NetworkMarks())do
                if mark:GetWidth()==10 then local _,_,_,x=mark:GetPoint()assert(x==100)end
            end
            manual.nodes['m:1']=nil manual.links={} manual.revision=2 selected=nil
            mod.GPSDrawNative(status)
            local after=mod.GPSNativeStats()
            assert(after.networkNodesDrawn==2 and after.networkDrawn==0)
            assert(after.shown and after.redraws==stats.redraws and after.lines==1,
                'manual topology edits changed the active route drawing')
            assert(base.u==nil and a.x==nil and b.map==nil,'view modified stored coordinates')
            manual={nodes={},links={},revision=0}
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().networkNodesDrawn==1,'profile change retained manual nodes')
        ''')

    def test_manual_selected_node_keeps_its_budget_slot_and_unsafe_links_are_not_drawn(self):
        self.check('''
            mod.GPSRoadsShown=function()return true end
            status.active=false
            ns.GPSRoadData={networks={}}
            manual={nodes={},links={},revision=1}
            for i=1,1500 do manual.nodes['m:'..i]={cont=2991,wx=i/1501*1000,wy=500}end
            selected='m:1499'
            function mod.GPSRoadEditSnapshot()return manual end
            function mod.GPSRoadEditPoint(ref)return manual.nodes[ref]end
            function mod.GPSRoadSelected()return selected end
            mod.GPSDrawNative(status)
            local stats=mod.GPSNativeStats()
            assert(stats.networkNodesDrawn==500 and stats.networkNodesPooled==500)
            local white=0
            for _,frame in ipairs(FRAMES)do
                if frame:GetObjectType()=='Texture'and frame:IsShown()and frame:GetWidth()==10 and frame.color then
                    white=white+1
                    local _,_,_,x=frame:GetPoint()assert(math.abs(x-1499/1501*1000)<1e-8)
                end
            end
            assert(white==1,'crowded native network omitted the selected node')
            manual={nodes={
                ['m:1']={cont=2991,wx=100,wy=300,layer=2521},
                ['m:2']={cont=2991,wx=900,wy=300,layer=2665},
                ['m:3']={cont=0,wx=500,wy=300},
                ['m:4']={cont=2991,wx=800,wy=300,layer=2521,ambiguous=true}
            },links={{a='m:1',b='m:2'},{a='m:1',b='m:3'},
                {a='m:1',b='missing'},{a='m:1',b='m:4'}},revision=2}
            selected=nil
            mod.GPSDrawNative(status)
            assert(mod.GPSNativeStats().networkNodesDrawn==2 and mod.GPSNativeStats().networkDrawn==0)
        ''')


if __name__ == '__main__':
    unittest.main()
