from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from app.db.session import get_session
from app.db.models import User, OpsTool, AgentSession

router = APIRouter()

@router.get("/overview")
def get_dashboard_overview(session: Session = Depends(get_session)):
    user_count = session.exec(select(func.count(User.id))).one()
    active_user_count = session.exec(select(func.count(User.id)).where(User.is_active == True)).one()
    tool_count = session.exec(select(func.count(OpsTool.id))).one()
    session_count = session.exec(select(func.count(AgentSession.id))).one()

    return {
        "clusters": {
            "prodStatus": "正常",
            "testStatus": "正常",
            "azCount": 2,
        },
        "resources": {
            "cpuUsage": 42,
            "memoryUsage": 55,
            "nodeCount": 12,
            "podRunning": 180,
        },
        "alerts": {
            "critical": 0,
            "warning": 3,
            "info": 5,
        },
        "ci": {
            "lastBuildStatus": "成功",
            "todayBuilds": 12,
            "failureRate": 8,
        },
        "summary": {
            "userCount": user_count,
            "activeUserCount": active_user_count,
            "toolCount": tool_count,
            "sessionCount": session_count,
        },
    }
