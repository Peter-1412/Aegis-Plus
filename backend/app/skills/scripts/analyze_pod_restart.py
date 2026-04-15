#!/usr/bin/env python3
"""
分析 Kubernetes Pod 重启情况。
依赖:
- 本机可执行 kubectl
- 已配置好 context
"""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any


def run_cmd(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="aegis")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    raw = run_cmd(["kubectl", "get", "pods", "-n", args.namespace, "-o", "json"])
    data: dict[str, Any] = json.loads(raw)

    rows = []
    for item in data.get("items", []):
        name = item["metadata"]["name"]
        phase = item.get("status", {}).get("phase", "Unknown")
        restart = 0
        reasons = []
        for cs in item.get("status", {}).get("containerStatuses", []) or []:
            restart += int(cs.get("restartCount", 0))
            waiting = (cs.get("state", {}) or {}).get("waiting", {})
            if waiting and waiting.get("reason"):
                reasons.append(waiting["reason"])
        rows.append((name, phase, restart, ",".join(sorted(set(reasons)))))

    rows.sort(key=lambda x: x[2], reverse=True)
    print(f"Namespace: {args.namespace}")
    print("name\tphase\trestarts\treasons")
    for row in rows[: args.top]:
        print(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}")


if __name__ == "__main__":
    main()
