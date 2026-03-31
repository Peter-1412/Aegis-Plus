from app.tools.jaeger_tool import jaeger_query_traces
from app.tools.loki_tool import LokiClient, make_loki_collect_evidence
from app.tools.prometheus_tool import prometheus_query_range
from app.tools.metrics_metadata_tool import metrics_metadata_lookup
from app.tools.log_guide_tool import log_query_guide_lookup
from app.tools.k8s_discovery_tool import list_services, k8s_get_namespaces, k8s_get_resource_yaml, k8s_list_events
from app.tools.skill_tool import skill_lookup


def build_tools(loki: LokiClient):
    return [
        metrics_metadata_lookup,
        log_query_guide_lookup,
        skill_lookup,
        list_services,
        k8s_get_namespaces,
        k8s_get_resource_yaml,
        k8s_list_events,
        prometheus_query_range,
        make_loki_collect_evidence(loki),
        jaeger_query_traces,
    ]
