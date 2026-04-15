#!/usr/bin/env bash
set -euo pipefail

# 用法:
#   bash collect_k8s_diagnostics.sh <namespace> <pod> [container]

NS="${1:?namespace is required}"
POD="${2:?pod is required}"
CONTAINER="${3:-}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="diag_${NS}_${POD}_${TS}"

mkdir -p "${OUT_DIR}"

echo "Collecting diagnostics into ${OUT_DIR}"
kubectl get pod "${POD}" -n "${NS}" -o yaml > "${OUT_DIR}/pod.yaml"
kubectl describe pod "${POD}" -n "${NS}" > "${OUT_DIR}/pod.describe.txt"
kubectl get events -n "${NS}" --sort-by=.lastTimestamp > "${OUT_DIR}/events.txt"

if [[ -n "${CONTAINER}" ]]; then
  kubectl logs "${POD}" -n "${NS}" -c "${CONTAINER}" --tail=2000 > "${OUT_DIR}/logs.current.txt" || true
  kubectl logs "${POD}" -n "${NS}" -c "${CONTAINER}" --previous --tail=2000 > "${OUT_DIR}/logs.previous.txt" || true
else
  kubectl logs "${POD}" -n "${NS}" --all-containers=true --tail=2000 > "${OUT_DIR}/logs.current.txt" || true
  kubectl logs "${POD}" -n "${NS}" --all-containers=true --previous --tail=2000 > "${OUT_DIR}/logs.previous.txt" || true
fi

echo "Done. Files:"
ls -1 "${OUT_DIR}"
