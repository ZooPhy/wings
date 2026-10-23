import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('briefing', Path(__file__).resolve().parents[1] / 'scripts/agency_briefing.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'brief.json'
        self.args = SimpleNamespace(audience='wildlife', decision_question='', brief_context_json=None,
                                    output=self.output, provider='ollama', model='test', url='http://localhost',
                                    timeout=10, max_output_tokens=2048, print_narrative=False, fail_on_error=True)
        self.evidence = {'facts': [{'id': 'SOURCE', 'data': {'samples': 10}}]}
        cited = {'text': 'An observed pattern informs comparison review.', 'evidence_ids': ['SOURCE']}
        self.assessment = {k: copy.deepcopy(cited) for k in ('finding', 'significance', 'decision', 'alternatives', 'information_gap')}
        self.brief = {'headline': 'An observed pattern informs review', **{k: copy.deepcopy(cited) for k in m.LABELS}}
        self.review = {'checks': {prefix + k: {'supported': True, 'reason': 'Supported by SOURCE.'}
                                 for prefix, keys in [('assessment.', self.assessment), ('brief.', self.brief)] for k in keys}}

    def run_pipeline(self, responses):
        requests = []
        def generate(*args):
            requests.append(args)
            checkpoint = json.loads(self.output.read_text())
            self.assertEqual(checkpoint['status'], 'GENERATING')
            self.assertNotIn('narrative', checkpoint)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response, {'seconds': 0}
        def write(path, value):
            path.write_text(json.dumps(value))
        status = m.run(self.args, self.evidence, generate, lambda *a: 'digest', write)
        return status, json.loads(self.output.read_text()), requests

    def test_three_stages_preserve_sources_and_prompts(self):
        status, record, requests = self.run_pipeline([self.assessment, self.brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual(len(requests), 3)
        self.assertEqual(record['validation']['review_status'], 'UNREVIEWED')
        self.assertEqual(record['validation']['automated_review'], 'PASSED')
        for call in requests:
            self.assertEqual(json.loads(call[3])['evidence_brief']['sources']['SOURCE'], self.evidence['facts'][0])
        self.assertEqual(len(record['narrative']['public_health_meaning']['items']), 3)

    def test_unknown_citation_repaired_then_reviewed(self):
        bad = copy.deepcopy(self.brief)
        bad['meaning']['evidence_ids'] = ['INVENTED']
        status, record, requests = self.run_pipeline([self.assessment, bad, {'assessment': self.assessment, 'brief': self.brief}, self.review])
        self.assertEqual(status, 0)
        self.assertEqual([a['phase'] for a in record['diagnostics']['attempts']], ['assessment', 'briefing', 'repair', 'review_repair'])

    def test_reviewer_rejection_never_publishes(self):
        bad = copy.deepcopy(self.review)
        bad['checks']['assessment.finding'].update(supported=False, reason='Claim not supported by source.')
        status, record, _ = self.run_pipeline([self.assessment, self.brief, bad, {'assessment': self.assessment, 'brief': self.brief}, bad])
        self.assertEqual(status, 1)
        self.assertNotIn('narrative', record)
        self.assertEqual(record['status'], 'ERROR')

    def test_timeout_preserves_completed_stages(self):
        status, record, _ = self.run_pipeline([self.assessment, TimeoutError('timeout')])
        self.assertEqual(status, 1)
        self.assertEqual(record['diagnostics']['attempts'][0]['response'], self.assessment)
        self.assertNotIn('narrative', record)

    def test_review_requires_complete_unique_coverage(self):
        for change in ('omit', 'extra', 'string_boolean'):
            review = copy.deepcopy(self.review)
            if change == 'omit': review['checks'].pop('brief.decision')
            elif change == 'extra': review['checks']['invented.section'] = review['checks']['assessment.finding']
            else: review['checks']['assessment.finding']['supported'] = 'true'
            self.assertTrue(m.review_errors(review))

    def test_context_is_explicit_and_cannot_overwrite_sources(self):
        path = Path(self.temp.name) / 'context.json'
        path.write_text(json.dumps({'collection_purpose': 'Routine submissions', 'additional_sources': [
            {'id': 'CONTEXT-HISTORY', 'kind': 'historical_comparison', 'text': 'Prior comparison supplied.', 'reference': 'Local reviewed report'}]}))
        packet = m.packet(self.evidence, 'wildlife', '', path)
        self.assertEqual(packet['sources']['CONTEXT-HISTORY']['provenance'], 'user_supplied_not_independently_verified')
        self.assertFalse(m.packet(self.evidence, 'wildlife', '')['context_provided'])
        path.write_text('{"additional_sources":[{"id":"SOURCE"}]}')
        with self.assertRaises(ValueError): m.packet(self.evidence, 'wildlife', '', path)

    def test_invalid_context_preserves_existing_output(self):
        self.output.write_text('existing accepted record')
        self.args.brief_context_json = Path(self.temp.name) / 'missing.json'
        status = m.run(self.args, self.evidence, None, None, None)
        self.assertEqual(status, 1)
        self.assertEqual(self.output.read_text(), 'existing accepted record')

    def test_long_assessment_proceeds_to_briefing_and_review(self):
        long = copy.deepcopy(self.assessment)
        long['finding']['text'] = 'word ' * 517  # Four other fields add 24: 541 total.
        status, record, requests = self.run_pipeline([long, self.brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual([a['phase'] for a in record['diagnostics']['attempts']],
                         ['assessment', 'briefing', 'review'])
        self.assertNotIn('assessment', json.loads(requests[1][3]))
        self.assertEqual(json.loads(requests[2][3])['assessment'], long)
        self.assertEqual(record['diagnostics']['attempts'][0]['assessment_word_count'], 541)
        self.assertEqual(record['validation']['assessment_presentation']['word_count'], 541)

    def test_assessment_repair_is_bounded(self):
        malformed = copy.deepcopy(self.assessment)
        del malformed['finding']
        status, record, requests = self.run_pipeline([malformed, malformed])
        self.assertEqual(status, 1)
        self.assertEqual(len(requests), 2)
        self.assertEqual(record['diagnostics']['failed_phase'], 'assessment_repair')
        self.assertNotIn('narrative', record)
        self.assertTrue(record['diagnostics']['attempts'][-1]['validation_errors'])

    def test_assessment_repair_still_checks_citations(self):
        bad = copy.deepcopy(self.assessment)
        bad['finding']['evidence_ids'] = ['INVENTED']
        status, record, _ = self.run_pipeline([bad, bad])
        self.assertEqual(status, 1)
        self.assertIn('valid original evidence IDs', record['error'])
        self.assertNotIn('narrative', record)

    def test_long_brief_is_edited_then_reviewed(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'word ' * 247  # 259 words across three bullets.
        status, record, requests = self.run_pipeline([self.assessment, brief, self.brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual([a['phase'] for a in record['diagnostics']['attempts']],
                         ['assessment', 'briefing', 'shorten', 'review'])
        self.assertEqual(json.loads(requests[-1][3])['brief'], self.brief)
        self.assertTrue(record['validation']['presentation']['shortening_attempted'])

    def test_length_alone_does_not_prevent_evidence_review(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'word ' * 247
        status, record, requests = self.run_pipeline([self.assessment, brief, brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual(len(requests), 4)
        self.assertEqual(record['validation']['presentation']['brief_word_count'], 259)
        self.assertTrue(record['validation']['presentation']['target_exceeded'])
        self.assertEqual(record['validation']['automated_review'], 'PASSED')

    def test_bad_shortening_does_not_bypass_original_review(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'word ' * 247
        bad = copy.deepcopy(self.brief)
        bad['meaning']['evidence_ids'] = ['MADE-UP']
        status, record, requests = self.run_pipeline([self.assessment, brief, bad, self.review])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(requests[-1][3])['brief'], brief)
        self.assertTrue(record['diagnostics']['attempts'][2]['validation_errors'])

    def test_inventory_preserves_family_scope_and_denominators(self):
        evidence = copy.deepcopy(self.evidence)
        evidence['observations'] = {'OBS': {'scope': {
            'level': 'comparison_family', 'family': 'ecology_vs_host',
            'model_ids': ['SOURCE'], 'supported_segments': ['NP', 'MP', 'NS'],
            'tested_segments': ['HA', 'NA', 'NP', 'MP', 'NS'],
            'tested_sample_counts': [10, 10, 10, 9, 10],
            'unestimated_segments': ['PB2', 'PB1', 'PA'], 'reporting_q_threshold': .05}}}
        inventory = m.packet(evidence, 'wildlife', '')['comparison_inventory'][0]
        self.assertEqual(inventory['supported_segments'], ['NP', 'MP', 'NS'])
        self.assertEqual(inventory['tested_sample_counts'], [10, 10, 10, 9, 10])
        self.assertEqual(inventory['evidence_ids'], ['SOURCE'])
        evidence['observations']['OBS']['scope']['model_ids'] = ['MISSING']
        with self.assertRaises(ValueError): m.packet(evidence, 'wildlife', '')

    def test_brief_length_does_not_relax_citation_checks(self):
        brief = copy.deepcopy(self.brief)
        brief['meaning']['text'] = 'word ' * 259
        self.assertFalse(m.check_prose(brief, m.LABELS, {'SOURCE': {}}, headline=True))
        brief['meaning']['evidence_ids'] = ['UNKNOWN']
        self.assertTrue(m.check_prose(brief, m.LABELS, {'SOURCE': {}}, headline=True))

    def test_equations_trigger_edit_even_in_short_brief(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'ΔR² ranges from 0.10 to 0.17 and permutation p‑values < 0.005.'
        status, record, requests = self.run_pipeline([self.assessment, brief, self.brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual([a['phase'] for a in record['diagnostics']['attempts']],
                         ['assessment', 'briefing', 'shorten', 'review'])
        self.assertTrue(json.loads(requests[2][3])['style_issues'])
        self.assertEqual(record['validation']['presentation']['style_check'], 'PASSED')

    def test_unresolved_equations_are_not_published(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'The result has q < 0.005.'
        status, record, requests = self.run_pipeline([
            self.assessment, brief, brief, {'assessment': self.assessment, 'brief': brief}])
        self.assertEqual(status, 1)
        self.assertNotIn('narrative', record)
        self.assertEqual(len(requests), 4)
        self.assertIn('Plain-language edit needed', record['error'])

    def test_plain_counts_are_allowed_and_style_covers_headline(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'Only 10 of the 30 samples could be compared.'
        self.assertFalse(m.briefing_style_errors(brief))
        for text in ['R^2 = 0.1', 'p-values were low', 'q = 0.01', 'HA, NA and NP',
                     'A same-host indicator improved model fit']:
            brief['headline'] = text
            self.assertTrue(m.briefing_style_errors(brief), text)

    def test_focused_writer_and_full_reviewer_receive_different_packets(self):
        self.evidence = {'facts': [
            {'id': 'MODEL-001', 'data': {'segment': 'HA', 'delta_r2': .12, 'fdr_q': .004}},
            {'id': 'MODEL-002', 'data': {'segment': 'NA', 'status': 'UNAVAILABLE'}},
            {'id': 'GENOME-SUMMARY', 'data': {'samples': 30}},
        ], 'observations': {'OBS': {'scope': {
            'level': 'comparison_family', 'family': 'host_vs_baseline',
            'model_ids': ['MODEL-001', 'MODEL-002'], 'supported_segments': ['HA'],
            'tested_segments': ['HA'], 'tested_sample_counts': [10],
            'unestimated_segments': ['NA'], 'reporting_q_threshold': .05}}}}
        for item in self.assessment.values(): item['evidence_ids'] = ['BRIEF-HOST']
        for key in m.LABELS: self.brief[key]['evidence_ids'] = ['BRIEF-HOST']
        status, record, requests = self.run_pipeline([self.assessment, self.brief, self.review])
        self.assertEqual(status, 0)
        writer = json.loads(requests[1][3])
        self.assertNotIn('assessment', writer)
        sources = writer['evidence_brief']['sources']
        self.assertNotIn('MODEL-001', sources)
        self.assertNotIn('delta_r2', json.dumps(sources))
        self.assertEqual(sources['BRIEF-HOST']['scope']['samples_per_completed_comparison'], [10])
        full = json.loads(requests[2][3])['evidence_brief']['sources']
        self.assertEqual(full['MODEL-001']['data']['delta_r2'], .12)
        self.assertEqual(full['BRIEF-HOST']['source_evidence_ids'], ['MODEL-001', 'MODEL-002'])
        self.assertEqual(record['diagnostics']['attempts'][0]['evidence_scope'], 'focused_writing')
        self.assertEqual(record['diagnostics']['attempts'][2]['evidence_scope'], 'full_review')

    def test_compact_projection_preserves_null_and_positive_families(self):
        full = {'audience': 'wildlife', 'decision_question': 'Question', 'scope': 'Run only',
                'context_provided': False, 'sources': {'MODEL-001': {}}, 'comparison_inventory': []}
        for family in ['host_vs_baseline', 'ecology_vs_host', 'environment_vs_ecology', 'migration_vs_ecology']:
            available = family in ['host_vs_baseline', 'ecology_vs_host']
            full['comparison_inventory'].append({
                'family': family, 'tested_segments': ['HA'] if available else [],
                'supported_segments': ['HA'] if family == 'ecology_vs_host' else [],
                'tested_sample_counts': [9] if available else [],
                'unestimated_segments': [] if available else ['HA'], 'evidence_ids': ['MODEL-001']})
        cards = m.writing_packet(full)['sources']
        self.assertEqual(cards['BRIEF-SEASON']['scope']['comparisons_with_reported_association'], 1)
        self.assertEqual(cards['BRIEF-HOST']['scope']['completed_without_reported_association'], 1)
        self.assertEqual(cards['BRIEF-WEATHER']['scope']['completed_comparisons'], 0)
        self.assertIn('unanswered question', cards['BRIEF-MIGRATION']['finding'])
        self.assertNotIn('source_evidence_ids', full['sources']['MODEL-001'])

    def test_inline_citations_are_not_display_prose(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'Bird species was associated with differences (MODEL-001).'
        self.assertTrue(m.briefing_style_errors(brief))

    def test_typing_preserves_assigned_unassigned_failed_and_missing(self):
        records = [
            {'status': 'RECORDED', 'call': 'D1.1'},
            {'status': 'RECORDED', 'call': 'Minor114'},
            {'status': 'NOT_ASSIGNED', 'call': None},
            {'status': 'H5_OR_NA_INDETERMINATE', 'call': None},
            {'status': 'FAILED', 'call': None},
            None,
        ]
        facts = {f'SAMPLE-{i}': {'category': 'sample', 'data': {
            'potential_subtype': 'H5N1', 'h5_status': 'INDETERMINATE' if i == 3 else 'DETECTED',
            **({'genotype': genotype} if genotype is not None else {})}}
                 for i, genotype in enumerate(records)}
        card = m.typing_card(facts)
        self.assertEqual(card['recorded_genotype_counts'], {'D1.1': 1, 'Minor114': 1})
        self.assertEqual(card['potential_subtype_counts'], {'H5N1': 6})
        self.assertEqual(card['h5_screen_status_counts'], {'DETECTED': 5, 'INDETERMINATE': 1})
        self.assertEqual(card['genotype_status_counts']['NOT_ASSIGNED'], 1)
        self.assertEqual(card['genotype_status_counts']['FAILED'], 1)
        self.assertEqual(card['genotype_records_missing'], 1)
        self.assertEqual(len(card['source_evidence_ids']), 6)

    def test_typing_does_not_invent_calls_from_conflicting_status(self):
        sources = {'SAMPLE-1': {'category': 'sample', 'data': {'genotype': {
            'status': 'NOT_ASSIGNED', 'call': 'D1.1'}}},
            'SAMPLE-2': {'category': 'sample', 'data': {'genotype': {
            'status': 'RECORDED', 'call': None}}}}
        card = m.typing_card(sources)
        self.assertEqual(card['recorded_genotype_counts'], {})
        self.assertEqual(card['genotype_status_call_inconsistencies'], 2)
        self.assertEqual(card['potential_subtype_missing'], 2)

    def test_explorer_typing_survives_into_writer_and_reviewer(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/generate_public_health_interpretation.py'
        spec = importlib.util.spec_from_file_location('typing_generator_test', path)
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        genotype = {'status': 'RECORDED', 'call': 'D1.1', 'reason': 'Recorded source explanation', 'source_file': 'genoflu/GenoFLU.tsv'}
        evidence = generator.build_evidence({'samples': [{'sample_id': 'X', 'host': 'BLVU',
            'potential_subtype': 'H5N1', 'ha_call': 'H5', 'na_call': 'N1',
            'h5_status': 'DETECTED', 'segments_pass': 8, 'genotype': genotype}]})
        fact = next(f for f in evidence['facts'] if f['category'] == 'sample')
        self.assertEqual(fact['data']['genotype'], genotype)
        self.assertEqual(fact['data']['ha_call'], 'H5')
        full = m.packet(evidence, 'wildlife', '')
        writer = m.writing_packet(full)
        self.assertEqual(writer['sources']['BRIEF-TYPING']['recorded_genotype_counts'], {'D1.1': 1})
        self.assertEqual(full['sources'][fact['id']]['data']['genotype']['reason'], genotype['reason'])
        self.assertNotIn('Recorded source explanation', json.dumps(writer))
        self.assertEqual(full['sources']['BRIEF-TYPING']['source_evidence_ids'], [fact['id']])

    def test_review_schema_requires_exactly_nine_named_judgments(self):
        schema = m.schemas(['SOURCE'])[2]['properties']['checks']
        self.assertEqual(schema['type'], 'object')
        self.assertEqual(set(schema['required']), set(m.REVIEW_SECTIONS))
        self.assertEqual(set(schema['properties']), set(m.REVIEW_SECTIONS))
        self.assertEqual(len(schema['required']), 9)
        self.assertFalse(schema['additionalProperties'])
        for item in schema['properties'].values():
            self.assertEqual(set(item['required']), {'supported', 'reason'})
            self.assertFalse(item['additionalProperties'])
        self.assertTrue(m.review_errors({'checks': []}))

    def test_citation_groups_move_to_structured_fields_without_changing_facts(self):
        brief = copy.deepcopy(self.brief)
        text = 'Only 10 samples (of 30) could be compared. (SAMPLING-BALANCE, BRIEF-HOST, GENOME-SUMMARY)'
        brief['learned']['text'] = text
        sources = {'SOURCE': {}, 'SAMPLING-BALANCE': {}, 'BRIEF-HOST': {}, 'GENOME-SUMMARY': {}}
        clean, changes = m.normalize_citations(brief, sources)
        self.assertEqual(clean['learned']['text'], 'Only 10 samples (of 30) could be compared.')
        self.assertEqual(clean['learned']['evidence_ids'], list(sources))
        self.assertEqual(brief['learned']['text'], text)
        self.assertEqual(changes[0]['original_text'], text)
        self.assertFalse(m.briefing_style_errors(clean, sources))

    def test_citation_cleanup_preserves_unknown_and_mixed_parentheses(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'Birds (BRIEF-HOST, UNKNOWN-ID) were sampled (SOURCE describes dates).'
        clean, changes = m.normalize_citations(brief, {'SOURCE': {}, 'BRIEF-HOST': {}})
        self.assertEqual(clean, brief)
        self.assertFalse(changes)
        self.assertTrue(m.briefing_style_errors(clean, {'SOURCE': {}, 'BRIEF-HOST': {}}))

    def test_normalized_brief_reaches_reviewer_and_raw_response_is_retained(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] += ' (SOURCE)'
        status, record, requests = self.run_pipeline([self.assessment, brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual(record['briefing']['learned']['text'], self.brief['learned']['text'])
        self.assertEqual(record['diagnostics']['attempts'][1]['response'], brief)
        self.assertTrue(record['diagnostics']['citation_normalizations'])
        self.assertNotIn('(SOURCE)', json.loads(requests[2][3])['brief']['learned']['text'])

    def test_embedded_briefing_is_edited_not_silently_extracted(self):
        brief = copy.deepcopy(self.brief)
        brief['decision']['text'] = 'Headline: A result. Learned: A result. Meaning: A result. Decision: Review it.'
        status, record, requests = self.run_pipeline([self.assessment, brief, self.brief, self.review])
        self.assertEqual(status, 0)
        self.assertEqual([a['phase'] for a in record['diagnostics']['attempts']],
                         ['assessment', 'briefing', 'shorten', 'review'])
        self.assertEqual(record['briefing'], self.brief)

    def test_repeated_prose_and_all_registered_source_ids_are_checked(self):
        brief = copy.deepcopy(self.brief)
        brief['learned']['text'] = 'These samples describe birds collected in one state with incomplete information about collection sites.'
        brief['decision']['text'] = brief['learned']['text'] + ' Review missing collection sites.'
        self.assertTrue(m.briefing_style_errors(brief))
        brief = copy.deepcopy(self.brief)
        brief['decision']['text'] += ' SAMPLING-BALANCE'
        self.assertTrue(m.briefing_style_errors(brief, {'SAMPLING-BALANCE': {}}))

    def test_unavailable_comparisons_cannot_be_presented_as_negative_findings(self):
        packet = {'comparison_inventory': [
            {'family': 'environment_vs_ecology', 'tested_segments': []},
            {'family': 'migration_vs_ecology', 'tested_segments': []}]}
        brief = copy.deepcopy(self.brief)
        brief['meaning']['text'] = 'Weather and migration do not appear to explain the variation.'
        self.assertEqual(len(m.evidence_scope_errors(brief, packet)), 2)
        brief['meaning']['text'] = 'These results could not establish whether weather or migration explained the differences.'
        self.assertFalse(m.evidence_scope_errors(brief, packet))
        packet['comparison_inventory'][0]['tested_segments'] = ['HA']
        brief['meaning']['text'] = 'Weather did not explain the differences.'
        self.assertFalse(m.evidence_scope_errors(brief, packet))

    def test_context_keeps_matching_scope_and_coverage_distinct(self):
        sources = {
            'DETECTION-SUMMARY': {'data': {'source_name': 'USDA APHIS wild-bird HPAI detections', 'status': 'READY', 'record_count': 19912}},
            'RELATIONSHIP-COVERAGE': {'data': {'detection_window_days': 14,
                'samples_eligible_for_state_date_detection_overlap': 30,
                'samples_with_state_date_detection_overlap': 30,
                'samples_with_migration': 28, 'samples_with_weather': 10}},
            'CONCORDANCE-READINESS': {'data': {'distinct_migration_contexts': 5,
                'samples_with_matched_migration_night': 28, 'samples_with_complete_environment_vector': 10}},
            'CONCORDANCE-METHODS': {'data': {'migration_context': {'source': 'BirdCast Migration Dashboard'}, 'weather_summary': 'Collection date plus/minus three days'}},
        }
        card = m.context_card(sources)
        self.assertEqual(card['public_detections']['samples_with_overlap'], 30)
        self.assertEqual(card['public_detections']['window_days_either_side'], 14)
        self.assertIn('not an epidemiological case link', card['public_detections']['matching_rule'])
        self.assertEqual(card['bird_migration']['samples_with_context'], 28)
        self.assertEqual(card['bird_migration']['distinct_contexts_in_entire_run'], 5)
        self.assertIn('not tracked', card['bird_migration']['interpretation'])
        self.assertEqual(card['weather']['samples_with_context'], 10)
        self.assertNotIn('19912', json.dumps(card))
        self.assertEqual(set(card['source_evidence_ids']), set(sources))

    def test_missing_context_is_not_replaced_with_zero_or_a_named_source(self):
        self.assertIsNone(m.context_card({}))
        card = m.context_card({'RELATIONSHIP-COVERAGE': {'data': {'samples_with_weather': 0}}})
        self.assertEqual(card['weather']['samples_with_context'], 0)
        self.assertIsNone(card['bird_migration']['samples_with_context'])
        self.assertIsNone(card['public_detections']['source_name'])
        self.assertIsNone(card['public_detections']['samples_with_overlap'])

    def test_context_card_reaches_writer_and_original_source_reaches_reviewer(self):
        self.evidence['facts'].append({'id': 'DETECTION-SUMMARY', 'data': {
            'source_name': 'USDA APHIS wild-bird HPAI detections', 'status': 'READY', 'record_count': 99}})
        for item in self.assessment.values(): item['evidence_ids'] = ['BRIEF-CONTEXT']
        for key in m.LABELS: self.brief[key]['evidence_ids'] = ['BRIEF-CONTEXT']
        status, record, requests = self.run_pipeline([self.assessment, self.brief, self.review])
        self.assertEqual(status, 0)
        writer_sources = json.loads(requests[1][3])['evidence_brief']['sources']
        self.assertEqual(writer_sources['BRIEF-CONTEXT']['public_detections']['source_name'], 'USDA APHIS wild-bird HPAI detections')
        full = json.loads(requests[2][3])['evidence_brief']['sources']
        self.assertEqual(full['DETECTION-SUMMARY']['data']['record_count'], 99)
        self.assertEqual(full['BRIEF-CONTEXT']['source_evidence_ids'], ['DETECTION-SUMMARY'])

if __name__ == '__main__':
    unittest.main()
