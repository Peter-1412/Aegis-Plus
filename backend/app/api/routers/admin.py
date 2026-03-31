from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Optional
from pydantic import BaseModel
import os

from app.db.session import get_session
from app.db.models import User, Role
from app.api.deps import get_current_admin

router = APIRouter()

class PatchUserRequest(BaseModel):
    id: int
    isActive: Optional[bool] = None
    role: Optional[str] = None

@router.get("/users")
def get_users(current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    users = session.exec(select(User).order_by(User.created_at.asc())).all()
    
    # Python sorting to emulate the SQL case sort for Role (ADMIN first)
    users.sort(key=lambda u: 1 if u.role == Role.ADMIN else 2)
    
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "role": u.role,
                "isActive": u.is_active,
                "createdAt": u.created_at,
                "lastLoginAt": u.last_login_at
            }
            for u in users
        ]
    }

@router.patch("/users")
def patch_user(req: PatchUserRequest, current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    user = session.get(User, req.id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
        
    if req.isActive is not None:
        user.is_active = req.isActive
    if req.role is not None:
        if req.role in [Role.ADMIN, Role.DEVELOPER, Role.READONLY]:
            user.role = Role(req.role)
            
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "isActive": user.is_active
        }
    }

exposed_keys = [
    "RANCHER_URL",
    "JENKINS_URL",
    "MINIO_URL",
    "HARBOR_URL",
    "GRAFANA_URL",
    "JAEGER_URL",
    "VM_MANAGER_URL",
    "PROMETHEUS_URL",
    "AGENT_API_URL",
]

@router.get("/config")
def get_config(current_user: User = Depends(get_current_admin)):
    env_vars = {}
    for key in exposed_keys:
        val = os.getenv(key)
        env_vars[key] = val if val else None
        
    return {
        "env": env_vars,
        "note": "修改环境变量后需重启后端服务生效"
    }
