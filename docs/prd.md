# 产品需求文档 (PRD)

## 1. 产品概述

Aegis 是一个专为 Kubernetes 集群设计的智能运维（AIOps）平台。它拥有一个现代化的 Web 控制台，并且原生集成了飞书机器人，通过 LangGraph 驱动的 AI Agent 以纯只读的方式对接 Prometheus、Loki、Jaeger 等可观测性组件，帮助运维人员（SRE）在群聊或 Web 界面中快速诊断故障根因。

**大一统架构更新**：系统现已完成前后端合并，提供开箱即用的“前端 (React) + 后端 (FastAPI)”极简部署体验。

## 2. 目标用户

- **SRE / 运维工程师**：日常处理集群告警，需要快速定位问题。
- **研发工程师**：应用出现异常时，通过机器人或 Web 界面自助查询日志和调用链，减少跨部门沟通成本。

## 3. 核心功能需求

### 3.1 飞书机器人交互 (ChatOps)
- **告警通知**：接收 Alertmanager Webhook，自动格式化并发送至指定群组，@ 对应值班人员。
- **自然语言问答**：支持用户在群内 @ 机器人并提问（如：“查一下 order-service 为什么 502”）。
- **模型切换**：用户可以通过命令指定大模型（如 `@AegisBot qwen ...` 或 `@AegisBot doubao ...`）。
- **异步响应**：请求发出后机器人先回复“收到”，分析完成后再将详细报告推送回群内。

### 3.2 Web 控制台交互
- **现代化 IDE 体验**：与主流 AI IDE（如 Trae, Cursor）一致的左侧历史会话、右侧对话流式界面。
- **结构化记忆**：每一轮对话不仅展示最终的文本结论，还会将 Agent 的**完整思考过程（Thought）、工具调用（Action）、日志结果（Observation）**通过手风琴组件或卡片的形式展示出来。
- **状态流转可视化**：直观展示 LangGraph 工作流在“生成计划”、“执行步骤”、“挂起等待”时的不同状态。

### 3.3 故障分析核心 (LangGraph 双模式架构)
- **智能分类**：系统能自动判断用户的意图，区分是简单的单一查询，还是需要复杂的多步排查。
- **ReAct 模式**：对简单查询直接调用工具，快速响应。
- **Plan-and-Execute 模式**：
  - 生成详细的排查计划并展示给用户。
  - 自动逐条执行计划，并在失败时自动重新规划（Re-plan）。
- **高危操作阻断 (Human-in-the-loop)**：
  - 在遇到包含诸如“重启(restart)”、“删除(delete)”、“缩容(scale)”等高危指令时，系统必须挂起（Interrupt）。
  - 通过飞书或 Web 界面提示用户：“检测到高危操作，是否继续执行？”。用户确认后，状态机恢复执行。

### 3.4 工具集 (Tools)
- **PromQL 执行器**：支持自然语言转 PromQL 并获取指标。
- **Loki 日志提取器**：根据服务名和时间范围获取报错日志。
- **Jaeger 链路查询器**：查询指定服务的异常 Trace。
- **K8s 发现工具**：查询 Namespace、Pod 事件、Yaml 配置等。

### 3.5 纯只读约束
- 系统的工具实现和 Prompt 必须严格限制 Agent 只能执行**读操作**（GET/List），不能提供任何写入/修改的工具（无 DELETE/POST/PUT）。

## 4. 部署与配置需求
- **单体服务**：提供一个统一的 Docker 镜像，内置 FastAPI 后端和编译好的 React 静态资源。
- **环境变量驱动**：支持通过 `LOKI_BASE_URL`、`PROMETHEUS_BASE_URL`、`DOUBAO_API_KEY` 等环境变量快速配置外部依赖。
- **SQLite 零依赖存储**：默认使用本地 SQLite（`aegis.db`）存储用户数据、聊天记录和 LangGraph 的 Checkpoint 状态，降低部署门槛。

---

# PRD: Aegis Ops Agent (Feishu Version)

## 1. Background and Objectives

### 1.1 Background

The Kubernetes cluster has already deployed observability components such as Prometheus, Loki, Jaeger, Grafana, and Promtail, but:

- Alert information is scattered across Alertmanager and various dashboards, with high correlation cost;
- When incidents occur, SREs need to switch between multiple tools to execute PromQL / LogQL / Trace queries;
- Frontline operations engineers are not familiar enough with underlying metrics and log formats, limiting troubleshooting efficiency.

The goal is to introduce an SRE-oriented intelligent Ops Agent that aggregates multi-source observability ability data "into Feishu groups", enabling operations to complete 80% of root cause localization work within chat window.

### 1.2 Objectives

- Provide a **read-only** Ops Agent:
  - Can only call query interfaces of Prometheus / Loki / Jaeger;
  - Cannot execute any changes or operations commands.
- Deep integration with Feishu Bot:
  - Support Alertmanager alert automatic forwarding to Feishu groups;
  - Support natural language questioning in group chats and trigger Ops analysis.
- Output structured Ops results:
  - Ranked root cause candidate list (including subjective probabilities);
  - Corresponding key metrics / logs / trace evidence;
  - Follow-up troubleshooting and remediation suggestions oriented towards operations engineers.

## 2. Roles and Use Cases

### 2.1 Roles

- SRE / Operations Engineer: Frontline incident troubleshooting and response personnel.
- Platform Engineer: Responsible for deployment and maintenance of Aegis Ops Agent.
- LLM Provider: Ark / Other OpenAI protocol compatible models.

