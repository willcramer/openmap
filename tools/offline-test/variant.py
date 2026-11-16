"""Load OpenMap and its separately packaged GPS variant in the same Lua 5.1 client.

Run: python -P tools/offline-test/variant.py (OPENMAP_CLIENT=retail for Retail).
Only the game's addon-enable and reload functions are simulated; addon code, toc
contents and package transformations are the actual files used by the build.
"""
import importlib.util
import os
from pathlib import Path
import re
import unittest

from lupa.lua51 import LuaRuntime


REPO = Path(__file__).resolve().parents[2]
ADDON = REPO / "OpenMap"
TOC = "OpenMap_Mainline.toc" if os.environ.get("OPENMAP_CLIENT") == "retail" else "OpenMap.toc"
spec = importlib.util.spec_from_file_location("openmap_package_variant", REPO / "tools/package/variant.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def sources():
    def expand(path):
        if path.suffix == ".xml":
            text = re.sub(r"<!--.*?-->", "", path.read_text(), flags=re.S)
            for name in re.findall(r'<(?:Script|Include)\s+file="([^"]+)"', text):
                yield from expand(path.parent / name.replace("\\", "/"))
        else:
            yield path

    for line in (ADDON / TOC).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"\s*\[[^\]]*\]\s*$", "", line)
        yield from expand(ADDON / line.replace("\\", "/"))


class VariantTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((Path(__file__).with_name("stub.lua")).read_text())
        self.lua.execute("""
            NIL_GLOBALS.OpenMapGPSDB, NIL_GLOBALS.OpenMapGPSCharDB = true, true
            NIL_GLOBALS.OpenMapGPSAPI, NIL_GLOBALS.OpenMapGPS_Binding = true, true
            loaded = {}
            addonChanges = {}
            reloads = 0
            saves = 0
            committed = {OpenMap=true,OpenMapGPS=true}
            pending = {OpenMap=true,OpenMapGPS=true}
            originalExists = true
            C_AddOns.IsAddOnLoaded = function(name) return loaded[name] or false end
            C_AddOns.DoesAddOnExist = function(name) return name ~= 'OpenMap' or originalExists end
            C_AddOns.EnableAddOn = function(name, character)
                assert(character == 'Player-1-0001', 'enable state must use character GUID')
                pending[name] = true
                addonChanges[#addonChanges+1] = 'enable:' .. name
            end
            C_AddOns.DisableAddOn = function(name, character)
                assert(character == 'Player-1-0001', 'disable state must use character GUID')
                pending[name] = false
                addonChanges[#addonChanges+1] = 'disable:' .. name
            end
            C_AddOns.SaveAddOns = function()
                committed = {OpenMap=pending.OpenMap,OpenMapGPS=pending.OpenMapGPS}
                saves = saves + 1
            end
            ReloadUI = function()
                assert(saves > reloads, 'enable changes must be saved before reload')
                reloads = reloads + 1
            end
        """)

    def load(self, gps=False):
        namespace = self.lua.table()
        name = "OpenMapGPS" if gps else "OpenMap"
        self.lua.globals()["gpsNS" if gps else "originalNS"] = namespace
        files = ([ADDON / "BootGPS.lua"] if gps else []) + list(sources())
        for path in files:
            source = path.read_bytes()
            if gps:
                _, source = package.gps_transform(str(path.relative_to(REPO)), source, "OpenMap/" + TOC)
            try:
                self.lua.execute(source.decode("utf-8-sig"), name, namespace)
            except Exception as exc:
                raise AssertionError(f"{name} load failed at {path.relative_to(REPO)}: {exc}") from exc
        self.lua.execute(f"loaded['{name}'] = true; FireEvent('ADDON_LOADED', '{name}')")
        return namespace

    def login(self):
        self.lua.execute("FireEvent('PLAYER_LOGIN'); FireEvent('PLAYER_ENTERING_WORLD', true, false); RunTimers(5)")
        self.lua.execute("assert(#ERRORS == 0, ERRORS[1])")

    def test_both_enabled_keeps_original_in_control_and_variant_dormant(self):
        self.load()
        self.login()
        self.lua.execute("""
            originalAPI, originalCommand, originalDB = OpenMapAPI, SlashCmdList.OPENMAP, OpenMapDB
            originalCharDB, originalBinding = OpenMapCharDB, OpenMap_Binding
            originalDB.worldmap.sentinel = 'unchanged'
            originalFrameCount = #FRAMES
        """)
        self.load(gps=True)
        self.lua.execute("""
            assert(gpsNS.variantDormant == true and gpsNS.modules == nil)
            assert(OpenMap == originalNS and OpenMapAPI == originalAPI)
            assert(SlashCmdList.OPENMAP == originalCommand and OpenMap_Binding == originalBinding)
            assert(OpenMapDB == originalDB and OpenMapCharDB == originalCharDB)
            assert(OpenMapDB.worldmap.sentinel == 'unchanged')
            assert(#FRAMES == originalFrameCount + 1, 'standby build created map frames')
            assert(rawget(_G, 'OpenMapGPS') == nil and rawget(_G, 'OpenMapGPSAPI') == nil)
            assert(SLASH_OPENMAPGPS1 == '/openmapgps' and SLASH_OPENMAPGPS2 == '/omgps')
            assert(type(SlashCmdList.OPENMAPGPS) == 'function')
        """)

    def test_dormant_switch_to_gps_changes_enable_state_then_reloads(self):
        self.load()
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            SlashCmdList.OPENMAPGPS('use gps')
            assert(#addonChanges == 2)
            assert(addonChanges[1] == 'enable:OpenMapGPS' and addonChanges[2] == 'disable:OpenMap')
            assert(reloads == 1)
            assert(saves == 1 and committed.OpenMap == false and committed.OpenMapGPS == true)
            assert(gpsNS.variantDormant, 'switch tried to hot-swap map hooks before reload')
        """)

    def test_active_variant_has_separate_saved_state_api_commands_and_media(self):
        self.lua.execute("""
            OpenMapDB = { untouched = true }
            OpenMapCharDB = { untouched = true }
        """)
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            assert(not gpsNS.variantDormant and OpenMapGPS == gpsNS)
            assert(OpenMapGPSAPI and type(OpenMapGPSAPI.IsStitched) == 'function')
            assert(rawget(_G, 'OpenMap') == nil and rawget(_G, 'OpenMapAPI') == nil)
            assert(rawget(SlashCmdList, 'OPENMAP') == nil)
            assert(OpenMapDB.untouched and OpenMapDB.worldmap == nil)
            assert(OpenMapCharDB.untouched and OpenMapCharDB.worldmap == nil)
            assert(gpsNS.modules.worldmap.db == OpenMapGPSDB.worldmap)
            assert(gpsNS.modules.worldmap.char == OpenMapGPSCharDB.worldmap)
            assert(gpsNS.Media.path == 'Interface\\\\AddOns\\\\OpenMapGPS\\\\Media\\\\')
            local before = #LOG
            SlashCmdList.OPENMAPGPS('gps status')
            assert(#LOG > before, 'GPS slash callback lost during Init')
        """)

    def test_active_variant_switches_back_while_retaining_standby_command(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            SlashCmdList.OPENMAPGPS('use original')
            assert(#addonChanges == 2 and addonChanges[1] == 'enable:OpenMapGPS')
            assert(addonChanges[2] == 'enable:OpenMap' and reloads == 1)
            assert(saves == 1 and committed.OpenMap == true and committed.OpenMapGPS == true)
        """)

    def test_switch_refuses_combat_without_changing_addon_state(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            IN_COMBAT = true
            SlashCmdList.OPENMAPGPS('use original')
            assert(#addonChanges == 0 and reloads == 0)
        """)

    def test_missing_original_does_not_disable_the_working_variant(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            originalExists = false
            SlashCmdList.OPENMAPGPS('use original')
            assert(#addonChanges == 0 and reloads == 0)
        """)

    def test_dormant_key_bindings_are_safe_without_variant_map_functions(self):
        self.load()
        self.load(gps=True)
        _, source = package.gps_transform("OpenMap/Bindings.xml", (ADDON / "Bindings.xml").read_bytes(), "OpenMap/" + TOC)
        for body in re.findall(r"<Binding\b[^>]*>(.*?)</Binding>", source.decode(), flags=re.S):
            self.lua.execute(body)
        self.lua.execute("assert(#ERRORS == 0, ERRORS[1])")

    def test_switch_survives_reload_into_gps_then_original_standby(self):
        self.load()
        self.load(gps=True)
        self.login()
        self.lua.execute("SlashCmdList.OPENMAPGPS('use gps')")
        enabled = self.lua.globals().committed
        self.assertFalse(enabled.OpenMap)
        self.assertTrue(enabled.OpenMapGPS)

        # Reload reconstructs addon loading from the saved GUID-specific list.
        self.setUp()
        self.lua.execute("pending.OpenMap=false; committed.OpenMap=false")
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            assert(not gpsNS.variantDormant and OpenMapGPSAPI)
            SlashCmdList.OPENMAPGPS('use original')
            assert(committed.OpenMap and committed.OpenMapGPS)
        """)

        self.setUp()
        self.load()
        self.load(gps=True)
        self.login()
        self.lua.execute("assert(gpsNS.variantDormant and OpenMapAPI)")

    def test_missing_character_guid_or_save_api_does_not_reload(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            UnitGUID=function() return nil end
            SlashCmdList.OPENMAPGPS('use gps')
            assert(#addonChanges==0 and saves==0 and reloads==0)
            UnitGUID=function() return 'Player-1-0001' end
            C_AddOns.SaveAddOns=nil
            SlashCmdList.OPENMAPGPS('use gps')
            assert(#addonChanges==0 and saves==0 and reloads==0)
        """)

    def test_failed_save_does_not_claim_a_reload_will_switch_addons(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            C_AddOns.SaveAddOns=function() error('save failed') end
            SlashCmdList.OPENMAPGPS('use gps')
            assert(reloads==0 and saves==0 and committed.OpenMap==true)
        """)

    def test_dormant_import_copies_preferences_without_aliasing_or_user_data(self):
        self.load()
        self.login()
        self.lua.execute("""
            sourceDB,sourceChar=OpenMapDB,OpenMapCharDB
            sourceDB.worldmap.brightness=.45
            sourceDB.worldmap.darkenColor={.2,.3,.4}
            sourceDB.worldmap.window={'TOPLEFT','TOPLEFT',31,-44}
            sourceDB.worldmap.windowScale=1.2
            sourceDB.worldmap.ctrlClickPin=false
            sourceDB.worldmap.foundOnly=true
            sourceDB.worldmap.enabled=false
            sourceDB.worldmap.pins={list={{note='original pin'}},nextId=2}
            sourceDB.worldmap.sketch={strokes={{'original stroke'}},nextId=2,tool='marker',ink=3,size=5,mark=9}
            sourceDB.worldmap.paint={notes={{'original note'}},nextId=2}
            sourceDB.worldmap.flightTimes={privateMeasurement=30}
            sourceDB.worldmap.newsSeen='original'
            sourceDB.worldmap.lastBench={privateSample=1}
            sourceDB.worldmap.gpsRoutes={originalGPS={points={{1,.1,.1},{1,.2,.2}}}}
            sourceChar.worldmap.unexploredOwn=true
            sourceChar.worldmap.unexplored='hide'
            sourceChar.worldmap.pin={1,.8,.8}
            sourceChar.worldmap.cvars={privateRestore='original'}
            sourceChar.worldmap.reports={'original report'}
            sourceChar.worldmap.flightsKnown={['original flight']=true}
            OpenMapGPSDB={worldmap={enabled=true,gpsUseRoads=false,gpsGuideAt={'CENTER'},
                gpsRoutes={GPSWalk={points={{1,.2,.2},{1,.3,.3}}}},
                pins={list={{note='GPS pin'}},nextId=2},
                sketch={strokes={{'GPS stroke'}},nextId=2,tool='quill'},
                paint={notes={{'GPS note'}},nextId=2},flightTimes={GPSMeasurement=12},newsSeen='GPS'}}
            OpenMapGPSCharDB={worldmap={pin={1,.4,.4},cvars={privateRestore='GPS'},
                reports={'GPS report'},flightsKnown={['GPS flight']=true}}}
        """)
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            SlashCmdList.OPENMAPGPS('sync settings')
            local target,c=OpenMapGPSDB.worldmap,OpenMapGPSCharDB.worldmap
            assert(target.brightness==.45 and target.windowScale==1.2 and target.foundOnly)
            assert(target.window[3]==31 and target.darkenColor[2]==.3 and target.ctrlClickPin==false)
            assert(target.enabled and target.gpsUseRoads==false and target.gpsGuideAt[1]=='CENTER')
            assert(target.gpsRoutes.GPSWalk and not target.gpsRoutes.originalGPS)
            assert(target.pins.list[1].note=='GPS pin' and target.paint.notes[1][1]=='GPS note')
            assert(target.sketch.strokes[1][1]=='GPS stroke' and target.sketch.nextId==2)
            assert(target.sketch.tool=='marker' and target.sketch.ink==3 and target.sketch.size==5 and target.sketch.mark==9)
            assert(target.flightTimes.GPSMeasurement==12 and not target.flightTimes.privateMeasurement)
            assert(target.newsSeen=='GPS' and target.lastBench==nil)
            assert(c.unexploredOwn and c.unexplored=='hide')
            assert(c.pin[2]==.4 and c.cvars.privateRestore=='GPS' and c.reports[1]=='GPS report')
            assert(c.flightsKnown['GPS flight'] and not c.flightsKnown['original flight'])
            assert(OpenMapDB==sourceDB and OpenMapCharDB==sourceChar)
            target.window[3]=99 target.darkenColor[2]=.9
            assert(sourceDB.worldmap.window[3]==31 and sourceDB.worldmap.darkenColor[2]==.3)
            assert(sourceDB.worldmap.pins.list[1].note=='original pin')
            assert(reloads==1 and saves==1 and not committed.OpenMap and committed.OpenMapGPS)
            assert(OpenMapGPSCharDB.gpsSettingsSyncResult and not OpenMapGPSCharDB.gpsSettingsSyncRequest)
        """)

    def test_active_sync_roundtrip_preserves_gps_state_and_consumes_request_once(self):
        def plain(value):
            if hasattr(value, 'items'):
                return {key: plain(item) for key, item in value.items()}
            return value

        def table(value):
            if isinstance(value, dict):
                return self.lua.table_from({key: table(item) for key, item in value.items()})
            return value

        self.lua.execute("committed.OpenMap=false; pending.OpenMap=false")
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            OpenMapGPSDB.worldmap.gpsRoutes={Keep={points={{1,.1,.1},{1,.2,.2}}}}
            OpenMapGPSDB.worldmap.gpsAllowEnemy=true
            OpenMapGPSDB.worldmap.gpsGuideAt={'CENTER','CENTER',80,90}
            SlashCmdList.OPENMAPGPS('sync settings')
            assert(committed.OpenMap and committed.OpenMapGPS and reloads==1)
            assert(OpenMapGPSCharDB.gpsSettingsSyncRequest)
        """)
        account = plain(self.lua.globals().OpenMapGPSDB)
        character = plain(self.lua.globals().OpenMapGPSCharDB)
        self.setUp()
        self.lua.globals().OpenMapGPSDB = table(account)
        self.lua.globals().OpenMapGPSCharDB = table(character)
        self.load()
        self.lua.execute("OpenMapDB.worldmap.brightness=.62; OpenMapDB.worldmap.pinsHidden=true")
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            assert(gpsNS.variantDormant and reloads==1)
            assert(not committed.OpenMap and committed.OpenMapGPS)
            assert(not OpenMapGPSCharDB.gpsSettingsSyncRequest and OpenMapGPSCharDB.gpsSettingsSyncResult)
            assert(OpenMapGPSDB.worldmap.brightness==.62 and OpenMapGPSDB.worldmap.pinsHidden)
        """)
        account = plain(self.lua.globals().OpenMapGPSDB)
        character = plain(self.lua.globals().OpenMapGPSCharDB)
        self.setUp()
        self.lua.execute("committed.OpenMap=false; pending.OpenMap=false")
        self.lua.globals().OpenMapGPSDB = table(account)
        self.lua.globals().OpenMapGPSCharDB = table(character)
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            assert(not gpsNS.variantDormant and OpenMapGPSAPI)
            assert(OpenMapGPSDB.worldmap.brightness==.62 and OpenMapGPSDB.worldmap.pinsHidden)
            assert(OpenMapGPSDB.worldmap.gpsRoutes.Keep and OpenMapGPSDB.worldmap.gpsAllowEnemy)
            assert(OpenMapGPSDB.worldmap.gpsGuideAt[3]==80)
            assert(not OpenMapGPSCharDB.gpsSettingsSyncRequest and not OpenMapGPSCharDB.gpsSettingsSyncResult)
            assert(reloads==0 and saves==0, 'completed import caused another automatic reload')
            local announced=false
            for _,message in ipairs(LOG) do if message:find('Map settings copied to GPS.',1,true) then announced=true end end
            assert(announced, 'completed import was not announced')
        """)

    def test_sync_missing_original_or_combat_does_not_queue_or_switch(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            originalExists=false
            SlashCmdList.OPENMAPGPS('sync settings')
            assert(not OpenMapGPSCharDB.gpsSettingsSyncRequest and #addonChanges==0 and reloads==0)
            originalExists=true IN_COMBAT=true
            SlashCmdList.OPENMAPGPS('sync settings')
            assert(not OpenMapGPSCharDB.gpsSettingsSyncRequest and #addonChanges==0 and reloads==0)
        """)

    def test_failed_handoff_clears_request_without_login_loop(self):
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            C_AddOns.SaveAddOns=function() error('save failed') end
            SlashCmdList.OPENMAPGPS('sync settings')
            assert(not OpenMapGPSCharDB.gpsSettingsSyncRequest and reloads==0)
            assert(LOG[#LOG]:find('Use the AddOns list',1,true))
        """)

    def test_failed_import_clears_saved_request_and_leaves_both_settings_unchanged(self):
        self.load()
        self.lua.execute("""
            OpenMapGPSDB={worldmap={brightness=.17,gpsRoutes={Keep={points={}}}}}
            OpenMapGPSCharDB={gpsSettingsSyncRequest=true,worldmap={unexplored='dim'}}
            beforeGPS,beforeChar=OpenMapGPSDB,OpenMapGPSCharDB
            OpenMapDB.worldmap=nil
        """)
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            assert(OpenMapGPSDB==beforeGPS and OpenMapGPSCharDB==beforeChar)
            assert(OpenMapGPSDB.worldmap.brightness==.17 and OpenMapGPSCharDB.worldmap.unexplored=='dim')
            assert(OpenMapDB.worldmap==nil and not OpenMapGPSCharDB.gpsSettingsSyncRequest)
            assert(reloads==0 and #addonChanges==0)
            assert(LOG[#LOG]:find('Map settings could not be copied.',1,true))
            FireEvent('PLAYER_LOGIN')
            assert(reloads==0 and #addonChanges==0)
        """)

    def test_char_override_absence_restores_account_preference(self):
        self.load()
        self.lua.execute("""
            OpenMapGPSDB={worldmap={}}
            OpenMapGPSCharDB={worldmap={unexplored='hide',unexploredOwn=true}}
        """)
        self.load(gps=True)
        self.login()
        self.lua.execute("""
            SlashCmdList.OPENMAPGPS('sync settings')
            assert(OpenMapGPSCharDB.worldmap.unexploredOwn==nil and OpenMapGPSCharDB.worldmap.unexplored==nil)
        """)


if __name__ == "__main__":
    unittest.main()
