from test_core import project
from jxcheck import core as c
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import json


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = project(self.root)
        c.capture_task(self.root, 'T1', 'task.md', ['app.py'], True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_completion_requires_evidence(self):
        with self.assertRaises(c.Invalid):
            c.checkpoint(self.root, 'T1', 'complete', 'review', 'executor')
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        c.checkpoint(self.root, 'T1', 'complete', 'review', 'executor')
        self.assertEqual(c.status(self.root, 'T1')['current_phase'], 'complete')
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'ready')

    def test_resume_marks_stale_completion(self):
        c.verify(self.root, 'T1')
        c.checkpoint(self.root, 'T1', 'complete', 'next feature', 'executor')
        with (self.root/'app.py').open('a') as f: f.write('\n# later change\n')
        s = c.status(self.root, 'T1')
        self.assertEqual(s['current_phase'], 'needs_review')
        self.assertEqual(s['recorded_phase'], 'complete')
        self.assertEqual(s['status'], 'stale')

    def test_history_and_checkpoints_preserve_evidence(self):
        c.verify(self.root, 'T1')
        c.checkpoint(self.root, 'T1', 'executing', 'review code', 'executor')
        c.checkpoint(self.root, 'T1', 'paused', 'resume review code', 'executor')
        self.assertEqual(len(list((self.root/'.artifacts/control/T1').glob('record-*.json'))), 2)
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'ready')
        self.assertEqual(c.status(self.root, 'T1')['next'], 'resume review code')

    def test_checkpoint_tampering_rejected(self):
        c.checkpoint(self.root, 'T1', 'planned', 'start', 'executor')
        p = next((self.root/'.artifacts/control/T1').glob('record-*.json'))
        data=c.read(p);data['phase']='complete';c.atomic(p,data)
        with self.assertRaises(c.Invalid): c.status(self.root, 'T1')

    def test_coverage_unverified_and_ready(self):
        result=c.coverage(self.root,'T1')
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['requirements'][0]['checks'][0]['observed'],'unverified')
        c.verify(self.root,'T1')
        self.assertEqual(c.coverage(self.root,'T1')['requirements'][0]['checks'][0]['observed'],'pass')

    def test_manual_requirement_cannot_complete(self):
        # New approved revision in an independent fixture, before task capture.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config=project(root)
            config['checks'][0]['kind']='manual'
            c.atomic(root/'.project/project.json',config)
            c.capture_task(root,'T1','task.md',['app.py'],True)
            self.assertEqual(c.verify(root,'T1')['status'],'pending_manual')
            with self.assertRaises(c.Invalid): c.checkpoint(root,'T1','complete','done','executor')

    def test_gate_cli_runs_checks_and_rejects_regression(self):
        repo=Path(__file__).resolve().parents[1]
        def gate():
            p=subprocess.run([sys.executable,'-m','jxcheck','--root',str(self.root),'gate','--task','T1'],cwd=repo,capture_output=True)
            return p.returncode,json.loads(p.stdout)
        code,result=gate()
        self.assertEqual(code,0)
        self.assertEqual(result['requirements'][0]['checks'][0]['observed'],'pass')
        (self.root/'app.py').write_text('def total(a,b): return a-b\n')
        code,result=gate()
        self.assertEqual(code,2)
        self.assertEqual(result['status'],'blocked')
