"""End-to-end acceptance using a copied distribution outside development tree.
Keeps inputs, process results and actual browser screenshots in evidence/isolated.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
evidence = ROOT/'evidence'
evidence.mkdir(exist_ok=True)
session = Path(tempfile.mkdtemp(prefix='jxcheck-distribution-'))
tool = session/'jxcheck.pyz'
shutil.copy2(ROOT/'dist/jxcheck-0.1.0.pyz',tool)
for name in ['software','documents']:
    shutil.copy2(ROOT/'templates'/f'{name}.manifest.json',session/f'{name}.json')
events=[]
start=time.time()
def run(domain, args, expect):
    cmd=[sys.executable,str(tool),'--root',str(session/domain),*args]
    p=subprocess.run(cmd,cwd=session,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    data=json.loads(p.stdout.decode('utf-8'))
    events.append({'args':args,'domain':domain,'returncode':p.returncode,'expected':expect,'actual':data})
    assert data['status']==expect,(args,data)
    assert (p.returncode==0)==(expect in ['preview','applied','captured','ready','ok']),data
    return data
try:
    for domain in ['software','documents']:
        run(domain,['init','--manifest',str(session/f'{domain}.json'),'--dry-run'],'preview')
        assert not (session/domain).exists()
        run(domain,['init','--manifest',str(session/f'{domain}.json'),'--apply'],'applied')
        repeated=run(domain,['init','--manifest',str(session/f'{domain}.json'),'--apply'],'applied')
        assert not repeated['changes']
        run(domain,['doctor'],'ok')
        scope=['app.py','index.html','new.txt'] if domain=='software' else ['state.json','handoff.json']
        run(domain,['task','--task','T1','--spec','task.md','--scope',*scope,'--apply'],'captured')
    software=session/'software'
    good=(software/'app.py').read_bytes()
    (software/'app.py').write_bytes(b'def total(a,b): return a-b\n')
    run('software',['verify','--task','T1'],'blocked')
    (software/'app.py').write_bytes(good)
    run('software',['verify','--task','T1'],'ready')
    page=(software/'index.html').read_bytes()
    (software/'index.html').write_bytes(page.replace(b'display:none',b'display:block'))
    run('software',['finish','--task','T1'],'stale')
    bad=run('software',['verify','--task','T1'],'blocked')
    assert next(x for x in bad['results'] if x['id']=='browser')['status']=='error'
    (software/'index.html').write_bytes(page)
    goodrun=run('software',['verify','--task','T1'],'ready')
    (software/'new.txt').write_text('untracked new source')
    run('software',['finish','--task','T1'],'stale')
    run('software',['verify','--task','T1'],'ready')
    receipt=Path(run('software',['finish','--task','T1'],'ready')['evidence'])
    screen=receipt.parent/'screen.png'
    original=screen.read_bytes()
    screen.write_bytes(b'fake image')
    run('software',['finish','--task','T1'],'blocked')
    screen.write_bytes(original)
    run('software',['finish','--task','T1'],'ready')
    run('documents',['verify','--task','T1'],'pending_manual')
    (session/'documents'/'handoff.json').write_text('{"status":"done"}')
    run('documents',['verify','--task','T1'],'blocked')
    assert not (session/'documents'/'.env').exists()
finally:
    out=evidence/'isolated'/time.strftime('%Y%m%d-%H%M%S')
    shutil.copytree(session,out)
    summary={'duration_seconds':time.time()-start,'events':events,'original_isolated_path':str(session),'retained_copy':str(out),
             'browser_module':os.environ.get('JX_PLAYWRIGHT_MODULE','playwright'),'browser_executable':os.environ.get('JX_BROWSER_EXECUTABLE','bundled'),
             'manual_interventions':0,'note':'These are controlled fixtures; no real business rollout or remote protections.'}
    (evidence/'acceptance.json').write_bytes(json.dumps(summary,ensure_ascii=False,indent=2).encode())
print(json.dumps({'status':'pass','events':len(events),'evidence':str(out),'seconds':summary['duration_seconds']}))
