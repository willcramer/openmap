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


if __name__ == "__main__":
    unittest.main()
