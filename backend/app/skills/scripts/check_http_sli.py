#!/usr/bin/env python3
"""
简单 HTTP SLI 检测脚本:
- 可用性: 成功率
- 性能: p50/p95/p99 延迟
"""

from __future__ import annotations

import argparse
import statistics
import time
from typing import List

import requests


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    d0 = s[f] * (c - k)
    d1 = s[c] * (k - f)
    return d0 + d1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--count", type=int, default=30, help="请求次数")
    parser.add_argument("--timeout", type=float, default=3.0, help="单次超时秒数")
    args = parser.parse_args()

    latencies = []
    success = 0
    fail = 0

    for _ in range(args.count):
        start = time.perf_counter()
        try:
            resp = requests.get(args.url, timeout=args.timeout)
            cost_ms = (time.perf_counter() - start) * 1000
            latencies.append(cost_ms)
            if 200 <= resp.status_code < 400:
                success += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    total = success + fail
    success_rate = (success / total * 100) if total else 0.0

    print(f"URL: {args.url}")
    print(f"Total: {total}, Success: {success}, Fail: {fail}, SuccessRate: {success_rate:.2f}%")
    if latencies:
        print(
            "Latency(ms): "
            f"min={min(latencies):.2f}, avg={statistics.mean(latencies):.2f}, "
            f"p50={percentile(latencies, 0.50):.2f}, "
            f"p95={percentile(latencies, 0.95):.2f}, "
            f"p99={percentile(latencies, 0.99):.2f}, max={max(latencies):.2f}"
        )


if __name__ == "__main__":
    main()
