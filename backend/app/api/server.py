from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import contextvars
import json
import logging
import time
import uuid
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.callbacks import AsyncCallbackHandler
from pydantic import BaseModel

from app.agent.ops_agent import OpsAgent, ensure_cst
from app.api.feishu_client import feishu_client
from app.models import OpsRequest, OpsResponse, TimeRange
from config.config import settings

# DB and Routers
from app.db.session import init_db
from app.api.routers import auth, admin, tools, agent, dashboard


from app.agent.shared import ops_agent, _request_id_var, OpsStreamHandler


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = _request_id_var.get()
        except Exception:
            record.request_id = None
        return True


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": "ops-service",
            "request_id": getattr(record, "request_id", None),
            "msg": record.getMessage(),
        }
        try:
            if record.exc_info:
                payload["exc"] = self.formatException(record.exc_info)
        except Exception:
            pass
        return json.dumps(payload, ensure_ascii=False)


class _HealthzAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if isinstance(args, tuple) and len(args) >= 2:
                req = args[1]
                if isinstance(req, str) and "/healthz" in req:
                    return False
            msg = record.getMessage()
            if "/healthz" in msg:
                return False
        except Exception:
            return True
        return True


_root = logging.getLogger()
_root.setLevel(logging.INFO)
_json_formatter = _JSONFormatter()
_has_handler = False
for _handler in _root.handlers:
    _handler.setFormatter(_json_formatter)
    _handler.addFilter(_RequestIdFilter())
    _has_handler = True
if not _has_handler:
    _handler = logging.StreamHandler()
    _handler.setFormatter(_json_formatter)
    _handler.addFilter(_RequestIdFilter())
    _root.addHandler(_handler)

logging.getLogger("uvicorn.access").addFilter(_HealthzAccessFilter())


app = FastAPI(title="Ops Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(tools.router, prefix="/api/tools", tags=["Tools"])
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = _request_id_var.set(req_id)
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = req_id
        return response
    finally:
        _request_id_var.reset(token)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}





def _sanitize_feishu_text(text: str) -> str:
    parts: list[str] = []
    for token in text.split():
        if token.startswith("@_user_"):
            continue
        parts.append(token)
    return " ".join(parts).strip()


def _extract_model_choice(text: str) -> tuple[str | None, str]:
    tokens = [t for t in text.split() if t]
    if not tokens:
        return None, ""
    cleaned = [t for t in tokens if not t.startswith("@")]
    if not cleaned:
        cleaned = tokens
    first = cleaned[0].strip().lower()
    if first in {"qwen", "glm", "deepseek", "doubao"}:
        remaining = " ".join(cleaned[1:]).strip()
        return first, remaining
    return None, " ".join(cleaned).strip()


class FeishuIncoming(BaseModel):
    chat_id: str
    text: str


async def _send_ops_result_to_feishu(chat_id: str, question: str, res: OpsResponse):
    lines: list[str] = []
    lines.append("【分析结果】")
    lines.append(f"问题：{question}")
    lines.append(f"结论：{res.summary}")
    if res.ranked_root_causes:
        lines.append("可能原因：")
        for c in res.ranked_root_causes[:3]:
            prob = f"，概率≈{c.probability:.2f}" if c.probability is not None else ""
            svc = f"（服务：{c.service}）" if c.service else ""
            lines.append(f"{c.rank}. {c.description}{svc}{prob}")
    if res.next_actions:
        lines.append("后续建议：")
        for idx, act in enumerate(res.next_actions, start=1):
            lines.append(f"{idx}. {act}")
    text_msg = "\n".join(lines)
    logging.info("sending feishu message, chat_id=%s, length=%s", chat_id, len(text_msg))
    await feishu_client.send_text_message(chat_id=chat_id, text=text_msg)

async def _save_feishu_chat_to_db(question: str, summary: str):
    try:
        from app.db.session import engine
        from sqlmodel import Session
        from app.db.models import AgentSession, AgentMessage
        with Session(engine) as session:
            new_session = AgentSession(
                title="来自飞书的提问",
                user_id=1 # Default Admin
            )
            session.add(new_session)
            session.commit()
            session.refresh(new_session)
            
            msg_user = AgentMessage(
                session_id=new_session.id,
                role="USER",
                content=question + "\n\n*(通过飞书机器人提问)*"
            )
            msg_agent = AgentMessage(
                session_id=new_session.id,
                role="AGENT",
                content=summary
            )
            session.add(msg_user)
            session.add(msg_agent)
            session.commit()
    except Exception as e:
        logging.error(f"Error syncing feishu chat to DB: {e}")


