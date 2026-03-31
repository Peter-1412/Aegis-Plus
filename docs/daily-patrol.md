# 每日自动化巡检 (Daily Patrol)

Aegis Ops Agent 提供了基于 Kubernetes CronJob 的每日自动化巡检功能，能够每天定时对集群健康状态进行"体检"，并将报告推送到飞书群。

## 1. 巡检内容

Agent 会根据预设的 Prompt 自动执行以下检查（时间窗口：过去 1 小时）：

1.  **节点健康度**：检查所有 Node 是否处于 `Ready` 状态。
2.  **核心组件状态**：扫描 `kube-system`, `monitoring`, `aegis` 等关键命名空间，查找是否存在 `CrashLoopBackOff` 或 `Error` 状态的 Pod。
3.  **告警统计**：统计过去 1 小时内触发的 `Critical` 级别告警数量。
4.  **资源瓶颈**（可选，视 Agent 决策）：如果发现节点压力大，可能会顺带检查 CPU/Memory 使用率 top 的 Pod。

## 2. 输出格式

巡检结果将以**飞书富文本消息**的形式发送到配置的默认运维群 (`FEISHU_DEFAULT_CHAT_ID`)。

**消息示例**：

```text
【分析结果】
问题：【每日例行巡检】请对当前 Kubernetes 集群和关键节点进行健康检查...
结论：截止 08:00，集群整体状态健康。所有 6 个节点均处于 Ready 状态。核心命名空间无异常 Pod。过去 1 小时内无 Critical 告警触发。

后续建议：
1. 建议关注 worker-03 节点的内存使用率（目前 85%），虽未触发告警但呈上升趋势。
```

如果有异常：

```text
【分析结果】
...
结论：发现集群存在异常。worker-02 节点处于 NotReady 状态已持续 15 分钟。monitoring 命名空间下 prometheus-0 Pod 正在 CrashLoopBackOff。

可能原因：
1. worker-02 节点 kubelet 心跳丢失，可能由于系统负载过高或网络分区（服务：kubelet），概率≈0.9
2. prometheus-0 因 OOMKilled 重启，需检查内存配额（服务：prometheus），概率≈0.8

后续建议：
1. 登录 worker-02 检查系统日志（journalctl -u kubelet）。
2. 检查 Prometheus 内存配置并考虑扩容 Request/Limit。
```

## 3. 工作原理

整个巡检流程是**完全自动化**且**无状态**的：

1.  **触发 (CronJob)**：
    Kubernetes 内置的 CronJob 控制器在每天 **08:00** 创建一个临时的 `Patrol Pod`。
    
2.  **调用 (API Request)**：
    该 Pod 启动后，执行 `curl` 命令，向 `ops-service` 的 HTTP 接口发送分析请求。
    *   **Endpoint**: `POST http://ops-service.aegis:8002/api/ops/analyze`
    *   **Payload**:
        ```json
        {
          "description": "【每日例行巡检】...",
          "notify_chat_id": "default"  // <--- 关键参数
        }
        ```

3.  **分析 (Agent Execution)**：
    `ops-service` 收到请求后：
    *   识别 `notify_chat_id="default"`，读取环境变量中的 `FEISHU_DEFAULT_CHAT_ID`。
    *   启动 LangChain Agent，根据 `description` 调用 Prometheus/Loki 工具采集数据。
    *   生成 JSON 格式的分析报告。

4.  **推送 (Feishu Push)**：
    `ops-service` 在返回 HTTP 响应给 `curl` 的同时，异步调用飞书 OpenAPI，将渲染好的文本消息推送到指定群组。

## 4. 配置与修改

巡检任务定义在 `k8s/patrol-cronjob.yaml` 中。

### 修改巡检时间
修改 `spec.schedule` 字段（Cron 表达式）：
```yaml
schedule: "0 8 * * *"  # 每天 08:00
```

### 修改巡检内容
修改 `command` 中的 JSON `description` 字段。你可以用自然语言增加要求，例如："顺便帮我看看 MySQL 的连接数是否正常"。

### 手动触发巡检
如果你想立即执行一次巡检，无需等待定时时间：
```bash
kubectl create job --from=cronjob/aegis-daily-patrol manual-patrol-001 -n aegis
```
