import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/'scripts/wings_amino_acids.py'
spec=importlib.util.spec_from_file_location('coords',p);aa=importlib.util.module_from_spec(spec);spec.loader.exec_module(aa)

def feature(text):return aa.features('>Feature x\n'+text)[0]

def mapping(seq,f):
    _,issues=aa.translate_feature(seq,f)
    return aa.cds_coordinate_map(seq,f,issues)

class CoordinateTests(unittest.TestCase):
    def test_forward_codons(self):
        m=mapping('ATGGAGAAATAA',feature('1\t12\tCDS'))
        self.assertEqual([c['positions'] for c in m['codons']],[[1,2,3],[4,5,6],[7,8,9],[10,11,12]])
        self.assertEqual([c['amino_acid'] for c in m['codons']],list('MEK*'))
    def test_codon_spanning_splice_junction(self):
        m=mapping('ATCCCGAAATAA',feature('1\t2\tCDS\n6\t12'))
        self.assertEqual(m['codons'][0]['positions'],[1,2,6])
        self.assertEqual(m['codons'][0]['bases'],'ATG')
        self.assertTrue(m['codons'][0]['crosses_junction'])
        self.assertEqual(m['codons'][1]['positions'],[7,8,9])
    def test_reverse_joined_codons(self):
        # Biological CDS is reverse complement of 12..11, then 7..1.
        seq='TTATTTCGCCAT'
        m=mapping(seq,feature('12\t11\tCDS\n7\t1'))
        self.assertEqual(m['codons'][0]['positions'],[12,11,7])
        self.assertEqual(m['codons'][0]['bases'],'ATG')
        self.assertTrue(m['codons'][0]['crosses_junction'])
        self.assertEqual(m['codons'][-1]['positions'],[3,2,1])
    def test_partial_codon_start(self):
        m=mapping('AATGAAATAA',feature('<1\t10\tCDS\n\t\t\tcodon_start\t2'))
        self.assertEqual(m['status'],'PARTIAL_CDS')
        self.assertEqual(m['codons'][0]['positions'],[2,3,4])
        self.assertEqual(m['codons'][0]['amino_acid'],'M')
    def test_slippage_is_not_guessed(self):
        m=mapping('ATGAAATAA',feature('1\t9\tCDS\n\t\t\tribosomal_slippage\t'))
        self.assertEqual(m['status'],'UNSUPPORTED_TRANSLATION');self.assertEqual(m['codons'],[])
    def test_overlap_within_cds_is_not_guessed(self):
        m=mapping('ATGAAATAA',feature('1\t6\tCDS\n5\t9'))
        self.assertEqual(m['status'],'UNSUPPORTED_TRANSLATION')
    def test_other_cds_frame_is_independent(self):
        one=mapping('AATGAAATAA',feature('1\t9\tCDS'))
        two=mapping('AATGAAATAA',feature('2\t10\tCDS'))
        self.assertEqual(one['codons'][0]['positions'],[1,2,3]);self.assertEqual(two['codons'][0]['positions'],[2,3,4])
    def test_trailing_partial_codon(self):
        m=mapping('ATGAAATA',feature('1\t8\tCDS'))
        self.assertEqual(m['untranslated_terminal_positions'],[7,8])
    def test_reverse_complement_bases(self):
        m=mapping('TTATTTCAT',feature('9\t1\tCDS'))
        self.assertEqual(m['codons'][0]['bases'],'ATG')
        self.assertEqual(m['codons'][1]['bases'],'AAA')
    def test_downstream_of_stop_is_flagged(self):
        m=mapping('ATGTAAGCTTAA',feature('1\t12\tCDS'))
        self.assertFalse(m['codons'][1]['after_stop'])
        self.assertTrue(m['codons'][2]['after_stop'])
    def test_ambiguity_preserved(self):
        m=mapping('ATGNNNTAA',feature('1\t9\tCDS'))
        self.assertEqual(m['codons'][1]['amino_acid'],'X')

if __name__=='__main__':unittest.main()
