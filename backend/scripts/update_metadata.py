import json
import logging
import os
import requests
from datetime import datetime, timezone
from kubernetes import client, config

# 配置 Prometheus 地址
PROMETHEUS_URL = os.getenv("PROMETHEUS_BASE_URL", "http://prometheus.monitoring.svc.cluster.local:9090")
# ConfigMap 配置
CONFIG_MAP_NAME = os.getenv("CONFIG_MAP_NAME", "aegis-metadata")
CONFIG_MAP_NAMESPACE = os.getenv("CONFIG_MAP_NAMESPACE", "aegis")
CONFIG_MAP_KEY = "my_cluster_metadata.json"

logging.basicConfig(level=logging.INFO)

def fetch_metadata():
    """从 Prometheus 获取所有 Target 的元数据"""
    url = f"{PROMETHEUS_URL}/api/v1/targets/metadata"
    try:
        logging.info(f"Connecting to Prometheus: {url}")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise ValueError(f"Prometheus API error: {data.get('error')}")
        return data.get("data", [])
    except Exception as e:
        logging.error(f"Failed to fetch metadata: {e}")
        return []

def process_metadata(raw_data):
    """处理原始元数据，按 Job 分组"""
    metrics_by_job = {}
    
    for item in raw_data:
        metric_name = item.get("metric")
        help_text = item.get("help")
        target_metadata = item.get("target", {})
        job = target_metadata.get("job", "unknown")
        
        # 过滤掉一些系统内部指标，只保留业务相关的
        # 这里可以根据实际情况调整过滤规则
        if not metric_name or metric_name.startswith("go_") or metric_name.startswith("process_"):
            continue
            
        if job not in metrics_by_job:
            metrics_by_job[job] = []
            
        # 避免重复
        exists = any(m["name"] == metric_name for m in metrics_by_job[job])
        if not exists:
            metrics_by_job[job].append({
                "name": metric_name,
                "job": job,
                "description": help_text,
                "label_keys": [] # Prometheus metadata API 通常不直接返回 label keys，需要额外查询 series
            })
            
    return metrics_by_job

def update_configmap(json_data):
    """更新 Kubernetes ConfigMap"""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except Exception:
            logging.error("Failed to load k8s config")
            return

    v1 = client.CoreV1Api()
    
    # 准备数据
    json_str = json.dumps(json_data, indent=2, ensure_ascii=False)
    
    try:
        # 尝试获取现有的 ConfigMap
        cm = v1.read_namespaced_config_map(name=CONFIG_MAP_NAME, namespace=CONFIG_MAP_NAMESPACE)
        cm.data[CONFIG_MAP_KEY] = json_str
        v1.replace_namespaced_config_map(name=CONFIG_MAP_NAME, namespace=CONFIG_MAP_NAMESPACE, body=cm)
        logging.info(f"Updated ConfigMap {CONFIG_MAP_NAME} in {CONFIG_MAP_NAMESPACE}")
    except client.exceptions.ApiException as e:
        if e.status == 404:
            # 如果不存在，创建新的
            metadata = client.V1ObjectMeta(name=CONFIG_MAP_NAME, namespace=CONFIG_MAP_NAMESPACE)
            cm = client.V1ConfigMap(metadata=metadata, data={CONFIG_MAP_KEY: json_str})
            v1.create_namespaced_config_map(namespace=CONFIG_MAP_NAMESPACE, body=cm)
            logging.info(f"Created ConfigMap {CONFIG_MAP_NAME} in {CONFIG_MAP_NAMESPACE}")
        else:
            logging.error(f"Failed to update ConfigMap: {e}")

def save_json(metrics_by_job):
    """保存为 Agent 可读的 JSON 格式并更新 ConfigMap"""
    output_data = {
        "export_time": datetime.now(timezone.utc).isoformat(),
        "prometheus_url": PROMETHEUS_URL,
        "job_categories": {
            "auto_discovered": {
                "metrics": []
            }
        }
    }
    
    # 展平结构
    all_metrics = []
    for job, metrics in metrics_by_job.items():
        all_metrics.extend(metrics)
        
    output_data["job_categories"]["auto_discovered"]["metrics"] = all_metrics
    output_data["total_metrics"] = len(all_metrics)
    
    update_configmap(output_data)

if __name__ == "__main__":
    logging.info("Starting metadata update...")
    raw = fetch_metadata()
    if raw:
        processed = process_metadata(raw)
        save_json(processed)
    else:
        logging.warning("No metadata fetched.")
