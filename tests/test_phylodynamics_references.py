import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phylodynamic_references as ref
import phylodynamic_selection as sel
from phylodynamic_estimands import focal_branches,entry_count
from phylodynamic_benchmark import simulate,prune,sample_pool
import numpy as np


def xml(acc='AB123.1',segment='4',when='02-Jan-2024'):
    return f'''<GBSet><GBSeq><GBSeq_accession-version>{acc}</GBSeq_accession-version>
<GBSeq_definition>Influenza A virus (H5N1) segment {segment}</GBSeq_definition><GBSeq_sequence>{'acgt'*30}</GBSeq_sequence>
<GBSeq_feature-table><GBFeature><GBFeature_key>source</GBFeature_key><GBFeature_quals>
<GBQualifier><GBQualifier_name>segment</GBQualifier_name><GBQualifier_value>{segment}</GBQualifier_value></GBQualifier>
<GBQualifier><GBQualifier_name>collection_date</GBQualifier_name><GBQualifier_value>{when}</GBQualifier_value></GBQualifier>
<GBQualifier><GBQualifier_name>geo_loc_name</GBQualifier_name><GBQualifier_value>USA: Kentucky</GBQualifier_value></GBQualifier>
<GBQualifier><GBQualifier_name>host</GBQualifier_name><GBQualifier_value>Coragyps atratus</GBQualifier_value></GBQualifier>
<GBQualifier><GBQualifier_name>db_xref</GBQualifier_name><GBQualifier_value>BioSample:SAMN123</GBQualifier_value></GBQualifier>
</GBFeature_quals></GBFeature></GBSeq_feature-table></GBSeq></GBSet>'''.encode()


