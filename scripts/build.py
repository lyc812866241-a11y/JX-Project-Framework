"""Build portable zipapp and example manifests using standard library only."""
from pathlib import Path
import json
import shutil
import tempfile
import zipapp

ROOT = Path(__file__).resolve().parents[1]
def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2)+'\n').encode())

# Published rules/ is authoritative; never discover personal parent directories.
with tempfile.TemporaryDirectory() as tmp:
    stage = Path(tmp)
    shutil.copytree(ROOT/'jxcheck',stage/'jxcheck',ignore=shutil.ignore_patterns('__pycache__'))
    (ROOT/'dist').mkdir(exist_ok=True)
    zipapp.create_archive(stage,ROOT/'dist/jxcheck-0.2.0.pyz',main='jxcheck.core:main',compressed=True)

spec = '\n'.join('## '+h+'\n隔离演示：验证已配置行为，不代表真实项目验收。' for h in ['目标','上下文','范围','约束','验收'])
rules = '''# 示例项目协作入口
当前执行者维护本项目。先读本文件、task.md、state.json；只按当前批准任务执行，未知标待核验。
自然语言请求整理成目标、上下文、范围、约束、验收；授权范围内持续执行，扩大范围先修订。
每次修复查直接原因、上游产生机制与检出缺口，保留能抓原缺陷的检查。
K09 同根因扩展审查：提炼触发条件与错误模式，沿共享实现/调用方/模板/复制逻辑查同类位置，记录范围及候选确认/排除/待核验依据；范围内连同源头修复，超范围先修订授权。验证原例、确认同类位置及旧功能；收尾披露未查未修项，不能凭单点通过宣称全部解决。
任务拆分必须说明读写边界、接口唯一维护者及依赖；本例不创建子任务。
当前状态在 state.json，结构和维护流程在本文件，历史证据在 .artifacts/runs；task.md 保留原要求。
源版本 2026-09-10-r6；初始化/升级核对 K01—K12、W01—W05，语义映射见 inheritance.md。
结构变化更新本地图及引用，当前/历史分开，交接写下一步；实际环境变化更新 project.json 非敏感环境标识。
不存真密钥；没有外部服务不建 .env，新增服务后重新绑定环境说明和验证。
本例无发布/部署。后续启用时另明确版本、授权、恢复及实际入口验证。

## 维护与验证
读取 .project/project.json 的绑定与检查，doctor 检查配置，task 冻结合同，verify 执行，finish 核对证据。
源码/测试/配置变化后重新验证；ready 仅指配置标准满足；人工项保留 pending_manual。
每次交付列增改删移、结构影响、验证及待办。升级先 dry-run，有用户修改冲突则合并后另审。
恢复用 .artifacts/upgrades 的恢复记录，保留后续用户修改。CLI 不接管宿主，不证明读懂规则。

## 文件地图
- [模式格式](TASKSPEC.md)：按用户指定模式转换；只整理不启动；维护者为当前执行者。
- [任务](task.md)：五项目标与边界，由执行者维护。
- [状态](state.json)：当前状态，更新后核对交接。
- [.project/project.json](.project/project.json)：唯一检查与维护绑定合同；task 读取并冻结，verify/finish 消费。
- [继承映射](inheritance.md)：源规则落点和领域适配；实际业务项目必须重新审阅。
- .project/tasks/：任务基线；.artifacts/runs/：执行器证据，不充当源码。
'''
inheritance = '''# 隔离示例继承映射
源：2026-09-10-r6。此表是示例设计审阅，真实项目需重新核对具体业务。
K01/K02：AGENTS 开头，权威读取、未知与授权。
K04 模式增量：AGENTS 引用本地 TASKSPEC.md，包含四种配置及实际启动核验。
K03/K04/K05：task.md 五项语义；project.json 唯一检查合同；task 冻结与范围检查。
K06/K09/K12：AGENTS 维护验证；verify/finish；修复先复现再检查原缺陷。
K07：AGENTS 任务拆分的所有者与边界，本例单执行者。
K08/K11：AGENTS 状态/历史/地图/环境变化触发与恢复路径。
K10：本映射及源版本；升级需差异/场景核对。
W01：AGENTS 文件地图；结构变化后更新引用和检查定义。
W02：AGENTS 维护验证；必需项失败禁止完成。
W03：无部署场景，启用时绑定授权、实际版本与恢复检查。
W04：manifest 绑定既有记录，init 预览后应用，doctor 验证；Git 初始化独立按目标授权执行。
W05：AGENTS 维护步骤及 project.json 各角色的 owner/触发/验证。
结构机器检查不能证明语义充分性；四类维护场景在交付验收报告中另行审阅。
'''
for domain in ['software','documents']:
    files = {'AGENTS.md':rules,'TASKSPEC.md':(ROOT/'rules/TASKSPEC.md').read_text(encoding='utf-8'),'task.md':spec,'state.json':'{"status":"active","next":"verify"}\n','inheritance.md':inheritance}
    config = {'schema':1,'runner':'0.2.0','rule_version':'2026-09-10-r6','environment_id':'isolated-local-no-secrets','build_id':'source-snapshot',
              'requirements':['R1'], 'bindings':{role:{'path':'state.json' if role=='state' else 'AGENTS.md','owner':'current-executor','read_when':'task start','update_when':'state/structure/rules change','verify':'doctor + document checks + semantic review'} for role in ['entry','state','map','history','maintenance']}}
    check = {'id':'primary','requirements':['R1'],'expected':'declared behavior holds','owner':'current-executor','required':True,'steps':'run declared checks','evidence':['structured report']}
    if domain=='software':
        files['app.py']='def total(a,b): return a+b\n'
        files['check.py']='''import sys, xml.etree.ElementTree as E
from app import total
r=E.Element('testsuite');t=E.SubElement(r,'testcase',name='existing_addition')
if total(2,3)!=5:E.SubElement(t,'failure',message='addition regression')
E.ElementTree(r).write(sys.argv[1])
'''
        files['index.html']='<!doctype html><meta charset="utf-8"><title>Local cart fixture</title><h1>Cart</h1><button id="add" onclick="document.querySelector(\'#count\').textContent=\'1\'">Add item</button><p id="count">0</p><div id="overlay" style="display:none;position:fixed;inset:0;background:#ddd">Blocking overlay</div>'
        files['browser_check.cjs']=(ROOT/'scripts/browser_check.cjs').read_text(encoding='utf-8')
        check.update(kind='junit',argv=['{python}','check.py','{run}/unit.xml'],cwd='.',report='{run}/unit.xml',expected_cases=['existing_addition'])
        config['requirements'].append('R2')
        config['checks']=[check,{**check,'id':'browser','requirements':['R2'],'kind':'json','argv':['node','browser_check.cjs','{run}/browser.json'],
                                  'report':'{run}/browser.json','assertions':{'visibleAtCenter':True,'clicked':True},'attachments':['{run}/screen.png'],'timeout':30,
                                  'expected':'button center unobscured; click increments count to 1','steps':'open local page at 960x640, hit test, click, screenshot'}]
        files['AGENTS.md']+='\n- app.py → check.py 验证加法；index.html → browser_check.cjs 验证遮挡与点击；源码快照绑定两条链。\n'
    else:
        files['handoff.json']='{"status":"active"}\n'
        check.update(kind='document',documents=['AGENTS.md'],equal=[['state.json#status','handoff.json#status']])
        config['checks']=[check,{**check,'id':'human-understanding','kind':'manual','expected':'user independently applies lesson','steps':'user explains a new example; identity confirmation outside CLI'}]
        files['AGENTS.md']+='\n- handoff.json：交接状态，与 state.json 一致；理解判断保留人工待验收。\n'
    files['.project/project.json']=json.dumps(config,ensure_ascii=False,indent=2)+'\n'
    dump(ROOT/'templates'/f'{domain}.manifest.json',{'schema':1,'files':files})
print('Built portable zipapp and two runnable manifests')
