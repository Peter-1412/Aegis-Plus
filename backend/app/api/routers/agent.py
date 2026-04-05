import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db.session import get_session
from app.db.models import AgentSession, AgentMessage, User
from app.api.deps import get_current_user
from app.agent.ops_agent import ensure_cst
from app.agent.llm import stream_rendered_answer
from app.models import OpsRequest, TimeRange
from app.agent.shared import ops_agent, OpsStreamHandler, _request_id_var

router = APIRouter()

def utf8_slice(s: str, length: int) -> str:
    return s[:length] + "..." if len(s) > length else s


def build_rendered_content(summary: str, ranked_root_causes: list[dict], next_actions: list[str]) -> str:
    parts = ["分析结论", summary.strip() or "暂无结论。"]

    if ranked_root_causes:
        lines = ["", "根因排查候选"]
        for idx, cause in enumerate(ranked_root_causes, start=1):
            description = str(cause.get("description") or "").strip()
            probability = cause.get("probability")
            confidence = ""
            if isinstance(probability, (int, float)):
                confidence = f" (置信度 {(float(probability) * 100):.0f}%)"
            service = str(cause.get("service") or "").strip()
            service_suffix = f" [{service}]" if service else ""
            lines.append(f"{idx}. {description}{service_suffix}{confidence}")
        parts.extend(lines)

    if next_actions:
        parts.extend(["", "后续建议"])
        parts.extend([f"- {str(action).strip()}" for action in next_actions if str(action).strip()])

    return "\n".join(parts).strip()


def iter_text_chunks(text: str, chunk_size: int = 24):
    if not text:
        return
    for idx in range(0, len(text), chunk_size):
        yield text[idx : idx + chunk_size]


def build_render_prompt(summary: str, ranked_root_causes: list[dict], next_actions: list[str]) -> str:
    payload = {
        "summary": summary,
        "ranked_root_causes": ranked_root_causes,
        "next_actions": next_actions,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "你是一个智能运维助手。请把下面这份结构化排查结果改写成给用户直接展示的自然语言答复。\n"
        "要求：\n"
        "1. 使用中文。\n"
        "2. 先给出明确结论，再给出根因候选和后续建议。\n"
        "3. 不要输出 JSON，不要输出 Markdown 代码块。\n"
        "4. 语气专业、简洁、可执行。\n"
        "5. 如果有多个根因候选，按可能性从高到低描述。\n\n"
        f"结构化结果：\n{payload_text}\n"
    )