async def _handle_feishu_text(chat_id: str, text: str):
    raw_text = text.strip()
    if not raw_text:
        return
    text = _sanitize_feishu_text(raw_text)
    model_choice, question = _extract_model_choice(text)
    if not question:
        question = text
    now = datetime.now(timezone(timedelta(hours=8)))
    logging.info(
        "feishu request received, chat_id=%s, text=%s, model=%s",
        chat_id,
        question,
        model_choice or settings.default_model,
    )
    ack_text = "收到，我来帮您查询，预计需要 1~5 分钟，我会在之后把结果发给您。"
    try:
        logging.info("sending feishu ack, chat_id=%s, length=%s", chat_id, len(ack_text))
        await feishu_client.send_text_message(chat_id=chat_id, text=ack_text)
    except Exception as exc:
        logging.exception("send feishu ack failed: %s", exc)
        
    req = OpsRequest(
        description=question,
        time_range=TimeRange(start=now - timedelta(minutes=15), end=now),
        session_id=chat_id,
        model=model_choice or settings.default_model,
    )
    
    # 异步执行，不阻塞当前的 HTTP 响应，这样飞书的长连接回调能立即返回
    async def do_analyze():
        logging.info(
            "start ops for chat_id=%s, window=%s~%s",
            chat_id,
            (now - timedelta(minutes=15)).isoformat(),
            now.isoformat(),
        )
        t0 = time.monotonic()
        try:
            res = await ops_agent.analyze(req)
        except Exception as exc:
            logging.exception("ops failed for feishu, chat_id=%s, error=%s", chat_id, exc)
            error_text = "抱歉，分析过程中出现错误，请稍后重试或联系平台同学查看日志。"
            try:
                await feishu_client.send_text_message(chat_id=chat_id, text=error_text)
            except Exception as send_exc:
                logging.exception("send feishu error message failed: %s", send_exc)
            return
            
        dt = time.monotonic() - t0
        logging.info(
            "ops finished, chat_id=%s, duration_s=%.3f, summary_len=%s",        
            chat_id,
            dt,
            len(res.summary or ""),
        )
        await _send_ops_result_to_feishu(chat_id, question, res)
        # 同步保存到运维平台的 SQLite 数据库
        asyncio.create_task(_save_feishu_chat_to_db(question, res.summary or ""))

    asyncio.create_task(do_analyze())


@app.post("/feishu/receive")
async def feishu_receive(payload: FeishuIncoming) -> dict[str, str]:
    await _handle_feishu_text(payload.chat_id, payload.text)
    return {"status": "ok"}


class Alert(BaseModel):
    status: str | None = None
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    startsAt: datetime | None = None
    endsAt: datetime | None = None


class AlertmanagerWebhook(BaseModel):
    status: str | None = None
    receiver: str | None = None
    alerts: list[Alert] = []





@app.post("/api/ops/analyze", response_model=OpsResponse)
async def analyze(req: OpsRequest) -> OpsResponse:
    try:
        if req.time_range is None:
            now = datetime.now(timezone(timedelta(hours=8)))
            req.time_range = TimeRange(start=now - timedelta(hours=1), end=now)
        
        t0 = time.monotonic()
        res = await ops_agent.analyze(req)
        dt = time.monotonic() - t0
        logging.info(
            "ops analyze api done, duration_s=%.3f, summary_len=%s, root_causes=%s, next_actions=%s",
            dt,
            len(res.summary or ""),
            len(res.ranked_root_causes or []),
            len(res.next_actions or []),
        )
        
        if req.notify_chat_id:
            target_chat_id = req.notify_chat_id
            if target_chat_id == "default":
                # 直接从环境变量获取，避免 Pydantic 默认值 None 的问题
                import os
                target_chat_id = os.getenv("FEISHU_DEFAULT_CHAT_ID", "")
            
            if target_chat_id:
                # Fire and forget notification to avoid blocking API response
                asyncio.create_task(_send_ops_result_to_feishu(target_chat_id, req.description, res))
            else:
                logging.warning("notify_chat_id requested but FEISHU_DEFAULT_CHAT_ID env is empty")
                
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ops/analyze/stream")
async def analyze_stream(req: OpsRequest):
    queue: asyncio.Queue = asyncio.Queue()
    req_id = _request_id_var.get() or str(uuid.uuid4())

    async def runner():
        try:
            token = _request_id_var.set(req_id)
            handler = OpsStreamHandler(queue)
            
            if req.time_range is None:
                now = datetime.now(timezone(timedelta(hours=8)))
                req.time_range = TimeRange(start=now - timedelta(hours=1), end=now)
                
            start = ensure_cst(req.time_range.start)
            end = ensure_cst(req.time_range.end)
            logging.info(
                "ops stream start, start=%s, end=%s, session_id=%s",
                start.isoformat(),
                end.isoformat(),
                handler.session_id,
            )
            await queue.put(
                {
                    "event": "start",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "request_id": req_id,
                }
            )
            t0 = time.monotonic()
            res = await ops_agent.analyze(req, callbacks=[handler])
            dt = time.monotonic() - t0
            meta = {
                "event": "final",
                "summary": res.summary,
                "ranked_root_causes": [c.model_dump() for c in res.ranked_root_causes],
                "next_actions": res.next_actions,
                "trace": res.trace.dict() if res.trace else None,
                "request_id": req_id,
            }
            logging.info(
                "ops stream final, duration_s=%.3f, summary_len=%s, root_causes=%s, next_actions=%s",
                dt,
                len(res.summary or ""),
                len(res.ranked_root_causes or []),
                len(res.next_actions or []),
            )
            await queue.put(meta)
        except Exception as exc:
            logging.exception("ops stream error: %s", exc)
            await queue.put({"event": "error", "message": str(exc), "request_id": req_id})
        finally:
            logging.info("ops stream end")
            try:
                _request_id_var.reset(token)
            except Exception:
                pass
            await queue.put({"event": "end", "request_id": req_id})

    asyncio.create_task(runner())

    async def iterator() -> AsyncIterator[bytes]:
        while True:
            item = await queue.get()
            data = json.dumps(item, ensure_ascii=False) + "\n"
            yield data.encode("utf-8")
            if item.get("event") == "end":
                break

    return StreamingResponse(iterator(), media_type="application/x-ndjson")


