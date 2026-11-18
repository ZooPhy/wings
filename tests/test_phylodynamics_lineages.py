import csv, hashlib, json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phylodynamic_lineages as lin
import phylodynamic_temporal as temporal
import phylodynamic_selection as sel
from phylodynamic_inference import infer

def row(k,source='reference',sequence='ACGT'*30):
    return dict(id=k,source=source,accession=k if source=='reference' else '',sample_id=k if source=='study' else '',sequence=sequence,location='USA:KY',month='2024-01',date='2024-01-01',host='bird',sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest())

def call(clade='2.3.4.4b',status='good',errors=''):
    return {'clade':clade,'qc.overallStatus':status,'errors':errors,'isReverseComplement':'false'}

class Lineages(unittest.TestCase):
    def test_clade_scope_independent_of_dates_and_geography(self):
        study=[row('s','study')];refs=[row('a'),row('b'),row('c')]
        calls={'s':call(),'a':call(),'b':call('Am-nonGsGD'),'c':call(status='bad')}
        kept,excluded,audit=lin.classify(study,refs,calls)
        self.assertEqual([r['id'] for r in kept],['a'])
        self.assertEqual({r['reason'] for r in excluded},{'different_clade','nextclade_unusable'})
        self.assertEqual(audit['status'],'ready')
        refs[0].update(date='1900-01-01',location='ARG:ARG')
        self.assertEqual([r['id'] for r in lin.classify(study,refs,calls)[0]],['a'])

    def test_unresolved_and_mixed_study_clades_block(self):
        s=[row('s','study'),row('t','study')];refs=[row('r')]
        for c,reason in [(call('2.3.2.1a'),'multiple_study_clades_require_separate_analyses'),(call(errors='failed'),'study_clade_unresolved_or_bad_qc')]:
            kept,_,audit=lin.classify(s,refs,{'s':call(),'t':c,'r':call()})
            self.assertFalse(kept);self.assertIn(reason,audit['reasons']);self.assertEqual(len(s),2)
        with self.assertRaises(ValueError):lin.classify(s,refs,{'s':call()})

    def test_nearest_callable_overlap(self):
        s=[row('s','study','ACGTACGT')];refs=[row('r1'),row('r2'),row('r3')]
        a={'s':'ACGTACGT','r1':'ACGTACGT','r2':'ACGTACGA','r3':'------GT'}
        ids,audit=lin.nearest_anchors(s,refs,a,2)
        self.assertEqual(ids,['r1','r2']);self.assertEqual(audit[0]['compared_sites'],8)
        self.assertEqual(audit[1]['distance'],1/8)
        with self.assertRaises(ValueError):lin.nearest_anchors(s,refs,a,3)

    def test_anchor_retention_and_caps(self):
        pool=[row('r'+str(i)) for i in range(10)]
        for i,r in enumerate(pool):r['location']='USA:OH' if i<5 else 'USA:KY'
        cfg=sel.configuration(dict(max_references=4,max_per_location=3))
        for strategy in ('balanced','available','diversity'):
            chosen=sel.select(pool,[row('s','study')],cfg,strategy,4,['r0','r7'])
            self.assertEqual(len(chosen),4);self.assertTrue({'r0','r7'}<={r['id'] for r in chosen})
        with self.assertRaises(ValueError):sel.select(pool,[],cfg,'balanced',4,['r0','r1','r2','r3'])
        with self.assertRaises(ValueError):sel.select(pool,[],cfg,'available',4,['missing'])

    def test_frozen_dataset_reuse_offline_corruption(self):
        with tempfile.TemporaryDirectory() as t:
            cfg=lin.configuration(dict(cache_dir=t))
            with self.assertRaisesRegex(ValueError,'offline'):lin.frozen_dataset(cfg,True)
            def run(args,**kwargs):
                d=Path(args[args.index('--output-dir')+1]);d.mkdir()
                for n in ('reference.fasta','tree.json','pathogen.json'):(d/n).write_text('{}')
            listing=json.dumps([dict(path=lin.DATASET,version=dict(tag='test-version'))])
            with patch.object(lin.subprocess,'check_output',return_value=listing),patch.object(lin.subprocess,'run',side_effect=run) as tool:
                d,manifest=lin.frozen_dataset(cfg)
                self.assertEqual(manifest['resolved_tag'],'test-version');self.assertEqual(tool.call_count,1)
                self.assertIn('test-version',tool.call_args.args[0])
                self.assertEqual(lin.frozen_dataset(cfg,True)[1],manifest)
            (d/'reference.fasta').write_text('corrupt')
            with self.assertRaisesRegex(ValueError,'changed'):lin.frozen_dataset(cfg,True)

    def test_screen_adapter_orientation_and_audit(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);study=[row('s','study')];refs=[row('r'),row('out')]
            def run(args,**kwargs):
                table=Path(args[args.index('--output-tsv')+1]);aln=Path(args[args.index('--output-fasta')+1])
                calls=[dict(seqName=k,**call('other' if k=='out' else '2.3.4.4b')) for k in ('s','r','out')]
                calls[1]['isReverseComplement']='true'
                with table.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(calls[0]),delimiter='\t');w.writeheader();w.writerows(calls)
                aln.write_text(''.join('>'+k+'\n'+'ACGT'*30+'\n' for k in ('s','r','out')))
            with patch.object(lin,'frozen_dataset',return_value=(p,{'resolved_tag':'test'})),patch.object(lin.subprocess,'check_output',return_value='nextclade test'),patch.object(lin.subprocess,'run',side_effect=run):
                kept,excluded,audit=lin.screen(study,refs,'HA',p/'out',lin.configuration({}),1)
            self.assertEqual(len(kept),1);self.assertEqual(audit['anchor_ids'],['r'])
            self.assertTrue(audit['decisions'][1]['reverse_complemented'])
            self.assertEqual(excluded[0]['reason'],'different_clade')
            self.assertTrue((p/'out/lineage.json').is_file())

    def test_unsupported_segment_and_legacy_inference_block(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);kept,_,audit=lin.screen([row('s','study')],[row('r')],'NA',p,lin.configuration({}),1)
            self.assertFalse(kept);self.assertEqual(audit['status'],'blocked')
            selection=dict(id='HA/balanced/replicate_1',segment='HA',strategy='balanced',replicate=1,seed=1,study=1,references=1,locations={},config=sel.configuration({}),status='ready',reasons=[])
            (p/'selection.json').write_text(json.dumps(selection))
            out=p/'inference';out.mkdir();(out/'movie.json').write_text('{}');(out/'dated_nodes.json').write_text('[]')
            result=infer(p,out,1)
            self.assertIn('missing_or_unresolved_lineage_screen',result['reasons'])
            self.assertIsNone(json.loads((out/'movie.json').read_text()));self.assertFalse((out/'dated_nodes.json').exists())