def build_timeline_payload(item: dict) -> dict | None:
    event_type = item.get("event")
    step_id = item.get("step_id")
    if not step_id:
        return None

    if event_type == "thought_summary":
        return {
            "id": step_id,
            "kind": "thought_summary",
            "title": item.get("title") or "思路摘要",
            "content": item.get("thought") or "",
            "phase": item.get("workflow_stage") or "planning",
            "status": "completed",
        }

    if event_type == "tool_call_started":
        return {
            "id": step_id,
            "kind": "tool_call",
            "toolName": item.get("tool") or "",
            "status": item.get("status") or "started",
            "inputText": item.get("tool_input") or "",
            "outputText": "",
            "resultState": item.get("result_state"),
            "resultSummary": item.get("result_summary"),
            "meta": item.get("meta") or {},
        }

    if event_type == "tool_call_running":
        return {
            "id": step_id,
            "kind": "tool_call",
            "toolName": item.get("tool") or "",
            "status": "running",
            "inputText": item.get("tool_input") or "",
            "resultState": item.get("result_state"),
            "resultSummary": item.get("result_summary"),
            "meta": item.get("meta") or {},
        }

    if event_type == "tool_call_completed":
        return {
            "id": step_id,
            "kind": "tool_call",
            "toolName": item.get("tool") or "",
            "status": "completed",
            "outputText": item.get("observation") or "",
            "resultState": item.get("result_state") or "ok",
            "resultSummary": item.get("result_summary"),
        }

    if event_type in {"tool_call_failed"}:
        return {
            "id": step_id,
            "kind": "tool_call",
            "toolName": item.get("tool") or "",
            "status": "failed",
            "outputText": item.get("error_message") or item.get("message") or "",
            "resultState": item.get("result_state") or "runtime_error",
            "resultSummary": item.get("result_summary"),
        }

    return None

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
    
    async def runner():
        try:
            token = _request_id_var.set(req_id)
            handler = OpsStreamHandler(queue)
            assistant_message_id = f"assistant-{req_id}"
            
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
            
            res = await ops_agent.analyze(ops_req, callbacks=[handler])

            ranked_root_causes = [c.model_dump() for c in res.ranked_root_causes]
            next_actions = res.next_actions
            fallback_content = build_rendered_content(
                res.summary,
                ranked_root_causes,
                next_actions,
            )

            await queue.put({
                "event": "assistant_message_start",
                "message_id": assistant_message_id,
                "request_id": req_id,
            })

            try:
                rendered_content = await stream_rendered_answer(
                    ops_req.model,
                    build_render_prompt(res.summary, ranked_root_causes, next_actions),
                    lambda token: queue.put({
                        "event": "assistant_message_delta",
                        "message_id": assistant_message_id,
                        "delta": token,
                        "request_id": req_id,
                    }),
                )
            except Exception as render_exc:
                logging.exception("render stream error: %s", render_exc)
                rendered_content = fallback_content
                for chunk in iter_text_chunks(rendered_content):
                    await queue.put({
                        "event": "assistant_message_delta",
                        "message_id": assistant_message_id,
                        "delta": chunk,
                        "request_id": req_id,
                    })

            await queue.put({
                "event": "assistant_message_end",
                "message_id": assistant_message_id,
                "content": rendered_content,
                "request_id": req_id,
            })
            
            meta = {
                "event": "final",
                "summary": res.summary,
                "ranked_root_causes": ranked_root_causes,
                "next_actions": next_actions,
                "trace": res.trace.model_dump() if res.trace else None,
                "message_id": assistant_message_id,
                "content": rendered_content,
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
        timeline_map: dict[str, dict] = {}
        timeline_order: list[str] = []

        def upsert_timeline(item: dict):
            payload = build_timeline_payload(item)
            if not payload:
                return
            timeline_id = payload["id"]
            existing = timeline_map.get(timeline_id)
            if timeline_id not in timeline_map:
                timeline_order.append(timeline_id)
                timeline_map[timeline_id] = payload
                return

            if existing and payload["kind"] == "tool_call" and existing.get("kind") == "tool_call":
                existing.update({k: v for k, v in payload.items() if v not in (None, "", {})})
            else:
                timeline_map[timeline_id] = payload

        while True:
            item = await queue.get()
            event_type = item.get("event")
            if event_type in [
                "thought_summary",
                "tool_call_started",
                "tool_call_running",
                "tool_call_completed",
                "tool_call_failed",
            ]:
                upsert_timeline(item)

            if event_type == "final":
                ranked_root_causes = item.get("ranked_root_causes") or []
                next_actions = item.get("next_actions") or []
                timeline = [timeline_map[item_id] for item_id in timeline_order if item_id in timeline_map]
                structured_content = {
                    "version": 3,
                    "content": item.get("content") or "",
                    "summary": item.get("summary"),
                    "ranked_root_causes": ranked_root_causes,
                    "next_actions": next_actions,
                    "timeline": timeline,
                }
                final_payload = {**item, "timeline": timeline}
                yield (json.dumps(final_payload, ensure_ascii=False) + "\n").encode("utf-8")

                from app.db.session import engine
                with Session(engine) as db:
                    agent_msg = AgentMessage(
                        session_id=db_session.id,
                        role="AGENT",
                        content=item.get("content") or "",
                        metadata_json=json.dumps(structured_content, ensure_ascii=False)
                    )
                    db.add(agent_msg)
                    sess = db.get(AgentSession, db_session.id)
                    if sess:
                        sess.updated_at = datetime.now(timezone.utc)
                        db.add(sess)
                    db.commit()
                continue

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
