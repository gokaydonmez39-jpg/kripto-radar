from pathlib import Path
import contextlib
from datetime import datetime,timedelta,timezone
import importlib.util
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / '.github' / 'workflows'
LEGACY = 'nasdaq-xray/canonical_official_source_guard.json'
sys.path.insert(0, str(ROOT/'nasdaq-xray'))
from terminal_official_guard_contract import git_blob, verify_terminal_guard

PAIR = {LEGACY, 'nasdaq-xray/official_pit_ledger.json'}
TERMINAL_GUARD = 'nasdaq-xray/canonical_current_terminal_official_guard.json'

def step(workflow, name):
    config = yaml.safe_load((WF / workflow).read_text())
    return next(s for job in config['jobs'].values() for s in job['steps']
                if s.get('name') == name)

def published_files(workflow, name):
    return set(re.search(r'^files=\(\n(.*?)^\)', step(workflow,name)['run'],
                         flags=re.M|re.S).group(1).split())

class WriterContract(unittest.TestCase):
    def test_shared_final_does_not_own_witness_pair(self):
        files = published_files('xray-canonical-current-final.yml', 'Commit current final artifacts')
        self.assertEqual(files & PAIR, set())
        self.assertIn(TERMINAL_GUARD, files)

    def test_resilience_bulk_does_not_own_witness_pair(self):
        files = published_files('xray-resilience-observability.yml', 'Commit resilience artifacts')
        self.assertEqual(files & PAIR, set())
        self.assertIn('nasdaq-xray/canonical_macro_context.json', files)

def heredoc(step_text, anchor=None):
    script=step_text.split(anchor,1)[-1] if anchor else step_text
    body=script.split("<<'PY'\n",1)[1].split("\nPY",1)[0]
    return body


class IsolatedFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/'nasdaq-xray'
        self.root.mkdir()
        self.doc={"schema":"XRAY_OFFICIAL_SOURCE_GUARD_V1","execution":"NONE",
                  "real_money":"NO-GO","alpha_authority":False}
        self.write(LEGACY,{**self.doc,"witness":"live"})
        self.write(TERMINAL_GUARD,{**self.doc,"witness":"terminal"})
        self.bound={"path":TERMINAL_GUARD,"blob_sha":git_blob((self.base/TERMINAL_GUARD).read_bytes())}
        self.terminal='nasdaq-xray/canonical_current_terminal.json'
        self.write(self.terminal,{"evidence":{"official_halt_guard":self.bound},"asof_et":"2026-11-16"})
        self.git('init','-q')
        self.git('config','user.name','XRAY test')
        self.git('config','user.email','test@example.invalid')
        self.git('add','.')
        self.git('commit','-qm','local fixture')

    def git(self,*cmd):
        return subprocess.run(['git','-C',str(self.base),*cmd],
                              text=True,capture_output=True,check=True).stdout.strip()

    def write(self,name,payload):
        path=self.base/name
        path.write_text(json.dumps(payload))
        return path

    def python(self,script):
        return subprocess.run([sys.executable,'-c',script], text=True, capture_output=True,
            cwd=self.base, env={**os.environ,"PYTHONPATH":str(ROOT/"nasdaq-xray"),
            "RUNNER_TEMP":str(self.base)}, check=False)

    def test_exact_archived_and_legacy_evidence(self):
        self.assertEqual(verify_terminal_guard(self.root,self.bound)["witness"],"terminal")
        old={"path":LEGACY,"blob_sha":git_blob((self.base/LEGACY).read_bytes())}
        with self.assertRaisesRegex(ValueError,"BINDING_INVALID"):
            verify_terminal_guard(self.root,old)
        self.assertEqual(verify_terminal_guard(self.root,old,legacy=True)["witness"],"live")

    def test_wrong_path_blob_safety_and_symlink_fail(self):
        for edit in ({"path":"nasdaq-xray/../file.json"},{"blob_sha":"f"*40}):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                verify_terminal_guard(self.root,{**self.bound,**edit})
        path=self.write(TERMINAL_GUARD,{**self.doc,"alpha_authority":True})
        with self.assertRaisesRegex(ValueError,"SAFETY_INVALID"):
            verify_terminal_guard(self.root,{**self.bound,"blob_sha":git_blob(path.read_bytes())})
        path.unlink()
        path.symlink_to((self.base/LEGACY).name)
        with self.assertRaisesRegex(ValueError,"NOT_REGULAR"):
            verify_terminal_guard(self.root,self.bound)

    def test_real_workflows_block_protected_paths_at_git_index(self):
        for workflow, label, reason in (
            ('xray-canonical-current-final.yml','Commit current final artifacts','XRAY_FINAL_WITNESS_PATH_WRITE_BLOCKED'),
            ('xray-resilience-observability.yml','Commit resilience artifacts','XRAY_RESILIENCE_BULK_WITNESS_PATH_WRITE_BLOCKED'),
        ):
            script=step(workflow,label)['run']
            gate=re.search(r'^  if ! git diff --cached --quiet -- [^\n]+\n.*?^  fi',script,flags=re.M|re.S).group(0)
            self.git('reset','--hard','HEAD')
            self.assertEqual(subprocess.run(['bash','-c',gate],cwd=self.base).returncode,0)
            self.write(LEGACY,{**self.doc,"witness":"unexpected index write"})
            self.git('add',LEGACY)
            result=subprocess.run(['bash','-c',gate],cwd=self.base,text=True,capture_output=True)
            self.assertEqual(result.returncode,1)
            self.assertIn(reason,result.stderr)

    def test_exact_staged_guard_gate_from_real_workflow(self):
        final=step('xray-canonical-current-final.yml','Commit current final artifacts')['run']
        check=heredoc(final,'case "$event_guard"')
        ok=self.python(check)
        self.assertEqual(ok.returncode,0,ok.stderr)
        self.write(TERMINAL_GUARD,{**self.doc,"witness":"unrelated future evidence"})
        self.assertEqual(self.python(check).returncode,0)  # index remains the actual commit candidate
        self.git('add',TERMINAL_GUARD)
        rejected=self.python(check)
        self.assertIn("XRAY_FINAL_STAGED_OFFICIAL_GUARD_MISMATCH",rejected.stderr)
        self.assertNotEqual(rejected.returncode,0)

    def test_real_attestor_uses_committed_evidence_and_not_new_live_blob(self):
        truth=step('xray-live-truth-attestation.yml',
                   'Independently read all current blobs and compute truth report')['run']
        script=heredoc(truth)
        def verdict():
            result=self.python(script)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((self.base/'xray_live_truth_attestation.json').read_bytes())
            self.assertEqual(report['execution'],'NONE')
            self.assertTrue(report['this_workflow_never_authorizes_true_full_go'])
            return report['diagnostics']['terminal_drift_sources']
        self.assertNotIn('official_halt_guard',verdict())
        self.write(LEGACY,{**self.doc,"witness":"newer independent live guard"})
        self.git('add',LEGACY)
        self.git('commit','-qm','independent witness moves')
        self.assertNotIn('official_halt_guard',verdict())
        self.write(TERMINAL_GUARD,{**self.doc,"witness":"mismatch"})
        self.assertIn('official_halt_guard',verdict())
        new={"path":TERMINAL_GUARD,"blob_sha":git_blob((self.base/TERMINAL_GUARD).read_bytes())}
        self.write(self.terminal,{"evidence":{"official_halt_guard":new},"asof_et":"2026-11-16"})
        self.assertIn('official_halt_guard',verdict())

    def test_final_uses_distinct_source_from_live_default(self):
        module=ROOT/'nasdaq-xray'/'build_current_terminal.py'
        def read(enable):
            env={**os.environ,"PYTHONPATH":str(module.parent)}
            env.pop('XRAY_USE_TERMINAL_OFFICIAL_EVIDENCE',None)
            if enable: env['XRAY_USE_TERMINAL_OFFICIAL_EVIDENCE']='1'
            return subprocess.check_output([sys.executable,'-c',
                 'import build_current_terminal as t; print(t.OFFICIAL_HALT_GUARD.name)'],
                 text=True,env=env).strip()
        self.assertEqual(read(True),Path(TERMINAL_GUARD).name)
        self.assertEqual(read(False),Path(LEGACY).name)

    def test_manual_current_guard_veto_is_not_replaced_by_terminal_snapshot(self):
        from manual_decision_report import verify_live_guard
        now=datetime(2026,11,16,21,20,tzinfo=timezone.utc)
        live={**self.doc,"status":"PASS","generated_at_utc":now.isoformat(),
              "sources":{"trade_halts":{"status":"PASS","active_halt_symbols":["TEST"]},
                         "security_status":{"status":"PASS","suspension_symbols":[]}},
              "candidate_safety":{"veto_symbols":["TEST"]}}
        verify_live_guard(live,[{"symbol":"OK"}],now)
        with self.assertRaisesRegex(ValueError,"CANDIDATE_VETO"):
            verify_live_guard(live,[{"symbol":"TEST"}],now)
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_OR_STALE"):
            verify_live_guard(live,[{"symbol":"OK"}],now+timedelta(seconds=901))
        with self.assertRaisesRegex(ValueError,"VETO_NOT_BOUND"):
            verify_live_guard({**live,"candidate_safety":{"veto_symbols":[]}},[{"symbol":"TEST"}],now)
        with self.assertRaisesRegex(ValueError,"GUARD_INVALID"):
            verify_live_guard({**live,"alpha_authority":True},[{"symbol":"OK"}],now)

    def test_actual_producer_cli_keeps_live_blob_unchanged_in_terminal_mode(self):
        source=ROOT/'nasdaq-xray'/'official_source_guard.py'
        target=self.root/source.name
        target.write_bytes(source.read_bytes())
        original=(self.base/LEGACY).read_bytes()
        mock=types.ModuleType("resilience_runtime")
        def offline(*a,**k):
            raise RuntimeError("fixture no network")
        mock.fetch_text=offline
        with patch.dict(sys.modules,{"resilience_runtime":mock}), patch.object(sys,"argv",[str(target),"--terminal-evidence"]), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(target),run_name="__main__")
        self.assertEqual((self.base/LEGACY).read_bytes(),original)
        generated=json.loads((self.base/TERMINAL_GUARD).read_bytes())
        self.assertEqual(generated["status"],"DEGRADED")
        self.assertEqual(generated["execution"],"NONE")
        self.assertIs(generated["alpha_authority"],False)


if __name__=='__main__':
    unittest.main()