class Temporal(unittest.TestCase):
    def fixture(self):
        from datetime import date
        meta={f't{i}':{'date':f'{2010+i}-01-01'} for i in range(12)}
        start=date(2009,1,1).toordinal()
        lengths={k:(date.fromisoformat(v['date']).toordinal()-start)/365.25*.002 for k,v in meta.items()}
        return '('+','.join(f'{k}:{lengths[k]:.14f}' for k in meta)+');',meta

    def test_known_clock_and_root_search(self):
        import numpy as np
        tree,meta=self.fixture();m=temporal.Regression(tree,meta);fit=m.fit(m.dates)
        self.assertAlmostEqual(fit['rate'],.002,places=10);self.assertAlmostEqual(fit['r2'],1,places=10)
        dates=np.random.default_rng(17).permutation(m.dates);result=m.fit(dates)
        x=dates-dates.mean();best=float('inf')
        for edge,(u,v,l) in enumerate(m.edges):
            for fraction in np.linspace(0,l,201):
                y=m.Y[edge]+fraction*m.S[edge];yc=y-y.mean();res=yc-x*(x@yc)/(x@x)
                best=min(best,float(res@res))
        self.assertLessEqual(result['sse'],best+1e-14);self.assertAlmostEqual(result['sse'],best,delta=1e-8)

    def test_same_date_clusters(self):
        meta={k:dict(date=f'{2020+i}-01-01') for k,i in zip('abcdef',[0,0,1,1,3,4])}
        m=temporal.Regression('((a:1,b:1):1,(c:1,d:1):2,e:5,f:6);',meta)
        groups=[{m.ids[i] for i in g} for g in m.clusters(m.fit(m.dates))]
        self.assertIn({'a','b'},groups);self.assertIn({'c','d'},groups)

    def test_clock_diagnostics_reproducible_and_weak_fit_blocks(self):
        tree,meta=self.fixture()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);f=p/'tree';f.write_text(tree);cfg=temporal.configuration(dict(permutations=99))
            a=temporal.diagnose(f,meta,p,cfg,.1,14);b=temporal.diagnose(f,meta,p,cfg,.1,14)
            self.assertEqual(a,b);self.assertEqual(a['status'],'passed')
            self.assertEqual(a['permutations']['tips']['p_value'],.01)
            f.write_text('('+','.join(k+':.01' for k in meta)+');')
            a=temporal.diagnose(f,meta,p,cfg,.1,14)
            self.assertEqual(a['status'],'blocked');self.assertIn('weak_raw_ml_clock_fit',a['reasons'])

    def test_invalid_inputs(self):
        for s in ('(a:-1,b:2,c:3);','(a:nan,b:1);','(a:1,b:2)'):
            with self.assertRaises(ValueError):temporal.parse_tree(s)
        with self.assertRaises(ValueError):temporal.Regression('(a:1,b:2,c:3);',{'a':{'date':'2020-01-01'}})
        for cfg in ({'permutations':1},{'alpha':float('nan')},{'extra':True}):
            with self.assertRaises(ValueError):temporal.configuration(cfg)
@unittest.skipUnless(__import__('os').environ.get('WINGS_TEST_PHYLODYNAMIC_LINEAGES')=='1', 'Requires real Nextclade and dataset download')
class NextcladeIntegration(unittest.TestCase):
    def test_dataset_reference_and_reverse_complement(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);cfg=lin.configuration(dict(cache_dir=str(p/'cache')))
            dataset,_=lin.frozen_dataset(cfg)
            seq=next(iter(lin.read_fasta(dataset/'reference.fasta').values())).replace('-','')
            reverse=seq.translate(str.maketrans('ACGT','TGCA'))[::-1]
            study=[row('study','study',seq)];refs=[row('forward',sequence=seq),row('reverse',sequence=reverse)]
            kept,_,audit=lin.screen(study,refs,'HA',p/'classification',cfg,1)
            self.assertEqual(audit['status'],'ready',audit);self.assertEqual(len(kept),2)
            self.assertTrue(next(x for x in audit['decisions'] if x['id']=='reverse')['reverse_complemented'])
            self.assertEqual(kept[1]['sequence'],seq)

if __name__=='__main__':unittest.main()

