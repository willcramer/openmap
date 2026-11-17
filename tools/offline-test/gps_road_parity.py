"""Optional differential audit against a separately installed Forever Maps Graph.

FOREVER_MAPS_REFERENCE=/path/to/ForeverMaps python -P tools/offline-test/gps_road_parity.py

No reference source is bundled, modified or imported into OpenMap. The local file
is a test oracle in a Lua state without filesystem, network, OS or Python access.
Without the environment variable, these optional tests skip; gps_roads.py keeps
the independently authored, required topology and constraint regression tests.
"""
import hashlib
import math
import os
from pathlib import Path
import random
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = os.environ.get("FOREVER_MAPS_REFERENCE")


@unittest.skipUnless(REFERENCE, "set FOREVER_MAPS_REFERENCE to a local reference installation")
class RoadParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graph_path = Path(REFERENCE) / "Routing/Graph.lua"
        if not graph_path.is_file():
            raise AssertionError("FOREVER_MAPS_REFERENCE must contain Routing/Graph.lua")
        toc_path = Path(REFERENCE) / "ForeverMaps.toc"
        version = next((line.partition(":")[2].strip() for line in toc_path.read_text().splitlines()
                        if line.startswith("## Version:")), "unknown") if toc_path.is_file() else "unknown"
        print("Reference version:", version, "Graph SHA256:", hashlib.sha256(graph_path.read_bytes()).hexdigest())
        lua = cls.lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False, register_builtins=False)
        lua.execute("""
            os, io, package, python, debug = nil, nil, nil, nil, nil
            require, dofile, loadfile, load, loadstring, getfenv, setfenv = nil,nil,nil,nil,nil,nil,nil
            reference = {}
            mod={}
            ns={Safe={Value=function(value) return value end},GetModule=function() return mod end}
            function mod.GPSRoadPoint(raw,cont)
                local p={}
                for k,v in pairs(raw) do p[k]=v end
                p.cont,p.x,p.y=cont,raw.wx/100000,raw.wy/100000
                return p
            end
        """)
        lua.execute(graph_path.read_text(), "ForeverMaps", lua.globals().reference)
        lua.execute((ROOT / "OpenMap/Data/Forever/Roads.lua").read_text(), "OpenMap", lua.globals().ns)
        lua.execute((ROOT / "OpenMap/Map/GPSRoads.lua").read_text(), "OpenMap", lua.globals().ns)
        lua.execute("""
            function CreateFrame() return setmetatable({}, {__index=function() return function() end end}) end
            UnitFactionGroup=function() return oracleFaction or 'Alliance' end
            GetLocale=function() return 'enUS' end
            reference.On=function() end
            reference.OnLogin=function() end
            reference.IsSecret=function() return false end
            reference.config={network={entryRadius=100,autoLinkRadius=200,offRoad=2,
                offroadMode='shortest',factionMode='warn',levelMode='warn'}}
            reference.Network={Get=function() return activeNet end}
            reference.GetPlayerPosition=function() return 0,0,0 end
        """)
        for name in ("Destinations", "Travel"):
            path = Path(REFERENCE) / ("Routing/" + name + ".lua")
            print(name + " SHA256:", hashlib.sha256(path.read_bytes()).hexdigest())
            lua.execute(path.read_text(), "ForeverMaps", lua.globals().reference)
        lua.execute("""
            reference.Travel.SwimCost=function() return 1.5 end
            function referencePinRoute(net,fromID,toID,dx,dy,tx,ty,faction,mode)
                activeNet,oracleFaction=net,faction
                reference.config.network.offroadMode=mode
                local f,t=net.nodes[fromID],net.nodes[toID]
                local dest={kind='pin',key='pin:audit',x=t[1]+ty,y=t[2]+tx}
                return reference.Travel.Plan({dest},{f[1]+dy,f[2]+dx,instance=0})
            end
            function oracleNetwork(cont)
                local net={nodes={}}
                for id,n in pairs(ns.GPSRoadData.networks[cont].nodes) do
                    local p={}
                    for k,v in pairs(n) do p[k]=v end
                    p[1],p[2],p[3]=n.wy,n.wx,n.map
                    net.nodes[id]=p
                end
                return net
            end
            function endpoint(cont,id)
                return mod.GPSRoadNode(cont,id)
            end
            function referenceCost(net,fromID,toID,faction,offroadCost,swimCost,dx,dy)
                local from=net.nodes[fromID]
                local p=net.nodes[toID]
                local target={node=toID,x=p[1],y=p[2]}
                local route=reference.Graph.Route(net,from[1]+(dy or 0),from[2]+(dx or 0),{target},{
                    blocked=reference.Graph.BlockedFor(net,faction),
                    offroadCost=offroadCost or 1,swimCost=swimCost or 1.5,
                    offRoad=2,entryRadius=100,directRadius=0,area=from.area,piece=from.piece,layer=from.layer})
                return route and route.cost
            end
            function referenceProductCost(net,fromID,toID,faction,mode,levelMode,ghost,dx,dy)
                local from,target=net.nodes[fromID],net.nodes[toID]
                local blocked,high={},{}
                if not ghost then
                    high=reference.Graph.BlockedFor(net,faction)
                    for id in pairs(reference.Graph.HighNodes(net,30,function(id) return id%60 end)) do
                        if levelMode=='never' then blocked[id]=true elseif levelMode=='avoid' then high[id]=true end
                    end
                end
                local factor=ghost and 1 or mode=='needed' and 1000 or mode=='avoid' and 4 or 1
                local route=reference.Graph.Route(net,from[1]+dy,from[2]+dx,
                    {{node=toID,x=target[1],y=target[2]}},
                    {blocked=blocked,high=high,highCost=1000,offroadCost=factor,swimCost=1.5,
                    offRoad=2,entryRadius=100,directRadius=0,area=from.area,piece=from.piece,layer=from.layer})
                return route and route.cost
            end
        """)
        cls.networks = {cont: lua.globals().oracleNetwork(cont)
                        for cont in lua.globals().ns.GPSRoadData.networks.keys()}

    def test_every_imported_direction_matches_reference_can_walk(self):
        compared = 0
        for continent, net in self.networks.items():
            for node_id, node in net.nodes.items():
                for other in node.links.keys():
                    expected = self.lua.globals().reference.Graph.CanWalk(net, node_id, other)
                    actual = self.lua.globals().mod.GPSRoadCanWalk(continent, node_id, other)
                    self.assertEqual(bool(actual), bool(expected), (continent, node_id, other))
                    compared += 1
        self.assertEqual(compared, 19416)
        print("Compared", compared, "directed adjacency entries with reference Graph.CanWalk")

    def test_every_tower_stop_winding_matches_reference(self):
        compared = 0
        for continent, net in self.networks.items():
            for node_id, node in net.nodes.items():
                if node.tower:
                    stops = self.lua.globals().reference.Graph.TowerStops(net, node_id)
                    for stop in stops.values():
                        actual = self.lua.globals().mod.GPSRoadNode(continent, stop[1])
                        self.assertAlmostEqual(actual.stairTurn * math.tau, stop[2], places=8,
                                               msg=(continent, node_id, stop[1]))
                        compared += 1
        self.assertGreaterEqual(compared, 24)
        print("Compared", compared, "tower stops with reference Graph.TowerStops")

    def test_one_hundred_known_node_shortest_path_costs(self):
        randomizer = random.Random(20261116)
        compared, mismatches = 0, []
        for continent, count, faction in ((0, 40, "Alliance"), (1, 40, "Horde"), (2991, 20, "Alliance")):
            net = self.networks[continent]
            own = faction.lower()
            ids = sorted(node_id for node_id, node in net.nodes.items()
                         if not node.nostart and not node.tower and not node.towerOf and not node.piece and not node.layer
                         and (node.type not in ("alliance", "horde") or node.type == own))
            context = self.lua.table_from({"faction": faction, "allowUnknownFloor": True})
            for _ in range(count):
                start, finish = randomizer.sample(ids, 2)
                expected = self.lua.globals().referenceCost(net, start, finish, faction, 1, 1.5)
                result = self.lua.globals().mod.GPSRoadRoute(
                    self.lua.globals().endpoint(continent, start),
                    self.lua.globals().endpoint(continent, finish), context)
                route, reason, stats = (*result, None)[:3] if isinstance(result, tuple) else (result, None, None)
                actual = stats.cost if route is not None else None
                if expected is None or actual is None:
                    if expected != actual:
                        mismatches.append((continent, start, finish, expected, actual, reason))
                elif not math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-6):
                    mismatches.append((continent, start, finish, expected, actual, reason))
                compared += 1
        self.assertEqual(compared, 100)
        self.assertFalse(mismatches, "Known-node path cost mismatches: " + repr(mismatches[:10]))
        print("Compared", compared, "known-node weighted shortest-path costs")

    def test_one_hundred_offset_entry_route_costs(self):
        randomizer = random.Random(620261116)
        compared, mismatches = 0, []
        for continent, count, faction in ((0, 40, "Alliance"), (1, 40, "Horde"), (2991, 20, "Alliance")):
            net = self.networks[continent]
            own = faction.lower()
            ids = sorted(node_id for node_id, node in net.nodes.items()
                         if not node.nostart and not node.tower and not node.towerOf and not node.piece and not node.layer
                         and (node.type not in ("alliance", "horde") or node.type == own))
            for i in range(count):
                start, finish = randomizer.sample(ids, 2)
                dx, dy = randomizer.uniform(-12, 12), randomizer.uniform(-12, 12)
                offroad = "avoid" if i % 2 else "allow"
                expected = self.lua.globals().referenceCost(net, start, finish, faction, 3 if offroad == "avoid" else 1, 1.5, dx, dy)
                at = self.lua.globals().endpoint(continent, start)
                at.wx, at.wy = at.wx + dx, at.wy + dy
                context = self.lua.table_from({"faction": faction, "allowUnknownFloor": True, "offroad": offroad, "offroadMultiplier": 3})
                result = self.lua.globals().mod.GPSRoadRoute(at, self.lua.globals().endpoint(continent, finish), context)
                route, reason, stats = (*result, None)[:3] if isinstance(result, tuple) else (result, None, None)
                actual = stats.cost if route is not None else None
                if expected is None or actual is None:
                    if expected != actual:
                        mismatches.append((continent, start, finish, expected, actual, reason))
                elif not math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-6):
                    mismatches.append((continent, start, finish, expected, actual, reason))
                compared += 1
        self.assertFalse(mismatches, "Offset entry cost mismatches: " + repr(mismatches[:10]))
        self.assertEqual(compared, 100)
        print("Compared", compared, "offset entries with weighted off-road approaches")

    def test_one_hundred_arbitrary_pin_destinations(self):
        randomizer = random.Random(16112026)
        mismatches, compared = [], 0
        for continent, count, faction in ((0, 40, "Alliance"), (1, 40, "Horde"), (2991, 20, "Alliance")):
            net = self.networks[continent]
            ids = sorted(i for i, n in net.nodes.items() if not n.nostart and not n.tower
                         and not n.towerOf and not n.piece and not n.layer)
            for i in range(count):
                start, finish = randomizer.sample(ids, 2)
                dx, dy = randomizer.uniform(-12, 12), randomizer.uniform(-12, 12)
                spread = 400 if i % 5 == 0 else 30
                tx, ty = randomizer.uniform(-spread, spread), randomizer.uniform(-spread, spread)
                mode = "avoid" if i % 2 else "shortest"
                result = self.lua.globals().referencePinRoute(net, start, finish, dx, dy, tx, ty, faction, mode)
                expected_route = result[0] if isinstance(result, tuple) else result
                expected = expected_route.cost if expected_route else None
                at = self.lua.globals().endpoint(continent, start)
                at.wx, at.wy = at.wx + dx, at.wy + dy
                at.area = None  # Travel.Plan(from) has no live area/piece context.
                target = self.lua.globals().endpoint(continent, finish)
                target.wx, target.wy = target.wx + tx, target.wy + ty
                target.nodeID = None
                target.area = None
                context = self.lua.table_from({"faction": faction, "allowEnemy": True,
                    "allowUnknownFloor": True, "offroad": mode})
                result = self.lua.globals().mod.GPSRoadRoute(at, target, context)
                route, reason, stats = (*result, None)[:3] if isinstance(result, tuple) else (result, None, None)
                actual = stats.cost if route else None
                if ((expected is None or actual is None) and expected != actual
                        or expected is not None and actual is not None
                        and not math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-6)):
                    mismatches.append((continent, start, finish, dx, dy, tx, ty, expected, actual, reason))
                compared += 1
        self.assertEqual(compared, 100)
        self.assertFalse(mismatches, "Arbitrary pin destination mismatches: " + repr(mismatches[:10]))
        print("Compared", compared, "arbitrary map pins with both endpoints offset (20 far targets)")

    def test_far_pins_and_named_destination_auto_link_boundary(self):
        self.lua.execute("""
            local saved=ns.GPSRoadData
            ns.GPSRoadData={version='target-fixture',networks={[0]={nodes={
                [1]={wx=0,wy=0,links={[2]=true}},[2]={wx=10000,wy=0,links={[1]=true}},
            }}}}
            mod.GPSInvalidateRoads()
            local net=oracleNetwork(0)
            activeNet=net
            reference.config.network.offroadMode='avoid'
            for _,distance in ipairs({199,201,600,1000,1500}) do
                local dest={kind='pin',key='pin:far:'..distance,x=distance,y=5000}
                local expected=reference.Travel.Plan({dest},{0,0,instance=0})
                local route,reason,stats=mod.GPSRoadRoute(endpoint(0,1),{cont=0,wx=5000,wy=distance},
                    {offroad='avoid',allowEnemy=true})
                assert(route,reason)
                assert(math.abs(expected.cost-stats.cost)<1e-7,expected.cost..'/'..stats.cost)
            end
            -- Named catalog destinations have a separate node-link contract.
            -- OpenMap coordinate/pin routes must not accidentally acquire this
            -- 200-yard classification or stop short at an auto-linked node.
            for _,distance in ipairs({199,200,201,600,1000}) do
                local dest={kind='landmark',key='catalog:'..distance,x=distance,y=0}
                local id,how,d=reference.Destinations.LinkOf(net,dest)
                assert(id==1 and d==distance)
                assert(how==(distance<=200 and 'auto' or 'far'))
            end
            net.dest={manual={node=2,pos={0,123}}}
            local id,how,d=reference.Destinations.LinkOf(net,{kind='landmark',key='manual',x=0,y=0})
            assert(id==2 and how=='manual' and d==9877)
            local other=mod.GPSOtherFloor
            mod.GPSOtherFloor=function() return false end
            ns.GPSRoadData={version='target-room-fixture',networks={[0]={nodes={
                [1]={wx=80,wy=0,piece='roomA',layer=true,links={[2]=true}},
                [2]={wx=100,wy=0,piece='roomA',layer=true,links={[1]=true}},
                [3]={wx=0,wy=0,piece='roomB',layer=true,links={[4]=true}},
                [4]={wx=20,wy=0,piece='roomB',layer=true,links={[3]=true}},
            }}}}
            mod.GPSInvalidateRoads()
            net=oracleNetwork(0)
            activeNet=net
            local expected=reference.Travel.Plan({{kind='pin',key='pin:room',room='roomA',indoor=true,x=0,y=0}},
                {0,80,instance=0})
            local route,reason,stats=mod.GPSRoadRoute(endpoint(0,1),{cont=0,wx=0,wy=0,piece='roomA',layer=true},
                {offroad='avoid',allowEnemy=true})
            assert(route,reason)
            assert(math.abs(expected.cost-stats.cost)<1e-7,expected.cost..'/'..stats.cost)
            mod.GPSOtherFloor=other
            ns.GPSRoadData=saved
            mod.GPSInvalidateRoads()
        """)
        print("Compared pin tails at 199/201/600/1000/1500 yards and audited catalog auto/manual links")

    def test_layer_and_same_floor_room_entry_contracts(self):
        self.lua.execute("""
            local saved,other=ns.GPSRoadData,mod.GPSOtherFloor
            local function compare(nodes,from,toID)
                ns.GPSRoadData={version='fixture',networks={[0]={nodes=nodes}}}
                mod.GPSInvalidateRoads()
                local net=oracleNetwork(0)
                local target=net.nodes[toID]
                local expected=reference.Graph.Route(net,from.wy,from.wx,
                    {{node=toID,x=target[1],y=target[2]}},
                    {layer=from.layer,piece=from.piece,offRoad=2,entryRadius=100,directRadius=0,swimCost=1.5})
                local route,reason,stats=mod.GPSRoadRoute(from,endpoint(0,toID),{allowUnknownFloor=true})
                assert(expected and route,reason)
                assert(math.abs(expected.cost-stats.cost)<1e-7,tostring(from.layer)..':'..expected.cost..'/'..stats.cost)
            end
            local nodes={
                [1]={wx=0,wy=0,links={[2]=true}},[2]={wx=100,wy=0,links={[1]=true,[4]=true}},
                [3]={wx=0,wy=2,layer=true,links={[4]=true}},[4]={wx=100,wy=2,layer=true,links={[3]=true,[2]=true,[6]=true}},
                [5]={wx=0,wy=4,layer=1458,links={[6]=true}},[6]={wx=100,wy=4,layer=1458,links={[5]=true,[4]=true}},
            }
            for _,layer in ipairs({false,true,1458}) do compare(nodes,{wx=0,wy=0,cont=0,layer=layer},6) end
            mod.GPSOtherFloor=function() return false end
            for _,distance in ipairs({20,30}) do
                compare({
                    [1]={wx=distance,wy=0,piece='roomA',layer=true,links={[2]=true}},
                    [2]={wx=100,wy=0,piece='roomA',layer=true,links={[1]=true,[4]=true}},
                    [3]={wx=0,wy=0,piece='roomB',layer=true,links={[4]=true}},
                    [4]={wx=0,wy=100,piece='roomB',layer=true,links={[2]=true,[3]=true}},
                },{wx=0,wy=0,cont=0,piece='roomA',layer=true},4)
            end
            ns.GPSRoadData,mod.GPSOtherFloor=saved,other
            mod.GPSInvalidateRoads()
        """)
        print("Compared outdoor/indoor/Undercity layers and same-floor piece entry slack")

    def test_one_hundred_product_preference_and_ghost_routes(self):
        randomizer = random.Random(11262016)
        compared, mismatches = 0, []
        minimum = self.lua.eval("function(node) return node.nodeID%60 end")
        for continent, count, faction in ((0, 40, "Alliance"), (1, 40, "Horde"), (2991, 20, "Alliance")):
            net = self.networks[continent]
            ids = sorted(node_id for node_id, node in net.nodes.items()
                         if not node.nostart and not node.tower and not node.towerOf and not node.piece and not node.layer)
            for i in range(count):
                mode, level_mode = ("shortest", "avoid", "needed")[i % 3], ("warn", "avoid", "never")[i % 3]
                ghost = i % 5 == 0
                eligible = [node_id for node_id in ids if ghost or level_mode != "never"
                            or net.nodes[node_id].type != "offroad" or node_id % 60 <= 30]
                start, finish = randomizer.sample(eligible, 2)
                dx, dy = randomizer.uniform(-5, 5), randomizer.uniform(-5, 5)
                expected = self.lua.globals().referenceProductCost(net, start, finish, faction, mode, level_mode, ghost, dx, dy)
                at = self.lua.globals().endpoint(continent, start)
                at.wx, at.wy = at.wx + dx, at.wy + dy
                context = self.lua.table_from({"faction": faction, "allowUnknownFloor": True,
                    "allowEnemy": True, "offroad": mode, "aboveLevel": level_mode,
                    "playerLevel": 30, "minLevel": minimum, "ghost": ghost})
                result = self.lua.globals().mod.GPSRoadRoute(at, self.lua.globals().endpoint(continent, finish), context)
                route, reason, stats = (*result, None)[:3] if isinstance(result, tuple) else (result, None, None)
                actual = stats.cost if route is not None else None
                if expected is None or actual is None:
                    if expected != actual: mismatches.append((continent, start, finish, mode, level_mode, ghost, expected, actual, reason))
                elif not math.isclose(expected, actual):
                    mismatches.append((continent, start, finish, mode, level_mode, ghost, expected, actual, reason))
                compared += 1
        self.assertFalse(mismatches, "Product preference mismatches: " + repr(mismatches[:10]))
        self.assertEqual(compared, 100)
        print("Compared", compared, "product preference/ghost routes (synthetic level weights)")


if __name__ == "__main__":
    unittest.main()
