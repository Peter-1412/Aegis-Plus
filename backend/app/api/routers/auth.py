from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db.session import get_session
from app.db.models import User, Role, AuditLog
from app.core.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.api.deps import get_current_user
import re

router = APIRouter()

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str

def validate_username(username: str) -> str:
    if len(username) < 2 or len(username) > 20:
        return "姓名长度必须在 2 到 20 个字符之间"
    # 取消仅限中文的限制，或者允许英文、数字、中文组合
    if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9_-]+$", username):
        return "姓名只能包含中文、字母、数字、下划线或连字符"
    return ""

def validate_password(password: str) -> str:
    if len(password) < 8:
        return "密码长度不能少于 8 个字符"
    return ""

@router.post("/register")
def register(req: RegisterRequest, session: Session = Depends(get_session)):
    err_msg = validate_username(req.username)
    if err_msg:
        raise HTTPException(status_code=400, detail=err_msg)
        
    err_msg = validate_password(req.password)
    if err_msg:
        raise HTTPException(status_code=400, detail=err_msg)
        
    existing_user = session.exec(select(User).where(User.username == req.username)).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="用户名已存在")
        
    user_count = session.exec(select(User)).all()
    is_first_user = len(user_count) == 0
    
    hashed_password = get_password_hash(req.password)
    role = Role.ADMIN if is_first_user else Role.DEVELOPER
    
    new_user = User(
        username=req.username,
        password_hash=hashed_password,
        role=role,
        is_active=is_first_user
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    msg = "已创建首个管理员账号" if is_first_user else "注册成功，等待管理员审批"
    return {
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "role": new_user.role,
            "isActive": new_user.is_active
        },
        "message": msg
    }

@router.post("/login")
def login(req: LoginRequest, response: Response, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == req.username)).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
        
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号未激活，请等待管理员审批")
        
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    
    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action="LOGIN",
        resource_type="User",
        resource_id=str(user.id),
        metadata_json='{"username": "' + user.username + '"}'
    )
    session.add(audit)
    session.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    
    response.set_cookie(
        key="auth_token",
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax"
    )
    
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role
        }
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("auth_token")
    return {"success": True}

@router.get("/me")
def get_me(request: Request, session: Session = Depends(get_session)):
    try:
        user = get_current_user(request, session)
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "isActive": user.is_active,
                "createdAt": user.created_at,
                "lastLoginAt": user.last_login_at
            }
        }
    except HTTPException:
        return {"user": None}

@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    err_msg = validate_password(req.newPassword)
    if err_msg:
        raise HTTPException(status_code=400, detail=err_msg)
        
    if not verify_password(req.currentPassword, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
        
    current_user.password_hash = get_password_hash(req.newPassword)
    session.add(current_user)
    
    audit = AuditLog(
        user_id=current_user.id,
        action="CHANGE_PASSWORD",
        resource_type="User",
        resource_id=str(current_user.id)
    )
    session.add(audit)
    session.commit()
    return {"success": True}
