import importlib.util
import io
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_public_health_interpretation.py"
spec = importlib.util.spec_from_file_location("interpretation", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def payload():
    return {
        "samples": [
            {"sample_id": "S1", "host": "goose", "country": "USA", "state": "AZ", "collection_date": "2026-01-01", "segments_pass": 8, "review_flags": "NONE"},
            {"sample_id": "S2", "host": "duck", "country": "USA", "state": "AZ", "collection_date": "2026-01-02", "segments_pass": 5, "review_flags": "LOW_COVERAGE"},
        ],
        "genomic_ecological_concordance": {"readiness": {"minimum_unique_samples": 8}, "models": [
            {"segment": "HA", "comparison": "host_vs_baseline", "status": "READY", "display_status": "READY", "n_samples": 10, "delta_r2": 0.2, "fdr_q": 0.01}
        ]},
        "outbreak_context": {"status": "READY", "source_name": "APHIS", "sha256": "abc", "states": {"AZ": "Arizona"}, "records": [{"source_row": 1, "state_code": "AZ", "collection_date": "2026-01-05", "detected_date": "2026-01-06"}]},
    }


def selection(evidence, observation="OBS-RUN-QC", actions=None):
    return {
        "headline": "Genome completeness differs among the sampled birds.",
        "what_we_know": [{"observation_id": observation}],
        "public_health_meaning": {"text": "The sampled genomes differ in completeness; comparisons need to retain their QC context.",
                                 "evidence_ids": evidence["observations"][observation]["evidence_ids"]},
        "recommended_actions": actions or [],
    }


def context_payload():
    source = payload()
    source["trees"] = {"HA": {"root": {"support": .95, "children": [{"sample_id": "S1"}, {"sample_id": "S2"}]}}}
    return source


def context_selection(evidence, extra=None):
    selected = module.synthesis_plan(evidence) + ([extra] if extra else [])
    return {
        "headline": "Interpret host group membership alongside collection timing and public detection context.",
        "what_we_know": [{"observation_id": key} for key in selected],
        "public_health_meaning": {
            "text": "Some selected segment-tree groups contain samples from different hosts, which were sampled on different collection dates. Public detection overlaps provide shared state-level context, but their presence alone does not distinguish the genomic groups. Compare the sampled hosts with collection timing alongside the segment results.",
            "evidence_ids": selected,
        },
        "recommended_actions": [],
    }


def relationship_selection(evidence, *, all_groups=True):
    catalog = module.relationship_catalog(evidence)
    groups = [key for key, row in catalog['claims'].items() if row['kind'] == 'group_membership']
    groups = groups[:3] if all_groups else groups[:1]
    relations = {catalog['claims'][key]['scope']['date_relation'] for key in groups}
    takeaway = ('SHARED-AND-DIFFERENT-DATES' if {'same_date', 'multiple_dates'} <= relations else
                'CROSS-HOST-TIME' if 'multiple_dates' in relations else 'CROSS-HOST')
    return {'takeaway_id': takeaway, 'claim_ids': groups + catalog['required_claim_ids'], 'recommended_actions': []}


def reported_context_response():
    return {
        "headline": "Segment‑tree groups largely separate by host, but a minority mix hosts and many genomes are incomplete",
        "what_we_know": [{"observation_id": "OBS-HOST-GROUPING"}, {"observation_id": "OBS-RUN-QC"}],
        "public_health_meaning": {
            "text": "Three of the 47 segment‑tree groups contain more than one host species, showing that most genomic clusters are host‑specific but a few cross‑species mixes exist. At the same time, only 14 of 30 samples have all eight segments passing quality control, indicating that a substantial portion of the data may be incomplete for downstream analyses.",
            "evidence_ids": ["OBS-HOST-GROUPING", "OBS-RUN-QC"],
        },
        "recommended_actions": [],
    }


def separate_host_groups():
    source = payload()
    labels = ['Black Vulture', 'Canada Goose', 'Red-tailed Hawk', 'Snow Goose', 'Turkey Vulture']
    source['samples'] = [{**source['samples'][index % 2], 'sample_id': f'S{index + 1}', 'host': label}
                         for index, label in enumerate(labels)]
    source['trees'] = {
        'NP': {'root': {'support': .95, 'children': [{'sample_id': 'S1'}, {'sample_id': 'S2'}]}},
        'PB2': {'root': {'support': .95, 'children': [{'sample_id': 'S3'}, {'sample_id': 'S4'}]}},
    }
    return source


def reported_conflation_response():
    return {
        'headline': 'Samples from multiple bird species were collected at different times across the same U.S. state, with all samples linked to state‑level surveillance records',
        'public_health_meaning': {
            'evidence_ids': ['OBS-HOST-GROUPING', 'OBS-HOST-TIMING', 'OBS-DETECTION-CONTEXT'],
            'text': 'The segment‑tree groups show that Black Vulture, Canada Goose, Red‑tailed Hawk, Snow Goose, and Turkey Vulture samples were all represented in the same genomic clusters, indicating that the sampled viruses are not confined to a single host species. Collection dates differ by host, so the observed host mixing cannot be attributed to a single sampling event. Every eligible sample also has a public detection record in the same state within 14 days of collection, providing state‑level surveillance context but not distinguishing the genomic groups. Together, these findings illustrate that the circulating viruses were sampled from diverse hosts over a spread of dates, all within the same geographic area, and that state surveillance data are available for each sample.”},',
        },
        'recommended_actions': [],
        'what_we_know': [{'observation_id': key} for key in ['OBS-HOST-GROUPING', 'OBS-HOST-TIMING', 'OBS-DETECTION-CONTEXT', 'OBS-RUN-QC']],
    }


def thirty_sample_context():
    """Synthetic regression fixture with distinct host pairs and 14/30 QC."""
    source = separate_host_groups()
    source['samples'] += [{**source['samples'][0], 'sample_id': f'S{index}'} for index in range(6, 31)]
    for index, sample in enumerate(source['samples']):
        sample['segments_pass'] = 8 if index < 14 else 5
        sample['collection_date'] = '2025-10-21'
    for index, day in enumerate(('2025-04-15', '2025-04-15', '2026-04-08', '2025-12-11')):
        source['samples'][index]['collection_date'] = day
    source['trees']['PA'] = {'root': {'support': .95, 'children': [{'sample_id': key} for key in ('S1', 'S2', 'S6')]}}
    source['outbreak_context']['records'] = [
        {'source_row': index, 'state_code': 'AZ', 'collection_date': day}
        for index, day in enumerate(('2025-04-15', '2025-10-21', '2025-12-11', '2026-04-08'))
    ]
    return source


def reported_precaution_response(evidence):
    response = context_selection(evidence, extra='OBS-RUN-QC')
    response['headline'] = 'Segment‑tree groups span multiple hosts and dates, with full‑segment genomes in half the samples'
    response['public_health_meaning']['text'] = (
        'The selected segment‑tree groups show that samples from different bird species—Black Vulture, Canada Goose, Red‑tailed Hawk, and Snow Goose—were collected on distinct dates and clustered together in the NP, PA, and PB2 segment trees. '
        'All eligible samples overlap the same US state and fall within 14 days of public detection records, providing state‑level surveillance context but not linking any sample to a specific case. '
        'Genome completeness is mixed: 14 of the 30 samples have all eight segments passing QC, while 16 have fewer than eight passing segments. '
        'This pattern indicates that while the sampling captures a range of hosts and times, only about half of the genomes are fully complete for downstream analysis. '
        'The findings highlight the need to review QC and missing‑segment records before drawing conclusions about viral circulation.'
    )
    return response


def analysis_payload():
    """Synthetic nested-model fixture; no sequencing or movement inference."""
    source = thirty_sample_context()
    base = ['temporal_days', 'geographic_km']
    rows = []
    for segment in ('HA', 'NP'):
        for family, reduced, added in (
            ('host_vs_baseline', base, 'same_host'),
            ('ecology_vs_host', base + ['same_host'], 'seasonal_profile_distance'),
            ('environment_vs_ecology', base + ['same_host', 'seasonal_profile_distance'], 'environmental_distance'),
            ('migration_vs_ecology', base + ['same_host', 'seasonal_profile_distance'], 'migration_context_distance'),
        ):
            row = dict(segment=segment, comparison=family, status='READY', display_status='READY',
                       reduced_status='READY', full_status='READY', n_samples=10, n_pairs=45,
                       reduced_predictors=','.join(reduced), full_predictors=','.join(reduced + [added]),
                       reduced_r2=.5, full_r2=.6, delta_r2=.1, fdr_q=.01, permutation_p=.005,
                       permutations_requested=999, permutations_valid=999)
            if family == 'ecology_vs_host' and segment == 'HA':
                row['fdr_q'] = .7
            if family == 'environment_vs_ecology':
                row.update(status='REDUCED_READY__FULL_RANK_DEFICIENT', display_status='INSUFFICIENT_INDEPENDENT_VARIATION',
                           full_status='RANK_DEFICIENT', full_r2=None, delta_r2=None, fdr_q=None, permutation_p=None)
            if family == 'migration_vs_ecology':
                row.update(status='INSUFFICIENT_MIGRATION_CONTEXTS', display_status='INSUFFICIENT_MIGRATION_CONTEXTS',
                           n_samples=8, n_pairs=28, n_migration_contexts=2, minimum_migration_contexts=8,
                           eligible_sample_ids=[f'S{i}' for i in range(1, 9)],
                           full_r2=None, delta_r2=None, fdr_q=None, permutation_p=None)
            rows.append(row)
    source['genomic_ecological_concordance'] = {
        'schema_version': 'wings.genomic_ecological_concordance.v3',
        'analysis_kind': 'exploratory_dyadic_model_comparison',
        'response': 'segment-specific patristic distance among unambiguous WINGS sample tips',
        'models': rows,
        'readiness': {'minimum_unique_samples': 8, 'samples_with_matched_migration_night': 28,
                      'total_samples': 30, 'distinct_migration_contexts': 5},
        'weather_summary': '7-day collection window',
    }
    return source


def analysis_selection(evidence):
    return {'takeaway_id': 'ANALYSIS-FINDING', 'claim_ids': module.relationship_catalog(evidence)['required_claim_ids'],
            'recommended_actions': []}


class AnalysisSynthesisTests(unittest.TestCase):
    def test_completed_analyses_take_priority_over_tree_membership_inventory(self):
        evidence = module.build_evidence(analysis_payload())
        response = analysis_selection(evidence)
        narrative = module.materialize_selection(response, evidence)
        self.assertEqual(narrative['grounding']['mode'], 'analysis_selection')
        self.assertIn('Bird species and seasonal patterns', narrative['headline'])
        self.assertEqual(module.validate_response(response, narrative, evidence), [])
        self.assertEqual(set(module.synthesis_plan(evidence)), {'OBS-ANALYSIS-' + code for code in ('HOST', 'ECOLOGY', 'WEATHER', 'MIGRATION')})
        self.assertTrue(all(2 <= len(row['bullets']) <= 3 for row in narrative['what_we_know']))
        self.assertIn('each comparison used 10 of the 30 samples', narrative['public_health_meaning']['note'])
        self.assertIn('10.0 percentage points', narrative['what_we_know'][0]['text'])
        self.assertEqual(len(narrative['public_health_meaning']['items']), 3)

    def test_agency_brief_is_short_and_technical_evidence_remains_separate(self):
        evidence = module.build_evidence(analysis_payload())
        narrative = module.materialize_selection(analysis_selection(evidence), evidence)
        meaning = narrative['public_health_meaning']
        visible = narrative['headline'] + ' ' + meaning['text'] + ' ' + meaning['note']
        self.assertLess(len(visible.split()), 150)
        for jargon in ('host identity', 'FDR', 'R²', 'predictor', 'estimable', 'denominator', 'NP, MP', 'subset', 'state-night'):
            self.assertNotIn(jargon, visible)
        self.assertIn('mix of birds sampled', meaning['text'])
        self.assertIn('later surveillance rounds', meaning['text'])
        self.assertIn('do not identify a weather condition or migration period', meaning['text'])
        self.assertIn('R²', narrative['what_we_know'][0]['text'])
        self.assertIn('state-night', narrative['what_we_know'][-1]['text'])
        changed = copy.deepcopy(narrative)
        changed['public_health_meaning']['note'] = 'All 30 samples supported this finding.'
        self.assertTrue(module.validate(changed, evidence))

    def test_surveillance_implications_require_their_supporting_findings(self):
        source = analysis_payload()
        for row in source['genomic_ecological_concordance']['models']:
            if row['comparison'] in ('host_vs_baseline', 'ecology_vs_host'):
                row['fdr_q'] = .8
        evidence = module.build_evidence(source)
        narrative = module.materialize_selection(analysis_selection(evidence), evidence)
        self.assertNotIn('Compare the same bird species over time', str(narrative['public_health_meaning']))
        self.assertNotIn('Follow the seasonal pattern', str(narrative['public_health_meaning']))
        self.assertIn('do not yet identify a surveillance priority', narrative['headline'])
        self.assertEqual(module.validate(narrative, evidence), [])

    def test_unestimated_weather_and_migration_preserve_their_own_denominators(self):
        evidence = module.build_evidence(analysis_payload())
        claims = module.concordance_catalog(evidence)['claims']
        migration = claims['ANALYSIS-MIGRATION']['observation']['text']
        self.assertIn('2 distinct state-night contexts', migration)
        self.assertIn('minimum is 8', migration)
        self.assertIn('28 of 30 samples', migration)
        self.assertIn('5 contexts', migration)
        self.assertIn('different denominator', migration)
        self.assertEqual(claims['ANALYSIS-WEATHER']['scope']['tested_segments'], [])
        self.assertIn('cannot be separated', claims['ANALYSIS-WEATHER']['observation']['text'])
        self.assertIn('HA: no statistical support', claims['ANALYSIS-ECOLOGY']['observation']['text'])
        self.assertEqual(claims['ANALYSIS-ECOLOGY']['scope']['supported_segments'], ['NP'])

    def test_all_comparison_families_required_and_free_prose_not_accepted(self):
        evidence = module.build_evidence(analysis_payload())
        response = analysis_selection(evidence)
        response['claim_ids'].remove('ANALYSIS-MIGRATION')
        self.assertIn('Include every required comparison family', module.validate_response(response, module.materialize_selection(response, evidence), evidence))
        response = analysis_selection(evidence)
        response['headline'] = 'Invented claim'
        self.assertTrue(module.validate_response(response, module.materialize_selection(response, evidence), evidence))

    def test_invalid_stats_predictors_and_duplicate_segments_cannot_support_claims(self):
        for change in ({'fdr_q': None}, {'fdr_q': float('nan')}, {'fdr_q': .05}, {'delta_r2': .8},
                       {'n_samples': 3}, {'permutations_valid': 0}, {'full_predictors': 'same_host'}, {'full_status': 'RANK_DEFICIENT'}):
            with self.subTest(change=change):
                source = analysis_payload()
                for row in source['genomic_ecological_concordance']['models']:
                    if row['comparison'] == 'host_vs_baseline':
                        row.update(change)
                evidence = module.build_evidence(source)
                self.assertEqual(module.concordance_catalog(evidence)['claims']['ANALYSIS-HOST']['scope']['supported_segments'], [])
        source = analysis_payload()
        source['genomic_ecological_concordance']['models'].append(copy.deepcopy(source['genomic_ecological_concordance']['models'][0]))
        evidence = module.build_evidence(source)
        self.assertEqual(module.concordance_catalog(evidence)['claims']['ANALYSIS-HOST']['scope']['supported_segments'], ['NP'])

    def test_changes_to_rendered_statistics_or_source_values_invalidate_summary(self):
        evidence = module.build_evidence(analysis_payload())
        response = analysis_selection(evidence)
        narrative = module.materialize_selection(response, evidence)
        changed = copy.deepcopy(narrative)
        changed['what_we_know'][0]['bullets'][1] = 'All 30 samples were analyzed.'
        self.assertTrue(module.validate(changed, evidence))
        next(row for row in evidence['facts'] if row['id'] == 'MODEL-001')['data']['fdr_q'] = .9
        self.assertTrue(module.validate(narrative, evidence))

    def test_prompt_and_schema_are_compact_and_retain_all_families(self):
        evidence = module.build_evidence(analysis_payload())
        system, user = module.prompt(evidence)
        schema = module.response_schema(evidence)
        self.assertEqual(schema['properties']['claim_ids']['minItems'], 4)
        self.assertEqual(schema['properties']['claim_ids']['maxItems'], 4)
        self.assertLess(len((system + user).encode()), 10000)
        self.assertNotIn('TREE-GROUP-', user)
        self.assertIn('ANALYSIS-MIGRATION', user)

    def test_cli_fresh_sources_include_analysis_metadata_and_revalidate_offline(self):
        source = analysis_payload()
        analysis = source.pop('genomic_ecological_concordance')
        evidence = module.build_evidence(source, analysis)
        response = analysis_selection(evidence)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explorer, concordance, output = root/'explorer.json', root/'concordance.json', root/'interpretation.json'
            explorer.write_text(json.dumps(source)); concordance.write_text(json.dumps(analysis))
            argv = ['interpretation', '--explorer-json', str(explorer), '--concordance-json', str(concordance),
                    '--output', str(output), '--enabled', 'true', '--model', 'test-model', '--fail-on-error']
            with patch('sys.argv', argv), patch.object(module, 'ollama_generate', return_value=(response, {})), patch.object(module, 'model_digest', return_value='test'):
                self.assertEqual(module.main(), 0)
            record = json.loads(output.read_text())
            self.assertEqual(record['validation']['mode'], 'analysis_selection')
            self.assertEqual(record['narrative']['grounding']['mode'], 'analysis_selection')
            with patch.object(module, 'ollama_generate') as model:
                self.assertEqual(module.revalidate_saved(record, evidence, output, False), 0)
                model.assert_not_called()
            self.assertEqual(json.loads(output.read_text())['validation']['mode'], 'analysis_selection')


class InterpretationTests(unittest.TestCase):
    def test_observation_bullets_keep_host_combinations_and_dates_separate(self):
        evidence = module.build_evidence(thirty_sample_context())
        source_before = module.canonical(evidence['facts'])
        narrative = module.materialize_selection(relationship_selection(evidence), evidence)
        cards = {row['observation_id']: row for row in narrative['what_we_know']}
        for card in cards.values():
            self.assertIn(len(card['bullets']), (2, 3))
            self.assertTrue(card['text'])  # Full source detail remains in the artifact.
        grouping = cards['OBS-HOST-GROUPING']['bullets']
        self.assertIn('Black Vulture and Canada Goose share selected groups in NP, PA.', grouping)
        self.assertIn('Red-tailed Hawk and Snow Goose share selected groups in PB2.', grouping)
        self.assertNotIn('Turkey Vulture', ' '.join(grouping))
        timing = ' '.join(cards['OBS-HOST-TIMING']['bullets'])
        self.assertIn('Red-tailed Hawk: 8 Apr 2026', timing)
        self.assertIn('Snow Goose: 11 Dec 2025', timing)
        self.assertEqual(module.canonical(evidence['facts']), source_before)

    def test_implications_are_review_steps_with_selected_source_citations(self):
        evidence = module.build_evidence(thirty_sample_context())
        response = relationship_selection(evidence)
        narrative = module.materialize_selection(response, evidence)
        meaning = narrative['public_health_meaning']
        self.assertEqual(len(meaning['items']), 3)
        self.assertIn('wildlife and public-health surveillance colleagues', meaning['text'])
        self.assertIn('Black Vulture and Canada Goose; Red-tailed Hawk and Snow Goose', meaning['text'])
        self.assertNotIn('Turkey Vulture', meaning['text'])
        self.assertIn('both shared and different collection dates', meaning['text'])
        self.assertIn('before prioritizing groups for follow-up', meaning['text'])
        self.assertNotEqual(meaning['text'], ' '.join(row['text'] for row in narrative['grounding']['claims']))
        by_id = {row['claim_id']: row for row in narrative['grounding']['claims']}
        for item in meaning['items']:
            self.assertEqual(item['kind'], 'suggested_surveillance_review')
            self.assertTrue(set(item['claim_ids']) <= set(response['claim_ids']))
            supported = {key for cid in item['claim_ids'] for key in by_id[cid]['evidence_ids']}
            self.assertEqual(set(item['evidence_ids']), supported)
        self.assertEqual(narrative['recommended_actions'], [])
        self.assertEqual(module.validate(narrative, evidence), [])

    def test_implication_timing_uses_selected_groups_not_whole_run(self):
        evidence = module.build_evidence(thirty_sample_context())
        catalog = module.relationship_catalog(evidence)
        same = next(key for key, row in catalog['claims'].items() if row.get('scope', {}).get('date_relation') == 'same_date')
        response = {'takeaway_id':'CROSS-HOST', 'claim_ids':[same, 'REL-DETECTION-CONTEXT'], 'recommended_actions':[]}
        narrative = module.materialize_selection(response, evidence)
        timing = narrative['public_health_meaning']['items'][1]
        self.assertIn('records sharing a collection date', timing['text'])
        self.assertNotIn('both shared and different', timing['text'])
        self.assertEqual(timing['claim_ids'], [same])
        self.assertIn('Black Vulture and Canada Goose', narrative['public_health_meaning']['items'][0]['text'])
        self.assertNotIn('Red-tailed Hawk', narrative['public_health_meaning']['text'])
        source = thirty_sample_context()
        source['samples'][0].pop('collection_date')
        incomplete = module.build_evidence(source)
        response['claim_ids'] = [same, 'REL-DETECTION-CONTEXT']
        text = module.materialize_selection(response, incomplete)['public_health_meaning']['items'][1]['text']
        self.assertIn('Fill the missing collection dates', text)
        self.assertNotIn('records sharing a collection date', text)

    def test_detection_implications_change_with_overlap_and_omit_absent_context(self):
        for matched in (0, 1, 30):
            evidence = module.build_evidence(thirty_sample_context())
            coverage = next(row for row in evidence['facts'] if row['id'] == 'RELATIONSHIP-COVERAGE')['data']
            coverage['samples_with_state_date_detection_overlap'] = matched
            evidence = module.prepare_evidence(evidence)
            narrative = module.materialize_selection(relationship_selection(evidence), evidence)
            detection = narrative['public_health_meaning']['items'][-1]
            self.assertEqual(detection['claim_ids'], ['REL-DETECTION-CONTEXT'])
            expected = 'No eligible sample met' if matched == 0 else 'matched and unmatched' if matched == 1 else 'Every eligible sample meets'
            self.assertIn(expected, detection['text'])
            self.assertEqual(module.validate(narrative, evidence), [])
        next(row for row in evidence['facts'] if row['id'] == 'RELATIONSHIP-COVERAGE')['data'].pop('samples_with_state_date_detection_overlap')
        evidence = module.prepare_evidence(evidence)
        narrative = module.materialize_selection(relationship_selection(evidence), evidence)
        self.assertEqual(len(narrative['public_health_meaning']['items']), 2)

    def test_edited_bullets_or_implication_citations_fail_source_validation(self):
        evidence = module.build_evidence(thirty_sample_context())
        narrative = module.materialize_selection(relationship_selection(evidence), evidence)
        for field in ('bullet', 'text', 'citation'):
            changed = json.loads(json.dumps(narrative))
            if field == 'bullet':
                changed['what_we_know'][0]['bullets'][0] = 'All hosts belong to the same outbreak.'
            elif field == 'text':
                changed['public_health_meaning']['items'][0]['text'] = 'Prioritize this group as high risk.'
            else:
                changed['public_health_meaning']['items'][0]['evidence_ids'] = ['SAMPLE-030']
            self.assertTrue(module.validate(changed, evidence))

    def test_bullet_limits_for_large_catalogs_and_unknown_qc(self):
        evidence = module.build_evidence(thirty_sample_context())
        timing = evidence['observations']['OBS-HOST-TIMING']
        timing['scope']['dates_by_host'] = {f'Host {i}':['2026-01-01'] for i in range(12)}
        self.assertEqual(len(module.observation_bullets(timing)), 2)
        grouping = evidence['observations']['OBS-HOST-GROUPING']
        grouping['scope']['group_memberships'] += [{'hosts':['Other host', 'Another host'], 'segment':'HA'}]
        grouping['scope']['segments'].append('HA')
        bullets = module.observation_bullets(grouping)
        self.assertEqual(len(bullets), 3)
        self.assertIn('3 different host combinations', bullets[0])
        qc = evidence['observations']['OBS-RUN-QC']
        self.assertEqual(len(module.observation_bullets(qc)), 2)
        qc['scope']['unknown'] = 1
        self.assertEqual(len(module.observation_bullets(qc)), 3)

    def test_relationship_catalog_checks_each_group_own_hosts_and_dates(self):
        evidence = module.build_evidence(thirty_sample_context())
        catalog = module.relationship_catalog(evidence)
        groups = {row['scope']['segment']: row for row in catalog['claims'].values() if row['kind'] == 'group_membership'}
        self.assertEqual(groups['NP']['scope']['hosts'], ['Black Vulture', 'Canada Goose'])
        self.assertEqual(groups['PA']['scope']['hosts'], ['Black Vulture', 'Canada Goose'])
        self.assertEqual(groups['PB2']['scope']['hosts'], ['Red-tailed Hawk', 'Snow Goose'])
        self.assertEqual(groups['NP']['scope']['date_relation'], 'same_date')
        self.assertEqual(groups['PA']['scope']['date_relation'], 'multiple_dates')
        self.assertEqual(groups['PB2']['scope']['date_relation'], 'multiple_dates')
        self.assertIn('2025-04-15', groups['NP']['text'])
        self.assertIn('2025-10-21', groups['PA']['text'])
        self.assertIn('2025-12-11', groups['PB2']['text'])
        self.assertIn('2026-04-08', groups['PB2']['text'])
        response = relationship_selection(evidence)
        narrative = module.materialize_selection(response, evidence)
        self.assertEqual(module.validate_response(response, narrative, evidence), [])
        self.assertNotIn('QC', narrative['public_health_meaning']['text'])
        self.assertEqual(len(narrative['grounding']['claims']), 4)

    def test_partial_group_dates_do_not_become_same_or_different_date_claims(self):
        source = thirty_sample_context()
        source['samples'][0].pop('collection_date')
        evidence = module.build_evidence(source)
        catalog = module.relationship_catalog(evidence)
        groups = {row['scope']['segment']: row for row in catalog['claims'].values() if row['kind'] == 'group_membership'}
        for segment in ('NP', 'PA'):
            self.assertEqual(groups[segment]['scope']['date_relation'], 'incomplete_dates')
            self.assertEqual(groups[segment]['scope']['missing_date_count'], 1)
            self.assertIn('incomplete', groups[segment]['text'])
        self.assertNotIn('SHARED-AND-DIFFERENT-DATES', catalog['takeaways'])

    def test_takeaway_must_be_supported_by_selected_groups_not_other_groups(self):
        evidence = module.build_evidence(thirty_sample_context())
        catalog = module.relationship_catalog(evidence)
        same = next(key for key, row in catalog['claims'].items() if row['kind'] == 'group_membership' and row['scope']['date_relation'] == 'same_date')
        response = {'takeaway_id': 'CROSS-HOST-TIME', 'claim_ids': [same, 'REL-DETECTION-CONTEXT'], 'recommended_actions': []}
        narrative = module.materialize_selection(response, evidence)
        errors = module.validate_response(response, narrative, evidence)
        self.assertTrue(any('collection-date relationship' in error for error in errors), errors)
        response['takeaway_id'] = 'CROSS-HOST'
        self.assertEqual(module.validate_response(response, module.materialize_selection(response, evidence), evidence), [])

    def test_relationship_mode_rejects_the_reported_generated_overclaim(self):
        evidence = module.build_evidence(thirty_sample_context())
        bad = context_selection(evidence, extra='OBS-RUN-QC')
        bad['headline'] = 'Segment-tree groups span multiple hosts and collection dates, yet public detections provide only state-level context'
        bad['public_health_meaning']['text'] = (
            'The selected segment-tree groups show that samples from different bird species—Black Vulture with Canada Goose, and Red-tailed Hawk with Snow Goose—appear together in the same NP, PA, and PB2 trees, but the hosts were collected on distinct dates. '
            'The public-detection overlap rule applies to every eligible sample, so it does not help distinguish these groups. '
            'Together, these observations indicate that the sampled genomes cluster by segment rather than by host, and that the surveillance context is limited to state and date windows rather than specific case linkages.'
        )
        self.assertTrue(module.validate_response(bad, module.materialize_selection(bad, evidence), evidence))
        native = relationship_selection(evidence)
        native['headline'] = bad['headline']
        self.assertTrue(module.validate_response(native, module.materialize_selection(native, evidence), evidence))

    def test_relationship_rendering_cannot_be_changed_to_an_unsupported_statement(self):
        evidence = module.build_evidence(thirty_sample_context())
        response = relationship_selection(evidence)
        narrative = module.materialize_selection(response, evidence)
        for field, value in (('headline', 'Genomes cluster by segment rather than by host.'),
                             ('meaning', 'All hosts were collected on distinct dates.')):
            changed = json.loads(json.dumps(narrative))
            if field == 'headline':
                changed['headline'] = value
            else:
                changed['public_health_meaning']['text'] = value
            self.assertTrue(module.validate(changed, evidence))
        changed = json.loads(json.dumps(narrative))
        changed['grounding']['claims'][0]['scope']['hosts'] = ['Turkey Vulture', 'Snow Goose']
        self.assertTrue(module.validate(changed, evidence))

    def test_changed_source_dates_invalidate_an_existing_relationship_render(self):
        evidence = module.build_evidence(thirty_sample_context())
        narrative = module.materialize_selection(relationship_selection(evidence), evidence)
        changed = json.loads(json.dumps(evidence))
        next(row for row in changed['facts'] if row['id'] == 'SAMPLE-001')['data']['collection_date'] = '2025-04-16'
        errors = module.validate(narrative, changed)
        self.assertTrue(errors)

    def test_missing_group_member_fact_is_not_silently_dropped(self):
        evidence = module.build_evidence(thirty_sample_context())
        group = next(row for row in evidence['facts'] if row['id'].startswith('TREE-GROUP-') and row['data']['segment'] == 'NP')
        group['data']['sample_ids'].append('ABSENT-SAMPLE')
        with self.assertRaisesRegex(ValueError, 'needs all member sample records'):
            module.relationship_catalog(evidence)

    def test_relationship_selection_rejects_unknown_duplicate_and_context_only_ids(self):
        evidence = module.build_evidence(thirty_sample_context())
        good = relationship_selection(evidence)
        for ids in (['INVENTED'], [good['claim_ids'][0], good['claim_ids'][0], 'REL-DETECTION-CONTEXT'],
                    ['REL-DETECTION-CONTEXT', 'REL-RUN-QC'], [], 'REL-DETECTION-CONTEXT', [None]):
            with self.subTest(ids=ids):
                response = {**good, 'claim_ids': ids}
                self.assertTrue(module.validate_response(response, module.materialize_selection(response, evidence), evidence))
        for actions in ([{'action_id': 'INVENTED'}], [{'action_id': 'REVIEW-QC', 'text': 'Extra instructions'}], None):
            response = {**good, 'recommended_actions': actions}
            self.assertTrue(module.validate_response(response, module.materialize_selection(response, evidence), evidence))

    def test_offline_relationship_validation_preserves_raw_selection_and_model_history(self):
        evidence = module.build_evidence(thirty_sample_context())
        response = relationship_selection(evidence)
        original = {'schema_version': module.SCHEMA, 'model': 'local', 'prompt_version': '1.5.0',
                    'prompt': {'system': 'original'}, 'prompt_sha256': 'original-hash',
                    'status': 'ERROR', 'error': 'earlier validation error', 'evidence': evidence,
                    'diagnostics': {'attempts': [{'response': response, 'validation_errors': ['earlier error']}]}}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'record.json'
            target.write_text(json.dumps(original))
            argv = [str(SCRIPT), '--evidence-json', str(target), '--output', str(target), '--validate-saved']
            with patch('sys.argv', argv), patch.object(module, 'ollama_generate') as generate, patch.object(module.urllib.request, 'urlopen') as network:
                self.assertEqual(module.main(), 0)
            generate.assert_not_called(); network.assert_not_called()
            record = json.loads(target.read_text())
            self.assertEqual(record['diagnostics']['attempts'], original['diagnostics']['attempts'])
            self.assertEqual(record['prompt'], original['prompt'])
            self.assertEqual(record['prompt_sha256'], original['prompt_sha256'])
            self.assertEqual(record['validation']['mode'], 'relationship_selection')
            self.assertEqual(record['narrative']['grounding']['selection'], response)
            self.assertEqual(record['narrative']['grounding']['presentation_version'], module.PRESENTATION_VERSION)
            self.assertEqual(len(record['narrative']['public_health_meaning']['items']), 3)
            self.assertEqual(record['evidence']['facts'], evidence['facts'])
            self.assertEqual(record['diagnostics']['validation_reviews'][-1]['presentation_version'], module.PRESENTATION_VERSION)
            self.assertEqual(module.validate(record['narrative'], evidence), [])

    def test_reported_precaution_is_allowed_but_membership_and_exact_half_need_revision(self):
        evidence = module.build_evidence(thirty_sample_context())
        response = reported_precaution_response(evidence)
        errors = module.validate(module.materialize_selection(response, evidence), evidence)
        self.assertFalse(any('circulation' in error for error in errors), errors)
        self.assertTrue(any('named hosts do not occur together' in error for error in errors), errors)
        self.assertTrue(any("'half'" in error and '14 of 30' in error for error in errors), errors)

    def test_precaution_does_not_mask_a_positive_claim_in_another_clause(self):
        evidence = module.build_evidence(payload())
        precaution = 'Review QC before drawing conclusions about viral circulation.'
        self.assertEqual(module.prose_claim_errors('text', precaution, evidence), [])
        for statement in (
            precaution + ' Ongoing circulation is evident.',
            'The virus is circulating; ' + precaution,
            'Review QC before drawing conclusions about viral circulation is established.',
            'Review QC before drawing conclusions about circulation; transmission occurred.',
        ):
            with self.subTest(statement=statement):
                self.assertTrue(any('unsupported causal' in error for error in module.prose_claim_errors('text', statement, evidence)))

    def test_exact_half_checks_do_not_reject_explicit_approximation(self):
        evidence = module.build_evidence(thirty_sample_context())
        selected = {'OBS-RUN-QC'}
        for text in ('Full-segment genomes in half the samples.', 'Half the samples have complete genomes.',
                     'Exactly half of the samples have all eight segments passing QC.'):
            with self.subTest(text=text):
                self.assertTrue(module.completeness_proportion_errors(text, evidence, selected))
        for text in ('Full-segment genomes in about half the samples.', 'About half the samples have complete genomes.',
                     'Nearly half of the genomes are fully complete.', '14 of 30 samples have all eight segments passing QC.'):
            with self.subTest(text=text):
                self.assertEqual(module.completeness_proportion_errors(text, evidence, selected), [])
        balanced = module.build_evidence(payload())
        self.assertEqual(module.completeness_proportion_errors('Half the samples have complete genomes.', balanced, selected), [])

    def test_each_named_segment_must_support_the_named_host_combination(self):
        evidence = module.build_evidence(thirty_sample_context())
        self.assertEqual(module.prose_claim_errors('text', 'Black Vulture and Canada Goose clustered together in NP and PA.', evidence), [])
        errors = module.prose_claim_errors('text', 'Black Vulture and Canada Goose clustered together in NP and PB2.', evidence)
        self.assertTrue(any('named hosts' in error for error in errors), errors)

    def test_corrected_example_preserves_pairs_and_date_scope(self):
        evidence = module.build_evidence(thirty_sample_context())
        response = context_selection(evidence, extra='OBS-RUN-QC')
        response['headline'] = 'Different host pairings appear in different segment-tree groups.'
        response['public_health_meaning']['text'] = (
            'Black Vulture and Canada Goose samples cluster together in NP and PA; Red-tailed Hawk and Snow Goose samples cluster together in PB2. '
            'The NP group shares a collection date, while the PA and PB2 groups span dates, so comparisons among sampled hosts need to retain both collection timing and segment identity. '
            'Public detection records overlap all eligible sample state/date windows, giving shared regional context that does not distinguish these groups.'
        )
        self.assertEqual(module.validate(module.materialize_selection(response, evidence), evidence), [])

    def test_explicit_non_inferences_are_not_positive_circulation_claims(self):
        evidence = module.build_evidence(context_payload())
        for statement in (
            'These observations do not establish ongoing circulation.',
            'We cannot infer circulation or transmission from these records.',
            'Circulation cannot be inferred from these observations.',
            'Regional circulation has not been established.',
            'This is not evidence of circulation.',
            'These observations cannot estimate prevalence or incidence.',
        ):
            with self.subTest(statement=statement):
                response = context_selection(evidence)
                response['public_health_meaning']['text'] += ' ' + statement
                self.assertEqual(module.validate(module.materialize_selection(response, evidence), evidence), [])

    def test_negation_never_excuses_other_positive_or_absence_claims(self):
        evidence = module.build_evidence(payload())
        for statement in (
            'These findings show ongoing circulation.',
            'The findings may suggest circulation.',
            'There is no circulation.',
            'There is no evidence for circulation.',
            'These observations do not establish circulation, but ongoing circulation is clear.',
            'Circulation cannot be inferred. Transmission is established.',
            'This is not evidence of circulation; environmental persistence explains the observations.',
            'This establishes not only circulation but also transmission.',
            'We cannot infer circulation and prevalence is high.',
            'The data do not establish host specificity but show circulation.',
        ):
            with self.subTest(statement=statement):
                errors = module.prose_claim_errors('public_health_meaning.text', statement, evidence)
                self.assertTrue(any('unsupported causal' in error for error in errors), errors)

    def test_offline_validation_accepts_non_inference_and_preserves_generation_provenance(self):
        evidence = module.build_evidence(payload())
        response = selection(evidence)
        response['public_health_meaning']['text'] += ' These observations do not establish circulation.'
        original = {
            'schema_version': module.SCHEMA, 'status': 'ERROR', 'provider': 'ollama',
            'model': 'original-local-model', 'model_digest': 'original-digest',
            'prompt_version': '1.4.2', 'prompt_sha256': 'original-prompt-hash',
            'prompt': {'system': 'original system', 'user': 'original user'},
            'runtime': {'elapsed_seconds': 4.774}, 'evidence': evidence,
            'evidence_sha256': module.hashlib.sha256(module.canonical(evidence)).hexdigest(),
            'error': 'old circulation rejection', 'validation': {'version': 'old', 'review_status': 'UNREVIEWED'},
            'diagnostics': {'failed_phase': 'saved_repair', 'attempts': [{
                'phase': 'saved_repair', 'response': response, 'validation_errors': ['old circulation rejection'],
                'prompt': {'system': 'saved repair'}, 'runtime': {'elapsed_seconds': 4.774}}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'record.json'
            target.write_text(json.dumps(original))
            argv = [str(SCRIPT), '--evidence-json', str(target), '--output', str(target), '--validate-saved', '--print-narrative']
            stdout = io.StringIO()
            with patch('sys.argv', argv), patch('sys.stdout', stdout), patch.object(module, 'ollama_generate') as generate, patch.object(module, 'model_digest') as digest, patch.object(module.urllib.request, 'urlopen') as network:
                self.assertEqual(module.main(), 0)
            generate.assert_not_called()
            digest.assert_not_called()
            network.assert_not_called()
            result = json.loads(target.read_text())
            for key in ('provider', 'model', 'model_digest', 'prompt_version', 'prompt_sha256', 'prompt', 'runtime'):
                self.assertEqual(result[key], original[key])
            self.assertNotIn('generated_at', result)
            self.assertNotIn('error', result)
            self.assertNotIn('failed_phase', result['diagnostics'])
            self.assertEqual(result['status'], 'GENERATED')
            self.assertEqual(result['diagnostics']['attempts'], original['diagnostics']['attempts'])
            self.assertEqual(result['narrative']['public_health_meaning']['text'], response['public_health_meaning']['text'])
            self.assertEqual(result['validation']['version'], module.VALIDATION_VERSION)
            self.assertEqual(result['validation']['review_status'], 'UNREVIEWED')
            review = result['diagnostics']['validation_reviews'][0]
            self.assertEqual(review['source_attempt_index'], 0)
            self.assertEqual(review['previous_validation'], original['validation'])
            self.assertEqual(review['previous_error'], original['error'])
            self.assertEqual(review['previous_evidence_sha256'], original['evidence_sha256'])
            self.assertEqual(review['checked_evidence_sha256'], result['evidence_sha256'])
            self.assertIn('REVALIDATED:', stdout.getvalue())
            self.assertIn(response['public_health_meaning']['text'], stdout.getvalue())

    def test_offline_validation_rejects_latest_draft_without_overwriting_either_file(self):
        evidence = module.build_evidence(context_payload())
        bad = context_selection(evidence)
        bad['public_health_meaning']['text'] += ' These findings show ongoing circulation.'
        record = {'evidence': evidence, 'diagnostics': {'attempts': [
            {'response': context_selection(evidence)}, {'response': bad}]}}
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source.json', Path(directory) / 'output.json'
            source.write_text(json.dumps(record))
            target.write_text('existing output')
            before = source.read_bytes()
            for output in (target, source):
                stdout, stderr = io.StringIO(), io.StringIO()
                argv = [str(SCRIPT), '--evidence-json', str(source), '--output', str(output), '--validate-saved']
                with patch('sys.argv', argv), patch('sys.stdout', stdout), patch('sys.stderr', stderr), patch.object(module.urllib.request, 'urlopen') as network:
                    self.assertEqual(module.main(), 1)
                network.assert_not_called()
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(target.read_text(), 'existing output')
                self.assertIn('free-form headlines and interpretations are not accepted', stderr.getvalue())
                self.assertIn('REJECTED SAVED DRAFT', stdout.getvalue())
                self.assertIn(bad['public_health_meaning']['text'], stdout.getvalue())

    def test_offline_validation_does_not_fall_back_from_malformed_latest_response(self):
        evidence = module.build_evidence(payload())
        for attempts in ([], [{'response': selection(evidence)}, {'response': 'malformed'}]):
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'record.json'
                target.write_text(json.dumps({'evidence': evidence, 'diagnostics': {'attempts': attempts}}))
                before = target.read_bytes()
                argv = [str(SCRIPT), '--evidence-json', str(target), '--output', str(target), '--validate-saved']
                with patch('sys.argv', argv), patch('sys.stderr', io.StringIO()):
                    self.assertEqual(module.main(), 1)
                self.assertEqual(target.read_bytes(), before)

    def test_reported_conflation_gets_specific_factual_and_format_errors(self):
        evidence = module.build_evidence(separate_host_groups())
        narrative = module.materialize_selection(reported_conflation_response(), evidence)
        errors = ' '.join(module.validate(narrative, evidence))
        for text in ('public_health_meaning.text: circulating', 'sample-to-record', 'sampling-event effects',
                     'viral host range', 'named hosts do not occur together', 'JSON closing delimiters'):
            self.assertIn(text, errors)

    def test_membership_catalog_keeps_named_hosts_and_dates_in_separate_groups(self):
        evidence = module.build_evidence(separate_host_groups())
        observation = evidence['observations']['OBS-HOST-GROUPING']
        members = observation['scope']['group_memberships']
        self.assertEqual([row['hosts'] for row in members], [['Black Vulture', 'Canada Goose'], ['Red-tailed Hawk', 'Snow Goose']])
        self.assertNotIn('Turkey Vulture', observation['text'])
        self.assertIn('Black Vulture — 2026-01-01', observation['text'])
        compact = module.prompt_catalog(evidence)
        self.assertEqual(compact['observations']['OBS-HOST-GROUPING']['group_memberships'], members)
        source_facts = json.dumps(evidence['facts'], sort_keys=True)
        self.assertEqual(json.dumps(module.prepare_evidence(evidence)['facts'], sort_keys=True), source_facts)

    def test_membership_check_respects_named_segment_and_independent_clauses(self):
        evidence = module.build_evidence(separate_host_groups())
        for text in ('Black Vulture and Canada Goose share a group in NP.',
                     'Black Vulture and Canada Goose share a group in NP; Red-tailed Hawk and Snow Goose share a group in PB2.',
                     'Black Vulture and Snow Goose do not share a group.'):
            self.assertEqual(module.prose_claim_errors('text', text, evidence), [], text)
        for text in ('Black Vulture and Snow Goose share a group.',
                     'Black Vulture and Canada Goose share a group in PB2.'):
            self.assertTrue(any('named hosts' in err for err in module.prose_claim_errors('text', text, evidence)), text)

    def test_scope_appropriate_wording_remains_allowed(self):
        evidence = module.build_evidence(separate_host_groups())
        for text in ('Public records overlap the state and date windows of the samples.',
                     'These samples are not linked to individual surveillance records.',
                     'Sampling-event identities were not supplied.',
                     'The sampled sequences appear in groups containing different hosts.'):
            self.assertEqual(module.prose_claim_errors('text', text, evidence), [], text)
        self.assertTrue(module.prose_claim_errors('text', 'The samples are not only linked to surveillance records but identified as cases.', evidence))

    def test_latest_repair_prompt_contains_exact_memberships_without_rejected_prose(self):
        evidence = module.build_evidence(separate_host_groups())
        rejected = reported_conflation_response()
        errors = module.validate(module.materialize_selection(rejected, evidence), evidence)
        _, prompt = module.repair_prompt(evidence, rejected, errors)
        self.assertIn('group_memberships', prompt)
        self.assertIn('TREE-GROUP-001', prompt)
        self.assertIn('TREE-GROUP-002', prompt)
        self.assertNotIn(rejected['public_health_meaning']['text'], prompt)
        fixed = context_selection(evidence, extra='OBS-RUN-QC')
        self.assertEqual(module.validate(module.materialize_selection(fixed, evidence), evidence, module.repair_observation_ids(rejected, evidence)), [])

    def test_reported_host_specificity_response_requires_context_and_rewriting(self):
        evidence = module.build_evidence(context_payload())
        rejected = module.materialize_selection(reported_context_response(), evidence)
        errors = " ".join(module.validate(rejected, evidence))
        for message in ("biological host specificity", "OBS-HOST-TIMING", "OBS-DETECTION-CONTEXT"):
            self.assertIn(message, errors)
        self.assertEqual(module.validate(module.materialize_selection(context_selection(evidence), evidence), evidence), [])

    def test_host_specificity_denials_do_not_hide_later_assertions(self):
        for text in ("These groups do not establish biological host specificity.",
                     "Host specificity has not been tested.", "These groups are not necessarily host-specific."):
            self.assertFalse(module.claims_host_specificity(text), text)
        for text in ("Most groups are host-specific.", "Most groups are host‑specific.",
                     "Most groups are species specific.", "The groups are not only host-specific but distinct.",
                     "Host specificity has not been tested. Most groups are host-specific."):
            self.assertTrue(module.claims_host_specificity(text), text)

    def test_context_citations_alone_do_not_turn_qc_prose_into_synthesis(self):
        evidence = module.build_evidence(context_payload())
        response = context_selection(evidence)
        response['public_health_meaning']['text'] = 'Most genomes have incomplete data, limiting downstream comparisons.'
        narrative = module.materialize_selection(response, evidence)
        self.assertTrue(any('explain the contribution' in error for error in module.validate(narrative, evidence)))
        response = context_selection(evidence)
        response['public_health_meaning']['evidence_ids'] = ['OBS-HOST-GROUPING', 'OBS-HOST-TIMING']
        self.assertTrue(any('cite the source facts for OBS-DETECTION-CONTEXT' in error for error in module.validate(module.materialize_selection(response, evidence), evidence)))

    def test_missing_context_is_never_added_to_the_synthesis_plan(self):
        source = context_payload()
        source.pop('outbreak_context')
        for sample in source['samples']:
            sample.pop('collection_date')
        evidence = module.build_evidence(source)
        self.assertEqual(module.synthesis_plan(evidence), ['OBS-HOST-GROUPING'])
        response = selection(evidence, observation='OBS-HOST-GROUPING')
        response['public_health_meaning']['text'] = 'Samples from different hosts occur together in selected segment-tree groups.'
        self.assertEqual(module.validate(module.materialize_selection(response, evidence), evidence), [])
        self.assertEqual(module.synthesis_plan(module.build_evidence(payload())), [])

    def test_context_repair_expands_selection_consistently_in_prompt_and_schema(self):
        evidence = module.build_evidence(context_payload())
        response = reported_context_response()
        original = json.dumps(response)
        required = ['OBS-HOST-GROUPING', 'OBS-HOST-TIMING', 'OBS-DETECTION-CONTEXT', 'OBS-RUN-QC']
        self.assertEqual(module.repair_observation_ids(response, evidence), required)
        schema = module.response_schema(evidence, response)
        self.assertNotIn('headline', schema['properties'])
        self.assertNotIn('public_health_meaning', schema['properties'])
        self.assertEqual(schema['properties']['claim_ids']['items']['enum'], list(module.relationship_catalog(evidence)['claims']))
        system, prompt = module.repair_prompt(evidence, response, ['missing context'])
        for key in module.relationship_catalog(evidence)['claims']:
            self.assertIn(key, prompt)
        self.assertNotIn('Three of the 47', prompt)
        self.assertIn('biological host specificity', system)
        self.assertEqual(json.dumps(response), original)
        response['what_we_know'] += [{'observation_id': 'OBS-SAMPLING-BALANCE'}, {'observation_id': 'OBS-CONTEXT-COVERAGE'}]
        self.assertEqual(module.repair_observation_ids(response, evidence), required)

    def test_saved_context_repair_keeps_audit_and_accepts_expanded_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'record.json'
            evidence = module.build_evidence(context_payload())
            rejected = reported_context_response()
            target.write_text(json.dumps({'model': 'local', 'evidence': evidence,
                                         'diagnostics': {'attempts': [{'response': rejected, 'validation_errors': []}]}}))
            response = relationship_selection(evidence)
            rendered = module.materialize_selection(response, evidence)
            argv = [str(SCRIPT), '--evidence-json', str(target), '--output', str(target), '--enabled', 'true',
                    '--model', 'local', '--repair-saved', '--fail-on-error', '--print-narrative']
            stdout = io.StringIO()
            with patch('sys.argv', argv), patch.object(module, 'ollama_generate', return_value=(response, {})) as call, patch.object(module, 'model_digest', return_value='digest'), patch('sys.stdout', stdout):
                self.assertEqual(module.main(), 0)
            self.assertEqual(call.call_count, 1)
            result = json.loads(target.read_text())
            self.assertEqual(result['status'], 'GENERATED')
            self.assertEqual(result['validation']['required_observation_ids'], module.synthesis_plan(evidence))
            self.assertEqual(result['diagnostics']['attempts'][0]['response'], rejected)
            self.assertEqual(result['diagnostics']['attempts'][-1]['validation_errors'], [])
            self.assertIn('HEADLINE: ' + rendered['headline'], stdout.getvalue())
            for implication in rendered['public_health_meaning']['items']:
                self.assertIn(implication['text'], stdout.getvalue())
            self.assertIn('OBS-HOST-TIMING:', stdout.getvalue())
            self.assertNotIn(rejected['public_health_meaning']['text'], stdout.getvalue())

    def test_automatic_context_repair_uses_expanded_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'record.json'
            evidence = module.build_evidence(context_payload())
            target.write_text(json.dumps({'evidence': evidence}))
            argv = [str(SCRIPT), '--evidence-json', str(target), '--output', str(target), '--enabled', 'true', '--model', 'local', '--fail-on-error']
            replies = [(reported_context_response(), {}), (relationship_selection(evidence), {})]
            with patch('sys.argv', argv), patch.object(module, 'ollama_generate', side_effect=replies) as call, patch.object(module, 'model_digest', return_value='digest'):
                self.assertEqual(module.main(), 0)
            self.assertEqual(call.call_count, 2)
            result = json.loads(target.read_text())
            self.assertEqual(result['status'], 'GENERATED')
            self.assertTrue(result['diagnostics']['attempts'][0]['validation_errors'])
            self.assertEqual(result['diagnostics']['attempts'][1]['validation_errors'], [])

    def test_schema_constrains_structure_without_distorting_prose(self):
        evidence = module.build_evidence(payload())
        before = json.dumps(evidence, sort_keys=True)
        schema = module.response_schema(evidence)
        props = schema["properties"]
        for field in (props["headline"], props["public_health_meaning"]["properties"]["text"]):
            self.assertEqual(field["type"], "string")
            self.assertNotIn("pattern", field)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(before, json.dumps(evidence, sort_keys=True))

    def test_prompt_exposes_context_before_qc_without_raw_fact_duplication(self):
        evidence = module.build_evidence(payload())
        evidence["facts"].append(module.fact("UNRELATED", "extra", "Unused", {"large": "x" * 100000}))
        system, user = module.prompt(evidence)
        self.assertIn("What did connecting these results teach us?", system)
        self.assertNotIn("UNRELATED", user)
        self.assertNotIn("Record completeness and representation shape", system)
        self.assertLess(user.index("OBS-DETECTION-CONTEXT"), user.index("OBS-RUN-QC"))
        self.assertLess(len(user), 15000)

    def test_full_concordance_supplies_models_and_readiness(self):
        source = payload()
        source.pop("genomic_ecological_concordance")
        full = {"models": [{"segment": "NP", "comparison": "example", "status": "READY", "n_samples": 2}],
                "readiness": {"minimum_unique_samples": 9}, "sample_features": []}
        evidence = module.build_evidence(source, full)
        by_id = {row['id']: row for row in evidence['facts']}
        self.assertEqual(by_id['MODEL-001']['data']['segment'], 'NP')
        self.assertEqual(by_id['CONCORDANCE-READINESS']['data'], full['readiness'])

    def test_saved_weather_changes_are_not_reported_as_entirely_absent(self):
        source = payload()
        source.pop("genomic_ecological_concordance")
        source["trees"] = {"HA": {"root": {"support": .95, "children": [{"sample_id": "S1"}, {"sample_id": "S2"}]}}}
        evidence = module.build_evidence(source)
        group = next(row for row in evidence['facts'] if row['id'] == 'TREE-GROUP-001')
        group['data']['weather']['change_from_prior_7_days_to_collection_window']['temperature_c'] = {
            'n': 1, 'median': -3, 'min': -3, 'max': -3}
        before = json.dumps(evidence['facts'], sort_keys=True)
        rebuilt = module.prepare_evidence(evidence)
        coverage = rebuilt['observations']['OBS-CONTEXT-COVERAGE']
        self.assertEqual(coverage['scope']['weather_change_group_count'], 1)
        self.assertEqual(coverage['scope']['model_rows'], 0)
        self.assertEqual(coverage['scope']['recorded_coverage']['samples_with_weather'], 0)
        self.assertIn('zero concordance-weather count', coverage['text'])
        self.assertIn('median change -3 C', rebuilt['observations']['OBS-TREE-GROUP-001']['text'])
        self.assertEqual(json.dumps(rebuilt['facts'], sort_keys=True), before)
        self.assertEqual(module.prepare_evidence(rebuilt), rebuilt)

    def test_host_grouping_counts_groups_not_independent_birds(self):
        source = payload()
        root = {"support": .95, "children": [{"sample_id": "S1"}, {"sample_id": "S2"}]}
        source['trees'] = {'HA': {'root': root}, 'NP': {'root': root}}
        evidence = module.build_evidence(source)
        finding = evidence['observations']['OBS-HOST-GROUPING']
        self.assertEqual(finding['scope']['mixed_host_groups'], 2)
        self.assertEqual(finding['scope']['segments'], ['HA', 'NP'])
        self.assertEqual(finding['evidence_ids'].count('SAMPLE-001'), 1)
        self.assertNotIn('independent birds', finding['text'])
        narrative = module.materialize_selection(context_selection(evidence), evidence)
        self.assertEqual(module.validate(narrative, evidence), [])

    def test_detection_overlap_takeaway_depends_on_denominator(self):
        evidence = module.build_evidence(payload())
        self.assertIn('every eligible sample', evidence['observations']['OBS-DETECTION-CONTEXT']['text'])
        coverage = next(row for row in evidence['facts'] if row['id'] == 'RELATIONSHIP-COVERAGE')
        coverage['data']['samples_with_state_date_detection_overlap'] = 1
        restored = module.prepare_evidence(evidence)
        self.assertNotIn('every eligible sample', restored['observations']['OBS-DETECTION-CONTEXT']['text'])
        self.assertIn('1 of 2', restored['observations']['OBS-DETECTION-CONTEXT']['text'])

    def test_reported_observation_citations_resolve_without_a_number_word_ban(self):
        source = payload()
        hosts = ["BLVU"] * 18 + ["CAGO"] * 2 + ["RTHA"] * 2 + ["SNGO"] * 2 + ["TUVU"] * 6
        source["samples"] = [{"sample_id": f"S{i:03}", "host": host, "segments_pass": 8 if i < 14 else 5} for i, host in enumerate(hosts)]
        evidence = module.build_evidence(source, host_names={"BLVU": "Black Vulture", "CAGO": "Canada Goose", "RTHA": "Red-tailed Hawk", "SNGO": "Snow Goose", "TUVU": "Turkey Vulture"})
        response = {
            "headline": "Genome completeness varied across the 30 samples, with 14 fully complete and 16 incomplete",
            "public_health_meaning": {
                "evidence_ids": ["OBS-RUN-QC", "OBS-SAMPLING-BALANCE"],
                "text": "Among the 30 samples, 14 had all eight segments passing QC while 16 had fewer than eight passing segments. The run included 18 Black Vulture (BLVU), 2 Canada Goose (CAGO), 2 Red-tailed Hawk (RTHA), 2 Snow Goose (SNGO), and 6 Turkey Vulture (TUVU) samples, but no sensitivity analysis was performed to adjust for this sampling imbalance.",
            },
            "recommended_actions": [],
            "what_we_know": [{"observation_id": "OBS-RUN-QC"}, {"observation_id": "OBS-SAMPLING-BALANCE"}],
        }
        original = json.dumps(response, sort_keys=True)
        narrative = module.materialize_selection(response, evidence)
        self.assertEqual(json.dumps(response, sort_keys=True), original)
        self.assertEqual(narrative["public_health_meaning"]["evidence_ids"], [f"SAMPLE-{i:03}" for i in range(1, 31)] + ["SAMPLING-BALANCE"])
        errors = module.validate(narrative, evidence)
        # Numerical prose is draft text, not automatically verified by the
        # observation-card checks. Natural spelling is no longer forbidden.
        self.assertEqual(errors, [])
        narrative["headline"] = "Sampling and genome completeness shape host comparisons."
        narrative["public_health_meaning"]["text"] = "The sampled birds are unevenly represented across hosts, and genome completeness varies. Read host comparisons alongside the sample representation and QC records."
        self.assertEqual(module.validate(narrative, evidence), [])
        self.assertEqual(module.materialize_selection(narrative, evidence), narrative)

    def test_citation_resolution_preserves_unknown_and_unselected_errors(self):
        evidence = module.build_evidence(payload())
        for identifier in ("OBS-SAMPLING-BALANCE", "OBS-UNKNOWN", {}, None):
            response = selection(evidence)
            response["public_health_meaning"]["evidence_ids"] = [identifier]
            narrative = module.materialize_selection(response, evidence)
            self.assertEqual(narrative["public_health_meaning"]["evidence_ids"], [identifier])
            self.assertTrue(any("valid evidence IDs" in error for error in module.validate(narrative, evidence)))
        response = selection(evidence)
        response["public_health_meaning"]["evidence_ids"] = ["OBS-RUN-QC", "SAMPLE-001"]
        narrative = module.materialize_selection(response, evidence)
        self.assertEqual(narrative["public_health_meaning"]["evidence_ids"], ["SAMPLE-001", "SAMPLE-002"])
        self.assertEqual(module.validate(narrative, evidence), [])

    def test_structured_schema_uses_selected_catalogs_and_allows_empty_actions(self):
        evidence = module.build_evidence(payload())
        response = selection(evidence)
        response["what_we_know"].append({"observation_id": "OBS-SAMPLING-BALANCE"})
        schema = module.response_schema(evidence, response)
        props = schema["properties"]
        allowed = ["OBS-RUN-QC", "OBS-SAMPLING-BALANCE"]
        self.assertEqual(props["public_health_meaning"]["properties"]["evidence_ids"]["items"]["enum"], allowed)
        self.assertEqual(props["what_we_know"]["items"]["properties"]["observation_id"]["enum"], allowed)
        self.assertEqual((props["what_we_know"]["minItems"], props["what_we_know"]["maxItems"]), (2, 2))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(module.response_schema(evidence)["properties"]["what_we_know"]["items"]["properties"]["observation_id"]["enum"]), set(evidence["observations"]))
        evidence["followups"] = {}
        self.assertEqual(module.response_schema(evidence)["properties"]["recommended_actions"]["maxItems"], 0)
        evidence["observations"] = {}
        with self.assertRaisesRegex(ValueError, "No source-rendered observations"):
            module.response_schema(evidence)

    def test_repair_cannot_silently_drop_a_selected_observation(self):
        evidence = module.build_evidence(payload())
        narrative = module.materialize_selection(selection(evidence), evidence)
        self.assertIn("Repair must preserve the selected observation IDs", module.validate(narrative, evidence, ["OBS-RUN-QC", "OBS-SAMPLING-BALANCE"]))

    def test_robustness_limitations_do_not_excuse_a_positive_claim(self):
        evidence = module.build_evidence(payload())
        for text in (
            "This sampling imbalance and incomplete genomic data limit the ability to draw robust conclusions about viral diversity or host associations.",
            "Robustness has not been tested.",
            "We cannot establish robust conclusions.",
            "The result is not demonstrably robust.",
        ):
            narrative = module.materialize_selection(selection(evidence), evidence)
            narrative["public_health_meaning"]["text"] = text
            self.assertEqual(module.validate(narrative, evidence), [], text)
        for text in ("The pattern is robust.", "The pattern is not only robust but conclusive.",
                     "Robustness has not been tested. The host association is robust.",
                     "We cannot draw robust conclusions; nevertheless the pattern is robust."):
            self.assertTrue(module.claims_untested_robustness(text), text)

    def test_reported_majority_error_uses_the_run_denominator(self):
        for complete, rejected in ((14, True), (15, True), (16, False)):
            source = payload()
            source["samples"] = [{"sample_id": f"S{i:03}", "host": "BLVU", "segments_pass": 8 if i < complete else 5} for i in range(30)]
            evidence = module.build_evidence(source, host_names={"BLVU": "Black Vulture"})
            narrative = module.materialize_selection(selection(evidence), evidence)
            narrative["headline"] = "Most samples had complete genomic data, but sampling was heavily skewed toward Black Vulture and limited to Kentucky"
            errors = module.validate(narrative, evidence)
            self.assertEqual(any("contradicts run QC" in error for error in errors), rejected)
        narrative["headline"] = "All samples were collected in Kentucky."
        self.assertFalse(any("Completeness" in error for error in module.validate(narrative, evidence)))

    def test_repair_prompt_omits_unselected_evidence_and_old_prose(self):
        evidence = module.build_evidence(payload())
        evidence["facts"].append(module.fact("UNSELECTED", "extra", "Do not include", {"large": "x" * 100000}))
        response = selection(evidence)
        response["public_health_meaning"]["text"] = "REJECTED OLD PROSE " * 1000
        _, repair = module.repair_prompt(evidence, response, ["numeric prose"])
        self.assertLess(len(repair), 15000)
        self.assertNotIn("UNSELECTED", repair)
        self.assertNotIn("REJECTED OLD PROSE", repair)
        self.assertIn("OBS-RUN-QC", repair)
        self.assertNotIn("OBS-MODEL-001", repair)
        self.assertIn("SAMPLE-002", repair)
        self.assertIn("HOST-GLOSSARY", repair)
        _, fallback = module.repair_prompt(evidence, {}, ["missing selection"])
        self.assertIn("Choose 1–4 distinct observation IDs", fallback)
        self.assertNotIn("Keep exactly these observation IDs", fallback)

    def test_ollama_request_limits_generation_and_records_timings(self):
        raw = {"message": {"content": '{"ok":true}'}, "done_reason": "stop", "prompt_eval_duration": 123, "eval_duration": 456}
        schema = module.response_schema(module.build_evidence(payload()))
        with patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(raw).encode())) as send:
            answer, runtime = module.ollama_generate("http://127.0.0.1:11434/api/chat", "gpt-oss:20b", "system", "user", 30, 2048, schema)
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual(body["format"], schema)
        self.assertEqual(runtime["response_schema_sha256"], module.hashlib.sha256(module.canonical(schema)).hexdigest())
        self.assertEqual(body["think"], "low")
        self.assertEqual(body["options"]["num_predict"], 2048)
        self.assertEqual(answer, {"ok": True})
        self.assertEqual(runtime["prompt_eval_duration"], 123)
        self.assertEqual(runtime["eval_duration"], 456)
        raw["done_reason"] = "length"
        with patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(raw).encode())):
            with self.assertRaisesRegex(ValueError, "generation limit"):
                module.ollama_generate("http://127.0.0.1:11434/api/chat", "gpt-oss:20b", "system", "user", 30)

    def test_saved_repair_makes_only_one_small_request_and_preserves_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record.json"
            evidence = module.build_evidence(payload())
            rejected = selection(evidence)
            rejected["headline"] = "Most samples had complete genomic data."
            rejected["what_we_know"].append({"observation_id": "OBS-SAMPLING-BALANCE"})
            repaired = selection(evidence)
            repaired["what_we_know"] = rejected["what_we_know"]
            repaired["public_health_meaning"]["evidence_ids"] = ["OBS-RUN-QC", "OBS-SAMPLING-BALANCE"]
            target.write_text(json.dumps({"model": "local", "evidence": evidence,
                                         "diagnostics": {"attempts": [{"response": rejected, "validation_errors": ["old error"]}]}}))
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--enabled", "true", "--model", "local", "--repair-saved", "--fail-on-error"]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate", return_value=(repaired, {})) as call, patch.object(module, "model_digest", return_value="digest"):
                self.assertEqual(module.main(), 0)
            self.assertEqual(call.call_count, 1)
            self.assertIn("Compact evidence:", call.call_args.args[3])
            record = json.loads(target.read_text())
            self.assertEqual(record["status"], "GENERATED")
            self.assertNotIn("error", record)
            self.assertEqual(record["diagnostics"]["attempts"][0]["response"], rejected)
            self.assertEqual(record["diagnostics"]["attempts"][-1]["phase"], "saved_repair")
            self.assertEqual(record["diagnostics"]["attempts"][-1]["response"], repaired)
            self.assertEqual(record["narrative"]["public_health_meaning"]["evidence_ids"], ["SAMPLE-001", "SAMPLE-002", "SAMPLING-BALANCE"])
            self.assertEqual(record["prompt"]["response_schema"], call.call_args.args[6])

    def test_timeout_records_repair_phase_and_preserves_completed_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record.json"
            evidence = module.build_evidence(payload())
            target.write_text(json.dumps({"evidence": evidence}))
            rejected = selection(evidence)
            rejected["headline"] = "Most samples had complete genomic data."
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--enabled", "true", "--model", "local", "--fail-on-error"]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate", side_effect=[(rejected, {}), TimeoutError("timed out")]):
                self.assertEqual(module.main(), 1)
            record = json.loads(target.read_text())
            self.assertEqual(record["diagnostics"]["failed_phase"], "repair")
            self.assertEqual(record["diagnostics"]["attempts"][0]["response"], rejected)
            self.assertIn("during repair", record["error"])

    def test_evidence_is_bounded_and_contains_no_sequences_or_trees(self):
        source = payload()
        source["trees"] = {"HA": "(S1,S2);"}
        source["samples"][0]["sequence"] = "ACGT"
        evidence = module.build_evidence(source)
        text = json.dumps(evidence)
        self.assertIn("GENOME-SUMMARY", text)
        self.assertIn("SAMPLE-001", text)
        self.assertNotIn("ACGT", text)
        self.assertNotIn("(S1,S2)", text)

    def test_authoritative_host_map_prevents_alpha_code_guessing(self):
        source = payload()
        source["samples"][0].update(host="BLVU", host_common_name="Blue-winged Teal")
        source["samples"][1].update(host="RTHA", host_common_name="Red-throated Herring Gull")
        names = {"BLVU": "Black Vulture", "RTHA": "Red-tailed Hawk"}
        evidence = module.build_evidence(source, host_names=names)
        sample_facts = [item for item in evidence["facts"] if item["category"] == "sample"]
        self.assertEqual(sample_facts[0]["data"]["host_name"], "Black Vulture (BLVU)")
        self.assertEqual(sample_facts[1]["data"]["host_name"], "Red-tailed Hawk (RTHA)")
        glossary = next(item for item in evidence["facts"] if item["id"] == "HOST-GLOSSARY")
        self.assertEqual(glossary["data"], names)

    def test_validator_rejects_invented_host_expansion(self):
        source = payload()
        source["samples"][0]["host"] = "BLVU"
        evidence = module.build_evidence(source, host_names={"BLVU": "Black Vulture"})
        narrative = {
            "headline": "Blue-winged Teal (BLVU) appears in the samples.",
            "what_we_know": [
                {"title": "Genome recovery", "text": "One of two samples has eight passing segments.", "evidence_ids": ["GENOME-SUMMARY"]},
                {"title": "Host", "text": "Blue-winged Teal (BLVU) was sampled.", "evidence_ids": ["SAMPLE-001"]},
            ],
            "public_health_meaning": {"text": "Review the sampled hosts.", "evidence_ids": ["SAMPLING-BALANCE"]},
            "recommended_actions": [{"text": "Confirm sample metadata.", "evidence_ids": ["SAMPLING-BALANCE"]}],
        }
        self.assertTrue(any("host label for BLVU must be Black Vulture (BLVU)" in error for error in module.validate(narrative, evidence)))

    def test_relationship_layer_connects_supported_tree_group_to_context(self):
        source = payload()
        source["trees"] = {"HA": {"root": {"children": [
            {"support": 95, "children": [{"sample_id": "S1", "name": "S1"}, {"sample_id": "S2", "name": "S2"}]},
            {"name": "reference"},
        ]}}}
        concordance = {"sample_features": [
            {"sample_id": "S1", "environment_vector_available": True, "temperature_7d_mean_c": 4, "precipitation_7d_total_mm": 2, "wind_7d_mean_max_kmh": 12,
             "migration_available": True, "migration_context_key": "US-AZ|2025-12-31", "migration_intensity_percentile": .8, "migration_progress": .6},
            {"sample_id": "S2", "environment_vector_available": True, "temperature_7d_mean_c": 6, "precipitation_7d_total_mm": 0, "wind_7d_mean_max_kmh": 16,
             "migration_available": True, "migration_context_key": "US-AZ|2026-01-01", "migration_intensity_percentile": .4, "migration_progress": .7},
        ]}
        evidence = module.build_evidence(source, concordance)
        group = next(item for item in evidence["facts"] if item["id"] == "TREE-GROUP-001")
        self.assertEqual(group["data"]["segment"], "HA")
        self.assertEqual(group["data"]["host_counts"], {"duck": 1, "goose": 1})
        self.assertEqual(group["data"]["migration"]["distinct_state_night_contexts"], 2)
        self.assertEqual(group["data"]["weather"]["temperature_7d_mean_c"]["median"], 5)
        self.assertEqual(group["data"]["detection_overlap"]["samples_with_overlap"], 2)
        balance = next(item for item in evidence["facts"] if item["id"] == "SAMPLING-BALANCE")
        self.assertEqual(balance["data"]["sensitivity_analysis"], "NOT_PERFORMED")

    def test_unsupported_trees_do_not_become_genomic_clusters(self):
        source = payload()
        source["trees"] = {"HA": {"root": {"support": .4, "children": [{"sample_id": "S1"}, {"sample_id": "S2"}]}}}
        evidence = module.build_evidence(source)
        self.assertFalse(any(item["id"].startswith("TREE-GROUP-") for item in evidence["facts"]))
        coverage = next(item for item in evidence["facts"] if item["id"] == "RELATIONSHIP-COVERAGE")
        self.assertEqual(coverage["data"]["supported_tree_groups"], 0)

    def test_weather_change_compares_prior_and_collection_windows(self):
        source = payload()
        source["ecological_context"] = {
            "bindings": {"S1": {"status": "READY", "weather_key": "AZ-1"}},
            "weather": {"AZ-1": {"rows": [
                {"date": "2025-12-24", "temperature_2m_mean": 2, "precipitation_sum": 1, "wind_speed_10m_max": 10},
                {"date": "2025-12-31", "temperature_2m_mean": 5, "precipitation_sum": 3, "wind_speed_10m_max": 14},
            ]}},
        }
        changes = module.weather_change_features(source)["S1"]
        self.assertEqual(changes["temperature_change_c"], 3)
        self.assertEqual(changes["precipitation_change_mm"], 2)
        self.assertEqual(changes["wind_change_kmh"], 4)

    def test_validator_requires_grounded_citations_and_numbers(self):
        evidence = module.build_evidence(payload())
        valid = module.materialize_selection(selection(evidence), evidence)
        self.assertEqual(module.validate(valid, evidence), [])
        invalid = json.loads(json.dumps(valid))
        invalid["public_health_meaning"]["text"] = "99 samples prove transmission."
        invalid["public_health_meaning"]["evidence_ids"] = ["MISSING"]
        errors = " ".join(module.validate(invalid, evidence))
        self.assertIn("valid evidence IDs", errors)
        self.assertIn("causal", errors)

    def test_action_may_cite_direct_sample_evidence(self):
        evidence = module.build_evidence(payload())
        narrative = module.materialize_selection(selection(evidence, actions=[{"action_id": "REVIEW-QC"}]), evidence)
        self.assertEqual(module.validate(narrative, evidence), [])
        self.assertEqual(narrative["recommended_actions"][0]["evidence_ids"], ["SAMPLE-002"])

    def test_hyphens_and_whitespace_are_normalized_in_titles_and_text(self):
        source = payload()
        source["samples"][0]["host"] = "RTHA"
        evidence = module.build_evidence(source, host_names={"RTHA": "Red-tailed Hawk"})
        for dash in ("-", "\u2010", "\u2011", "\u2013", "\u2212"):
            narrative = module.materialize_selection(selection(evidence), evidence)
            narrative["headline"] = f"Red{dash}tailed\u00a0Hawk (RTHA) is represented in this run."
            self.assertEqual(module.validate(narrative, evidence), [], dash)
        narrative["headline"] = "Red-throated Herring Gull (RTHA) is represented in this run."
        self.assertTrue(any("host label" in err for err in module.validate(narrative, evidence)))

    def test_title_is_validated_not_just_paragraph(self):
        source = payload()
        source["samples"][0]["host"] = "RTHA"
        evidence = module.build_evidence(source, host_names={"RTHA": "Red-tailed Hawk"})
        narrative = module.materialize_selection(selection(evidence), evidence)
        narrative["what_we_know"][0]["title"] = "Red-throated Herring Gull (RTHA)"
        self.assertTrue(any("host label" in err for err in module.validate(narrative, evidence)))

    def test_empty_actions_are_valid_and_complete_data_has_no_qc_task(self):
        source = payload()
        source["samples"][1]["segments_pass"] = 8
        evidence = module.build_evidence(source)
        self.assertEqual(evidence["followups"], {})
        self.assertEqual(module.validate(module.materialize_selection(selection(evidence), evidence), evidence), [])

    def test_observation_counts_use_distinct_group_members_not_run_totals(self):
        source = payload()
        source["samples"].append({"sample_id": "S3", "host": "other", "segments_pass": 8})
        source["trees"] = {"HA": {"root": {"support": 95, "children": [{"sample_id": "S1"}, {"sample_id": "S2"}, {"sample_id": "S2"}]}}}
        evidence = module.build_evidence(source)
        observation = evidence["observations"]["OBS-TREE-GROUP-001"]
        self.assertEqual(observation["scope"]["samples"], 2)
        self.assertEqual(observation["scope"]["complete"], 1)
        self.assertEqual(evidence["observations"]["OBS-RUN-QC"]["scope"]["complete"], 2)
        self.assertIn("Within this group, 1 of 2 samples", observation["text"])
        valid = module.materialize_selection(context_selection(evidence, extra=observation["observation_id"]), evidence)
        self.assertEqual(module.validate(valid, evidence), [])
        valid["what_we_know"][-1]["text"] = observation["text"].replace("Within this group, 1 of 2", "Within this group, 2 of 3")
        self.assertTrue(any("scoped source" in err for err in module.validate(valid, evidence)))

    def test_natural_numeric_prose_is_allowed_but_observation_cards_are_source_exact(self):
        evidence = module.build_evidence(payload())
        narrative = module.materialize_selection(selection(evidence), evidence)
        narrative['public_health_meaning']['text'] = 'One of the two samples has all eight segments passing QC.'
        self.assertEqual(module.validate(narrative, evidence), [])
        narrative['what_we_know'][0]['text'] = 'Two samples have all eight segments passing QC.'
        self.assertTrue(any('scoped source' in error for error in module.validate(narrative, evidence)))

    def test_previous_unsupported_population_claims_are_rejected(self):
        evidence = module.build_evidence(payload())
        for text in ("This indicates ongoing circulation in the region.", "The virus persists in wetlands.",
                     "Assess potential spillover risks.", "This establishes H5N1 prevalence.",
                     "H5N1 was detected in these birds.", "This pattern is robust."):
            narrative = module.materialize_selection(selection(evidence), evidence)
            narrative["public_health_meaning"]["text"] = text
            self.assertTrue(module.validate(narrative, evidence), text)

    def test_environmental_sampling_cannot_be_invented_as_followup(self):
        evidence = module.build_evidence(payload())
        narrative = module.materialize_selection(selection(evidence), evidence)
        narrative["recommended_actions"] = [{"text": "Sample wetlands in spring to investigate environmental persistence.", "evidence_ids": ["SAMPLING-BALANCE"]}]
        self.assertTrue(any("followups" in err for err in module.validate(narrative, evidence)))

    def test_model_cannot_attach_unrelated_valid_ids_to_meaning(self):
        evidence = module.build_evidence(payload())
        narrative = module.materialize_selection(selection(evidence), evidence)
        narrative["public_health_meaning"]["evidence_ids"] = ["DETECTION-SUMMARY"]
        self.assertTrue(any("selected observations" in err for err in module.validate(narrative, evidence)))

    def test_reported_bad_response_cannot_pass_on_valid_ids_alone(self):
        source = payload()
        source["samples"][0]["host"] = "BLVU"
        source["samples"][1]["host"] = "RTHA"
        source["trees"] = {"HA": {"root": {"support": 95, "children": [{"sample_id": "S1"}, {"sample_id": "S2"}]}}}
        evidence = module.build_evidence(source, host_names={"BLVU": "Black Vulture", "RTHA": "Red-tailed Hawk"})
        narrative = {
            "headline": "H5N1 detected in multiple bird species in Kentucky during fall 2025 to spring 2026",
            "what_we_know": [{"title": "Black Vulture (BLVU)",
                             "text": "Fourteen of the 30 Black Vulture samples tested positive for H5N1, with 14 complete genomes.",
                             "evidence_ids": ["TREE-GROUP-001"]}],
            "public_health_meaning": {"text": "This indicates ongoing circulation in the region.", "evidence_ids": ["SAMPLING-BALANCE"]},
            "recommended_actions": [{"text": "Implement environmental sampling of wetlands in spring 2026.", "evidence_ids": ["TREE-GROUP-001"]}],
        }
        errors = " ".join(module.validate(narrative, evidence))
        for message in ("free-form observations/actions", "population or risk claim"):
            self.assertIn(message, errors)

    def test_duplicate_selections_and_changed_scope_are_rejected(self):
        evidence = module.build_evidence(payload())
        narrative = module.materialize_selection(selection(evidence), evidence)
        narrative["what_we_know"].append(dict(narrative["what_we_know"][0]))
        self.assertTrue(any("duplicate observation_id" in error for error in module.validate(narrative, evidence)))
        narrative["what_we_know"] = narrative["what_we_know"][:1]
        narrative["what_we_know"][0]["scope"]["complete"] = 99
        self.assertTrue(any("scope must match" in error for error in module.validate(narrative, evidence)))

    def test_unavailable_group_members_are_not_silently_counted(self):
        evidence = module.build_evidence(payload())
        evidence["facts"].append(module.fact("TREE-GROUP-099", "integrated_relationship", "Group", {"segment": "HA", "sample_ids": ["S1", "MISSING"]}))
        self.assertNotIn("OBS-TREE-GROUP-099", module.prepare_evidence(evidence)["observations"])

    def test_markdown_endpoint_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record.json"
            target.write_text(json.dumps({"evidence": module.build_evidence(payload())}))
            url = "[http://127.0.0.1:11434/api/chat](http://127.0.0.1:11434/api/chat)"
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--enabled", "true", "--model", "local", "--url", url, "--fail-on-error"]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate") as call:
                self.assertEqual(module.main(), 1)
            self.assertFalse(call.called)
            self.assertIn("plain HTTP", json.loads(target.read_text())["error"])

    def test_repair_success_keeps_rejected_attempt_for_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record.json"
            evidence = module.build_evidence(payload())
            target.write_text(json.dumps({"evidence": evidence}))
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--enabled", "true", "--model", "local"]
            replies = [({"headline": "Unsupported draft"}, {"attempt": 1}), (selection(evidence), {"attempt": 2})]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate", side_effect=replies), patch.object(module, "model_digest", return_value="digest"):
                self.assertEqual(module.main(), 0)
            record = json.loads(target.read_text())
            self.assertEqual(record["status"], "GENERATED")
            self.assertTrue(record["diagnostics"]["attempts"][0]["validation_errors"])
            self.assertEqual(record["diagnostics"]["attempts"][1]["validation_errors"], [])

    def test_malformed_items_return_errors_not_exceptions(self):
        evidence = module.build_evidence(payload())
        for value in (None, [], {}, {"headline": "Draft", "what_we_know": [None], "recommended_actions": [False], "public_health_meaning": {"text": "Draft", "evidence_ids": [{}]}}):
            self.assertTrue(module.validate(value, evidence))

    def test_saved_evidence_preserves_context_and_recomputes_catalogs(self):
        original = module.build_evidence(payload())
        original["observations"]["OBS-RUN-QC"]["text"] = "Wrong count."
        restored = module.prepare_evidence(original)
        self.assertNotIn("Wrong count", restored["observations"]["OBS-RUN-QC"]["text"])
        self.assertEqual(restored["facts"], original["facts"])

    def test_rejected_drafts_and_errors_are_saved_and_cli_can_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interpretation.json"
            target.write_text(json.dumps({"evidence": module.build_evidence(payload())}))
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--enabled", "true", "--model", "local", "--fail-on-error"]
            response = {"headline": "Ongoing circulation"}
            with patch("sys.argv", argv), patch.object(module, "ollama_generate", return_value=(response, {})) as generate:
                self.assertEqual(module.main(), 1)
            record = json.loads(target.read_text())
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(record["status"], "ERROR")
            self.assertNotIn("narrative", record)
            self.assertEqual(len(record["diagnostics"]["attempts"]), 2)
            self.assertEqual(record["diagnostics"]["attempts"][0]["response"], response)
            self.assertTrue(record["diagnostics"]["attempts"][0]["validation_errors"])

    def test_cli_materializes_selection_and_records_review_status(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interpretation.json"
            evidence = module.build_evidence(payload())
            target.write_text(json.dumps({"evidence": evidence}))
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--enabled", "true", "--model", "local", "--fail-on-error"]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate", return_value=(selection(evidence), {})), patch.object(module, "model_digest", return_value="digest"):
                self.assertEqual(module.main(), 0)
            record = json.loads(target.read_text())
            self.assertEqual(record["status"], "GENERATED")
            self.assertEqual(record["validation"]["review_status"], "UNREVIEWED")
            self.assertEqual(record["narrative"]["recommended_actions"], [])
            self.assertEqual(record["narrative"]["what_we_know"][0]["text"], evidence["observations"]["OBS-RUN-QC"]["text"])

    def test_missing_host_map_does_not_overwrite_existing_record(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record.json"
            original = json.dumps({"evidence": module.build_evidence(payload())})
            target.write_text(original)
            argv = [str(SCRIPT), "--evidence-json", str(target), "--output", str(target), "--host-map", str(Path(directory) / "absent.tsv")]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate") as generate:
                self.assertEqual(module.main(), 1)
            self.assertFalse(generate.called)
            self.assertEqual(target.read_text(), original)

    def test_disabled_mode_writes_evidence_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "explorer.json"
            output = Path(directory) / "interpretation.json"
            source.write_text(json.dumps(payload()))
            with patch("sys.argv", [str(SCRIPT), "--explorer-json", str(source), "--output", str(output)]), patch.object(module, "ollama_generate") as call:
                self.assertEqual(module.main(), 0)
            self.assertFalse(call.called)
            record = json.loads(output.read_text())
            self.assertEqual(record["status"], "DISABLED")
            self.assertEqual(record["schema_version"], module.SCHEMA)

    def test_nonlocal_endpoint_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "explorer.json"
            output = Path(directory) / "interpretation.json"
            source.write_text(json.dumps(payload()))
            argv = [str(SCRIPT), "--explorer-json", str(source), "--output", str(output), "--enabled", "true", "--model", "gpt-oss:20b", "--url", "https://example.org/api/chat"]
            with patch("sys.argv", argv), patch.object(module, "ollama_generate") as call:
                self.assertEqual(module.main(), 0)
            self.assertFalse(call.called)
            self.assertIn("Refusing a nonlocal", json.loads(output.read_text())["error"])


if __name__ == "__main__":
    unittest.main()
