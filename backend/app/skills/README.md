# Aegis 运维 SKILL 索引

## 为什么拆分而不是一个大手册
- 推荐拆分：`总索引 + 场景手册 + 可执行脚本`。
- 原因是检索更快、更新更安全、复用率更高，也更适合 Agent 按场景动态加载。
- 大而全手册适合人阅读，不适合 Agent 在排障时快速定位最小可执行步骤。

## 目录结构
- `daily_patrol.md`：每日巡检技能（已存在）。
- `ops_troubleshooting_manual.md`：通用排障思路与执行框架。
- `common_incident_playbook.md`：高频故障场景 Playbook。
- `scripts/check_k8s_core_health.sh`：K8s 核心健康快速体检。
- `scripts/collect_k8s_diagnostics.sh`：一键采集 Pod 诊断信息。
- `scripts/check_http_sli.py`：HTTP 可用性和延迟 SLI 检测。
- `scripts/analyze_pod_restart.py`：基于 `kubectl` 输出分析重启异常 Pod。

## 使用建议
- 先阅读 `ops_troubleshooting_manual.md`，建立统一思考框架。
- 再按故障类型查 `common_incident_playbook.md` 对应条目。
- 最后运行 `scripts/` 下脚本快速收集证据，避免拍脑袋操作。

## 约束
- 默认只读排障，除非明确审批，不执行变更类动作（删除、重启、扩缩容、回滚）。
- 输出结论必须附证据（命令输出、指标值、时间窗口）。
