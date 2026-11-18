"""Real external-tool integration; enabled by the dedicated conda CI job."""
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from phylodynamic_selection import write_json, write_tsv, digest, configuration
from phylodynamic_inference import infer


@unittest.skipUnless(os.environ.get('WINGS_TEST_PHYLODYNAMIC_TOOLS')=='1', 'Requires MAFFT, IQ-TREE and TreeTime conda environment')
class ToolsIntegration(unittest.TestCase):
    def test_real_alignment_tree_dating_and_mapping(self):
        rng=random.Random(123)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); selected=root/'selected'; selected.mkdir()
            ancestor=''.join(rng.choice('ACGT') for _ in range(5000))
            rows=[];sequences=[]
            # Clocklike synthetic sequences; independent terminal substitutions
            # plus clade-specific inherited substitutions, with staggered dates.
            for i in range(16):
                seq=list(ancestor)
                for site in range((i//4)*25,(i//4)*25+25):
                    seq[site]=next(x for x in 'ACGT' if x!=seq[site])
                for site in rng.sample(range(150,5000),25+20*i):
                    seq[site]=rng.choice([x for x in 'ACGT' if x!=seq[site]])
                tid=f'tip{i}'
                rows.append(dict(id=tid,date=f'{2020+i//4}-{1+(i%4)*3:02d}-01',
                    location='USA:KY' if i%3 else 'USA:OH',sample_id=tid,accession=''))
                sequences.append('>'+tid+'\n'+''.join(seq)+'\n')
            fasta=selected/'input.fasta';fasta.write_text(''.join(sequences))
            write_tsv(selected/'tips.tsv',list(rows[0]),rows)
            write_json(selected/'selection.json',dict(id='HA/balanced/replicate_1',segment='HA',strategy='balanced',
                replicate=1,seed=17,study=16,references=0,status='ready',reasons=[],
                lineage=dict(status='ready',target_clade='synthetic-fixture'),
                config=configuration(dict(histories=50,min_clock_r2=.01,temporal=dict(permutations=99))),
                selected_sha256=digest(fasta),locations={'USA:KY':10,'USA:OH':6},
                location_metadata=[dict(id='USA:KY',label='Kentucky',lat=37,lon=-85),
                                   dict(id='USA:OH',label='Ohio',lat=40,lon=-83)]))
            result=infer(selected,root/'output',1)
            self.assertEqual(result['status'],'complete',result)
            self.assertGreater(result['clock_rate'],0)
            movie=json.loads((root/'output/movie.json').read_text())
            self.assertEqual(len(movie['segments'][0]['histories']),50)
            self.assertFalse(movie['synthetic'])  # schema marks inference; fixture itself is synthetic

if __name__=='__main__':unittest.main()
