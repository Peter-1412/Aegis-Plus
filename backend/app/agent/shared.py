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

class OpsStreamHandler(AsyncCallbackHandler):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.session_id = str(uuid.uuid4())
        self.step_counter = 0
        self.current_workflow_stage = "thinking"
        self.current_step_id: str | None = None

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

    async def on_llm_start(self, serialized, prompts, **kwargs):
        self.current_workflow_stage = "thinking"
        self.current_step_id = self._next_step_id()
        prompt = prompts[0] if prompts else ""
        model_name = None
        if isinstance(serialized, dict):
            model_name = serialized.get("kwargs", {}).get("model_name") or serialized.get("model_name") or serialized.get("model")
        await self._send_event(
            "llm_start",
            {
                "prompt": prompt,
                "step_id": self.current_step_id,
                "model": model_name or "unknown",
            },
        )

    async def on_llm_new_token(self, token: str, **kwargs):
        await self._send_event(
            "llm_token",
            {
                "token": token,
                "step_id": self.current_step_id,
            },
        )

    async def on_llm_end(self, response, **kwargs):
        text = ""
        try:
            generations = getattr(response, "generations", None)
            if generations:
                first = generations[0][0]
                value = getattr(first, "text", None) or getattr(first, "message", None)
                if value is not None:
                    text = str(value)
        except Exception:
            text = ""
        await self._send_event(
            "llm_end",
            {
                "response": text,
                "step_id": self.current_step_id,
            },
        )

    async def on_agent_action(self, action, **kwargs):
        tool = getattr(action, "tool", "") or ""
        tool_input = getattr(action, "tool_input", None)
        log = getattr(action, "log", None)
        thought = str(log) if log else None
        if thought:
            self.current_workflow_stage = "planning"
            self.current_step_id = self._next_step_id()
            await self._send_event(
                "agent_thought",
                {
                    "thought": thought,
                    "step_id": self.current_step_id,
                },
            )
        self.current_workflow_stage = "executing"
        if not self.current_step_id:
            self.current_step_id = self._next_step_id()
        await self._send_event(
            "agent_action",
            {
                "tool": str(tool),
                "tool_input": _stringify(tool_input),
                "log": str(log) if log else None,
                "step_id": self.current_step_id,
            },
        )

    async def on_tool_start(self, serialized, input_str, **kwargs):
        name = None
        if isinstance(serialized, dict):
            name = serialized.get("name") or serialized.get("tool")
        if not name:
            name = str(serialized)
        self.current_workflow_stage = "executing"
        self.current_step_id = self._next_step_id()
        await self._send_event(
            "tool_start",
            {
                "tool": name,
                "tool_input": _stringify(input_str),
                "step_id": self.current_step_id,
            },
        )

    async def on_tool_end(self, output, **kwargs):
        self.current_workflow_stage = "observing"
        observation = _stringify(output)
        await self._send_event(
            "tool_end",
            {
                "observation": observation,
                "step_id": self.current_step_id,
            },
        )
        await self._send_event(
            "agent_observation",
            {
                "observation": observation,
                "step_id": self.current_step_id,
            },
        )

    async def on_chain_error(self, error, **kwargs):
        await self._send_event(
            "error",
            {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "step_id": self.current_step_id,
            },
        )

