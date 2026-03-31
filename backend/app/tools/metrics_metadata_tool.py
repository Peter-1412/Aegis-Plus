from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import tool


_META_CACHE: dict | None = None
_METRICS_CACHE: list[dict] | None = None
_PATHS_CACHE: list[str] | None = None


def _candidate_paths() -> list[Path]:
    here = Path(__file__).resolve()
    # In Docker: /app/app/tools/metrics_metadata_tool.py
    # Data dir: /app/app/data/
    app_dir = here.parent.parent
    
    candidates = [
        app_dir / "data" / "my_cluster_metadata.json",
        app_dir / "data" / "metrics_metadata.json",
    ]
    return candidates


def _load_metadata() -> tuple[dict | None, list[dict] | None, list[str]]:
    global _META_CACHE, _METRICS_CACHE, _PATHS_CACHE
    if _META_CACHE is not None and _METRICS_CACHE is not None and _PATHS_CACHE is not None:
        return _META_CACHE, _METRICS_CACHE, _PATHS_CACHE
    paths = _candidate_paths()
    _PATHS_CACHE = [str(p) for p in paths]
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("metrics metadata read failed: %s, path=%s", exc, path)
            continue
        metrics: list[dict] = []
        for category in (data.get("job_categories") or {}).values():
            for item in category.get("metrics") or []:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                metrics.append(
                    {
                        "name": name,
                        "job": item.get("job") or "",
                        "label_keys": item.get("label_keys") or [],
                        "description": item.get("description") or "",
                    }
                )
        _META_CACHE = {
            "export_time": data.get("export_time"),
            "prometheus_url": data.get("prometheus_url"),
            "total_metrics": data.get("total_metrics") or len(metrics),
        }
        _METRICS_CACHE = metrics
        return _META_CACHE, _METRICS_CACHE, _PATHS_CACHE
    return None, None, _PATHS_CACHE


@tool(
    "metrics_metadata_lookup",
    description="查询集群指标元信息（来源于 my_cluster_metadata.json）。可按关键字或 job 过滤，返回指标名与标签键。",
)
async def metrics_metadata_lookup(keyword: str | None = None, job: str | None = None, limit: int = 200) -> dict:
    meta, metrics, paths = _load_metadata()
    if metrics is None or meta is None:
        return {
            "error": "metrics_metadata_not_found",
            "message": "未找到指标元信息文件",
            "searched_paths": paths or [],
        }
    keyword_norm = (keyword or "").strip().lower()
    job_norm = (job or "").strip().lower()
    filtered: list[dict] = []
    for item in metrics:
        name = str(item.get("name") or "")
        desc = str(item.get("description") or "")
        job_val = str(item.get("job") or "")
        if keyword_norm and keyword_norm not in name.lower() and keyword_norm not in desc.lower():
            continue
        if job_norm and job_norm != job_val.lower():
            continue
        filtered.append(item)
    safe_limit = max(1, min(int(limit or 200), 500))
    return {
        "export_time": meta.get("export_time"),
        "prometheus_url": meta.get("prometheus_url"),
        "total_metrics": meta.get("total_metrics"),
        "matched": len(filtered),
        "metrics": filtered[:safe_limit],
    }
