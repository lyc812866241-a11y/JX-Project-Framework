# 接入、升级与恢复

## 新项目或现有项目

1. 明确目标与授权，读取实际 AGENTS、文件、Git 状态及必选五项工作流。按需生成/适配本地条款，逐项审阅 K01—K12 与 W01—W05；不能复制 ID 就宣布继承。
2. 复用项目已有规格、状态、地图、工作流和测试；准备 manifest 与 project.json。templates 中是受控样例，不直接应用到业务根目录。
3. init --dry-run 给出逐文件 unified diff。既有不同文件会报冲突；先在授权下合并并审阅，不能强制覆盖。已有文件无需修改时，可以只绑定而不列入受管 files。
4. init --apply 创建锁和必要文件。doctor 核对当前执行器、路径、所有者、需求和命令；缺环境阻塞，不能编造验证结果。
5. 语义适配/维护场景审阅通过后，按项目原规则处理 Git 初始化；CLI 不调用 Git。记录“已绑定”，运行具体正反例后再记“本地实测”。

## 日常修复

先确定规格/检查及受保护旧测试，得到当前任务授权，再 task --apply 冻结基线。缺陷测试先证明能发现旧问题，在隔离副本重现也可；修复后 verify/finish。检查合同改变需明确差异和理由，使用新修订任务 ID 保留旧证据。

## 包或规则升级

保留旧发行包与项目快照，核对新包摘要。使用新版工具与目标 manifest 执行 upgrade --dry-run，审阅规则/测试期望/执行命令变化。--apply 只更新没有用户改动的受管文件，保存 .artifacts/upgrades/<ID>/recovery.json，输出 backup ID。冲突不写入；不会删除旧文件。

```powershell
python .\jxcheck-0.2.0.pyz --root C:\项目路径 upgrade --manifest .\project.manifest.json --dry-run
python .\jxcheck-0.2.0.pyz --root C:\项目路径 upgrade --manifest .\project.manifest.json --apply
python .\jxcheck-0.2.0.pyz --root C:\项目路径 restore --backup 返回的ID
python .\jxcheck-0.2.0.pyz --root C:\项目路径 restore --backup 返回的ID --apply
```

恢复逐字节还原备份，只删除本次创建且仍未被改动的文件；后续用户修改冲突时停止恢复。先处理差异不能强行清空目录。程序/数据/外部副作用的恢复不在文件安装器能力内。

## 中断或锁残留

检查 .artifacts/jxcheck.lock 中的 PID、启动时间和实际进程，确认原验证/安装进程及相关检查子进程都已停止，再在批准范围内删除这一个锁文件。不得凭超时或看似旧文件自动清锁。验证中断的 latest 保持 running，重跑 verify 会新建一轮，旧成功不会代替它。

若有 install.pending.json，先按其中 backup 检查恢复清单；doctor 会阻塞。确认进程停止并解除残留锁后，执行 restore 预览/恢复。保留目录中用户后续变化。恢复成功后重新 doctor、捕获必要新修订任务并验证。

这套保护防协作进程竞争与误用；同权限任意写文件仍可绕过。远程合并要求另配置可信 CI、汇总检查和分支保护，不能把本地锁当权限隔离。

## 从 v0.1.0/r5 升级到 v0.2.0/r6

保留旧包与合同，按来源差异更新本地工作流以及project.json的runner/rule_version，制作新的manifest并先预览；执行upgrade应用到未冲突文件，更新锁。配置变更后旧任务合同不匹配是预期拒绝，需在明确修订范围后用新任务ID捕获，不能覆盖旧证据。旧版本没有checkpoint，首次从实际规格建立，不编造历史。

执行器新增命令但不改变schema=1的既有字段；新锁的runner_hash会不同，不能拿旧包运行新锁项目。返回旧版时用restore保留的字节和旧执行器，再重新验证，不把恢复文件等同于业务验收。

## TASK_SPEC_MODES_V1 格式增量

执行器仍为 v0.2.0/r6。新增 [模式格式](rules/TASKSPEC.md)，源版本用实际提交 SHA 区分。新项目将格式本地化并从 AGENTS 引用；旧项目仅在升级授权内合并格式、地图与 K04 映射，再做正常/反例审阅。已有任务和调度不自动切换，已有证据按原合同保留。
