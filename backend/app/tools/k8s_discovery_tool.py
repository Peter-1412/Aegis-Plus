from __future__ import annotations

from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from kubernetes import client, config
from pydantic import BaseModel, Field
import logging

_K8S_CLIENT_INITIALIZED = False

def _init_k8s_client():
    global _K8S_CLIENT_INITIALIZED
    if _K8S_CLIENT_INITIALIZED:
        return
    try:
        # 尝试加载集群内配置
        config.load_incluster_config()
        logging.info("Kubernetes in-cluster config loaded.")
        _K8S_CLIENT_INITIALIZED = True
    except config.ConfigException:
        try:
            # 尝试加载本地 kubeconfig
            config.load_kube_config()
            logging.info("Kubernetes kube-config loaded.")
            _K8S_CLIENT_INITIALIZED = True
        except Exception as e:
            logging.error(f"Failed to load Kubernetes config: {e}")

@tool(
    "list_services",
    description="列出当前 Kubernetes 集群中正在运行的服务列表。无需参数。返回服务名称、Namespace 及对应的 Pod 数量。",
)
def list_services() -> List[Dict[str, Any]]:
    _init_k8s_client()
    if not _K8S_CLIENT_INITIALIZED:
        return [{"error": "无法连接到 Kubernetes 集群，请检查配置。"}]

    v1 = client.CoreV1Api()
    try:
        # 获取所有 Pods
        pods = v1.list_pod_for_all_namespaces(watch=False)
        services = {}

        for pod in pods.items:
            ns = pod.metadata.namespace
            labels = pod.metadata.labels or {}
            
            # 尝试从常见标签中提取服务名
            # 优先级: app > app.kubernetes.io/name > k8s-app > component > name
            app_name = labels.get("app") or \
                       labels.get("app.kubernetes.io/name") or \
                       labels.get("k8s-app") or \
                       labels.get("component") or \
                       labels.get("name")

            if not app_name:
                continue

            key = f"{ns}/{app_name}"
            if key not in services:
                services[key] = {
                    "namespace": ns,
                    "service": app_name,
                    "pod_count": 0,
                    "example_pod": pod.metadata.name
                }
            services[key]["pod_count"] += 1

        # 转换为列表并按 Namespace 排序
        result = list(services.values())
        result.sort(key=lambda x: (x["namespace"], x["service"]))
        return result

    except Exception as e:
        logging.error(f"Error listing services: {e}")
        return [{"error": str(e)}]


@tool(
    "k8s_get_namespaces",
    description="列出集群中所有的 Namespace。无需参数。返回 Namespace 列表。",
)
def k8s_get_namespaces() -> List[str]:
    _init_k8s_client()
    if not _K8S_CLIENT_INITIALIZED:
        return ["Error: K8s client not initialized"]
    v1 = client.CoreV1Api()
    try:
        ns_list = v1.list_namespace()
        return [ns.metadata.name for ns in ns_list.items]
    except Exception as e:
        return [f"Error: {str(e)}"]


@tool(
    "k8s_list_events",
    description="列出指定 Namespace 中的 Events（事件）。常用于排查 Pod 启动失败、调度失败等问题。参数：namespace。返回事件列表（包含时间、类型、对象、原因、消息）。",
)
def k8s_list_events(namespace: str) -> str:
    _init_k8s_client()
    if not _K8S_CLIENT_INITIALIZED:
        return "Error: K8s client not initialized"
    
    v1 = client.CoreV1Api()
    try:
        # 获取事件列表，按时间倒序排序
        events = v1.list_namespaced_event(namespace)
        items = events.items
        # Sort by last_timestamp (if available) or event_time, descending
        items.sort(key=lambda x: x.last_timestamp or x.event_time or x.first_timestamp, reverse=True)
        
        # 只返回最近的 20 条，避免 Token 爆炸
        recent_events = items[:20]
        
        result = []
        for e in recent_events:
            ts = e.last_timestamp or e.event_time or e.first_timestamp
            obj_kind = e.involved_object.kind
            obj_name = e.involved_object.name
            line = f"[{ts}] Type={e.type} Reason={e.reason} Object={obj_kind}/{obj_name} Message={e.message}"
            result.append(line)
            
        if not result:
            return "No events found in this namespace."
            
        return "\n".join(result)

    except Exception as e:
        return f"Error listing events: {str(e)}"


