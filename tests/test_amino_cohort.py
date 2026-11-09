import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cohort',ROOT/'scripts/assign_cohort_amino_references.py');cohort=importlib.util.module_from_spec(spec);spec.loader.exec_module(cohort)


def samples(evidence_hash):
    base={'NS1':'MACDEFGHIKLMNPQRS','NEP':'MNPQRSTVWYACDEFGH'};variants={}
    for gene,count in [('NS1',7),('NEP',3)]:
        variants[gene]=[base[gene]]+[base[gene][:i+2]+'W'+base[gene][i+3:] for i in range(count-1)]
    out=[]
    for i in range(30):
        proteins=[];refs=[]
        for gene,count in [('NS1',7),('NEP',3)]:
            n=i%count;sequence=variants[gene][n];accession='SYN_'+gene+'_'+str(n)+'.1';rid=accession+':'+gene
            refs.append(dict(id=rid,accession=accession,protein_id=accession,gene=gene,segment='NS',sequence=sequence,strain='Synthetic '+str(n),source_url='https://example.org/synthetic'))
            proteins.append(dict(gene=gene,segment='NS',seqid='ns',status='READY',query_sequence=sequence,reference_id=rid,reference_alignment=sequence,query_alignment=sequence,changes=[],issues=[]))
        out.append({'sample':'sample'+str(i),'proteins':proteins,'provenance':{'panel':{'schema_version':1,'references':refs},'evidence_sha256':evidence_hash,'min_identity':.9,'min_coverage':.9}})
    return out


class CohortTests(unittest.TestCase):
    def test_recovers_seven_and_three_variants_with_shared_references(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);evidence=root/'evidence.json';evidence.write_text(json.dumps({'schema_version':1,'entries':[]}))
            data=samples(cohort.aa.sha(evidence));paths=[];originals=[]
            for sample in data:
                path=root/(sample['sample']+'.json');path.write_text(json.dumps(sample));paths.append(path);originals.append(path.read_bytes())
            cohort.run(paths,root/'cohort',evidence)
            results=[json.loads((root/'cohort'/s['sample']/'changes.json').read_text()) for s in data]
            for gene,count in [('NS1',7),('NEP',3)]:
                records=[p for sample in results for p in sample['proteins'] if p['gene']==gene]
                self.assertEqual(len({p['reference_id'] for p in records}),1)
                self.assertEqual(len({p['query_sequence'] for p in records}),count)
                self.assertGreater(sum(len(p['changes']) for p in records),0)
            self.assertEqual([p.read_bytes() for p in paths],originals)
            panel=json.loads((root/'cohort/cohort_reference_panel.json').read_text())
            self.assertEqual(len(panel['references']),2);self.assertEqual(len(panel['cohort_samples']),30)
            self.assertEqual(results[0]['provenance']['panel_sha256'],cohort.aa.sha(root/'cohort/sample0/reference_panel.json'))
            cohort.aa.render(type('Args',(),dict(inputs=[str(root/'cohort'/s['sample']/'changes.json') for s in data],html=str(root/'report.html'),tsv=str(root/'report.tsv'),json=str(root/'report.json')))())
            html=(root/'report.html').read_text();self.assertIn('At least 80%',html);self.assertIn('All samples',html)
    def test_selection_is_stable_when_sample_order_changes(self):
        data=samples('hash');a=cohort.choose_panel(data);b=cohort.choose_panel(list(reversed(data)))
        self.assertEqual([r['id'] for r in a['references']],[r['id'] for r in b['references']])
    def test_evidence_mismatch_does_not_write_results(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);evidence=root/'evidence.json';evidence.write_text('{}');source=root/'s.json';source.write_text(json.dumps(samples('wrong')[0]))
            with self.assertRaises(ValueError):cohort.run([source],root/'out',evidence)
            self.assertFalse((root/'out').exists())
    def test_input_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'sample0/changes.json';source.parent.mkdir();source.write_text(json.dumps(samples('wrong')[0]))
            with self.assertRaises(ValueError):cohort.run([source],root,root/'evidence.json')

if __name__=='__main__':unittest.main()
