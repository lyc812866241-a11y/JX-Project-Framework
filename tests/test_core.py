import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jxcheck import core as c


SPEC = '\n'.join('## ' + s + '\nExample' for s in ['目标', '上下文', '范围', '约束', '验收'])


def project(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'AGENTS.md').write_text('Entry: [state](state.json)\n', encoding='utf-8')
    c.atomic(root / 'state.json', {'status': 'active'})
    (root / 'task.md').write_text(SPEC, encoding='utf-8')
    (root / 'app.py').write_text('def total(a, b): return a + b\n', encoding='utf-8')
    (root / 'check.py').write_text('''import sys, xml.etree.ElementTree as E
from app import total
r=E.Element('testsuite'); t=E.SubElement(r,'testcase', name='existing_addition')
if total(2,3)!=5: E.SubElement(t,'failure', message='addition regression')
E.ElementTree(r).write(sys.argv[1])
''', encoding='utf-8')
    config = {'schema': 1, 'runner': c.__version__, 'rule_version': c.RULE_VERSION,
              'requirements': ['R1'], 'environment_id': 'isolated-no-secrets', 'build_id': 'source-snapshot',
              'bindings': {role: {'path': 'AGENTS.md' if role != 'state' else 'state.json', 'owner': 'maintainer', 'read_when': 'start', 'update_when': 'change', 'verify': 'local check'} for role in c.ROLES},
              'checks': [{'id': 'addition', 'requirements': ['R1'], 'expected': '2+3=5; old addition unchanged',
                          'owner': 'maintainer', 'kind': 'junit', 'steps': 'run regression', 'evidence': ['junit'], 'required': True,
                          'argv': ['{python}', 'check.py', '{run}/unit.xml'], 'cwd': '.', 'report': '{run}/unit.xml', 'expected_cases': ['existing_addition']}]}
    c.atomic(root / '.project/project.json', config)
    c.atomic(root / '.project/framework.lock.json', {'runner': c.__version__, 'rule_version': c.RULE_VERSION, 'source_hash': 'test-fixture', 'runner_hash': c.identity(), 'files': {}})
    return config


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def freeze(self, scope=None):
        c.capture_task(self.root, 'T1', 'task.md', scope or ['app.py', 'check.py', 'new.py', 'config.json'], True)

    def save(self):
        c.atomic(self.root / '.project/project.json', self.config)

    def test_A04_normal(self):
        self.freeze()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'ready')

    def test_A05_failure_skip_zero_environment(self):
        for xml in ['<testsuite><testcase name="existing_addition"><failure/></testcase></testsuite>', '<testsuite><testcase name="existing_addition"><skipped/></testcase></testsuite>', '<testsuite/>', '<testsuite errors="1"><testcase name="existing_addition"/></testsuite>']:
            with self.subTest(xml=xml):
                (self.root / 'check.py').write_text('import sys\nopen(sys.argv[1],"w").write(' + repr(xml) + ')')
                if not (self.root / '.project/tasks/T1.json').exists(): self.freeze()
                self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')
        self.config['checks'][0]['argv'][0] = 'jx_nonexistent_executable_98465'
        self.save()
        self.assertEqual(c.doctor(self.root)['status'], 'blocked')

    def test_A06_changed_contract(self):
        self.freeze()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        for key, val in [('argv', ['{python}', '-c', 'print("PASS")']), ('expected', 'accept anything')]:
            self.config['checks'][0][key] = val
            self.save()
            self.assertEqual(c.finish(self.root, 'T1')['status'], 'blocked')
            with self.assertRaises(c.Invalid): c.verify(self.root, 'T1')

    def test_A07_all_source_changes_stale(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'app.py', 'check.py'], check=True, capture_output=True)
        tracked = subprocess.run(['git', '-C', str(self.root), 'ls-files'], check=True, capture_output=True, text=True).stdout
        self.assertIn('app.py', tracked)
        self.assertNotIn('new.py', tracked)
        self.freeze()
        for name in ['app.py', 'check.py', 'new.py', 'config.json']:
            self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
            with (self.root / name).open('a') as f: f.write('\n')
            self.assertEqual(c.finish(self.root, 'T1')['status'], 'stale')

    def test_A08_evidence_replacement(self):
        self.freeze()
        r = c.verify(self.root, 'T1')
        p = Path(r['evidence']).parent / 'unit.xml'
        p.write_text('PASS')
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'blocked')

    def test_A08_missing_report_and_attachment(self):
        self.config['checks'][0]['attachments'] = ['{run}/screenshot.png']
        self.save(); self.freeze()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')
        (self.root / 'check.py').write_text('print("PASS")')
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')

    def test_A09_A10_regression_red_green_deleted_test(self):
        self.freeze()
        (self.root / 'app.py').write_text('def total(a,b): return a-b\n')
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')
        (self.root / 'app.py').write_text('def total(a,b): return a+b\n')
        # Avoid timestamp-based Python pyc reuse; runner must disable bytecode cache.
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        (self.root / 'check.py').unlink()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')

    def test_A03_missing_bindings_owner_requirements(self):
        original = copy.deepcopy(self.config)
        for kind in ['binding', 'owner', 'requirement', 'path']:
            self.config = copy.deepcopy(original)
            if kind == 'binding': del self.config['bindings']['state']
            if kind == 'owner': del self.config['bindings']['map']['owner']
            if kind == 'requirement': self.config['requirements'].append('R2')
            if kind == 'path': self.config['bindings']['maintenance']['path'] = 'absent.md'
            self.save()
            self.assertEqual(c.doctor(self.root)['status'], 'blocked')

    def test_A12_document_and_manual(self):
        ch = self.config['checks'][0]
        ch.update(kind='document', documents=['AGENTS.md'])
        self.config['checks'].append({**ch, 'id': 'human', 'kind': 'manual', 'steps': 'User judges understanding'})
        self.save(); self.freeze()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'pending_manual')
        self.assertFalse((self.root / '.env').exists())

    def test_A13_scope_link_state(self):
        ch = self.config['checks'][0]
        ch.update(kind='document', documents=['AGENTS.md'], equal=[['state.json#status', 'handoff.json#status']])
        c.atomic(self.root / 'handoff.json', {'status': 'active'})
        self.save(); self.freeze(['AGENTS.md', 'handoff.json'])
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        c.atomic(self.root / 'handoff.json', {'status': 'done'})
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')
        c.atomic(self.root / 'handoff.json', {'status': 'active'})
        (self.root / 'AGENTS.md').write_text('[bad](missing.md)')
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')
        (self.root / 'outside.txt').write_text('unauthorized')
        with self.assertRaises(c.Invalid): c.verify(self.root, 'T1')

    def test_A14_fake_flags(self):
        (self.root / 'VERIFIED').write_text('PASS')
        (self.root / 'READ').write_text('read all files')
        self.freeze()
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'blocked')

    def test_A15_busy_interrupted_and_task_isolation(self):
        self.freeze()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        with c.lock(self.root):
            self.assertEqual(c.finish(self.root, 'T1')['status'], 'blocked')
            with self.assertRaises(c.Invalid): c.verify(self.root, 'T1')
        c.atomic(self.root / '.artifacts/T1.latest.json', {'state': 'running', 'run': 'partial'})
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'blocked')
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')
        self.assertEqual(c.finish(self.root, 'T2')['status'], 'blocked')

    def test_A01_A02_install_upgrade_restore(self):
        target = self.root / 'target'
        manifest = self.root / 'manifest.json'
        c.atomic(manifest, {'schema': 1, 'files': {'AGENTS.md': 'owned v1\n'}})
        self.assertEqual(c.installation(target, manifest)['status'], 'preview')
        self.assertFalse(target.exists())
        c.installation(target, manifest, True)
        self.assertEqual(c.installation(target, manifest, True)['changes'], [])
        c.atomic(manifest, {'schema': 1, 'files': {'AGENTS.md': 'owned v2\n'}})
        (target / 'AGENTS.md').write_text('user change')
        self.assertEqual(c.installation(target, manifest, True, True)['status'], 'conflict')
        self.assertEqual((target / 'AGENTS.md').read_text(), 'user change')
        (target / 'AGENTS.md').write_bytes(b'owned v1\n')
        result = c.installation(target, manifest, True, True)
        self.assertEqual((target / 'AGENTS.md').read_text(), 'owned v2\n')
        c.restore(target, result['backup'], True)
        self.assertEqual((target / 'AGENTS.md').read_text(), 'owned v1\n')

    def test_A02_restore_preserves_later_change(self):
        manifest = self.root / 'm.json'
        c.atomic(manifest, {'schema': 1, 'files': {'owned.md': 'initial'}})
        r = c.installation(self.root, manifest, True)
        (self.root / 'owned.md').write_text('later user edit')
        with self.assertRaises(c.Invalid): c.restore(self.root, r['backup'], True)

    def test_secret_exclusion_and_path_escape(self):
        (self.root / '.env').write_text('FAKE_TEST_ONLY=placeholder')
        self.assertNotIn('.env', c.snapshot(self.root))
        with self.assertRaises(c.Invalid): c.inside(self.root, '../escape')

    def test_A10_partial_test_deletion_detected(self):
        self.freeze()
        (self.root / 'check.py').write_text('import sys\nopen(sys.argv[1],"w").write(\'<testsuite><testcase name="easy_new_test"/></testsuite>\')')
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'blocked')

    def test_A15_actual_process_contention_and_crash(self):
        self.freeze()
        script = 'from pathlib import Path; from jxcheck.core import lock; import sys,time;\nwith lock(Path(sys.argv[1])):\n print("locked",flush=True)\n time.sleep(30)'
        process = subprocess.Popen([sys.executable, '-c', script, str(self.root)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.assertRaises(c.Invalid): c.verify(self.root, 'T1')
        finally:
            process.kill(); process.wait(); process.stdout.close()
        self.assertEqual(c.finish(self.root, 'T1')['status'], 'blocked')
        # Recovery only after independently confirming the process has exited.
        self.assertIsNotNone(process.returncode)
        (self.root / '.artifacts/jxcheck.lock').unlink()
        self.assertEqual(c.verify(self.root, 'T1')['status'], 'ready')

    def test_source_changes_during_run_stale(self):
        with (self.root/'check.py').open('a') as f: f.write('\nopen("new.py","w").write("changed during run")\n')
        self.freeze()
        self.assertEqual(c.verify(self.root,'T1')['status'],'stale')


if __name__ == '__main__':
    unittest.main(verbosity=2)
