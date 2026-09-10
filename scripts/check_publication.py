"""Check routes, publication boundaries and a copied runner's real behavior.
Does not simulate or certify a fresh AI conversation.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import ast

ROOT=Path(__file__).resolve().parents[1]
IGNORE={'.git','evidence','.artifacts','dist','__pycache__','.venv','node_modules'}
def visible():
    return [p for p in ROOT.rglob('*') if p.is_file() and not any(x in IGNORE for x in p.relative_to(ROOT).parts)]

files=visible()
links=0
for p in files:
    text=p.read_text(encoding='utf-8-sig')
    assert not re.search(r'[A-Za-z]:[\\/]Users[\\/][^\s<>]+',text), 'Personal machine path: '+str(p.relative_to(ROOT))
    assert not re.search(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)',text), 'Credential pattern: '+str(p.relative_to(ROOT))
    if p.suffix=='.md':
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text):
            target=target.split('#')[0].strip('<>')
            if target and not re.match(r'[A-Za-z]+:',target):
                assert (p.parent/target).exists(),(p.relative_to(ROOT),target)
                links+=1

readme=(ROOT/'README.md').read_text(encoding='utf-8')
start=(ROOT/'START_HERE.md').read_text(encoding='utf-8')
assert '(START_HERE.md)' in readme[:1000], 'Startup must be in first screen'
for phrase in ['仅收到链接','链接附目标','用户只要求审计','目录未知','现有项目','没有浏览器/文件工具','没有业务实现']:
    assert phrase in start, 'Missing startup scenario: '+phrase
assert '用户不需要提供长提示词' in start
rules=(ROOT/'rules/AGENTS-通用框架.md').read_text(encoding='utf-8')
assert all('| '+k+' |' in rules for k in [*[f'K{i:02}' for i in range(1,13)],*[f'W{i:02}' for i in range(1,6)]])

source_lock=json.loads((ROOT/'sources.lock.json').read_text(encoding='utf-8'))
known={r['repo'] for r in source_lock['sources']}
assert len(known)==4
for row in source_lock['sources']:
    assert re.fullmatch('[a-f0-9]{40}',row['commit'])
    assert row['license']=='MIT'
    for f in row['files']:
        assert '/blob/'+row['commit']+'/' in f['url']
        assert re.fullmatch('[a-f0-9]{64}',f['sha256'])
mapping=json.loads((ROOT/'integration-map.json').read_text(encoding='utf-8'))['entries']
assert len(mapping)==9 and len({r['id'] for r in mapping})==9
test_names={n.name for p in (ROOT/'tests').glob('test_*.py') for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef)}
for row in mapping:
    assert row['source'] in known and (ROOT/row['workflow']).is_file()
    symbols={n.name for n in ast.walk(ast.parse((ROOT/row['implementation']).read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef)}
    assert set(row['symbols'])<=symbols and set(row['tests'])<=test_names
assert '**未执行**' in (ROOT/'FULL_TEST_PLAN.md').read_text(encoding='utf-8')

with tempfile.TemporaryDirectory(prefix='jx-publication-smoke-') as d:
    temp=Path(d)
    # Copy only reviewed public source to a directory with no JX parent rules.
    clean=temp/'source';clean.mkdir()
    for p in files:
        dest=clean/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    def execute(argv,cwd):
        return subprocess.run(argv,cwd=cwd,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    built=execute([sys.executable,'scripts/build.py'],clean)
    assert built.returncode==0,built.stderr.decode(errors='replace')
    runner=temp/'runner.pyz';shutil.copy2(clean/'dist/jxcheck-0.2.0.pyz',runner)
    target=temp/'project'
    events=[]
    def cli(args,expected):
        p=execute([sys.executable,str(runner),'--root',str(target),*args],temp)
        data=json.loads(p.stdout.decode('utf-8'))
        assert data['status']==expected,(args,data)
        assert (p.returncode==0)==(expected in {'preview','applied','ok','captured','saved','ready'}),(args,p.returncode)
        events.append({'command':args[0],'expected':expected,'actual':data['status']})
    manifest=str(clean/'templates/documents.manifest.json')
    cli(['init','--manifest',manifest,'--dry-run'],'preview');assert not target.exists()
    cli(['init','--manifest',manifest,'--apply'],'applied')
    cli(['doctor'],'ok')
    cli(['task','--task','INIT','--spec','task.md','--scope','handoff.json','--apply'],'captured')
    cli(['verify','--task','INIT'],'pending_manual')
    cli(['coverage','--task','INIT'],'pending_manual')
    cli(['checkpoint','--task','INIT','--phase','paused','--next','await actual human review','--owner','executor'],'saved')
    cli(['status','--task','INIT'],'pending_manual')
    cli(['checkpoint','--task','INIT','--phase','complete','--next','done','--owner','executor'],'blocked')
    cli(['gate','--task','INIT'],'pending_manual')
    shell=shutil.which('pwsh') or shutil.which('powershell')
    if shell:
        p=execute([shell,'-NoProfile','-File',str(clean/'templates/project-gate.ps1'),'-Runner',str(runner),'-ProjectRoot',str(target),'-TaskId','INIT','-PythonExecutable',sys.executable],temp)
        assert p.returncode==2, 'Adapter must propagate pending_manual as failure'
    (target/'handoff.json').write_text('{"status":"changed"}')
    cli(['finish','--task','INIT'],'stale')
    cli(['verify','--task','INIT'],'blocked')
    p=target/'.project/project.json';config=json.loads(p.read_text(encoding='utf-8'));del config['bindings']['state']['owner'];p.write_text(json.dumps(config),encoding='utf-8')
    cli(['doctor'],'blocked')

summary={'status':'pass','public_files':len(files),'local_links':links,'startup_scenarios_present':7,
         'fusion_mappings':len(mapping),'sources':len(known),'powershell_adapter':'negative verified' if shell else 'not available',
         'isolated_commands':events,'new_ai_session_behavior':'not independently tested'}
(ROOT/'evidence').mkdir(exist_ok=True)
(ROOT/'evidence/publication-check.json').write_bytes(json.dumps(summary,ensure_ascii=False,indent=2).encode())
print(json.dumps(summary,ensure_ascii=False))
