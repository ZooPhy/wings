"""Opt-in two-request live NCBI compatibility check; no study data sent."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from phylodynamic_references import NCBI,reference_configuration,query_for,checked_xml,parse_genbank,matches_subtype
cfg=reference_configuration({});client=NCBI(cfg)
query=query_for(dict(subtypes=['H5'],segments=['HA']))
root=checked_xml(client.request('esearch',dict(db='nuccore',term=query,retmax=1,idtype='acc',retmode='xml')))
if root.find('ErrorList') is not None:raise RuntimeError('NCBI query errors; inspect query compatibility')
acc=root.findtext('./IdList/Id')
if not acc:raise RuntimeError('No H5 HA record returned by NCBI query')
rows=list(parse_genbank(client.request('efetch',dict(db='nuccore',id=acc,rettype='gb',retmode='xml'))))
assert len(rows)==1 and rows[0][0]['accession']==acc
assert rows[0][0]['segment']=='HA' and matches_subtype(rows[0][0]['subtype'],['H5'])
assert rows[0][1]
print('PASS: live NCBI query and versioned HA GenBank XML retrieval. Annotation is not independent clade validation.')
