# Aegis 架构设计

Aegis 已经升级为“大一统”全栈架构，整个系统由纯 React 前端和纯 Python 后端构成，极大地简化了部署与维护成本。

## 1. 整体架构概览

```mermaid
graph TD
    subgraph K8s Cluster
        Frontend[Web 前端 - React]
        Backend[Backend 服务 - FastAPI]
        SQLite[(SQLite 数据库)]
        
        Frontend -->|HTTP / WebSocket| Backend
        Backend -->|SQLModel| SQLite
        
        subgraph Agent Core (LangGraph)
            Router{路由: 复杂 vs 简单}
            PlanNode[Plan 节点]
            ReActNode[ReAct 执行节点]
            Router --> PlanNode
            Router --> ReActNode
        end
        
        Backend --> Agent Core
    end
    
    subgraph Observability
        Prometheus
        Loki
        Jaeger
    end
    
    subgraph Feishu
        Bot[飞书机器人]
    end
    
    Agent Core -->|查询指标| Prometheus
    Agent Core -->|查询日志| Loki
    Agent Core -->|查询链路| Jaeger
    
    Bot <-->|WebSocket| Backend
```

## 2. 核心模块说明

### 2.1 Web 前端 (frontend)
- **技术栈**：React + TypeScript + Vite + Ant Design
- **职责**：
  - 提供现代化的智能运维工作台界面。
  - 管理运维工具导航（Tools）。
  - 提供与 Aegis 机器人的对话流式界面，支持解析复杂 Markdown 与结构化运维记录展示。

### 2.2 Backend 服务 (backend)
- **技术栈**：Python + FastAPI + SQLModel (SQLite) + LangGraph
- **职责**：
  - **静态资源托管**：编译后的前端代码由 FastAPI 直接提供服务。
  - **用户与鉴权**：处理用户的注册、登录（JWT），区分 Admin 和 Developer 权限。
  - **业务 API**：提供工具管理、Dashboard 数据统计等 CRUD 接口。
  - **飞书集成**：通过 WebSocket 长连接（lark-oapi）接收飞书消息，并将 Agent 的分析结果异步推回飞书群聊。
  - **Agent 入口**：暴露流式聊天接口 (`/api/agent/chat/stream`) 给前端，将 LangGraph 的运行事件实时推送给前端。

### 2.3 Agent Core (LangGraph)
Aegis 的灵魂所在，采用 LangGraph 实现了双模式动态切换的架构：
- **ReAct 模式**：用于快速、单步的查询。
- **Plan-and-Execute 模式**：对于复杂的故障排查，先规划全局步骤，再逐步执行，并支持动态重规划。
- **持久化与中断**：利用 `AsyncSqliteSaver` 记录每一步状态，支持在执行高危工具前挂起，等待人工审批。

## 3. 时序流程 / Sequence Flow

### 3.1 Alertmanager 告警 → 飞书通知

(流程保持不变，参考 PRD)

### 3.2 飞书群聊 @机器人 → 运维分析

1.  **用户提问**：SRE 在群内 @AegisBot "帮我看下订单服务为什么慢"。
2.  **事件分发**：飞书长连接网关收到消息，转发给 `OpsAgent`。
3.  **服务发现与元数据检索 (Optional)**：Agent 可能首先调用 `list_services` 确认服务是否存在，或调用 `metrics_metadata_lookup` 确认具体指标 Key。
4.  **指标分析**：Agent 调用 `prometheus_query_range` 查询延迟和错误率。
5.  **日志佐证**：发现异常时间点后，调用 `loki_collect_evidence` 查询该时间段的 Error 日志。
6.  **结果汇总**：Agent 综合指标与日志，生成根因分析报告。
7.  **消息推送**：`ops-service` 将报告发送回飞书群。

## 4. 配置与部署 / Configuration & Deployment

(保持不变，参考原文档)
