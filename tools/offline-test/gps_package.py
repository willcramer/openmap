"""The GPS package has its own identity without rewriting libraries or art.

Run: python -P tools/offline-test/gps_package.py
"""
import importlib.util
from pathlib import Path
import re
import unittest

from lupa.lua51 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("openmap_package_variant", ROOT / "tools/package/variant.py")
variant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(variant)


class GPSPackageTests(unittest.TestCase):
    def transform(self, path, text, toc="OpenMap/OpenMap.toc"):
        name, data = variant.gps_transform(path, text.encode(), toc)
        return name, data.decode()

    def test_each_client_has_separate_metadata_and_first_bootstrap(self):
        for toc in ("OpenMap.toc", "OpenMap_Mainline.toc"):
            with self.subTest(toc=toc):
                path = "OpenMap/" + toc
                name, text = self.transform(path, (ROOT / path).read_text(), path)
                self.assertEqual(name, "OpenMapGPS/" + toc.replace("OpenMap", "OpenMapGPS"))
                self.assertIn("## Title: |cffe6b85cOpenMap GPS Test|r", text)
                # AddonList's Group override makes this its own parent row,
                # despite the similar name and optional load-order dependency.
                self.assertEqual(re.findall(r"^## Group: (.+)$", text, re.M), ["OpenMapGPS"])
                self.assertIn("## SavedVariables: OpenMapGPSDB\n", text)
                self.assertIn("## SavedVariablesPerCharacter: OpenMapGPSCharDB\n", text)
                self.assertIn("## OptionalDeps: OpenMap, ", text)
                self.assertNotRegex(text, r"(?m)^## (?:Dependencies|RequiredDeps):.*\bOpenMap\b")
                self.assertNotIn("X-Curse-Project-ID", text)
                self.assertIn("## X-Website: https://github.com/willcramer/openmap", text)
                files = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
                self.assertEqual(files[0], "BootGPS.lua")
                self.assertEqual(files.count("BootGPS.lua"), 1)
                self.assertIn("OpenMapGPSIcon", text)

    def test_explicit_group_replaces_inherited_group_without_changing_category(self):
        source = "## Title: OpenMap\n## Group: OpenMap\n## Category: Map\n## OptionalDeps: Questie\nCore.lua\n"
        _, text = self.transform("OpenMap/OpenMap.toc", source)
        self.assertEqual(re.findall(r"^## Group: (.+)$", text, re.M), ["OpenMapGPS"])
        self.assertIn("## Category: Map\n", text)
        self.assertIn("## OptionalDeps: OpenMap, Questie\n", text)

    def test_runtime_names_saved_variables_slashes_and_paths_are_isolated(self):
        _, core = self.transform("OpenMap/Core.lua", (ROOT / "OpenMap/Core.lua").read_text())
        _, init = self.transform("OpenMap/Init.lua", (ROOT / "OpenMap/Init.lua").read_text())
        _, launcher = self.transform("OpenMap/Map/Launcher.lua", (ROOT / "OpenMap/Map/Launcher.lua").read_text())
        self.assertIn("_G.OpenMapGPS = ns", core)
        self.assertIn("OpenMapGPSDB = OpenMapGPSDB or {}", core)
        self.assertIn("OpenMapGPSCharDB = OpenMapGPSCharDB or {}", core)
        self.assertNotRegex(core, r"\bOpenMap(?:DB|CharDB)\b")
        self.assertIn('SLASH_OPENMAPGPS1, SLASH_OPENMAPGPS2 = "/openmapgps", "/omgps"', init)
        self.assertIn("SlashCmdList.OPENMAPGPS = Slash", init)
        self.assertIn("OpenMapGPS_OnAddonCompartmentClick", launcher)
        self.assertIn("OpenMapGPSIconRound", launcher)
        self.assertIn("https://github.com/willcramer/openmap/issues/new", core)

    def test_binding_ids_and_handlers_do_not_collide_or_run_when_dormant(self):
        _, text = self.transform("OpenMap/Bindings.xml", (ROOT / "OpenMap/Bindings.xml").read_text())
        self.assertIn('name="OPENMAPGPS_FIND" category="OpenMapGPS"', text)
        lua = LuaRuntime()
        bodies = re.findall(r"<Binding\b[^>]*>(.*?)</Binding>", text, re.S)
        self.assertTrue(bodies)
        for body in bodies:
            lua.execute(body)  # No handler exists in a dormant package; bindings must be harmless.
        lua.execute("called = 0; function OpenMapGPS_Binding() called = called + 1 end")
        for body in bodies:
            lua.execute(body)
        self.assertEqual(lua.globals().called, len(bodies))

    def test_art_libraries_and_notices_keep_original_bytes(self):
        cases = (
            ("OpenMap/Media/Textures/OpenMapIcon.tga", b"\0OpenMap\xff\x18"),
            ("OpenMap/Media/Textures/Forever/NOTICE.md", b"OpenMap credits Blizzard"),
            ("OpenMap/LICENSES/LibStub.txt", b"OpenMap attribution"),
            ("OpenMap/Libs/LibStub/LibStub.lua", b"local name = 'OpenMap'"),
            ("OpenMap/Libs/Libs.xml", b'<Script file="OpenMap.lua"/>'),
        )
        for path, source in cases:
            with self.subTest(path=path):
                name, data = variant.gps_transform(path, source, "OpenMap/OpenMap.toc")
                self.assertEqual(data, source)
                self.assertTrue(name.startswith("OpenMapGPS/"))
        self.assertEqual(variant.gps_path(cases[0][0]), "OpenMapGPS/Media/Textures/OpenMapGPSIcon.tga")

    def test_bootstrap_keeps_original_addon_detection_literal(self):
        source = b"OpenMapGPSInactive = C_AddOns.IsAddOnLoaded('OpenMap')"
        name, data = variant.gps_transform(variant.BOOTSTRAP, source, "OpenMap/OpenMap.toc")
        self.assertEqual(name, "OpenMapGPS/BootGPS.lua")
        self.assertEqual(data, source)

    def test_every_owned_lua_compiles_and_is_inert_when_dormant(self):
        lua = LuaRuntime()
        compile_ = lua.eval("function(src, name) local fn, err = loadstring(src, name); assert(fn, err); return fn end")
        namespace = lua.table_from({"variantDormant": True})
        for path in sorted((ROOT / "OpenMap").rglob("*.lua")):
            relative = path.relative_to(ROOT).as_posix()
            if "/Libs/" in relative or relative == variant.BOOTSTRAP:
                continue
            with self.subTest(path=relative):
                name, data = variant.gps_transform(relative, path.read_bytes(), "OpenMap/OpenMap.toc")
                self.assertTrue(data.startswith(variant.GUARD.encode()))
                compile_(data.decode("utf-8"), name)("OpenMapGPS", namespace)

    def test_slash_rewrite_does_not_corrupt_urls_or_longer_names(self):
        _, text = self.transform("OpenMap/Test.lua", "-- /openmap gps; /omap; https://example.com/openmap; /openmap-other\n")
        self.assertIn("/openmapgps gps; /omgps; https://example.com/openmap; /openmap-other", text)


if __name__ == "__main__":
    unittest.main()