class K8sResourceInput(BaseModel):
    resource_type: str = Field(description="资源类型，如 pod, deployment, service, node 等")
    namespace: str = Field(default="", description="命名空间，非 namespace 资源（如 node）传空字符串")
    name: str = Field(description="资源名称")

@tool(
    "k8s_get_resource_yaml",
    args_schema=K8sResourceInput,
    description="获取指定 Kubernetes 资源的 YAML 配置（脱敏后）。参数：resource_type (如 pod, deployment, service, configmap, event, node, ingress, pvc, pv, cronjob, job, statefulset, daemonset), namespace (非 namespace 资源传空字符串), name。注意：Secrets 不允许查看。",
)
def k8s_get_resource_yaml(resource_type: str, namespace: str, name: str) -> str:
    _init_k8s_client()
    if not _K8S_CLIENT_INITIALIZED:
        return "Error: K8s client not initialized"
    
    import yaml
    
    resource_type = resource_type.lower().strip()
    if resource_type in ["secret", "secrets"]:
        return "Error: Access to Secret resources is denied for security reasons."

    try:
        obj = None
        # Core V1
        v1 = client.CoreV1Api()
        if resource_type in ["pod", "pods"]:
            obj = v1.read_namespaced_pod(name, namespace)
        elif resource_type in ["service", "services", "svc"]:
            obj = v1.read_namespaced_service(name, namespace)
        elif resource_type in ["configmap", "cm"]:
            obj = v1.read_namespaced_config_map(name, namespace)
        elif resource_type in ["node", "nodes"]:
            obj = v1.read_node(name)
        elif resource_type in ["event", "events"]:
            obj = v1.read_namespaced_event(name, namespace)
        elif resource_type in ["pvc", "persistentvolumeclaim"]:
            obj = v1.read_namespaced_persistent_volume_claim(name, namespace)
        elif resource_type in ["pv", "persistentvolume"]:
            obj = v1.read_persistent_volume(name)
        
        # Apps V1
        if obj is None:
            apps_v1 = client.AppsV1Api()
            if resource_type in ["deployment", "deployments", "deploy"]:
                obj = apps_v1.read_namespaced_deployment(name, namespace)
            elif resource_type in ["statefulset", "sts"]:
                obj = apps_v1.read_namespaced_stateful_set(name, namespace)
            elif resource_type in ["daemonset", "ds"]:
                obj = apps_v1.read_namespaced_daemon_set(name, namespace)
            elif resource_type in ["replicaset", "rs"]:
                obj = apps_v1.read_namespaced_replica_set(name, namespace)

        # Batch V1
        if obj is None:
            batch_v1 = client.BatchV1Api()
            if resource_type in ["job", "jobs"]:
                obj = batch_v1.read_namespaced_job(name, namespace)
            elif resource_type in ["cronjob", "cj"]:
                obj = batch_v1.read_namespaced_cron_job(name, namespace)

        # Networking V1
        if obj is None:
            net_v1 = client.NetworkingV1Api()
            if resource_type in ["ingress", "ing"]:
                obj = net_v1.read_namespaced_ingress(name, namespace)
            elif resource_type in ["networkpolicy", "netpol"]:
                obj = net_v1.read_namespaced_network_policy(name, namespace)

        # Storage V1
        if obj is None:
            storage_v1 = client.StorageV1Api()
            if resource_type in ["storageclass", "sc"]:
                obj = storage_v1.read_storage_class(name)

        if obj is None:
            return f"Error: Unsupported resource type '{resource_type}' or resource not found."
        
        # 转为字典并清理 managedFields 等干扰信息
        obj_dict = obj.to_dict()
        if "metadata" in obj_dict:
            obj_dict["metadata"].pop("managed_fields", None)
            
        return yaml.dump(obj_dict, default_flow_style=False)
        
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return f"Error: Resource {resource_type}/{name} not found in namespace {namespace}."
        return f"Error: Kubernetes API error: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"
