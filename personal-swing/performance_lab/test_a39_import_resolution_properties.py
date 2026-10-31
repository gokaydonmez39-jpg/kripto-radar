"""A39 independent labels: project-root imports and ambiguity (offline only)."""
from __future__ import annotations
import copy
import random
import unittest
from a36_personal_source_audit import scan_sources, validate_report

ROOT = 'personal-swing/'
WORKFLOW = '.github/workflows/xray-personal-a39-fixture.yml'
SHA = 'e' * 40


def corpus():
    return {
        ROOT + 'performance_lab/guard.py': 'def verify(): return True\n',
        ROOT + 'research_lab/caller.py': 'from performance_lab.guard import verify\n',
        ROOT + 'research_lab/alias.py': 'from performance_lab import guard\n',
        ROOT + 'research_lab/direct.py': 'import performance_lab.guard\n',
        ROOT + 'research_lab/negative.py':
            '# import performance_lab.guard\n'
            's = "from performance_lab import guard"\n'
            'import vendor_not_installed.guard\n'
            'from performance_lab import missing_module\n',
        WORKFLOW: 'name: A39\njobs: {}\n',
    }


TRUTH = {
    (ROOT + 'research_lab/caller.py', ROOT + 'performance_lab/guard.py'),
    (ROOT + 'research_lab/alias.py', ROOT + 'performance_lab/guard.py'),
    (ROOT + 'research_lab/direct.py', ROOT + 'performance_lab/guard.py'),
}


def local_edges(r):
    return {(e['from'], e['to']) for e in r['edges'] if e['relation'] == 'imports'}


class A39ImportProperties(unittest.TestCase):
    def test_predeclared_graph_ground_truth(self):
        doc = corpus()
        a = scan_sources(doc, commit_sha=SHA)
        validate_report(a, doc)
        self.assertEqual(local_edges(a), TRUTH)
        self.assertTrue(all(e['confidence'] == 'INFERRED' for e in a['edges']
                            if (e['from'], e['to']) in TRUTH))
        self.assertFalse(a['runtime_reachable_proven'])
        self.assertFalse(a['orders'])

    def test_external_and_nonexistent_are_never_edges(self):
        doc = corpus()
        a = scan_sources(doc, commit_sha=SHA)
        self.assertEqual(local_edges(a), TRUTH)
        self.assertFalse(any(e['from'].endswith('negative.py') for e in a['edges']))

    def test_resolving_same_root_twice_does_not_duplicate(self):
        doc = corpus()
        doc[ROOT + 'engine.py'] = 'import performance_lab.guard\n'
        a = scan_sources(doc, commit_sha=SHA)
        edges = [e for e in a['edges'] if e['from'].endswith('engine.py')]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]['to'], ROOT + 'performance_lab/guard.py')

    def test_ambiguous_root_fails_closed_with_lead(self):
        doc = corpus()
        doc[ROOT + 'research_lab/performance_lab/guard.py'] = 'pass\n'
        a = scan_sources(doc, commit_sha=SHA)
        affected = {(e['from'], e['to']) for e in a['edges']
                    if e['from'].endswith(('caller.py', 'alias.py', 'direct.py'))}
        self.assertEqual(affected, set())
        self.assertEqual(sum(x['code'] == 'AMBIGUOUS_IMPORT_ROOTS' for x in a['findings']), 3)
        self.assertTrue(all(x['verdict'] == 'needs_validation'
                            and x['severity'] is None for x in a['findings']))

    def test_source_order_invariance_for_fifty_permutations(self):
        original = corpus()
        oracle = scan_sources(original, commit_sha=SHA)
        r = random.Random(3901)
        pairs = list(original.items())
        for _ in range(50):
            r.shuffle(pairs)
            shuffled = dict(pairs)
            got = scan_sources(shuffled, commit_sha=SHA)
            self.assertEqual(got, oracle)
            self.assertEqual(shuffled, dict(pairs))
        self.assertEqual(original, corpus())

    def test_line_provenance_and_report_tampering(self):
        original = corpus()
        got = scan_sources(original, commit_sha=SHA)
        for e in got['edges']:
            line = original[e['source_file']].splitlines()[e['line'] - 1]
            self.assertIn('guard', line)
        invalid = copy.deepcopy(got)
        invalid['coverage_ledger'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'LEDGER_SHA_DRIFT'):
            validate_report(invalid, original)


if __name__ == '__main__':
    unittest.main()
