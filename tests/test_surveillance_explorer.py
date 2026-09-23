from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "build_surveillance_explorer.py"
spec = importlib.util.spec_from_file_location("wse_builder", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_newick_parser_support_and_tip_mapping():
    tree = "(sampleA__HA_H5:0.1,(sampleB__HA_H5:0.2,sampleC__HA_H5:0.3)91.2:0.4);"
    root = mod.NewickParser(tree).parse()
    unmatched = []
    tips = mod.annotate_tree_samples(root, {"sampleA", "sampleB", "sampleC"}, unmatched)
    assert tips == 3
    assert unmatched == []
    internal = root["children"][1]
    assert internal["support"] == 91.2
    assert internal["children"][0]["sample_id"] == "sampleB"


def test_tip_mapping_legacy_prefix():
    ids = {"12-11-2025_barcode03"}
    assert mod.map_tip_to_sample("12-11-2025_barcode03_A_HA_H5", ids) == "12-11-2025_barcode03"


def test_first_tree_only(tmp_path):
    p = tmp_path / "HA_Tree.newick"
    p.write_text("(a:0.1,b:0.2);\n(a:0.2,b:0.3);\n", encoding="utf-8")
    first, count = mod.first_newick_tree_and_count(p)
    assert first == "(a:0.1,b:0.2);"
    assert count == 2
