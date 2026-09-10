"""Save actual unittest outcomes and tracebacks, not a manually written PASS."""
import json
from pathlib import Path
import time
import unittest
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

start=time.time()
suite=unittest.defaultTestLoader.discover('tests')
class Recorder(unittest.TextTestResult):
    def startTest(self,test):
        super().startTest(test)
        self.events.append({'test':test.id(),'started':time.time()})
    def addSuccess(self,test):
        super().addSuccess(test)
        self.events[-1].update(status='pass',seconds=time.time()-self.events[-1]['started'])
    def addFailure(self,test,err):
        super().addFailure(test,err)
        self.events[-1].update(status='fail',detail=self._exc_info_to_string(err,test))
    def addError(self,test,err):
        super().addError(test,err)
        self.events[-1].update(status='error',detail=self._exc_info_to_string(err,test))
    def __init__(self,*args):
        super().__init__(*args);self.events=[]
r=unittest.TextTestRunner(verbosity=2,resultclass=Recorder).run(suite)
Path('evidence').mkdir(exist_ok=True)
Path('evidence/unit-tests.json').write_bytes(json.dumps({'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'seconds':time.time()-start,'events':r.events},indent=2).encode())
raise SystemExit(0 if r.wasSuccessful() and r.testsRun else 1)
