# 集群日志查询指南 (LogQL)

本文档专门针对当前集群环境编写，指导如何使用 Grafana/Loki 查询各服务的日志。

## 1. 核心查询维度 (Labels)

在我们的集群中，Promtail 配置了以下四个核心标签用于筛选日志。查询时**必须**至少包含一个标签选择器。

| 标签名 | 说明 | 示例值 |
| :--- | :--- | :--- |
| `namespace` | Kubernetes 命名空间 | `monitoring`, `storage`, `ocr`, `aegis` |
| `app` | 服务名称 (来源于 Pod 的 `app` 标签) | `loki`, `mysql`, `ocr-webservice` |
| `pod` | Pod 实例名称 | `loki-57d4d658f6-xrk9w` |
| `container` | 容器名称 | `loki`, `promtail` |

> **注意**：只有在 Pod 定义中包含 `app` 标签的服务，才能使用 `app="..."` 进行快速查询。

---

## 2. 常用服务查询速查表

以下是集群中已部署服务的标准查询语句。直接复制到 Grafana 的 Explore 页面即可使用。

### 监控系统 (Monitoring)
| 服务 | LogQL 查询语句 |
| :--- | :--- |
| **Loki** | `{namespace="monitoring", app="loki"}` |
| **Promtail** | `{namespace="monitoring", app="promtail"}` |
| **Grafana** | `{namespace="monitoring", app="grafana"}` |
| **Prometheus** | `{namespace="monitoring", app="prometheus"}` |

### 存储服务 (Storage)
| 服务 | LogQL 查询语句 |
| :--- | :--- |
| **MySQL** | `{namespace="storage", app="mysql"}` |
| **MinIO** | `{namespace="storage", app="minio"}` |
| **RabbitMQ** | `{namespace="storage", app="rabbitmq"}` |

### 业务服务
| 服务 | LogQL 查询语句 |
| :--- | :--- |
| **OCR 服务** | `{namespace="ocr", app="ocr-webservice"}` |
| **Ops Service** | `{namespace="aegis", app="ops-service"}` |
| **DNS Test** | `{namespace="aegis", run="dns-test"}` (注意：该 Pod 使用 `run` 标签而非 `app`，可能无法直接用 `app` 标签查询，建议用 `{namespace="aegis", pod=~"dns-test.*"}`) |

### 系统组件 (Kube-System)
| 服务 | LogQL 查询语句 |
| :--- | :--- |
| **CoreDNS** | `{namespace="kube-system", k8s_app="kube-dns"}` (需确认 Promtail 是否提取了 `k8s-app` 标签，若无则用 `{namespace="kube-system", pod=~"coredns.*"}`) |
| **Calico** | `{namespace="kube-system", pod=~"calico-node.*"}` |

### 特殊说明：Chaos Mesh
Chaos Mesh 组件使用 `app.kubernetes.io/name` 等标签，而我们的 Promtail 配置目前主要提取 `app` 标签。因此建议使用 **Namespace + Pod正则** 进行查询：
```logql
{namespace="chaos-mesh", pod=~"chaos-.*"}
```

---

## 3. 实战查询技巧

### 3.1 查找错误日志
查询 **OCR 服务** 中包含 "Error" 或 "Exception" 的日志：
```logql
{namespace="ocr", app="ocr-webservice"} |= "Error"
# 或者使用正则同时匹配 Error 和 Exception (不区分大小写)
{namespace="ocr", app="ocr-webservice"} |~ "(?i)(error|exception)"
```

### 3.2 排除干扰日志
查询 **MySQL** 日志，但排除健康检查 (Health Check) 的记录：
```logql
{namespace="storage", app="mysql"} != "Health Check"
```

### 3.3 统计日志速率 (QPS)
查看 **Ops Service** 最近 1 小时的日志生成速率：
```logql
rate({namespace="aegis", app="ops-service"}[1m])
```

### 3.4 查看特定 Pod 的日志
如果你知道具体的 Pod 名字（例如 `ops-service-688999fdfb-kmfbt`），可以直接指定：
```logql
{pod="ops-service-688999fdfb-kmfbt"}
```

## 4. 常见问题

**Q: 为什么我查不到某些 Pod 的日志？**
A: 请检查该 Pod 是否有 `app` 标签。我们的 Promtail 配置主要依赖 `app` 标签进行索引。如果 Pod 没有 `app` 标签（例如使用 `run` 或 `k8s-app`），请尝试使用 `{namespace="...", pod=~"pod-name-prefix.*"}` 这种方式查询。

**Q: 日志时间对不上？**
A: Loki 默认使用日志采集的时间。如果应用日志本身包含时间戳，但与 Loki 显示的时间偏差很大，可能需要检查节点时间同步情况。
