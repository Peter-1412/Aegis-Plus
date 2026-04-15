from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging

from app.agent.graph import build_graph
from app.agent.executor import build_executor
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.agent.llm import get_llm
from app.tools import build_tools
from app.tools.loki_tool import LokiClient
from config.config import settings
from app.memory.store import get_memory
from app.models import AgentTrace, OpsOutput, OpsRequest, OpsResponse, TraceStep
from app.tools import build_tools
from config.config import settings
import aiosqlite


_CST = timezone(timedelta(hours=8))


def ensure_cst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_CST)
    return dt.astimezone(_CST)


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _build_trace(intermediate_steps) -> AgentTrace:
    steps: list[TraceStep] = []
    for idx, pair in enumerate(intermediate_steps or []):
        try:
            action, observation = pair
        except Exception:
            continue
        tool = str(getattr(action, "tool", "") or "")
        tool_input = getattr(action, "tool_input", None)
        log = getattr(action, "log", None)
        obs_text = _stringify(observation)
        if len(obs_text) > 8000:
            obs_text = obs_text[:8000] + "\n...(truncated)"
        inp_text = _stringify(tool_input)
        if len(inp_text) > 4000:
            inp_text = inp_text[:4000] + "\n...(truncated)"
        steps.append(
            TraceStep(
                index=idx,
                tool=tool,
                tool_input=inp_text or None,
                observation=obs_text or None,
                log=str(log) if log else None,
            )
        )
    return AgentTrace(steps=steps)


class OpsAgent:
    def __init__(self):
        self._loki = LokiClient(settings.loki_base_url, settings.loki_tenant_id, settings.request_timeout_s)
        
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.db_path = str(base_dir / "checkpoints.sqlite")

    async def _run_with_model(
        self,
        req: OpsRequest,
        model_name: str,
        callbacks: list | None = None,
    ) -> OpsResponse:
        start = ensure_cst(req.time_range.start)
        end = ensure_cst(req.time_range.end)
        if end <= start:
            raise ValueError("end必须大于start。")

        from app.agent.graph import build_graph
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        t0 = datetime.now(timezone.utc)
        thread_id = req.session_id
        stream_handler = callbacks[0] if callbacks else None
        config = {
            "configurable": {
                "thread_id": thread_id,
                "stream_handler": stream_handler,
            },
            "callbacks": callbacks,
        }

        async with AsyncSqliteSaver.from_conn_string(self.db_path) as saver:
            graph = build_graph().compile(checkpointer=saver, interrupt_before=["wait_for_confirmation"])
            
            state = await graph.aget_state(config)
            
            try:
                # 检查当前状态，看是否是需要继续执行 (RESUME)
                if state and state.next and state.next[0] == "wait_for_confirmation":
                    # Resuming after interrupt
                    await graph.aupdate_state(config, {"user_feedback": req.description})
                    res = await graph.ainvoke(None, config)
                elif state and not state.next:
                    # 前一个任务已经正常结束 (END)，此时用户发来了新问题
                    # 在 LangGraph 中，如果一个 thread 已经到达 END，直接 invoke 新的 input 并不会从 START 重新开始
                    # 所以我们需要给它分配一个新的内部 thread_id 以便开始全新的流程
                    new_thread_id = f"{thread_id}_{int(datetime.now().timestamp())}"
                    config["configurable"]["thread_id"] = new_thread_id
                    
                    # 构建新的 input 并保留历史记录
                    # 将上一次的 input 和 response 加入到 chat_history 中
                    from langchain_core.messages import HumanMessage, AIMessage
                    chat_history = state.values.get("chat_history", [])
                    if state.values.get("input") and state.values.get("response"):
                        chat_history.append(HumanMessage(content=state.values["input"]))
                        chat_history.append(AIMessage(content=state.values["response"]))
                    
                    agent_input = (
                        f"故障描述：{req.description}\n"
                        f"时间范围（CST，UTC+8）：{start.isoformat()} ~ {end.isoformat()}\n"
                    )
                    res = await graph.ainvoke({
                        "input": agent_input,
                        "model_name": model_name,
                        "session_id": thread_id, # 这里传回原始的，用于飞书通知
                        "chat_history": chat_history,
                    }, config)
                    
                    # 重新获取最新的状态
                    new_state = await graph.aget_state(config)
                else:
                    # New request (first time for this thread)
                    agent_input = (
                        f"故障描述：{req.description}\n"
                        f"时间范围（CST，UTC+8）：{start.isoformat()} ~ {end.isoformat()}\n"
                    )
                    res = await graph.ainvoke({
                        "input": agent_input,
                        "model_name": model_name,
                        "session_id": thread_id,
                    }, config)
            except Exception as exc:
                logging.exception("ops graph failed: %s", exc)
                raise
                
            new_state = await graph.aget_state(config)
            
        t1 = datetime.now(timezone.utc)
        
        # Check if graph interrupted
        if new_state.next and new_state.next[0] == "wait_for_confirmation":
            pending = new_state.values.get("pending_confirmation")
            if pending == "plan":
                plan = new_state.values.get("plan", [])
                plan_str = "\n".join([f"- {p}" for p in plan])
                summary = f"已为您生成执行计划，是否继续？\n\n计划内容：\n{plan_str}"
            elif pending == "step":
                step_idx = new_state.values.get("current_step_index", 0)
                plan = new_state.values.get("plan", [])
                step = plan[step_idx] if step_idx < len(plan) else "未知步骤"
                summary = f"下一步为高危操作，请确认是否执行：\n\n{step}"
            else:
                summary = "请确认是否继续执行。"
                
            resp = OpsResponse(
                summary=summary,
                ranked_root_causes=[],
                next_actions=[],
                trace=AgentTrace(steps=[]),
                model=model_name,
            )
            return resp

        # Graph finished
        raw = str(res.get("response") or "")
        try:
            out = OpsOutput.model_validate_json(raw)
        except Exception:
            logging.warning("ops output parse failed, treating as plain text")
            out = OpsOutput(summary=raw.strip(), ranked_root_causes=[], next_actions=[])
            
        # We don't have detailed trace for graph steps here easily, return empty trace or build from past_steps
        trace = AgentTrace(steps=[])
        
        resp = OpsResponse(
            summary=out.summary,
            ranked_root_causes=out.ranked_root_causes or [],
            next_actions=out.next_actions or [],
            trace=trace,
            model=model_name,
        )
        logging.info(
            "ops analyze end, model=%s, duration_s=%.3f, summary_len=%s",
            model_name,
            (t1 - t0).total_seconds(),
            len(resp.summary or ""),
        )
        return resp

    async def analyze(self, req: OpsRequest, callbacks: list | None = None) -> OpsResponse:
        logging.info(
            "ops analyze start, description_len=%s, session_id=%s, start_raw=%s, end_raw=%s, model=%s",
            len(req.description or ""),
            req.session_id,
            getattr(req.time_range, "start", None),
            getattr(req.time_range, "end", None),
            req.model or settings.default_model,
        )
        model_name = req.model or settings.default_model
        return await self._run_with_model(req, model_name, callbacks=callbacks)
