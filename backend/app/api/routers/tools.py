from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
import os
import requests
import logging

from app.db.session import get_session
from app.db.models import OpsTool, User
from app.api.deps import get_current_user, get_current_admin

router = APIRouter()

class SystemToolSpec(BaseModel):
    type: str
    name: str
    env_key: str
    description: str
    is_pinned_default: bool

SYSTEM_TOOLS = [
    SystemToolSpec(type="Rancher", name="Rancher 容器管理", env_key="RANCHER_URL", description="企业级 Kubernetes 集群管理平台，提供统一的集群部署与管理能力。", is_pinned_default=True),
    SystemToolSpec(type="Jenkins", name="Jenkins 流水线", env_key="JENKINS_URL", description="自动化 CI/CD 引擎，支持构建、测试、部署的全流程自动化。", is_pinned_default=True),
    SystemToolSpec(type="MinIO", name="MinIO 对象存储", env_key="MINIO_URL", description="高性能分布式对象存储服务，兼容 Amazon S3 API。", is_pinned_default=False),
    SystemToolSpec(type="Harbor", name="Harbor 镜像仓库", env_key="HARBOR_URL", description="企业级云原生制品仓库，提供镜像扫描、签名和策略复制功能。", is_pinned_default=True),
    SystemToolSpec(type="Grafana", name="Grafana 可视化", env_key="GRAFANA_URL", description="开源数据可视化与监控分析平台，支持多种数据源接入。", is_pinned_default=True),
    SystemToolSpec(type="Jaeger", name="Jaeger 链路追踪", env_key="JAEGER_URL", description="端到端分布式链路追踪系统，用于监控和排查微服务延迟问题。", is_pinned_default=False),
    SystemToolSpec(type="VirtualMachine", name="虚拟机管理", env_key="VM_MANAGER_URL", description="基础设施虚拟机生命周期管理平台。", is_pinned_default=False),
    SystemToolSpec(type="Prometheus", name="Prometheus 监控", env_key="PROMETHEUS_URL", description="云原生监控报警系统，提供强大的多维数据模型和查询语言。", is_pinned_default=False),
]

def is_system_tool(created_by_id: Optional[int], tool_type: str) -> bool:
    if created_by_id is not None:
        return False
    return any(s.type == tool_type for s in SYSTEM_TOOLS)

def sync_system_tools(session: Session):
    for spec in SYSTEM_TOOLS:
        val = os.getenv(spec.env_key, "").strip()
        
        if not val:
            # delete if exists
            existing = session.exec(select(OpsTool).where(OpsTool.created_by_id == None, OpsTool.type == spec.type)).first()
            if existing:
                session.delete(existing)
            continue
            
        existing = session.exec(select(OpsTool).where(OpsTool.created_by_id == None, OpsTool.type == spec.type)).first()
        if not existing:
            new_tool = OpsTool(
                name=spec.name,
                type=spec.type,
                environment="PROD",
                url=val,
                health_check_url=val,
                description=spec.description,
                is_pinned=spec.is_pinned_default,
                created_by_id=None
            )
            session.add(new_tool)
        else:
            existing.name = spec.name
            existing.url = val
            existing.health_check_url = val
            existing.description = spec.description
            session.add(existing)
            
    # cleanup legacy
    session.commit()
    system_tools = session.exec(select(OpsTool).where(OpsTool.created_by_id == None)).all()
    valid_types = {s.type for s in SYSTEM_TOOLS}
    for tool in system_tools:
        if tool.type not in valid_types:
            session.delete(tool)
    session.commit()


@router.get("")
def get_tools(session: Session = Depends(get_session)):
    sync_system_tools(session)
    tools = session.exec(select(OpsTool).order_by(OpsTool.is_pinned.desc(), OpsTool.environment.asc(), OpsTool.name.asc())).all()
    
    return {
        "tools": [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "environment": t.environment,
                "url": t.url,
                "healthCheckUrl": t.health_check_url,
                "description": t.description,
                "isPinned": t.is_pinned,
                "createdAt": t.created_at,
                "updatedAt": t.updated_at,
                "createdById": t.created_by_id,
                "isSystem": is_system_tool(t.created_by_id, t.type)
            } for t in tools
        ]
    }

class ToolRequest(BaseModel):
    id: Optional[int] = None
    name: str
    type: str
    environment: str
    url: str
    healthCheckUrl: Optional[str] = None
    description: Optional[str] = None
    isPinned: bool

@router.post("")
def create_tool(req: ToolRequest, current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    tool = OpsTool(
        name=req.name,
        type=req.type,
        environment=req.environment,
        url=req.url,
        health_check_url=req.healthCheckUrl,
        description=req.description,
        is_pinned=req.isPinned,
        created_by_id=current_user.id
    )
    session.add(tool)
    session.commit()
    session.refresh(tool)
    return {"tool": tool}

@router.put("")
def update_tool(req: ToolRequest, current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    if req.id is None:
        raise HTTPException(status_code=400, detail="缺少工具 ID")
        
    existing = session.get(OpsTool, req.id)
    if not existing:
        raise HTTPException(status_code=404, detail="工具不存在")
        
    if is_system_tool(existing.created_by_id, existing.type):
        existing.is_pinned = req.isPinned
    else:
        existing.name = req.name
        existing.type = req.type
        existing.environment = req.environment
        existing.url = req.url
        existing.health_check_url = req.healthCheckUrl
        existing.description = req.description
        existing.is_pinned = req.isPinned
        
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return {"tool": existing}

class DeleteRequest(BaseModel):
    id: int

@router.delete("")
def delete_tool(req: DeleteRequest, current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    existing = session.get(OpsTool, req.id)
    if not existing:
        raise HTTPException(status_code=404, detail="工具不存在")
        
    if is_system_tool(existing.created_by_id, existing.type):
        raise HTTPException(status_code=400, detail="系统工具由配置提供，无法删除")
        
    session.delete(existing)
    session.commit()
    return {"success": True}

@router.get("/health")
def get_tools_health(session: Session = Depends(get_session)):
    tools = session.exec(select(OpsTool)).all()
    statuses = []
    
    for t in tools:
        url = t.health_check_url if t.health_check_url else t.url
        status = "UNKNOWN"
        if url:
            try:
                resp = requests.get(url, timeout=3)
                if 200 <= resp.status_code < 400:
                    status = "UP"
                else:
                    status = "DOWN"
            except:
                status = "DOWN"
        statuses.append({"id": t.id, "status": status})
        
    return {"statuses": statuses}
