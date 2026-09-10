# 配置与证据合同 v1

维护者：框架维护者；实现唯一入口 jxcheck/core.py。合同改变同时更新实现、测试、示例、来源版本及迁移说明。

## 项目配置 .project/project.json

JSON 对象：schema=1、runner=0.1.0、rule_version=2026-09-10-r5；requirements 为不重复需求 ID 数组；environment_id/build_id 为项目实际非敏感标识。

bindings 必含 entry/state/map/history/maintenance。每项为 path、owner、read_when、update_when、verify；path 是现有项目文件的相对路径，允许多角色合并同一文件。不得用占位文档冒充已完成业务事实。环境说明按实际领域绑定，不强制 .env。

checks 为非空数组，每项包含：

| 字段 | 约束 |
|---|---|
| id | 稳定、唯一，字母数字下划线连字符 |
| requirements | 关联需求 ID；每条项目需求至少一个必需检查覆盖 |
| expected / owner / steps / evidence | 可观察期望、维护者、操作、证据种类；不能只写“通过” |
| required | JSON boolean；必需项 skip/error/not_run 不能通过 |
| kind | junit、json、document、manual |
| argv / cwd | 自动检查的参数数组及项目内工作目录；不启用 shell；{python} 是当前 Python |
| report | 自动检查的 {run}/独立文件名，旧报告不会复用 |
| expected_cases | junit 必须保留的 testcase name 数组；删除/重命名会拒绝，测试含义仍需审阅 |
| assertions | json 顶层键到严格类型/期望值的映射；不是匹配 stdout 的 PASS 字符串 |
| attachments | 可选 {run}/文件数组；要求非空实际文件且后续摘要一致；截图存在≠布局正确 |
| timeout | 自动检查秒数，大于零且至多 3600，默认 60 |
| documents / equal | document 的本地 Markdown 文件链接检查、两组 文件.json#顶层键 的值一致断言 |

`{root}`、`{run}`、`{python}` 由运行器替换。每个检查的 report 应使用不同文件；输出/截图必须属于本次 run。自动脚本应能重复运行且只写批准产物，不在检查中修改业务代码。命令运行权限与父进程相同，不构成沙箱。

JUnit 读取真实 testcase、failure、error、skipped；零测试、任何错误/失败、必需跳过或缺少受保护测试均阻止完成。项目已有 pytest 等可输出 JUnit；未支持的格式不得仅凭退出码适配为成功。

document 仅处理本地文件存在和明确 JSON 字段相等。链接目标语义、章节存在、教学掌握等不由这个适配器自动证明，重要语义应绑定 manual 或更具体检查。

## 安装清单及锁

manifest：schema=1，files 是“项目相对路径 → UTF-8 完整文本”的映射。清单由 AI 根据当前项目准备，既有文件先保留/合并内容并审阅；执行器不自动理解和特异化业务。init 拒绝覆盖不同内容；upgrade 只自动替换上次安装摘要仍匹配的受管文件。不会自动删除旧文件、初始化 Git 或更改权限。

.project/framework.lock.json 保存来源清单摘要、规则/执行器版本、执行器源码摘要及受管文件摘要。doctor 校验运行器锁、实际绑定和需求覆盖；verify 的 task 冻结整个 project.json，避免检查中途变更。

## 任务与结果

.project/tasks/<ID>.json 保存五项规格摘要、project.json 摘要、基线文件摘要、允许写集及记录时间。用 fnmatch 相对路径模式匹配范围，`src/*` 覆盖其下目录；范围决定可检查的差异，不提供操作系统写权限限制。任务记录本身从该任务差异检查豁免，其他控制文件不豁免。不同任务共享项目文件时须顺序调整或隔离工作树。

verify 持有项目级独占锁；每次有唯一 run ID。开始即将 latest 标 running，结束原子写 receipt 和 complete 指针。finish 只接受完整且摘要一致的当前记录，验证期间/中断后不复用旧成功。

receipt 保存检查状态、退出码/计数、执行时间、运行时、任务和项目摘要、源码快照、附件摘要及局限。源码内容变化、执行器变化、验证期间变化均使证据过期；删除/替换附件导致阻塞。

状态：ready / pending_manual / blocked / stale。原始检查状态：pass / fail / skip / error / not_run。人工项不接受 user_said、PASS、VERIFIED 作为身份凭证。

固定排除：.git/.artifacts/__pycache__/.venv/node_modules、.pyc、.env 及 .env.*（除 .env.example）、credentials.json/secrets.json、.pem/.key/.pfx；排除项不在源码验证承诺内，不允许把业务源码移入这些目录规避验证。不能保证识别任意命名的秘密，项目负责秘密隔离。依赖版本、设备和外部环境由显式标识与项目检查补充。
