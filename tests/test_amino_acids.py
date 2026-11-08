import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aa',ROOT/'scripts/wings_amino_acids.py')
aa=importlib.util.module_from_spec(spec);spec.loader.exec_module(aa)

class AminoTests(unittest.TestCase):
    def test_translation(self):
        self.assertEqual(len(aa.CODE),64)
        f=aa.features('>Feature x\n1\t12\tCDS\n\t\t\tproduct\tPB2 protein\n')[0]
        self.assertEqual(aa.translate_feature('ATGGAGAAATAA',f),('MEK',[]))
    def test_spliced_and_reverse(self):
        for seq,tbl in [('ATGCCCGAGTAA','1\t3\tCDS\n7\t12'),('TTATTTCAT','9\t1\tCDS')]:
            f=aa.features('>Feature x\n'+tbl+'\n\t\t\tproduct\tmatrix protein 2')[0]
            protein,issues=aa.translate_feature(seq,f)
            self.assertEqual(protein,'ME' if len(seq)==12 else 'MK');self.assertEqual(issues,[])
    def test_partial_frame_exception(self):
        f=aa.features('>Feature x\n<1\t8\tCDS\n\t\t\tcodon_start\t2\n\t\t\tribosomal_slippage\t')[0]
        _,issues=aa.translate_feature('AATGAAAT',f)
        self.assertIn('PARTIAL_CDS',issues);self.assertIn('UNSUPPORTED_TRANSLATION_EXCEPTION',issues)
        self.assertIn('INCOMPLETE_CODON_OR_FRAMESHIFT',issues)
    def test_overlap_separate_genes(self):
        f=aa.features('>Feature x\n1\t9\tCDS\n\t\t\tproduct\tpolymerase PB1\n2\t10\tCDS\n\t\t\tproduct\tPB1-F2 protein')
        self.assertEqual([aa.gene_name(x['qualifiers']) for x in f],['PB1','PB1-F2'])
    def test_invalid_bounds(self):
        f=aa.features('>Feature x\n1\t99\tCDS')[0]
        with self.assertRaises(ValueError):aa.translate_feature('ATG',f)
    def test_substitution(self):
        c=aa.compare('MACDEFGHIKLMNPQ','MACDEYGHIKLMNPQ')
        self.assertFalse(c['ambiguous_alignment']);self.assertEqual(c['changes'][0]['change'],'F6Y')
    def test_gap_numbering(self):
        c=aa.compare('MACDEFGHIKLMNPQ','MACDEFWGHIKLMNPY')
        self.assertEqual(c['changes'][-1]['change'],'Q15Y')
        self.assertEqual(c['changes'][0]['kind'],'insertion')
    def test_ambiguous_gap(self):
        self.assertTrue(aa.compare('MAAAACDEFG','MAAACDEFG')['ambiguous_alignment'])
    def test_unknown_not_substitution(self):
        self.assertEqual(aa.compare('MACDEFG','MACXEFG')['changes'],[])
    def test_stop_suppresses_downstream(self):
        c=aa.compare('MACDEFGHIKLM','MAC*EFYHIKLM')
        self.assertEqual(len(c['changes']),1);self.assertEqual(c['changes'][0]['kind'],'stop_gain')
    def test_product_disambiguation(self):
        self.assertEqual(aa.gene_name({'gene':['M'],'product':['matrix protein 2']}),'M2')
        self.assertEqual(aa.gene_name({'gene':['NS'],'product':['nuclear export protein']}),'NEP')
    def test_reference_evidence_guard(self):
        panel={'references':[{'id':'r','sequence':'MEK'}]}
        bad={'schema_version':1,'entries':[dict(reference_id='r',position=2,reference_aa='D',citation_url='https://example.org',statement='test',study_context='synthetic')]}
        with self.assertRaises(ValueError):aa.evidence_check(bad,panel)
    def test_fasta_duplicate(self):
        with self.assertRaises(ValueError):aa.fasta('>x\nAAA\n>x\nCCC')
    def test_end_to_end_and_safe_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'vadr').mkdir()
            ref='MACDEFGHIKLMNPQ';query='MACDEYGHIKLMNPQ'
            codons={v:k for k,v in aa.CODE.items()}
            nt=''.join(codons[x] for x in query)+'TAA'
            (p/'seq.fa').write_text('>x\n'+nt+'\n')
            (p/'vadr/x.vadr.pass.tbl').write_text('>Feature x\n1\t'+str(len(nt))+'\tCDS\n\t\t\tproduct\tPB2 protein\n')
            panel={'schema_version':1,'references':[dict(id='SYN.1:PB2',accession='SYN.1',protein_id='TEST.1',gene='PB2',segment='PB2',sequence=ref,source_url='https://example.org')]}
            (p/'panel.json').write_text(json.dumps(panel));(p/'evidence.json').write_text(json.dumps({'schema_version':1,'entries':[]}))
            args=argparse.Namespace(sample='test</script>',enabled=1,vadr_dir=str(p/'vadr'),panel=str(p/'panel.json'),evidence=str(p/'evidence.json'),consensus=[('PB2',str(p/'seq.fa'))],min_identity=.9,min_coverage=.9,output=str(p/'sample.json'))
            aa.analyze(args);data=json.loads((p/'sample.json').read_text())
            self.assertEqual(data['proteins'][0]['changes'][0]['change'],'F6Y')
            self.assertEqual(data['status'],'READY');self.assertIn('panel_sha256',data['provenance'])
            entry=dict(reference_id='SYN.1:PB2',position=6,reference_aa='F',alternate_aa='Y',statement='Synthetic annotation',study_context='Synthetic unit fixture',citation_url='https://example.org/test')
            (p/'evidence.json').write_text(json.dumps({'schema_version':1,'entries':[entry]}))
            aa.analyze(args);data=json.loads((p/'sample.json').read_text())
            self.assertEqual(data['proteins'][0]['changes'][0]['evidence'],[entry])
            entry['alternate_aa']='W';(p/'evidence.json').write_text(json.dumps({'schema_version':1,'entries':[entry]}))
            aa.analyze(args);data=json.loads((p/'sample.json').read_text())
            self.assertEqual(data['proteins'][0]['changes'][0]['evidence'],[])
            aa.render(argparse.Namespace(inputs=[args.output],html=str(p/'report.html'),tsv=str(p/'report.tsv'),json=str(p/'report.json')))
            text=(p/'report.html').read_text();self.assertNotIn('test</script>',text);self.assertIn('F6Y',text)
            (p/'run.html').write_text('<html><body>Run</body></html>')
            embed=argparse.Namespace(report=str(p/'run.html'),amino=str(p/'report.html'))
            aa.embed(embed);first=(p/'run.html').read_text();aa.embed(embed)
            self.assertEqual(first,(p/'run.html').read_text());self.assertIn('sandbox="allow-scripts allow-downloads"',first)
            args.panel=str(p/'absent');aa.analyze(args)
            self.assertEqual(json.loads((p/'sample.json').read_text())['status'],'NEEDS_REFERENCE')
            args.enabled=0;aa.analyze(args);self.assertEqual(json.loads((p/'sample.json').read_text())['status'],'DISABLED')