@app.post("/alertmanager/webhook")
async def alertmanager_webhook(payload: AlertmanagerWebhook):
    chat_id = settings.feishu_default_chat_id
    if not chat_id:
        return {"status": "ignored", "reason": "feishu_default_chat_id not configured"}
    alerts = payload.alerts or []
    if not alerts:
        return {"status": "ignored", "reason": "no alerts"}
    logging.info(
        "alertmanager webhook received, status=%s, alert_count=%s",
        payload.status,
        len(alerts),
    )
    lines: list[str] = []
    lines.append("@所有人")
    lines.append("【Kubernetes 集群告警通知】")
    lines.append(f"Alertmanager status: {payload.status or 'unknown'}")
    lines.append(f"告警数量: {len(alerts)}")
    lines.append("")
    for idx, alert in enumerate(alerts, start=1):
        labels = alert.labels or {}
        annotations = alert.annotations or {}
        name = labels.get("alertname") or "unnamed"
        severity = labels.get("severity") or "unknown"
        instance = labels.get("instance") or labels.get("pod") or labels.get("service") or "-"
        summary = annotations.get("summary") or annotations.get("description") or ""
        lines.append(f"{idx}. [{severity}] {name} @ {instance}")
        if summary:
            lines.append(f"   概要: {summary}")
    text_msg = "\n".join(lines)
    try:
        await feishu_client.send_text_message(chat_id=chat_id, text=text_msg)
        
        # 触发自动分析 (Auto-RCA)
        # 仅针对 firing 状态的告警，且避免重复触发
        if payload.status == "firing":
            # 构造分析描述
            descriptions = []
            for alert in alerts[:3]: # 只取前3个避免过长
                labels = alert.labels or {}
                annotations = alert.annotations or {}
                name = labels.get("alertname")
                instance = labels.get("instance") or labels.get("pod")
                desc = annotations.get("description") or annotations.get("summary")
                if name and instance:
                    descriptions.append(f"告警名: {name}, 实例: {instance}, 描述: {desc}")
            
            if descriptions:
                auto_analyze_desc = "收到 Alertmanager 告警，请立即进行根因分析：\n" + "\n".join(descriptions)
                logging.info("triggering auto-rca for alerts")
                
                # 异步触发分析，不阻塞 Webhook 响应
                req = OpsRequest(
                    description=auto_analyze_desc,
                    session_id="auto-rca-bot",
                    model=settings.default_model,
                    notify_chat_id="default"
                )
                asyncio.create_task(_send_ops_result_to_feishu(chat_id, auto_analyze_desc, await ops_agent.analyze(req)))

        return {"status": "ok", "sent_to": chat_id, "alert_count": len(alerts)}
    except Exception as exc:
        logging.exception("alertmanager forward to feishu failed: %s", exc)
        return {"status": "error", "reason": str(exc)}


import os
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# (at the bottom of api.py)

@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logging.exception("unhandled exception: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})

# Serve SPA
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    @app.api_route("/{path_name:path}", methods=["GET"])
    async def catch_all(request: Request, path_name: str):
        # Ignore API routes
        if path_name.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    logging.warning(f"Frontend dist not found at {frontend_dist}. API only mode.")
