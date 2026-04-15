#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   bash check_k8s_core_health.sh [context]

CTX="${1:-}"
if [[ -n "${CTX}" ]]; then
  kubectl config use-context "${CTX}" >/dev/null
fi

echo "== [1/4] Cluster nodes =="
kubectl get nodes -o wide
echo

echo "== [2/4] Non-running pods in key namespaces =="
for ns in kube-system monitoring aegis default; do
  echo "--- namespace: ${ns} ---"
  kubectl get pods -n "${ns}" --no-headers | awk '$3 != "Running" && $3 != "Completed" {print}'
done
echo

echo "== [3/4] Recent warning events =="
kubectl get events -A --field-selector type=Warning --sort-by=.lastTimestamp | tail -n 40
echo

echo "== [4/4] Top usage =="
kubectl top nodes || true
kubectl top pods -A --sort-by=cpu | head -n 20 || true

echo "Health check done."
