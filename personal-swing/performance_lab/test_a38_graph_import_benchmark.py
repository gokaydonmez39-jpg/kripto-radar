"""A38: independently labelled import graph cases, no upstream runtime and no I/O."""
import unittest
from a36_personal_source_audit import scan_sources, validate_report

SHA = 'c' * 40
W = '.github/workflows/xray-personal-a38-fixture.yml'
ROOT = 'personal-swing/'


def fixture():
    return {
        ROOT + 'engine.py': 'from performance_lab.guard import assess\nimport research_lab.source\nimport math\n',
        ROOT + 'performance_lab/guard.py': 'def assess(): return True\n',
        ROOT + 'research_lab/source.py': 'def source(): return 1\n',
        ROOT + 'research_lab/nested/inner.py': 'from .. import source\n',
        ROOT + 'research_lab/runner.py': (
            'from . import source\n'
            'from .source import source as run_source\n'
            'import never_installed_module\n'
        ),
        ROOT + 'research_lab/blocked.py': (
            'from .missing_module import foo\n'
            'import unrelated.externally_provided\n'
        ),
        W: 'name: A38\njobs:\n  check:\n    steps:\n      - uses: actions/checkout@' + 'a'*40 + '\n',
    }


# An independently predeclared set of literal import relationships.
TRUTH = {
    (ROOT+'engine.py', ROOT+'performance_lab/guard.py'),
    (ROOT+'engine.py', ROOT+'research_lab/source.py'),
    (ROOT+'research_lab/nested/inner.py', ROOT+'research_lab/source.py'),
    (ROOT+'research_lab/runner.py', ROOT+'research_lab/source.py'),
}


def labelled_edges(report):
    return {(x['from'], x['to']) for x in report['edges']
            if x['relation'] == 'imports'}


class A38Benchmark(unittest.TestCase):
    def test_predeclared_import_relationships_full_recall(self):
        files = fixture()
        report = scan_sources(files, commit_sha=SHA)
        validate_report(report, files)
        got = labelled_edges(report)
        self.assertEqual(got, TRUTH, f'missed={sorted(TRUTH-got)} unexpected={sorted(got-TRUTH)}')
        self.assertTrue(all(e['confidence']=='EXTRACTED' for e in report['edges']))
        self.assertFalse(report['orders'])
        self.assertFalse(report['writes'])
        self.assertFalse(report['network_calls'])

    def test_wrong_relative_parent_does_not_get_false_edge(self):
        files = fixture()
        files[ROOT+'research_lab/nested/inner.py'] = 'from ..not_here import source\n'
        r = scan_sources(files, commit_sha=SHA)
        self.assertFalse(any(x['from'].endswith('nested/inner.py') for x in r['edges']))

    def test_only_src_tree_and_not_external_dependencies(self):
        files = fixture()
        r = scan_sources(files, commit_sha=SHA)
        self.assertTrue(all(x['to'] in files for x in r['edges']))
        self.assertFalse(any(x['to'].endswith('math.py') for x in r['edges']))

    def test_report_deterministic_and_line_provenance(self):
        files = fixture()
        a = scan_sources(files, commit_sha=SHA)
        b = scan_sources(files, commit_sha=SHA)
        self.assertEqual(a, b)
        validate_report(a, files)
        for e in a['edges']:
            self.assertTrue(1 <= e['line'] <= len(files[e['source_file']].splitlines()))


if __name__=='__main__':
    unittest.main()
