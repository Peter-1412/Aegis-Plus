# 脚本快速上手

## 1) K8s 核心健康检查
```bash
bash backend/app/skills/scripts/check_k8s_core_health.sh
```

## 2) 一键采集 Pod 诊断包
```bash
bash backend/app/skills/scripts/collect_k8s_diagnostics.sh <namespace> <pod>
```

## 3) HTTP 可用性和延迟检测
```bash
python backend/app/skills/scripts/check_http_sli.py --url http://127.0.0.1:8000/healthz --count 30
```

## 4) 重启异常 Pod 分析
```bash
python backend/app/skills/scripts/analyze_pod_restart.py --namespace aegis --top 10
```

## 学习建议
- 每次排障都先输出时间窗口和影响范围。
- 每次结论都写出证据（命令输出、日志片段、指标值）。
- 先只读采证，再做变更动作。
