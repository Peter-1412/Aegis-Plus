# 技能：常见故障 Playbook

## 1. Pod 持续重启（CrashLoopBackOff）
### 先做什么
- `kubectl get pods -A | grep -E "CrashLoopBackOff|Error"`
- `kubectl describe pod <pod> -n <ns>`
- `kubectl logs <pod> -n <ns> --previous`

### 重点看什么
- 启动参数错误、配置缺失、依赖不可达、探针失败。
- 是否在最近发布后开始重启。

### 常见根因
- 环境变量缺失。
- 连接串/密钥错误。
- 资源限制太低导致 OOMKill。

## 2. 服务接口超时/高延迟
### 先做什么
- 查看入口网关 5xx、timeout、p95/p99。
- 查看应用线程池、数据库连接池是否耗尽。
- 查看下游接口响应时间是否突增。

### 常见根因
- 突发流量导致饱和。
- 慢 SQL 或锁等待。
- 下游服务抖动。

## 3. 节点 NotReady
### 先做什么
- `kubectl get nodes`
- `kubectl describe node <node>`
- 检查 kubelet、容器运行时、磁盘压力、网络状态。

### 常见根因
- 节点磁盘打满。
- CNI 异常。
- kubelet 进程故障。

## 4. 镜像拉取失败（ImagePullBackOff）
### 先做什么
- `kubectl describe pod <pod> -n <ns>` 看 Events。
- 验证镜像地址、tag、镜像仓库凭证。

### 常见根因
- tag 不存在。
- 仓库鉴权失败。
- DNS/网络访问仓库失败。

## 5. 数据库连接暴涨
### 先做什么
- 检查应用连接池配置和活跃连接数。
- 检查慢查询和长事务。

### 常见根因
- 连接泄漏。
- 未命中索引导致慢 SQL 堆积。
- 下游故障触发重试风暴。
