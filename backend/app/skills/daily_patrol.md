# 技能：Kubernetes 每日巡检 (Daily Patrol)

## 描述
本技能用于执行 Kubernetes 集群的全面健康检查。通过分析基础设施状态、核心服务健康度、告警历史及资源饱和度，生成一份结构化的运维日报。
目标用户是 SRE/运维工程师，旨在主动发现潜在风险。

## 输入参数
- 无需特定参数。上下文隐含在“每日巡检”或“健康检查”指令中。

## 工作流步骤 (Workflow Steps)

### 1. 基础设施健康检查 (Infrastructure Health)
**目标**：确保所有节点处于健康且可调度的状态。
- **执行动作**：
  1. 调用 `k8s_get_resource_yaml(resource_type="node", name="", namespace="")` 获取节点列表。
  2. 检查每个节点的 `status.conditions`，确认 `Type=Ready` 的状态必须为 `True`。
  3. 检查节点是否存在非预期的污点（`spec.taints`），例如 `NoSchedule`（排除 Master 节点）。
  4. **验证逻辑**：如果发现任何节点处于 `NotReady` 状态，必须记录节点名称及 `conditions` 中的 `Reason` 和 `Message`。

### 2. 核心命名空间巡检 (Core Workload Inspection)
**目标**：发现核心组件中的异常工作负载。
- **关注命名空间**：`kube-system`, `monitoring`, `aegis`, `storage`, `default`。
- **执行动作**：
  1. 调用 `list_services` 获取当前运行的服务概览。
  2. 针对上述命名空间，检查是否存在**非** `Running` 或 `Succeeded` 状态的 Pod。
  3. 重点排查以下状态：
     - `CrashLoopBackOff`：意味着应用反复崩溃。
     - `Pending`：意味着调度失败（资源不足或亲和性问题）。
     - `ImagePullBackOff`：意味着镜像拉取失败。
     - `Evicted`：意味着节点资源压力过大导致驱逐。
  4. **深挖**：如果发现异常 Pod，必须调用 `k8s_list_events(namespace=...)` 查询相关报错事件。

### 3. 告警历史分析 (Alert History)
**目标**：总结过去 24 小时内的严重告警。
- **执行动作**：
  1. 调用 `prometheus_query_range` 查询 `ALERTS{severity="critical", alertstate="firing"}`。
  2. 按 `alertname` 和 `instance` 进行聚合统计。
  3. **输出**：列出触发次数最多的前 3 个 Critical 告警。

### 4. 资源饱和度检查 (Resource Saturation)
**目标**：识别潜在的性能瓶颈。
- **执行动作**：
  1. 调用 `prometheus_query_range` 查询以下指标：
     - 集群整体 CPU 使用率：`sum(rate(container_cpu_usage_seconds_total[5m])) / sum(machine_cpu_cores) * 100`
     - 集群整体内存使用率：`sum(container_memory_working_set_bytes) / sum(machine_memory_bytes) * 100`
     - CPU 使用率最高的 Top 3 Pod。
     - 内存使用率最高的 Top 3 Pod。
  2. **阈值**：重点标记任何持续 15 分钟以上使用率超过 85% 的节点或组件。

### 5. 报告生成 (Report Generation)
**目标**：你必须严格遵守以下输出格式，将所有发现汇总成一份结构化的报告。
**关键规则**：
1. **不要**输出 JSON 格式，直接输出最终渲染好的富文本内容（作为 `summary` 字段的值）。
2. 必须包含“名称 | 状态 | 时间”的三列表格。
3. 状态列只能用 ✅ 或 ❌，不要写文字。
4. 如果有异常，必须在表格下方列出“详细异常说明”。

**强制参考模板**：

```text
【Aegis 每日巡检情况通报】

各位 SRE 同学：
    早上好！根据系统自动巡检程序运行结果，现将今日 Kubernetes 集群核心业务运行状况通报如下：

名称                状态       巡检时间
-----------------------------------------
[Node] worker-01    ✅         08:00
[Node] worker-02    ✅         08:00
[Node] master-01    ✅         08:00
[NS] kube-system    ✅         08:00
[NS] monitoring     ✅         08:00
[NS] aegis          ✅         08:00
[NS] storage        ❌         08:00
[Alert] 严重告警     ✅         08:00
-----------------------------------------

详细异常说明（若有）：
1. storage 命名空间下 minio-0 Pod 处于 CrashLoopBackOff 状态。
2. 发现 2 个 Critical 告警触发。

本次巡检结果 [正常/存在异常]，请相关人员留意。
若需进一步排查，请回复 "@AegisBot 帮我看下 xxx 的日志"。

巡检人：Aegis 智能助手
日期：{{current_date}}
```

## 约束条件 (Constraints)
- **只读原则**：严禁执行任何修改操作（如删除 Pod、驱逐节点等）。
- **证据导向**：报告中的每一个结论都必须有具体的指标数值或日志片段作为支撑。
