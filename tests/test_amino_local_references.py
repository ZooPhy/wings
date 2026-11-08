import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_refs',ROOT/'scripts/assign_amino_references.py');local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)


def xml(sequence='ATGCCCGAGTAA',accession='NC_999999.1',ha=False):
    root=ET.Element('GBSet');record=ET.SubElement(root,'GBSeq');ET.SubElement(record,'GBSeq_accession-version').text=accession;ET.SubElement(record,'GBSeq_sequence').text=sequence.lower()
    features=ET.SubElement(record,'GBSeq_feature-table')
    def feature(kind,loc,**quals):
        f=ET.SubElement(features,'GBFeature');ET.SubElement(f,'GBFeature_key').text=kind;ET.SubElement(f,'GBFeature_location').text=loc
        qs=ET.SubElement(f,'GBFeature_quals')
        for k,v in quals.items():q=ET.SubElement(qs,'GBQualifier');ET.SubElement(q,'GBQualifier_name').text=k;ET.SubElement(q,'GBQualifier_value').text=v
    feature('source','1..12',strain='Synthetic reference')
    if ha:
        feature('CDS','1..12',product='hemagglutinin',translation='MAC',protein_id='TEST_HA.1')
        feature('sig_peptide','1..3');feature('mat_peptide','4..6',product='HA1');feature('mat_peptide','7..12',product='HA2')
    else:
        feature('CDS','1..12',product='matrix protein 1',translation='MPE',protein_id='TEST_M1.1')
        feature('CDS','join(1..3,7..12)',product='matrix protein 2',translation='ME',protein_id='TEST_M2.1')
    return ET.tostring(root)


