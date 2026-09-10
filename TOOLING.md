# AI 执行说明

用户入口在 README/START_HERE；本页由 AI 阅读，不要求用户复制命令。

标准库运行：Python 3.12 已在 Windows 实测。克隆固定提交到临时目录后，可直接 `python -m jxcheck --help`，或执行 `python scripts/build.py` 获得 `dist/jxcheck-0.2.0.pyz`。公开版 build 只使用仓库内规则，不搜索父目录。

在目标项目制作专用 manifest（不要直接应用 templates 演示），按 [合同](CONTRACT.md) 绑定已有文件、领域检查、真实运行目录/前提与维护者。

```text
python <runner.pyz> --root <target> init --manifest <prepared-manifest.json> --dry-run
python <runner.pyz> --root <target> init --manifest <prepared-manifest.json> --apply
python <runner.pyz> --root <target> doctor
python <runner.pyz> --root <target> task --task <id> --spec <spec.md> --scope <approved-patterns> --apply
python <runner.pyz> --root <target> verify --task <id>
python <runner.pyz> --root <target> finish --task <id>
```

task 必须在规格/检查确定且业务修改前捕获；初次接入可先初始化、再为实际接入检查捕获基线。之后检查合同/规格变化需新修订 ID，保留历史。ready 仅满足配置标准；manual 保持 pending_manual，不证明人类身份。

首次无业务代码时，应运行实际文档/绑定检查，记录未来业务待办，不制造业务成功报告。UI 项目用真实浏览器检查，命令参数与结构化报告登记在合同中；不能用截图说明文本替代实际运行。

框架自身检查：`python -m unittest discover -s tests -v`；启动/公开包检查：`python scripts/check_publication.py`。

浏览器夹具：运行 build 后，可用已有 Node、Playwright、浏览器执行 `python scripts/acceptance.py`。通过 JX_PLAYWRIGHT_MODULE/JX_BROWSER_EXECUTABLE 指向已有组件；生成的 evidence 仅本地保留，默认不提交。

恢复和中断处理见 [UPGRADE.md](UPGRADE.md)。本地进程不是权限沙箱，不能自动接管宿主工具；外部环境与秘密值不由源码快照完全证明。

## v0.2.0 持续交付命令

`coverage --task <id>` 按需求显示对应检查和实际结果；无当前证据不报通过。`gate --task <id>` 重新执行verify并在ready后复核coverage，非ready返回2。

`checkpoint --task <id> --phase <phase> --next <下一步> --owner <负责人>` 保存恢复点，complete必须有当前ready；其他阶段只是进度记录。`status --task <id>` 比较实际版本和检查点，过期的complete显示needs_review。首次无检查点从实际规格开始；不要伪造恢复记录。

恢复点保存在.artifacts/control（不参与源码快照），不能代替项目业务状态；同步业务文档后重验。适配步骤见 [DELIVERY_LOOP](DELIVERY_LOOP.md) 和 [ADAPTERS](ADAPTERS.md)。

## 模式与执行器边界

[Task Spec 格式](rules/TASKSPEC.md) 由 AI 按需读取并适配。jxcheck 的 task/verify/finish 不会创建 Goal、定时或 Heartbeat；调用宿主机制后在运行记录保存真实标识与核验状态。本次不新增 CLI 模式参数。
