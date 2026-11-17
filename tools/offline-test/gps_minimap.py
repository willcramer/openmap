"""Actual minimap Lua projection, clipping, bounded work and passive pooling.

Run: python -P tools/offline-test/gps_minimap.py
"""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]


class GPSMinimapTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((Path(__file__).with_name('stub.lua')).read_text())
        self.lua.execute('''
            CPU,NOW,RADIUS,RAWX,RAWY,FACING=0,0,100,0,0,0
            ROTATING,IGNORED,INSIDE,SHAPE=false,false,false,'ROUND'
            Minimap=CreateFrame('Frame') Minimap:SetSize(200,200) Minimap:Show()
            local factory=CreateFrame
            ALLOCATIONS=0
            CreateFrame=function(...)
                local frame=factory(...)
                local lineFactory=frame.CreateLine
                frame.CreateLine=function(self,...)
                    ALLOCATIONS=ALLOCATIONS+1
                    local line=lineFactory(self,...)
                    line.SetStartPoint=function(self,...)self.start={...}end
                    line.SetEndPoint=function(self,...)self.finish={...}end
                    line.SetThickness=function(self,n)self.thickness=n end
                    line.SetColorTexture=function(self,...)self.solid={...}end
                    line.SetVertexColor=function(self,...)self.color={...}end
                    local show,hide=line.Show,line.Hide
                    line.Show=function(self)CPU=CPU+.02 show(self)end
                    line.Hide=function(self)CPU=CPU+.005 hide(self)end
                    return line
                end
                return frame
            end
            function debugprofilestop()return CPU end
            function GetTime()return NOW end
            function GetPlayerFacing()return FACING end
            function GetCVarBool()return ROTATING end
            function GetMinimapShape()return SHAPE end
            function IsInInstance()return INSIDE end
            C_Minimap={GetViewRadius=function()return RADIUS end,IsRotateMinimapIgnored=function()return IGNORED end}
            C_Map={GetWorldPosFromMapPos=function(map,p)
                return 1,{x=(.5-p.y)*1000,y=(p.x-.5)*1000}
            end}
            function CreateVector2D(x,y)return{x=x,y=y}end
            mod={defaults={},db={gpsRoutes={}}}
            ns={GetModule=function()return mod end,MapStitch={},L=setmetatable({},{__index=function(_,k)return k end}),Safe={
                Value=function(v)if issecretvalue and issecretvalue(v)then return nil end return v end,
                XY=function(p)return p.x,p.y end,
                Call=function(fn,...)if type(fn)~='function'then return end local ok,v=pcall(fn,...)if ok then return v end end
            }}
            function P(e,n)return{map=1,cont=1,wx=n,wy=e}end
            status={active=true,index=1,player=P(0,0),route={P(20,0),P(20,60),P(-20,60)}}
            mod.GPSOtherFloor=function(a,b)return a.piece and b.piece and a.piece~=b.piece end
        ''')
        self.lua.execute((ROOT / 'OpenMap/Map/GPS.lua').read_text(), 'OpenMap', self.lua.globals().ns)
        self.lua.execute('''
            mod.GPSStatus=function()return status end
            mod.GPSPlayer=function()return 1,.5+RAWY/1000,.5-RAWX/1000,nil,nil,1,RAWX,RAWY,0 end
        ''')
        self.lua.execute((ROOT / 'OpenMap/Map/GPSMinimap.lua').read_text(), 'OpenMap', self.lua.globals().ns)
        self.lua.execute('''
            function Lines()
                local out={}
                for _,frame in ipairs(FRAMES)do
                    local visible,parent=frame:IsShown(),frame:GetParent()
                    while parent do visible=visible and parent:IsShown()parent=parent:GetParent()end
                    if frame:GetObjectType()=='Line'and visible and frame.start then out[#out+1]=frame end
                end
                return out
            end
            function Drain()
                for _=1,1000 do
                    mod.GPSRunMinimapDrawing(1)
                    NOW=NOW+1/120
                    if not mod.GPSMinimapDrawingPending()then return end
                end
                error('minimap drawing did not finish')
            end
            function Draw()mod.GPSDrawMinimap(status)Drain()end
        ''')

    def test_north_up_projection_retains_bends_and_passive_owned_frame(self):
        self.lua.execute('''
            local w,h=Minimap:GetSize()
            Draw()
            local lines=Lines()
            assert(#lines==3 and mod.GPSMinimapStats().drawn==3)
            assert(lines[1].start[3]==0 and lines[1].start[4]==0)
            assert(math.abs(lines[1].finish[3]-20)<1e-8 and math.abs(lines[1].finish[4])<1e-8)
            assert(math.abs(lines[2].start[3]-20)<1e-8 and math.abs(lines[2].finish[4]-60)<1e-8)
            assert(lines[3].start[4]==lines[3].finish[4]and lines[3].start[3]>lines[3].finish[3])
            assert(lines[1].thickness==2 and lines[1].color[1]==.15 and lines[1].color[2]==1)
            assert(Minimap:GetWidth()==w and Minimap:GetHeight()==h,'minimap layout changed')
            assert(not lines[1]:GetParent():IsMouseEnabled(),'overlay intercepts minimap clicks')
        ''')

    def test_round_clipping_retains_segments_crossing_with_both_ends_outside(self):
        self.lua.execute('''
            status.route={P(-200,20),P(200,20)}status.index=1
            Draw()
            local lines=Lines()
            assert(#lines==2,'crossing segment disappeared')
            local road=lines[2]
            assert(road.start[3]<0 and road.finish[3]>0)
            for _,line in ipairs(lines)do
                for _,p in ipairs({line.start,line.finish})do assert((p[3]/97)^2+(p[4]/97)^2<=1.00000001)end
            end
        ''')

    def test_square_clipping_and_unknown_shapes_stay_inside_safe_circle(self):
        self.lua.execute('''
            status.route={P(200,200)}SHAPE='SQUARE'Draw()
            local line=Lines()[1]
            assert(math.abs(line.finish[3]-97)<1e-8 and math.abs(line.finish[4]-97)<1e-8)
            SHAPE='CORNER-TOPLEFT'NOW=NOW+.1 Drain()
            line=Lines()[1]
            assert(math.abs(line.finish[3]^2+line.finish[4]^2-97^2)<1e-5)
        ''')

    def test_rotation_uses_facing_and_respects_client_ignore_rotation(self):
        self.lua.execute('''
            status.route={P(0,60)}ROTATING=true FACING=math.pi/2 Draw()
            local line=Lines()[1]
            assert(math.abs(line.finish[3]-60)<1e-8 and math.abs(line.finish[4])<1e-8)
            IGNORED=true NOW=NOW+.1 Drain()
            line=Lines()[1]
            assert(math.abs(line.finish[3])<1e-8 and math.abs(line.finish[4]-60)<1e-8)
        ''')

    def test_zoom_resize_and_movement_reuse_line_pool(self):
        self.lua.execute('''
            Draw()
            RADIUS=200 NOW=NOW+.1 Drain()
            assert(math.abs(Lines()[1].finish[3]-10)<1e-8)
            local warmed=ALLOCATIONS
            RAWY=10 NOW=NOW+.1 Drain()
            assert(math.abs(Lines()[1].finish[3]-5)<1e-8)
            NOW=NOW+.1 Drain()
            assert(ALLOCATIONS==warmed,'unchanged geometry allocated regions')
            Minimap:SetSize(300,300)NOW=NOW+.1 Drain()
            assert(math.abs(Lines()[1].finish[3]-7.5)<1e-8)
        ''')

    def test_progress_removes_completed_segments_without_rebuilding_index(self):
        self.lua.execute('''
            Draw()
            local builds=mod.GPSMinimapStats().indexBuilds
            status.index=3 RAWY=20 NOW=NOW+.1 mod.GPSDrawMinimap(status)Drain()
            assert(#Lines()==1 and mod.GPSMinimapStats().indexBuilds==builds)
        ''')

    def test_stop_toggle_instance_unknown_and_missing_api_hide(self):
        cases = (
            'status.active=false mod.GPSDrawMinimap(status)',
            'mod.GPSSetMinimapShown(false)',
            'INSIDE=true',
            'status.player.unknown=true',
            'status.player.ambiguous=true',
            'C_Minimap.GetViewRadius=nil',
            'C_Map.GetWorldPosFromMapPos=nil',
            'Minimap:Hide()',
        )
        for change in cases:
            with self.subTest(change=change):
                self.setUp()
                self.lua.execute('Draw()assert(#Lines()>0)'+change+' NOW=NOW+.1 Drain()assert(#Lines()==0)')

    def test_floor_and_continent_guards_never_join_hidden_points(self):
        self.lua.execute('''
            status.player.layer=2
            status.route={P(20,0),P(20,30),P(20,60),P(-20,60)}
            status.route[1].layer=2 status.route[2].layer=3 status.route[3].layer=2 status.route[4].cont=9
            Draw()
            assert(#Lines()==1,'hidden floor/continent points became straight shortcuts')
            status.player.piece='upper' status.route[1].piece='lower'NOW=NOW+.1 Drain()
            assert(#Lines()==0)
        ''')

    def test_explicit_surface_roads_do_not_show_on_undercity_floor(self):
        self.lua.execute('''
            status.route={P(20,0),P(20,60)}
            for _,point in ipairs(status.route)do point.layer=false end
            Draw()
            assert(#Lines()==2,'ordinary outdoor surface route was hidden')
            status.player.layer=1458 NOW=NOW+.1 mod.GPSDrawMinimap(status)Drain()
            assert(#Lines()==0,'surface roads appeared on the underground floor')
            status.player.layer=false NOW=NOW+.1 mod.GPSDrawMinimap(status)Drain()
            assert(#Lines()==2,'returning to the surface did not restore its route')
        ''')

    def test_secret_radius_and_position_are_not_used_in_arithmetic(self):
        self.lua.execute('''
            Draw()
            local secret=setmetatable({},{__add=function()error('secret arithmetic')end,__lt=function()error('secret comparison')end})
            issecretvalue=function(v)return v==secret end
            C_Minimap.GetViewRadius=function()return secret end
            NOW=NOW+.1 Drain()assert(#Lines()==0)
            C_Minimap.GetViewRadius=function()return 100 end
            mod.GPSPlayer=function()return 1,0,0,nil,nil,1,secret,0 end
            NOW=NOW+.1 Drain()assert(#Lines()==0)
        ''')

    def test_large_route_build_is_cooperative_and_nearby_queries_are_bounded(self):
        self.lua.execute('''
            status.route={}
            for i=1,24000 do status.route[i]=P(i*10,0)end
            mod.GPSDrawMinimap(status)
            mod.GPSRunMinimapDrawing(1)
            assert(mod.GPSMinimapDrawingPending(),'large route indexing blocked one frame')
            Drain()
            local info=mod.GPSMinimapStats()
            assert(info.querySegments<=24 and info.queryNodes<30,'movement scanned the entire route')
            assert(info.drawn<=256 and info.allocated<=512)
            RAWY=40 NOW=NOW+.1 Drain()
            assert(mod.GPSMinimapStats().indexBuilds==1)
        ''')

    def test_dense_nearby_route_has_bounded_pool_and_cpu_slices(self):
        self.lua.execute('''
            status.route={}
            for i=1,2000 do status.route[i]=P(i%2==0 and 10 or 20,i%80)end
            mod.GPSDrawMinimap(status)
            local frames=0
            repeat
                local before=CPU
                mod.GPSRunMinimapDrawing(1)
                assert(CPU-before<=1.051,'minimap worker exceeded budget plus one line operation')
                NOW=NOW+1/120 frames=frames+1
            until not mod.GPSMinimapDrawingPending()
            assert(frames>2 and #Lines()==256)
            assert(ALLOCATIONS<=256)
        ''')

    def test_replacement_stop_and_floor_change_cancel_partial_staging(self):
        self.lua.execute('''
            Draw()
            local old=Lines()[1]:GetParent()
            status.route={}
            for i=1,2000 do status.route[i]=P(i%2==0 and 10 or 20,i%80)end
            mod.GPSDrawMinimap(status)
            mod.GPSRunMinimapDrawing(1)
            assert(mod.GPSMinimapDrawingPending()and not old:IsShown(),'obsolete route remained visible')
            status.route={P(0,30)}NOW=NOW+.1 mod.GPSDrawMinimap(status)Drain()
            assert(#Lines()==1 and math.abs(Lines()[1].finish[4]-30)<1e-8)
            status.player.layer=2 status.route[1].layer=3 NOW=NOW+.1 Drain()
            assert(#Lines()==0)
            status.active=false mod.GPSDrawMinimap(status)Drain()
            assert(#Lines()==0 and not mod.GPSMinimapDrawingPending())
        ''')

    def test_continued_movement_finishes_work_instead_of_restarting_each_poll(self):
        self.lua.execute('''
            status.route={}
            for i=1,2000 do status.route[i]=P(i%2==0 and 10 or 20,i%80)end
            mod.GPSDrawMinimap(status)
            for _=1,100 do
                RAWY=RAWY+.1 NOW=NOW+1/120
                mod.GPSRunMinimapDrawing(.2)
            end
            assert(mod.GPSMinimapStats().redraws>0,'moving player starved staged publication')
            assert(ALLOCATIONS<=512)
        ''')

    def test_world_axes_come_from_map_transform_not_assumed_coordinate_signs(self):
        self.lua.execute('''
            C_Map.GetWorldPosFromMapPos=function(map,p)return 1,{x=(.5-p.x)*1000,y=(p.y-.5)*1000}end
            status.route={{map=1,cont=1,wx=-20,wy=0},{map=1,cont=1,wx=-20,wy=-60}}
            Draw()
            local lines=Lines()
            assert(#lines==2 and math.abs(lines[1].finish[3]-20)<1e-8)
            assert(math.abs(lines[2].finish[4]-60)<1e-8)
        ''')

    def test_shape_mode_and_floor_changes_cannot_publish_stale_staging(self):
        self.lua.execute('''
            Draw()
            status.route={}
            for i=1,2000 do status.route[i]=P(i%2==0 and 10 or 20,i%80)end
            mod.GPSDrawMinimap(status)
            for _=1,10 do
                mod.GPSRunMinimapDrawing(.1)
                NOW=NOW+1/120
                if ALLOCATIONS>5 then break end
            end
            SHAPE='SQUARE'ROTATING=true FACING=math.pi/2 NOW=NOW+.1
            mod.GPSRunMinimapDrawing(.1)
            assert(#Lines()==0,'stale shape/rotation was published')
            Drain()
            assert(#Lines()==256)
            status.player.layer=2 mod.GPSDrawMinimap(status)
            assert(#Lines()==0,'floor change left stale overlay visible')
        ''')

    def test_disabling_or_missing_api_during_indexing_can_resume_cleanly(self):
        for suspend, resume in (
            ('mod.GPSSetMinimapShown(false)', 'mod.GPSSetMinimapShown(true)'),
            ('C_Minimap.GetViewRadius=nil', 'C_Minimap.GetViewRadius=function()return RADIUS end'),
        ):
            with self.subTest(suspend=suspend):
                self.setUp()
                self.lua.execute('''
                    status.route={}
                    for i=1,24000 do status.route[i]=P(i*10,0)end
                    mod.GPSDrawMinimap(status)mod.GPSRunMinimapDrawing(1)
                    assert(mod.GPSMinimapDrawingPending())
                ''' + suspend + '''
                    NOW=NOW+.1 mod.GPSRunMinimapDrawing(1)
                    assert(not mod.GPSMinimapDrawingPending())
                ''' + resume + '''
                    NOW=NOW+.1 mod.GPSDrawMinimap(status)Drain()
                    assert(mod.GPSMinimapStats().drawn>1,'resumed index omitted road segments')
                ''')

    def test_cold_room_data_is_not_built_by_minimap_position_reads(self):
        self.lua.execute('''
            local read=mod.GPSPlayer
            mod.GPSRoomsReady=function()return false end
            mod.GPSPlayer=function()error('cold room lookup on main thread')end
            Draw()
            assert(#Lines()==0 and not mod.GPSMinimapDrawingPending())
            mod.GPSRoomsReady=function()return true end
            mod.GPSPlayer=read
            NOW=NOW+.1 Draw()
            assert(#Lines()==3)
        ''')


if __name__ == '__main__':
    unittest.main()