class AcquisitionTests(unittest.TestCase):
    def test_offline_preparation_requires_all_segments(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);f=p/'cds.faa';out=p/'panel.json'
            genes={'MP':'M1','NS':'NS1'}
            text=''.join('>lcl|'+acc+'_prot_TEST.1 [protein='+genes.get(seg,seg)+'] [protein_id=TEST.1]\nMACDEFGHIKLMNPQ\n' for acc,seg in aa.SEGMENTS.items())
            f.write_text(text)
            args=argparse.Namespace(output=str(out),fasta=str(f),replace=False)
            aa.prepare(args);self.assertEqual(len(json.loads(out.read_text())['references']),8)
            original=out.read_bytes();aa.prepare(args);self.assertEqual(original,out.read_bytes())
            f.write_text(text.split('>lcl|')[0]);args.replace=True
            with self.assertRaises(ValueError):aa.prepare(args)
            self.assertEqual(original,out.read_bytes())
    def test_wrong_accession_version(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);f=p/'cds.faa';f.write_text('>lcl|NC_007357.11_prot_TEST.1 [gene=PB2] [protein_id=TEST.1]\nMACD\n')
            with self.assertRaises(ValueError):aa.prepare(argparse.Namespace(output=str(p/'panel.json'),fasta=str(f),replace=False))

if __name__=='__main__':unittest.main()