class LocalReferenceTests(unittest.TestCase):
    def test_versioned_accession_and_spliced_cds(self):
        records=local.references_from_xml(xml(),'NC_999999.1','MP','ATGCCCGAGTAA')
        self.assertEqual([(r['gene'],r['sequence']) for r in records],[('M1','MPE'),('M2','ME')])
        self.assertEqual(records[0]['strain'],'Synthetic reference')
        with self.assertRaises(ValueError):local.references_from_xml(xml(),'NC_999999.2','MP','ATGCCCGAGTAA')
        with self.assertRaises(ValueError):local.references_from_xml(xml(),'NC_999999.1','MP','ATGGGGGAGTAA')
        self.assertEqual(local.references_from_xml(xml(),'NC_999999.1','HA','ATGCCCGAGTAA'),[])
    def test_location_guards(self):
        self.assertEqual(local.location('complement(join(1..3,7..12))'),[(12,7),(3,1)])
        for text in ['<1..12','order(1..3,7..12)','OTHER.1:1..12']:
            with self.assertRaises(ValueError):local.location(text)
    def test_reference_regions_from_annotations(self):
        records=local.references_from_xml(xml('ATGGCTTGTTAA',ha=True),'NC_999999.1','HA','ATGGCTTGTTAA')
        self.assertEqual([(r['name'],r['start'],r['end']) for r in records[0]['reference_regions']],[('Signal peptide',1,1),('HA1',2,2),('HA2',3,3)])
    def test_manifest_checksum(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fasta=root/'reference.fasta';fasta.write_text('>NC_999999.1 |Synthetic segment 7\nATGCCCGAGTAA\n');manifest=root/'manifest.tsv'
            manifest.write_text('database_name\tfasta_sha256\nfluA_db\t'+local.aa.sha(fasta)+'\n')
            records,row=local.read_database(fasta,manifest);self.assertEqual(records['NC_999999.1'],'ATGCCCGAGTAA')
            fasta.write_text(fasta.read_text()+'A\n')
            with self.assertRaises(ValueError):local.read_database(fasta,manifest)
    def test_identical_references_are_equivalents(self):
        panel={'references':[dict(id='B.1:M1',gene='M1',segment='MP',sequence='MPE',accession='B.1',protein_id='B_P.1'),dict(id='A.1:M1',gene='M1',segment='MP',sequence='MPE',accession='A.1',protein_id='A_P.1')]}
        p=dict(gene='M1',segment='MP',query_sequence='MPE',issues=[],changes=[])
        local.aa.assess_protein(p,panel,[],.9,.9);self.assertEqual(p['status'],'READY');self.assertEqual(p['reference_id'],'A.1:M1');self.assertEqual(len(p['reference_equivalents']),2)
    def test_nonidentical_reference_ties_withheld(self):
        refs=[dict(id=name+'.1:HA',gene='HA',segment='HA',sequence=seq,accession=name+'.1',protein_id=name+'_P.1') for name,seq in [('A','MAYDE'),('B','MAWDE')]]
        p=dict(gene='HA',segment='HA',query_sequence='MACDE',issues=[],changes=[])
        local.aa.assess_protein(p,{'references':refs},[],0,0);self.assertEqual(p['status'],'AMBIGUOUS_REFERENCE')
    def test_offline_cli_and_report(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);cache=root/'cache';cache.mkdir();(cache/'NC_999999.1.xml').write_bytes(xml())
            fasta=root/'db.fasta';fasta.write_text('>NC_999999.1 |Synthetic reference\nATGCCCGAGTAA\n')
            manifest=root/'manifest.tsv';manifest.write_text('database_name\tfasta_sha256\nsynthetic\t'+local.aa.sha(fasta)+'\n')
            (root/'db.nin').write_text('synthetic index placeholder')
            evidence=root/'evidence.json';evidence.write_text(json.dumps({'schema_version':1,'entries':[]}))
            source=root/'source.json';source.write_text(json.dumps({'sample':'synthetic','proteins':[{'seqid':'q','gene':'M2','segment':'MP','query_sequence':'ME','status':'READY','changes':[],'issues':[]}],'segment_sequences':[{'seqid':'q','segment':'MP','sequence':'ATGCCCGAGTAA'}],'provenance':{'min_identity':.9,'min_coverage':.9}}));before=source.read_bytes()
            blast=root/'fake_blastn';blast.write_text('#!'+sys.executable+'\nimport sys\nprint("synthetic blast version" if "-version" in sys.argv else "NC_999999.1\\t100\\t100\\t100")\n');blast.chmod(0o755)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/assign_amino_references.py'),'--inputs',str(source),'--output-dir',str(root/'out'),'--fasta',str(fasta),'--db',str(root/'db'),'--manifest',str(manifest),'--cache',str(cache),'--evidence',str(evidence),'--blastn',str(blast),'--offline'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            out=root/'out/synthetic/changes.json';data=json.loads(out.read_text());self.assertEqual(data['proteins'][0]['reference_id'],'NC_999999.1:M2')
            self.assertEqual(data['provenance']['panel_sha256'],local.aa.sha(root/'out/synthetic/reference_panel.json'));self.assertEqual(source.read_bytes(),before)
            local.aa.render(argparse.Namespace(inputs=[str(out)],html=str(root/'report.html'),tsv=str(root/'report.tsv'),json=str(root/'report.json')))
            self.assertIn('Synthetic reference',(root/'report.html').read_text())

    def test_offline_assignment_from_saved_proteins(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);manifest=root/'manifest.tsv';manifest.write_text('synthetic manifest');fasta=root/'db.fa';fasta.write_text('>NC_999999.1\nATGCCCGAGTAA\n');evidence=root/'evidence.json';evidence.write_text(json.dumps({'schema_version':1,'entries':[]}))
            args=argparse.Namespace(db=root/'db',cache=root/'cache',offline=True,evidence=evidence,manifest=manifest,fasta=fasta,candidates=3,min_nt_identity=70,min_query_coverage=80,blast_version='synthetic')
            data={'sample':'synthetic','proteins':[{'gene':'M2','segment':'MP','query_sequence':'ME','status':'READY','changes':[],'issues':[]}],'segment_sequences':[{'seqid':'q','segment':'MP','sequence':'ATGCCCGAGTAA'}],'provenance':{'panel':{'old':True},'min_identity':.9,'min_coverage':.9}}
            before=json.dumps(data,sort_keys=True)
            with patch.object(local,'shortlist',return_value=[{'accession':'NC_999999.1','bitscore':100,'identity':100,'query_coverage':100}]),patch.object(local,'cached_record',return_value=xml()):
                result=local.assign_sample(data,{'NC_999999.1':'ATGCCCGAGTAA'},{'database_name':'synthetic'},args,root)
            self.assertEqual(result['proteins'][0]['reference_id'],'NC_999999.1:M2');self.assertEqual(result['proteins'][0]['status'],'READY');self.assertEqual(json.dumps(data,sort_keys=True),before)
            with self.assertRaises(ValueError):local.cached_record('NC_999999.1',root/'missing',True)

if __name__=='__main__':unittest.main()