### 2.2 Use Cases

#### Scenario A: Alert-Driven Passive Ops

1. A service anomaly occurs in cluster (error rate increase, latency jitter, node anomaly, etc.).
2. Prometheus triggers alert rules, Alertmanager sends Webhook to Aegis.
3. Aegis @mentions all in Feishu alert group, summarizes and displays key information.
4. On-duty SRE replies in the group "@bot help me check of root cause of this 502", triggering Ops workflow.
5. Agent calls metrics/logs/trace tools for analysis, replies with a structured Ops result message listing 1~3 most likely root causes and follow-up suggestions.

#### Scenario B: Proactive Health Check / Retrospective Analysis

1. SRE inputs in Feishu group:
   - "@bot help me check of root cause of order timeout last night at 23:00"
2. Agent performs historical retrospective using specified time window.
3. Returns structured Ops result similar to Scenario A, used for post-incident review.

## 3. Functional Requirements

### 3.1 Feishu Integration

1. Support enterprise self-built application mode, using `app_id` and `app_secret` to obtain `tenant_access_token`.
2. Support event subscription (long connection mode):
   - `im.message.receive_v1`: Receive messages where bot is @mentioned in group chats.
3. Support sending text messages to specified `chat_id` via OpenAPI `im/v1/messages`.
4. Support configuration:
   - `FEISHU_DEFAULT_CHAT_ID`: Default alert/Ops result push group.

### 3.2 Alertmanager Integration

1. Provide HTTP endpoint `/alertmanager/webhook`, compatible with standard Alertmanager Webhook format.
2. Support merging multiple alerts into a single Feishu message:
   - Display `alertname`, `severity`, `instance`/`pod`/`service` and other key labels;
   - Display `summary` or `description` annotations;
   - Message header defaults to include `@all`.
3. Webhook processing logic should return quickly to avoid blocking Alertmanager.

### 3.3 Ops Agent Capabilities

1. Entry Points:
   - Feishu message events: Automatically use text as `description`, using last 15 minutes as time window.
   - HTTP API: `/api/ops/analyze` and `/api/ops/analyze/stream`, supporting direct calls from external systems.
2. Tool Set (Read-Only):
   - `prometheus_query_range`: Query specified PromQL time series within time range.
   - `loki_collect_evidence`: Extract log lines containing error keywords/status codes from Loki, aggregated by service priority.
   - `jaeger_query_traces`: Query representative trace summary information for specified service within time range from Jaeger.
   - `metrics_metadata_lookup`: Query cluster metric metadata (e.g., metric names, labels) to avoid fabricating non-existent metrics.
3. Output Structure:
   - `summary`: Chinese natural language summary.
   - `ranked_root_causes`:
     - Contains `rank`, `service`, `probability`, `description`, `key_indicators`, `key_logs`.
     - Maximum 3 entries.
   - `next_actions`: Follow-up suggestions.
4. Agent Behavior Constraints & Interactions:
   - Adopts a LangGraph dual-mode architecture, automatically judging task complexity:
     - Simple tasks: Direct ReAct execution to return results.
     - Complex tasks: Generates a step-by-step troubleshooting plan and proactively displays the plan in Feishu.
   - **High-Risk Operation Interruption**: Before executing steps containing dangerous commands like restart, delete, or scale, the Agent automatically pauses and requests confirmation in Feishu. Execution resumes only after the user replies with consent.
   - System Prompt explicitly prohibits destructive change actions without confirmation.
   - Interaction state is persisted using SQLite Checkpointer, supporting resumption even across service restarts.

### 3.4 Security and Permissions

1. All access to Prometheus / Loki / Jaeger is completed via HTTP read-only interfaces.
2. Do not mount kubeconfig / cloud provider AK/SK and other high-privilege credentials in containers.
3. Feishu `app_secret`, `verification_token` and LLM `API_KEY` are all stored in K8s Secret.
4. Provide read-only HTTP APIs, do not expose any write operations.

## 4. Non-Functional Requirements

### 4.1 Performance

- Single Ops analysis should be controlled within 30~60 seconds by default.
- Tool call concurrency is controlled by LangChain Agent strategy, can add rate limiting in future iterations if necessary.

### 4.2 Availability

- ops-service should have at least 2 replicas in production environment, supporting rolling upgrades.
- Internal errors must not affect Alertmanager and Feishu normal operation (should return 200/simple error information even on failure).

### 4.3 Observability

- ops-service should output structured logs itself, facilitating retrieval in Loki.
- Key paths add simple metrics (such as request duration, LLM call failure count) can be supplemented in future iterations.

## 5. Deliverables

1. `ops-service` source code (Python + FastAPI + LangChain).
2. Directly buildable Dockerfile.
3. Kubernetes deployment manifests:
   - Namespace / ConfigMap / Secret / Deployment / Service.
4. Documentation:
   - README (Chinese and English)
   - `docs/api.md`: API documentation
   - `docs/architecture.md`: Architecture documentation
   - `docs/user-manual.md`: User manual (operations-oriented)

## 6. Future Iteration Directions (Non-Current Phase)

- Support multi-tenant, multi-cluster scenarios (isolated via labels/namespaces).
- Integration with more observability backends (Tempo / OpenSearch / ClickClickHouse, etc.).
- Introduce rule engine and knowledge base to structure and沉淀 experience-based SRE rules.
