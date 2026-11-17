"""Staged route cleanup is resumable and safe when a newer route cancels it."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / 'OpenMap/Map/Stitch.lua').read_text()
START = SOURCE.index('do\n\tlocal function RecyclePin')
END = SOURCE.index('\n-- a set with `build`', START)


class GPSRenderCleanupTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
            S={} tremove=table.remove
            function wipe(t)for k in pairs(t)do t[k]=nil end end
            dropped={}
            function DropAnchor(a)dropped[a]=(dropped[a]or 0)+1 end
            function Region(id)
                return {id=id,anchor='pin'..id,hidden=0,
                    Hide=function(self)self.hidden=self.hidden+1 end,
                    ClearAllPoints=function()end}
            end
            function Fixture()
                return {pins={Region(1),Region(2),Region(3)},
                    lines={Region(4),Region(5)},anchors={'a','b'},pinPool={},linePool={}}
            end
            function Check(s)
                assert(#s.pins==0 and #s.lines==0 and #s.anchors==0)
                assert(#s.pinPool==3 and #s.linePool==2)
                local seen={}
                for _,pool in ipairs({s.pinPool,s.linePool})do
                    for _,p in ipairs(pool)do
                        assert(not seen[p]and p.hidden==1,'a region was recycled twice')
                        seen[p]=true
                    end
                end
                for _,a in ipairs({'pin1','pin2','pin3','a','b'})do assert(dropped[a]==1)end
            end
        ''')
        self.lua.execute(SOURCE[START:END])

    def test_unbudgeted_cleanup_retains_existing_behavior(self):
        self.lua.execute('s=Fixture() S.ClearPinSet(s) Check(s)')

    def test_cleanup_yields_between_regions(self):
        self.lua.execute('''
            s=Fixture()
            local co=coroutine.create(function()S.ClearPinSet(s,function()coroutine.yield()end)end)
            local slices=0
            while coroutine.status(co)~='dead'do
                local before=#s.pins+#s.lines+#s.anchors
                assert(coroutine.resume(co))slices=slices+1
                assert(before-(#s.pins+#s.lines+#s.anchors)<=1)
            end
            assert(slices==8)Check(s)
        ''')

    def test_cancelled_partial_cleanup_can_restart_without_duplicate_pool_entries(self):
        for count in (1, 3, 4, 6):
            with self.subTest(slices=count):
                self.setUp()
                self.lua.execute('''
                    s=Fixture()
                    co=coroutine.create(function()S.ClearPinSet(s,function()coroutine.yield()end)end)
                ''')
                for _ in range(count):
                    self.lua.execute('assert(coroutine.resume(co))')
                self.lua.execute('co=nil S.ClearPinSet(s) Check(s)')


if __name__ == '__main__':
    unittest.main()
