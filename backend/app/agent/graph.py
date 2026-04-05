from typing import TypedDict, Annotated, List, Tuple
import operator
import json
import logging

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage

from app.agent.llm import get_llm
from app.agent.executor import build_executor

class AgentState(TypedDict):
    input: str
    task_type: str
    plan: List[str]
    current_step_index: int
    past_steps: Annotated[List[Tuple[str, str]], operator.add]
    response: str
    session_id: str
    model_name: str
    pending_confirmation: str # "plan" or "step"
    user_feedback: str
    chat_history: List[BaseMessage] # Added to retain multi-turn context
    abort_reason: str

from langchain_core.runnables.config import RunnableConfig

DEEP_DIVE_KEYWORDS = [
    "继续排查",
    "继续分析",
    "继续深挖",
    "深入排查",
    "深入分析",
    "详细排查",
    "进一步排查",
    "进一步分析",
    "继续查",
    "深挖",
    "深入",
]

CONNECTIVITY_ERROR_MARKERS = [
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


def _get_stream_handler(config: RunnableConfig):
    configurable = config.get("configurable") or {}
    stream_handler = configurable.get("stream_handler")
    if stream_handler and hasattr(stream_handler, "emit_agent_thought"):
        return stream_handler

    callbacks = config.get("callbacks")
    if callbacks is None:
        callback_list = []
    elif isinstance(callbacks, (list, tuple)):
        callback_list = list(callbacks)
    elif hasattr(callbacks, "handlers"):
        callback_list = list(getattr(callbacks, "handlers") or [])
    else:
        callback_list = [callbacks]
    for callback in callback_list:
        if hasattr(callback, "emit_agent_thought"):
            return callback
    return None


async def _emit_thought(config: RunnableConfig, thought: str):
    handler = _get_stream_handler(config)
    if handler:
        await handler.emit_agent_thought(thought)


def _stringify_observation(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _detect_connectivity_blocker(intermediate_steps) -> str | None:
    for pair in intermediate_steps or []:
        try:
            action, observation = pair
        except Exception:
            continue
        tool_name = str(getattr(action, "tool", "") or "未知工具")
        observation_text = _stringify_observation(observation)
        lowered = observation_text.lower()
        if any(marker in lowered for marker in CONNECTIVITY_ERROR_MARKERS):
            return f"{tool_name} 无法访问基础环境，可能未连接 VPN、未配置 kubeconfig，或监控/链路服务不可达。"
    return None


def _build_abort_response(summary: str, next_actions: list[str]) -> str:
    return json.dumps(
        {
            "summary": summary,
            "ranked_root_causes": [],
            "next_actions": next_actions,
        },
        ensure_ascii=False,
    )


def _looks_deep_dive_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in DEEP_DIVE_KEYWORDS)


def _detect_execution_failure(text: str | None) -> str | None:
    lowered = (text or "").lower()
    if not lowered:
        return None
    if "could not parse llm output" in lowered or "output_parsing_failure" in lowered:
        return "模型返回了不可解析的工具调用格式，当前节点已停止。"
    if "执行失败" in text or "失败" in text:
        return text or "当前工具节点执行失败。"
    return None

async def classify_task(state: AgentState, config: RunnableConfig) -> dict:
    current_input = state.get("input", "")
    if _looks_deep_dive_request(current_input):
        await _emit_thought(config, "识别到用户要求继续深挖，进入下一轮计划。")
        return {"task_type": "deep_dive"}
    await _emit_thought(config, "优先按单轮工具查询处理当前请求。")
    return {"task_type": "direct"}

def route_after_classify(state: AgentState) -> str:
    return "planner" if state.get("task_type") == "deep_dive" else "react_agent"

async def react_agent_node(state: AgentState, config: RunnableConfig) -> dict:
    llm = get_llm(state["model_name"])
    
    # 构建一个虚拟的 Memory 对象来传递 chat_history
    from langchain.memory import ConversationBufferMemory
    memory = None
    if state.get("chat_history"):
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        memory.chat_memory.messages = state["chat_history"]

    executor = build_executor(llm, memory)
    
    await _emit_thought(config, "开始执行单轮查询，优先使用最相关的工具收集证据。")
    try:
        res = await executor.ainvoke(
            {
                "input": (
                    f"{state['input']}\n\n"
                    "要求：\n"
                    "1. 优先只调用一个最相关的工具完成当前查询。\n"
                    "2. 只有第一个工具结果明显不足时，才允许追加下一个工具。\n"
                    "3. 如果工具失败、环境不可达或输出无法解析，立即停止当前节点并说明失败原因。\n"
                    "4. 不要自行扩展为多步排查计划。"
                )
            },
            config=config,
        )
    except Exception as exc:
        blocker = _detect_connectivity_blocker([(None, str(exc))]) or _detect_execution_failure(str(exc))
        if blocker:
            await _emit_thought(config, f"当前节点失败，停止继续调用工具。{blocker}")
            return {
                "response": _build_abort_response(
                    f"当前节点已停止。{blocker}",
                    [
                        "根据上面的失败原因修复环境或调整提问。",
                        "如果你希望我继续深挖，请在下一轮明确说明“继续排查”或“继续深挖”。",
                    ],
                ),
                "abort_reason": blocker,
            }
        raise
    blocker = (
        _detect_connectivity_blocker(res.get("intermediate_steps"))
        or _detect_connectivity_blocker([(None, res.get("output", ""))])
        or _detect_execution_failure(res.get("output", ""))
    )
    if blocker:
        await _emit_thought(config, f"当前节点失败，停止继续调用工具。{blocker}")
        return {
            "response": _build_abort_response(
                f"当前节点已停止。{blocker}",
                [
                    "根据上面的失败原因修复环境或调整提问。",
                    "如果你希望我继续深挖，请在下一轮明确说明“继续排查”或“继续深挖”。",
                ],
            ),
            "abort_reason": blocker,
        }
    return {"response": res.get("output", "")}

async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    llm = get_llm(state["model_name"])
    await _emit_thought(config, "正在生成下一轮深挖计划，本轮只推进一步。")
    
    context = ""
    if state.get("chat_history"):
        context = "\n".join([f"{m.type}: {m.content}" for m in state["chat_history"][-6:]])
    prompt = (
        "你是一个高级运维专家。用户明确要求继续深挖，请只生成“下一步最有价值的一步排查动作”。\n"
        "要求：\n"
        "1. 只输出一行，不要编号，不要多步骤。\n"
        "2. 这一步必须是可以直接执行的排查动作。\n"
        "3. 不要生成完整多步计划。\n"
        f"当前请求：{state['input']}\n"
        f"历史上下文：\n{context}"
    )
        
    res = await llm.ainvoke(prompt, config=config)
    plan = [line.strip().lstrip("0123456789.-* ") for line in res.content.split("\n") if line.strip()][:1]
    if plan:
        await _emit_thought(config, "已生成下一步深挖动作，开始执行本轮唯一一步。")
        return {"plan": plan, "current_step_index": 0, "pending_confirmation": "", "abort_reason": ""}
    return {
        "response": _build_abort_response(
            "当前未能生成可执行的下一步深挖动作。",
            [
                "请补充更明确的目标，例如服务名、时间范围或错误现象。",
                "如果只需要当前结果，请直接基于现有答案处理。",
            ],
        ),
        "abort_reason": "未生成可执行步骤",
    }

def route_after_planner(state: AgentState) -> str:
    return "generate_report" if state.get("abort_reason") else "execute_step"

async def execute_step_node(state: AgentState, config: RunnableConfig) -> dict:
    if state["current_step_index"] >= len(state["plan"]):
        return {"user_feedback": "", "pending_confirmation": ""}

    step = state["plan"][state["current_step_index"]]
    await _emit_thought(config, f"开始执行步骤：{step}")
    
    if state.get("user_feedback"):
        feedback = state["user_feedback"].strip().lower()
        logging.info(f"User feedback received: {feedback}")
        if state.get("pending_confirmation") == "step":
            if "不" in feedback or "no" in feedback or "停止" in feedback or "取消" in feedback:
                return {
                    "user_feedback": "",
                    "pending_confirmation": "",
                    "past_steps": [(step, f"被用户拒绝执行。原因：{feedback}")],
                    "current_step_index": state["current_step_index"] + 1
                }
            else:
                state["pending_confirmation"] = "step_confirmed" # Bypass risk check

    # Simple High risk check (移除了容易误判的词如“应用”，增加了“scale”、“缩放”)
    is_high_risk = any(keyword in step.lower() for keyword in ["重启", "删除", "修改", "kill", "delete", "restart", "update", "scale", "扩容", "缩容"])
    if is_high_risk and state.get("pending_confirmation") != "step_confirmed":
        return {"pending_confirmation": "step", "user_feedback": ""}

    llm = get_llm(state["model_name"])
    executor = build_executor(llm, None)
    
    context = "\n".join([f"步骤: {s}\n结果: {r}" for s, r in state.get("past_steps", [])])
    prompt = (
        f"初始请求: {state['input']}\n\n"
        f"之前执行的步骤和结果:\n{context}\n\n"
        f"当前需执行的步骤: {step}\n"
        "要求：\n"
        "1. 优先调用一个最相关的工具完成这一轮深挖。\n"
        "2. 如果工具失败、环境不可达或输出不可解析，立即停止当前节点。\n"
        "3. 不要扩展为新的多步计划。\n"
        "4. 返回内容应基于工具结果，简洁说明执行结果和证据。\n"
        "请执行该步骤，并返回执行结果。"
    )
    
    try:
        res = await executor.ainvoke({"input": prompt}, config=config)
        result = res.get("output", "")
        blocker = _detect_connectivity_blocker(res.get("intermediate_steps")) or _detect_connectivity_blocker([(None, result)])
        failure = _detect_execution_failure(result)
        blocker = blocker or failure
        if blocker:
            await _emit_thought(config, f"当前节点失败，停止本轮深挖。{blocker}")
            return {
                "past_steps": [(step, result or blocker)],
                "current_step_index": len(state["plan"]),
                "pending_confirmation": "",
                "user_feedback": "",
                "abort_reason": blocker,
            }
    except Exception as e:
        result = f"执行失败: {e}"
        blocker = _detect_connectivity_blocker([(None, result)]) or _detect_execution_failure(result)
        if blocker:
            await _emit_thought(config, f"当前节点失败，停止本轮深挖。{blocker}")
            return {
                "past_steps": [(step, result)],
                "current_step_index": len(state["plan"]),
                "pending_confirmation": "",
                "user_feedback": "",
                "abort_reason": blocker,
            }
        
    return {
        "past_steps": [(step, result)],
        "current_step_index": len(state["plan"]),
        "pending_confirmation": "",
        "user_feedback": "",
        "abort_reason": "",
    }

def route_after_execute(state: AgentState) -> str:
    if state.get("pending_confirmation") == "step":
        return "wait_for_confirmation"
    return "generate_report"

async def generate_report_node(state: AgentState, config: RunnableConfig) -> dict:
    if state.get("abort_reason"):
        return {
            "response": _build_abort_response(
                f"当前节点已停止。{state['abort_reason']}",
                [
                    "根据上面的失败原因修复环境或调整提问。",
                    "如果你希望我继续深挖，请在下一轮明确说明“继续排查”或“继续深挖”。",
                ],
            )
        }

    llm = get_llm(state["model_name"])
    context = "\n".join([f"步骤: {s}\n结果: {r}" for s, r in state.get("past_steps", [])])
    prompt = (
        "根据以下执行步骤和结果，生成最终的运维排查报告，给出结论和建议。\n\n"
        f"初始请求：{state['input']}\n"
        f"执行过程：\n{context}\n\n"
        "请严格输出符合以下 JSON Schema 的字符串（不要用 markdown 包裹，只输出纯 JSON）：\n"
        "{\n"
        '  "summary": "根因总结",\n'
        '  "ranked_root_causes": [{"rank": 1, "description": "原因", "probability": 0.9, "service": "服务名"}],\n'
        '  "next_actions": ["修复建议1", "修复建议2"]\n'
        "}"
    )
    res = await llm.ainvoke(prompt, config=config)
    return {"response": res.content}

async def wait_for_confirmation_node(state: AgentState) -> dict:
    # Dummy node to act as an interruption point
    return {}

def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("classify", classify_task)
    workflow.add_node("react_agent", react_agent_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("execute_step", execute_step_node)
    workflow.add_node("generate_report", generate_report_node)
    workflow.add_node("wait_for_confirmation", wait_for_confirmation_node)
    
    workflow.add_edge(START, "classify")
    workflow.add_conditional_edges("classify", route_after_classify)
    workflow.add_edge("react_agent", END)
    workflow.add_conditional_edges("planner", route_after_planner)
    
    # After waiting, user resumes the graph, it should go to execute_step
    workflow.add_edge("wait_for_confirmation", "execute_step")
    
    workflow.add_conditional_edges("execute_step", route_after_execute)
    workflow.add_edge("generate_report", END)
    
    return workflow
