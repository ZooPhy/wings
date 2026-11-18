import base64,gzip,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from refresh_phylodynamics_locations import refresh_html,refresh_bundle,plan_refresh,MARKER
VIEWER=(ROOT/'scripts/report/phylogeography-results.js').read_text()
OLD=MARKER+'\n// old presentation\n})(typeof globalThis!==\'undefined\'?globalThis:this);'
def standalone():return '<script type="application/json" id="results-data">{"preserve": [0,1,2]}</script><script>var boundaries={};\n'+OLD+'</script>'
def embedded():return '<script type="application/json">{"posterior":true}</script><script>globalThis.WINGS_PHYLODYNAMICS_ASSETS={script:"'+base64.b64encode(OLD.encode()).decode()+'",style:"KEEP",boundaries:"KEEP"};</script>'
class RefreshTests(unittest.TestCase):
 def test_standalone_preserves_data_and_boundary_script(self):
  new=refresh_html(standalone(),VIEWER)
  self.assertIn('{"preserve": [0,1,2]}',new);self.assertIn('var boundaries={};',new);self.assertIn(VIEWER,new)
  self.assertEqual(refresh_html(new,VIEWER),new)
 def test_embed_preserves_model_and_other_assets(self):
  new=refresh_html(embedded(),VIEWER)
  self.assertIn(base64.b64encode(VIEWER.encode()).decode(),new);self.assertIn('style:"KEEP",boundaries:"KEEP"',new)
  self.assertIn('{"posterior":true}',new)
 def test_bundle_changes_only_run_summary_html(self):
  data={'run_summary':{'html':embedded(),'id':'unchanged'},'samples':[{'id':'test','sequence':'UNCHANGED'}],'metadata':{'run':'preserved'}}
  original=json.dumps(data).encode()
  for raw in [original,gzip.compress(original)]:
   changed=refresh_bundle(raw,VIEWER);new=json.loads(gzip.decompress(changed) if raw[:2]==b'\x1f\x8b' else changed)
   self.assertNotEqual(new['run_summary']['html'],data['run_summary']['html'])
   new['run_summary']['html']=data['run_summary']['html'];self.assertEqual(new,data)
 def test_discovery_does_not_touch_results_json_or_unrelated_html(self):
  with tempfile.TemporaryDirectory() as tmp:
   run=Path(tmp);d=run/'results/run_summary';d.mkdir(parents=True)
   (d/'index.html').write_text(standalone());(d/'other.html').write_text('unchanged');(d/'results.json').write_text('{"posterior":42}')
   changes=plan_refresh(run,VIEWER);self.assertEqual(set(changes),{(d/'index.html').resolve()})
   self.assertEqual((d/'results.json').read_text(),'{"posterior":42}');self.assertEqual((d/'index.html').read_text(),standalone())
 def test_discovery_through_symlinked_run_root(self):
  # macOS /var and /private/var can refer to the same temporary directory.
  with tempfile.TemporaryDirectory() as tmp:
   parent=Path(tmp).resolve();physical=parent/'physical';physical.mkdir()
   alias=parent/'alias';alias.symlink_to(physical,target_is_directory=True)
   run=alias/'run';d=run/'results/run_summary';d.mkdir(parents=True)
   report=d/'index.html';report.write_text(standalone())
   aliased=plan_refresh(run,VIEWER);resolved=plan_refresh(run.resolve(),VIEWER)
   self.assertEqual(aliased,resolved)
   self.assertEqual(set(aliased),{report.resolve()})
   self.assertEqual(report.read_text(),standalone())
if __name__=='__main__':unittest.main()
