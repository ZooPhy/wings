"""Canonical-source regression checks; standard-library only."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("explorer_builder", ROOT / "scripts/build_explorer_assets.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ExplorerBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wings-asset-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        shutil.copytree(ROOT / "scripts/report", self.repo / "scripts/report")

    def test_checked_in_assets_are_current(self):
        self.assertEqual(builder.plan(ROOT), {})

    def test_build_is_deterministic_and_idempotent(self):
        first = builder.render_all(self.repo)
        self.assertEqual(first, builder.render_all(self.repo))
        builder.write_outputs(self.repo, first)
        self.assertEqual(builder.plan(self.repo), {})

    def test_canonical_module_edit_changes_only_js_bundle(self):
        path = self.repo / "scripts/report/explorer-tabs.js"
        path.write_bytes(path.read_bytes() + b"\n// synthetic source edit\n")
        changes = builder.plan(self.repo)
        self.assertEqual(set(changes), {"scripts/report/surveillance-explorer.js"})
        self.assertIn(b"// synthetic source edit", changes["scripts/report/surveillance-explorer.js"])
        original = (ROOT / "scripts/report/surveillance-explorer.js").read_bytes()
        self.assertEqual(original.split(b"// WINGS_BRAID_CLOCK_HOOK_BEGIN")[1], changes["scripts/report/surveillance-explorer.js"].split(b"// WINGS_BRAID_CLOCK_HOOK_BEGIN")[1])

    def test_amino_tab_survives_canonical_rebuild(self):
        source = (self.repo / "scripts/report/explorer-tabs.js").read_bytes().strip()
        output = builder.render_all(self.repo)["scripts/report/surveillance-explorer.js"]
        begin = b"/* WINGS_EXPLORER_TABS_JS_BEGIN */"
        end = b"/* WINGS_EXPLORER_TABS_JS_END */"
        self.assertEqual(output.count(begin), 1)
        self.assertEqual(output.count(end), 1)
        embedded = output.split(begin, 1)[1].split(end, 1)[0].strip()
        self.assertEqual(embedded, source)
        self.assertEqual(embedded.count(b"function mountAminoDashboard("), 1)
        self.assertIn(b"const aminoDashboard = mountAminoDashboard(explorer, panels.amino)", embedded)
        self.assertIn(b"aminoDashboard?.refresh()", embedded)
        builder.write_outputs(self.repo, builder.render_all(self.repo))
        self.assertEqual(builder.plan(self.repo), {})

    def test_amino_installer_refuses_migrated_checkout_before_any_write(self):
        sentinel = self.repo / "scripts/wings_amino_acids.py"
        sentinel.write_text("# existing local analysis script\n")
        before = {p.relative_to(self.repo): p.read_bytes()
                  for p in self.repo.rglob("*") if p.is_file()}
        for options in ([], ["--apply"], ["--apply", "--amino-report", "missing.html"]):
            with self.subTest(options=options):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/install_amino_explorer_tab.py"),
                     "--repo", str(self.repo), *options],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("legacy installer is disabled", result.stderr)
                self.assertIn("build_explorer_assets.py --write", result.stderr)
                after = {p.relative_to(self.repo): p.read_bytes()
                         for p in self.repo.rglob("*") if p.is_file()}
                self.assertEqual(after, before)

    def test_shared_concordance_style_updates_both_placements(self):
        path = self.repo / "scripts/report/genomic-ecological-concordance.css"
        path.write_bytes(b"/* synthetic shared CSS edit */\n" + path.read_bytes())
        changes = builder.plan(self.repo)
        self.assertEqual(set(changes), {"scripts/report/explorer-tabs.css", "scripts/report/surveillance-explorer.css"})
        self.assertEqual(changes["scripts/report/explorer-tabs.css"].count(b"synthetic shared CSS edit"), 1)
        self.assertEqual(changes["scripts/report/surveillance-explorer.css"].count(b"synthetic shared CSS edit"), 2)

    def test_direct_generated_edit_is_detected(self):
        path = self.repo / "scripts/report/surveillance-explorer.js"
        expected = path.read_bytes()
        path.write_bytes(expected + b"\n// accidental generated edit\n")
        self.assertEqual(builder.plan(self.repo)[str(path.relative_to(self.repo))], expected)

    def test_unknown_include_is_rejected(self):
        path = self.repo / "scripts/report/templates/surveillance-explorer.js.tpl"
        path.write_bytes(path.read_bytes() + b"@@WINGS:scripts/report/unknown.js@@")
        with self.assertRaisesRegex(ValueError, "Undeclared"):
            builder.render_all(self.repo)

    def test_cyclic_include_is_rejected(self):
        path = self.repo / "scripts/report/templates/explorer-tabs.css.tpl"
        path.write_bytes(b"@@WINGS:scripts/report/explorer-tabs.css@@")
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            builder.render_all(self.repo)

    def test_unsafe_source_is_rejected(self):
        path = self.repo / builder.MANIFEST
        manifest = json.loads(path.read_text())
        manifest["sources"].append("../outside.js")
        path.write_text(json.dumps(manifest))
        template = self.repo / "scripts/report/templates/surveillance-explorer.js.tpl"
        template.write_bytes(b"@@WINGS:../outside.js@@")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            builder.render_all(self.repo)

    def test_legacy_installers_cannot_overwrite_migrated_assets(self):
        for name in ("install_braid_clock", "install_explorer_tabs", "install_tree_studio", "install_dynamic_phenology"):
            with self.subTest(installer=name):
                spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with self.assertRaisesRegex(ValueError, "legacy installer is disabled"):
                    module.plan(self.repo)


if __name__ == "__main__":
    unittest.main()
