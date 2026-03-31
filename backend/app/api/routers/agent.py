import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db.session import get_session
from app.db.models import AgentSession, AgentMessage, User
from app.api.deps import get_current_user
from app.agent.ops_agent import ensure_cst
from app.models import OpsRequest, TimeRange
from app.agent.shared import ops_agent, OpsStreamHandler, _request_id_var

router = APIRouter()

def utf8_slice(s: str, length: int) -> str:
    return s[:length] + "..." if len(s) > length else s

@router.get("/sessions")
def get_sessions(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    sessions = session.exec(
        select(AgentSession)
        .where(AgentSession.user_id == current_user.id)
        .order_by(AgentSession.is_pinned.desc(), AgentSession.updated_at.desc())
    ).all()
    return {"sessions": sessions}

class CreateSessionRequest(BaseModel):
    title: str

@router.post("/sessions")
def create_session(req: CreateSessionRequest, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    title = req.title.strip() or "新建对话"
    new_session = AgentSession(title=title, user_id=current_user.id)
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    return {"session": new_session}

@router.get("/sessions/{session_id}")
def get_session_by_id(session_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    db_session = session.exec(
        select(AgentSession)
        .where(AgentSession.id == session_id, AgentSession.user_id == current_user.id)
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="会话不存在")
        
    # include messages
    messages = []
    for msg in db_session.messages:
        messages.append({
            "id": msg.id,
            "sessionId": msg.session_id,
            "role": msg.role,
            "content": msg.content,
            "metadata": msg.metadata_json,
            "createdAt": msg.created_at
        })
        
    return {
        "session": {
            "id": db_session.id,
            "title": db_session.title,
            "userId": db_session.user_id,
            "isPinned": db_session.is_pinned,
            "createdAt": db_session.created_at,
            "updatedAt": db_session.updated_at,
            "messages": messages
        }
    }

class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    isPinned: Optional[bool] = None

@router.put("/sessions/{session_id}")
def update_session(session_id: int, req: UpdateSessionRequest, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    db_session = session.exec(
        select(AgentSession)
        .where(AgentSession.id == session_id, AgentSession.user_id == current_user.id)
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="会话不存在")
        
    if req.title is not None:
        db_session.title = req.title
    if req.isPinned is not None:
        db_session.is_pinned = req.isPinned
        
    db_session.updated_at = datetime.now(timezone.utc)
    session.add(db_session)
    session.commit()
    return {"status": "ok"}

@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    db_session = session.exec(
        select(AgentSession)
        .where(AgentSession.id == session_id, AgentSession.user_id == current_user.id)
    ).first()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="会话不存在")
        
    session.delete(db_session)
    session.commit()
    return {"status": "ok"}


class ChatRequest(BaseModel):
    sessionId: Optional[int] = None
    message: str

@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, response: Response, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if not req.message:
        raise HTTPException(status_code=400, detail="消息不能为空")
        
    db_session = None
    if req.sessionId:
        db_session = session.exec(
            select(AgentSession)
            .where(AgentSession.id == req.sessionId, AgentSession.user_id == current_user.id)
        ).first()
        
    if not db_session:
        db_session = AgentSession(
            title=utf8_slice(req.message, 20),
            user_id=current_user.id
        )
        session.add(db_session)
        session.commit()
        session.refresh(db_session)
    elif db_session.title == "新建对话":
        db_session.title = utf8_slice(req.message, 20)
        session.add(db_session)
        session.commit()
        
    user_msg = AgentMessage(
        session_id=db_session.id,
        role="USER",
        content=req.message
    )
    session.add(user_msg)
    
    db_session.updated_at = datetime.now(timezone.utc)
    session.add(db_session)
    session.commit()
    
    response.headers["X-Session-ID"] = str(db_session.id)
    
    queue: asyncio.Queue = asyncio.Queue()
    req_id = _request_id_var.get() or str(uuid.uuid4())
    
    # Store things that need to be saved at the end
    steps_accumulator = []
    
    async def runner():
        try:
            token = _request_id_var.set(req_id)
            handler = OpsStreamHandler(queue)
            
            now = datetime.now(timezone(timedelta(hours=8)))
            ops_req = OpsRequest(
                description=req.message,
                session_id=str(db_session.id),
                time_range=TimeRange(start=now - timedelta(hours=1), end=now)
            )
            
            start = ensure_cst(ops_req.time_range.start)
            end = ensure_cst(ops_req.time_range.end)
            
            await queue.put({
                "event": "start",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "request_id": req_id,
            })
            
            t0 = time.monotonic()
            res = await ops_agent.analyze(ops_req, callbacks=[handler])
            dt = time.monotonic() - t0
            
            meta = {
                "event": "final",
                "summary": res.summary,
                "ranked_root_causes": [c.model_dump() for c in res.ranked_root_causes],
                "next_actions": res.next_actions,
                "trace": res.trace.model_dump() if res.trace else None,
                "request_id": req_id,
            }
            await queue.put(meta)
            
        except Exception as exc:
            logging.exception("ops stream error: %s", exc)
            await queue.put({"event": "error", "message": str(exc), "request_id": req_id})
        finally:
            try:
                _request_id_var.reset(token)
            except Exception:
                pass
            await queue.put({"event": "end", "request_id": req_id})

    asyncio.create_task(runner())

    async def iterator() -> AsyncIterator[bytes]:
        agent_content = ""
        while True:
            item = await queue.get()
            
            event_type = item.get("event")
            if event_type in ["agent_thought", "agent_action", "tool_start", "tool_end", "agent_observation", "error"]:
                steps_accumulator.append(item)
                
            if event_type == "final":
                agent_content = item.get("summary", "")
                structured_content = {
                    "summary": item.get("summary"),
                    "ranked_root_causes": item.get("ranked_root_causes"),
                    "next_actions": item.get("next_actions"),
                    "steps": steps_accumulator
                }
                
                # Save to DB
                # Note: We need a new synchronous session since we are in an async generator context and the outer session might be closed or concurrent
                from app.db.session import engine
                with Session(engine) as db:
                    agent_msg = AgentMessage(
                        session_id=db_session.id,
                        role="AGENT",
                        content=agent_content,
                        metadata_json=json.dumps(structured_content, ensure_ascii=False)
                    )
                    db.add(agent_msg)
                    sess = db.get(AgentSession, db_session.id)
                    if sess:
                        sess.updated_at = datetime.now(timezone.utc)
                        db.add(sess)
                    db.commit()
            
            data = json.dumps(item, ensure_ascii=False) + "\n"
            yield data.encode("utf-8")
            if item.get("event") == "end":
                break

    return StreamingResponse(iterator(), media_type="application/x-ndjson")

# A mock for the Feishu sync, can be called internally or by Feishu webhook
class SyncFeishuRequest(BaseModel):
    userId: int
    title: str
    question: str
    answer: str
    source: str

@router.post("/feishu-sync")
def sync_feishu_chat(req: SyncFeishuRequest, session: Session = Depends(get_session)):
    new_session = AgentSession(
        title=req.title,
        user_id=req.userId
    )
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    
    msg_user = AgentMessage(
        session_id=new_session.id,
        role="USER",
        content=req.question + "\n\n*(通过飞书机器人提问)*"
    )
    msg_agent = AgentMessage(
        session_id=new_session.id,
        role="AGENT",
        content=req.answer
    )
    session.add(msg_user)
    session.add(msg_agent)
    session.commit()
    
    return {"status": "ok", "sessionId": new_session.id}