class References(unittest.TestCase):
    def test_source_qualifiers_dates_segments(self):
        row,seq=list(ref.parse_genbank(xml()))[0]
        self.assertEqual(row['segment'],'HA');self.assertEqual(row['collection_date'],'2024-01-02')
        self.assertEqual(row['state'],'Kentucky');self.assertEqual(row['specimen_id'],'BioSample:SAMN123')
        self.assertEqual(seq,'ACGT'*30)
        self.assertEqual(list(ref.parse_genbank(xml(when='2024-01')))[0][0]['collection_date'],'2024-01')
        self.assertEqual(ref.annotated_segment('segment 4','6'),'')
        self.assertEqual(ref.annotated_segment('unannotated'),'')
        self.assertFalse(ref.matches_subtype('H15N1',['H5']))
        self.assertTrue(ref.matches_subtype('H5N8',['H5']))

    def test_local_export_version_join_and_header_segment(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);f=p/'r.fasta';m=p/'r.tsv'
            f.write_text('>AB123.1 |Influenza A virus (H5N1) segment 4\nACGT\n')
            m.write_text('Accession\tCountry\tUSA\tCollection_Date\nAB123\tUSA\tKentucky\t2024-01-02\n')
            r=list(ref.local_records(f,m))[0][0];self.assertEqual(r['accession'],'AB123.1');self.assertEqual(r['segment'],'HA')
            f.write_text(f.read_text()+'>AB123.2 segment 4 H5N1\nACGT\n')
            with self.assertRaisesRegex(ValueError,'ambiguous'):list(ref.local_records(f,m))

    def test_local_missing_metadata_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'f').write_text('>AB123.1 segment 4 H5N1\nACGT\n');(p/'m').write_text('Accession\n')
            with self.assertRaisesRegex(ValueError,'missing from metadata'):list(ref.local_records(p/'f',p/'m'))

    def test_scope_uses_collection_not_release_and_no_private_query(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'meta';p.write_text('sample_id\tcollection_date\tcountry\tstate\tha_call\nprivate_001\t2024-06-01\tUSA\tKY\tH5\n')
            cfg=sel.configuration(dict(countries=[],lookback_days=30,lookahead_days=0))
            scope=ref.scope_from_study(p,cfg)
            self.assertEqual(scope['start'],'2024-05-02');self.assertEqual(scope['subtypes'],['H5'])
            q=ref.query_for(scope);self.assertNotIn('private',q);self.assertNotIn('2024',q)
            self.assertEqual(scope['countries'],[])

    def test_history_pagination_freezes_versions(self):
        class Fake:
            def __init__(self):self.calls=[]
            def request(self,u,p):
                self.calls.append((u,p))
                if u=='esearch':return b'<eSearchResult><Count>5001</Count><QueryKey>1</QueryKey><WebEnv>x</WebEnv></eSearchResult>'
                return '\n'.join(f'AB{n}.1' for n in range(p['retstart'],p['retstart']+p['retmax'])).encode()
        with tempfile.TemporaryDirectory() as t:
            f=Fake();cfg=ref.reference_configuration({});r=ref.accession_snapshot(f,Path(t),'q',cfg)
            self.assertEqual(len(r['accessions']),5001);self.assertEqual(len(f.calls),3)
            ref.accession_snapshot(f,Path(t),'q',cfg);self.assertEqual(len(f.calls),3)
            with self.assertRaisesRegex(ValueError,'exceeds'):ref.accession_snapshot(f,Path(t),'q',dict(cfg,max_records=1))

    def test_partial_ncbi_batch_and_corrupt_cache_fail(self):
        class Fake:
            def request(self,u,p):return xml()
        with tempfile.TemporaryDirectory() as t:
            cfg=ref.reference_configuration(dict(cache_dir=t,subtypes=['H5']))
            scope=dict(subtypes=['H5'],segments=['HA'])
            manifest=dict(accessions=['AB123.1','AB124.1'])
            with patch.object(ref,'accession_snapshot',return_value=manifest):
                with self.assertRaisesRegex(ValueError,'omitted'):list(ref.remote_records(scope,cfg,Fake()))
            with patch.object(ref,'accession_snapshot',return_value=dict(accessions=['AB123.1'])):
                self.assertEqual(len(list(ref.remote_records(scope,cfg,Fake()))),1)
                cached=next(Path(t).rglob('*.xml'));cached.write_text('bad')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):list(ref.remote_records(scope,cfg,Fake()))

    def test_network_credentials_are_not_in_cache_key_or_errors(self):
        cfg=ref.reference_configuration({})
        with patch.dict('os.environ',{'NCBI_EMAIL':'private@example.com','NCBI_API_KEY':'secret-key'}):
            client=ref.NCBI(cfg)
            self.assertEqual(client.key,'secret-key')
        with patch.object(ref.urllib.request,'urlopen',side_effect=ref.urllib.error.HTTPError('https://example/?api_key=secret-key',403,'forbidden',None,None)):
            with self.assertRaises(RuntimeError) as c:client.request('esearch',dict(term='test'))
            self.assertNotIn('secret',str(c.exception))

    def test_global_context_country_geography(self):
        aliases,locations=sel.geography();cfg=sel.configuration(dict(countries=[]))
        row=sel.prepare_row(dict(collection_date='2024-01-01',country='France',state='Brittany'),'ACGT'*30,'reference','x',aliases,cfg,120)
        self.assertEqual(row['location'],'FRA:FRA');self.assertIn('(country)',locations[row['location']]['label'])
        self.assertEqual(row['reasons'],[])

    @patch('phylodynamic_lineages.screen')
    def test_segment_only_build_without_genoflu_and_specimen_dedup(self, screening):
        def screened(study,candidates,segment,output,*args):
            audit=dict(status='ready',reasons=[],target_clade='fixture-clade',study_clades=['fixture-clade'],anchor_ids=[])
            sel.write_json(output/'lineage.json',audit)
            return candidates,[],audit
        screening.side_effect=screened
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);meta=p/'meta.tsv';results=p/'results'
            meta.write_text('sample_id\tcollection_date\tcountry\tstate\nS\t2024-06-01\tUSA\tKY\n')
            sel.write_tsv(results/'S/coverage/coverage.tsv',['segment','overall_status','contig'],[dict(segment='HA',overall_status='PASS',contig='HA_H5')])
            (results/'S/merged').mkdir();(results/'S/merged/consensus_all_segments.fasta').write_text('>HA_H5\n'+'ACGT'*30+'\n')
            rows=[dict(accession=f'AB{i}.1',segment='HA',collection_date=f'2024-0{1+i%4}-01',country='USA',state='OH',host='bird',specimen_id='') for i in range(5)]
            rows[1].update(rows[0],accession='AB1.1') # distinct animals, identical sequences/date/location retained
            rows[2]['specimen_id']='BioSample:proven';rows[3].update(rows[2],accession='AB3.1')
            sel.write_tsv(p/'refs.tsv',list(rows[0]),rows);(p/'refs.fa').write_text(''.join('>'+r['accession']+'\n'+'ACGT'*30+'\n' for r in rows))
            cfg=dict(strategies=['balanced'],replicates=1,min_tips=3,min_date_span_days=1)
            summary=sel.build(results,meta,p/'refs.tsv',p/'refs.fa',p/'out',cfg)
            self.assertEqual(summary['segments']['HA']['eligible_references'],4)
            self.assertEqual(summary['segments']['HA']['exclusions']['duplicate_specimen_sequence'],1)
            self.assertEqual(summary['replicates'][0]['study'],1)

    def test_focal_estimand_excludes_background_and_stem(self):
        nodes=[dict(id='root',parent=None),dict(id='a',parent='root'),dict(id='x',parent='a'),dict(id='y',parent='a'),dict(id='z',parent='root')]
        branches,root=focal_branches(nodes,['x','y']);self.assertEqual(root,'a');self.assertEqual(branches,{'x','y'})
        h=dict(jumps=[dict(branch=b,to='A') for b in ('a','x','y','z')]);self.assertEqual(entry_count(h,'A',branches),2)
        self.assertEqual(focal_branches(nodes,['x']),(set(),None))

    def test_simulation_truth_and_pruning_are_traceable(self):
        nodes,tips,history=simulate(41000,'equal_rates',40)
        self.assertEqual((nodes,tips,history),simulate(41000,'equal_rates',40))
        by_id={r['id']:r for r in nodes}
        for j in history['jumps']:
            r=by_id[j['branch']];self.assertLess(by_id[r['parent']]['date'],j['date']);self.assertLessEqual(j['date'],r['date'])
        sampled=prune(nodes,{r['id'] for r in tips[:5]});ids={r['id'] for r in sampled}
        self.assertTrue(all(r['parent'] is None or r['parent'] in ids for r in sampled))

if __name__=='__main__':unittest.main()
