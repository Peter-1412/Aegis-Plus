import asyncio
import contextvars
import json
import uuid
from datetime import datetime, timezone
from langchain_core.callbacks import AsyncCallbackHandler

from app.agent.ops_agent import OpsAgent

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
ops_agent = OpsAgent()

def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _classify_tool_result(text: str, *, failed: bool = False) -> tuple[str, str]:
    lowered = (text or "").lower()
    connectivity_markers = [
        "prometheus_request_failed",
        "jaeger_request_failed",
        "connection refused",
        "failed to establish a new connection",
        "name or service not known",
        "nodename nor servname provided",
        "temporary failure in name resolution",
        "timed out",
        "timeout",
        "k8s client not initialized",
        "无法连接到 kubernetes 集群",
        "failed to load kubernetes config",
    ]
    if any(marker in lowered for marker in connectivity_markers):
        return "connectivity_blocked", "基础环境不可达或网络未连通"
    if failed:
        return "runtime_error", "工具执行失败"
    if "error" in lowered or '"error"' in lowered:
        return "runtime_error", "工具返回错误结果"
    if "no events found" in lowered or "no data" in lowered or '"series": []' in lowered:
        return "no_data", "工具返回为空或未找到数据"
    return "ok", "工具返回有效结果"

class OpsStreamHandler(AsyncCallbackHandler):
    def __init__(self, queue: asyncio.Queue, assistant_message_id: str | None = None):
        self.queue = queue
        self.assistant_message_id = assistant_message_id
        self.session_id = str(uuid.uuid4())
        self.step_counter = 0
        self.current_workflow_stage = "thinking"
        self.current_step_id: str | None = None
        self.pending_tool_step_id: str | None = None
        self.pending_tool_name: str | None = None
        self.pending_tool_input: str | None = None
        self.last_assistant_preview: str = ""

    def _next_step_id(self) -> str:
        self.step_counter += 1
        return f"step-{self.step_counter}"

    async def _send_event(self, event_type: str, data: dict, workflow_stage: str | None = None):
        payload = {
            "event": event_type,
            "event_type": event_type,
            "workflow_stage": workflow_stage or self.current_workflow_stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
        }
        payload.update(data)
        await self.queue.put(payload)

    async def _emit_assistant_preview(self, text: str):
        preview = (text or "").strip()
        if not preview or not self.assistant_message_id:
            return
        preview = preview.splitlines()[0].strip()
        if preview.lower().startswith("thought:"):
            preview = preview[8:].strip()
        if preview == self.last_assistant_preview:
            return
        self.last_assistant_preview = preview
        await self._send_event(
            "assistant_message_preview",
            {
                "message_id": self.assistant_message_id,
                "delta": preview,
            },
        )

    async def emit_agent_thought(self, thought: str):
        self.current_workflow_stage = "planning"
        thought_step_id = self._next_step_id()
        await self._send_event(
            "thought_summary",
            {
                "thought": thought,
                "step_id": thought_step_id,
                "title": "思路摘要",
            },
        )
        await self._emit_assistant_preview(thought)

    async def on_agent_action(self, action, **kwargs):
        tool = getattr(action, "tool", "") or ""
        tool_input = getattr(action, "tool_input", None)
        log = getattr(action, "log", None)
        thought = str(log) if log else None
        if thought:
            await self.emit_agent_thought(thought)
        self.current_workflow_stage = "executing"
        self.pending_tool_step_id = self._next_step_id()
        self.pending_tool_name = str(tool)
        self.pending_tool_input = _stringify(tool_input)
        self.current_step_id = self.pending_tool_step_id
        await self._send_event(
            "tool_call_started",
            {
                "tool": self.pending_tool_name,
                "tool_input": self.pending_tool_input,
                "step_id": self.pending_tool_step_id,
                "status": "started",
            },
        )
        await self._emit_assistant_preview(f"正在准备调用工具：{self.pending_tool_name}")

    async def on_tool_start(self, serialized, input_str, **kwargs):
        name = None
        if isinstance(serialized, dict):
            name = serialized.get("name") or serialized.get("tool")
        if not name:
            name = str(serialized)
        self.current_workflow_stage = "executing"
        step_id = self.pending_tool_step_id or self._next_step_id()
        tool_input = self.pending_tool_input or _stringify(input_str)
        self.current_step_id = step_id
        await self._send_event(
            "tool_call_running",
            {
                "tool": self.pending_tool_name or name,
                "tool_input": tool_input,
                "step_id": step_id,
                "status": "running",
            },
        )
        await self._emit_assistant_preview(f"正在调用工具：{self.pending_tool_name or name}")

    async def on_tool_end(self, output, **kwargs):
        self.current_workflow_stage = "observing"
        observation = _stringify(output)
        step_id = self.current_step_id or self.pending_tool_step_id
        result_state, result_summary = _classify_tool_result(observation)
        await self._send_event(
            "tool_call_completed",
            {
                "tool": self.pending_tool_name or "",
                "observation": observation,
                "step_id": step_id,
                "status": "completed",
                "result_state": result_state,
                "result_summary": result_summary,
            },
        )
        await self._emit_assistant_preview(f"已完成工具调用：{self.pending_tool_name or ''}。{result_summary}")
        self.pending_tool_step_id = None
        self.pending_tool_name = None
        self.pending_tool_input = None

    async def on_chain_error(self, error, **kwargs):
        error_text = str(error)
        result_state, result_summary = _classify_tool_result(error_text, failed=True)
        await self._send_event(
            "tool_call_failed" if self.pending_tool_step_id else "error",
            {
                "tool": self.pending_tool_name or "",
                "error_type": type(error).__name__,
                "error_message": error_text,
                "step_id": self.current_step_id,
                "status": "failed",
                "result_state": result_state,
                "result_summary": result_summary,
            },
        )
        if self.pending_tool_name:
            await self._emit_assistant_preview(f"工具调用失败：{self.pending_tool_name}。{result_summary}")

