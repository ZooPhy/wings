import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_phylodynamic_comparison import scoped_movie, write_comparison


def fixture():
    nodes=[dict(id='root',parent=None,date='2024-01-01'),dict(id='mrca',parent='root',date='2024-02-01'),
           dict(id='a',parent='mrca',date='2024-04-01',sample_id='WINGS-a',observed_state='B'),
           dict(id='b',parent='mrca',date='2024-05-01',sample_id='WINGS-b',observed_state='B'),
           dict(id='ref',parent='root',date='2024-06-01',observed_state='B')]
    jumps=[dict(branch='mrca',date='2024-01-15',**{'from':'A','to':'B'}),
           dict(branch='b',date='2024-03-01',**{'from':'B','to':'A'}),
           dict(branch='b',date='2024-04-15',**{'from':'A','to':'B'}),
           dict(branch='ref',date='2024-02-15',**{'from':'A','to':'B'})]
    movie=dict(schema='wings.phylogeography-movie.v1',synthetic=True,title='Synthetic comparison fixture',
       provenance=dict(method='Synthetic fixture',inference='synthetic',uncertainty='conditional-on-fixed-tree'),
       locations=[dict(id='A',label='A',lat=40,lon=-80),dict(id='B',label='B',lat=37,lon=-85)],
       segments=[dict(id='HA',nodes=nodes,histories=[dict(id='one',root_state='A',jumps=jumps)])])
    record=dict(id='HA/balanced/replicate_1',segment='HA',strategy='balanced',replicate=1,status='complete',reasons=[],study=2,references=1,
        focal_sample_ids=['WINGS-a','WINGS-b'],focal_mrca='mrca',introductions={'B':dict(mean=1,lower=1,upper=1,zero_probability=0)})
    return movie,record

class ComparisonTests(unittest.TestCase):
    def test_scope_excludes_stem_and_reference_but_preserves_movie(self):
        m,r=fixture();scoped,info=scoped_movie(m,r)
        self.assertEqual(info['histograms'],{'B':{'1':1}})
        self.assertEqual(info['study_mrca_date'],'2024-02-01')
        self.assertEqual(info['root_date'],'2024-01-01')
        self.assertEqual(scoped['segments'][0]['histories'],m['segments'][0]['histories'])
        self.assertNotIn('focal_sample_ids',m['segments'][0])

    def test_mismatched_results_and_missing_study_tips_fail(self):
        for field,value in [('focal_mrca','root'),('focal_sample_ids',['WINGS-a','absent']),('introductions',{'B':{'mean':3}})]:
            m,r=fixture();r[field]=value
            with self.assertRaises(ValueError):scoped_movie(m,r)

    def test_offline_bundle_blocked_primary_escape_and_clock_dates(self):
        m,r=fixture();r2=dict(r,id='HA/balanced/replicate_2',replicate=2,status='blocked',reasons=['clock failed'],introductions={})
        r['strategy']='</script><script>alert(1)</script>'
        summary=dict(analyses=[r,r2],primary_analyses=[r2['id']])
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);folder=root/'inference'/r['id'];folder.mkdir(parents=True)
            (folder/'movie.json').write_text(json.dumps(m))
            (folder/'clock_points.tsv').write_text('id\tdate\tsource\troot_distance\tcluster\na\t2024-04-01\tstudy\t0.02\t0\n')
            model=write_comparison(summary,root)
            self.assertEqual(model['primary_analyses'],[r2['id']])
            self.assertIsNone(model['analyses'][1]['movie_script'])
            self.assertAlmostEqual(model['analyses'][0]['clock_points'][0]['date'],2024.249,places=2)
            self.assertNotIn('</script><script>alert',(root/'comparison.html').read_text())
            self.assertTrue((root/model['analyses'][0]['movie_script']).is_file())
            self.assertTrue((root/'comparison_assets/phylogeography-movie.js').is_file())

    def test_bayesian_overlay_requires_matching_inputs_and_focal_set(self):
        import hashlib
        m,r=fixture()
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);folder=root/'inference'/r['id'];folder.mkdir(parents=True)
            for name,value in [('movie.json',m),('result.json',r),('dated_nodes.json',m['segments'][0]['nodes'])]:
                (folder/name).write_text(json.dumps(value))
            (folder/'alignment.fasta').write_text('synthetic alignment fixture')
            tips=root/'selection'/r['id']/'tips.tsv';tips.parent.mkdir(parents=True);tips.write_text('synthetic tips')
            hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ('result.json','dated_nodes.json','alignment.fasta')}
            hashes['tips.tsv']=hashlib.sha256(tips.read_bytes()).hexdigest()
            dating=dict(status='not_converged',analysis=r['id'],input_sha256=hashes,focal_sample_ids=r['focal_sample_ids'],tmrca=None)
            path=root/'bayesian'/r['id']/'initial/summary.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(dating))
            summary=dict(analyses=[r],primary_analyses=[r['id']])
            model=write_comparison(summary,root)
            self.assertEqual(model['analyses'][0]['bayesian_dating']['status'],'not_converged')
            ml=folder/'ml.treefile';ml.write_text('original ML fixture')
            dating['input_sha256']['ml.treefile']=hashlib.sha256(ml.read_bytes()).hexdigest()
            path.write_text(json.dumps(dating))
            self.assertEqual(write_comparison(summary,root)['analyses'][0]['bayesian_dating']['status'],'not_converged')
            ml.write_text('changed ML refinement')
            self.assertEqual(write_comparison(summary,root)['analyses'][0]['bayesian_dating']['status'],'stale_or_mismatched')
            ml.write_text('original ML fixture')
            (folder/'alignment.fasta').write_text('changed fixture')
            model=write_comparison(summary,root)
            self.assertEqual(model['analyses'][0]['bayesian_dating']['status'],'stale_or_mismatched')
            self.assertIsNone(model['analyses'][0]['bayesian_dating']['tmrca'])

    def test_no_path_traversal(self):
        m,r=fixture();r['id']='../../other'
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):write_comparison(dict(analyses=[r],primary_analyses=[]),Path(t))

if __name__=='__main__':unittest.main()
