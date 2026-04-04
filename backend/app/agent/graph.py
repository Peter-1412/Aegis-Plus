from typing import TypedDict, Annotated, List, Tuple, Any, Optional
import operator
import json
import logging

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage

from app.agent.llm import get_llm
from app.agent.executor import build_executor
from app.tools import build_tools
from app.tools.loki_tool import LokiClient
from config.config import settings

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

from langchain_core.runnables.config import RunnableConfig

DIAGNOSIS_KEYWORDS = [
    "分析",
    "排查",
    "故障",
    "异常",
    "报错",
    "为什么",
    "哪里",
    "看下",
    "看看",
    "根因",
    "慢",
    "502",
    "503",
    "超时",
]


def _get_stream_handler(config: RunnableConfig):
    callbacks = config.get("callbacks") or []
    for callback in callbacks:
        if hasattr(callback, "emit_agent_thought"):
            return callback
    return None


async def _emit_thought(config: RunnableConfig, thought: str):
    handler = _get_stream_handler(config)
    if handler:
        await handler.emit_agent_thought(thought)


def _looks_complex_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in DIAGNOSIS_KEYWORDS)

async def classify_task(state: AgentState, config: RunnableConfig) -> dict:
    current_input = state.get("input", "")
    if _looks_complex_request(current_input):
        await _emit_thought(config, "识别到故障排查类请求，进入多步诊断流程。")
        return {"task_type": "complex"}

    llm = get_llm(state["model_name"])
    
    # 构建包含历史记录的 prompt
    history_text = ""
    if state.get("chat_history"):
        history_text = "历史对话：\n" + "\n".join([f"{m.type}: {m.content}" for m in state["chat_history"][-4:]]) + "\n\n"

    prompt = (
        "你是一个智能运维助手。请分析以下用户的请求，判断它是需要多步排查和规划的复杂任务，还是只需单次查询或简单回复的简单任务。\n"
        "如果包含'查一下'、'获取'、'打招呼'等简单指令且不涉及多服务或深层根因，则是 simple。\n"
        "如果是'分析故障'、'为什么'、'根因'、'排查'等，则是 complex。\n"
        f"{history_text}"
        f"当前请求：{state['input']}\n"
        "只需回答 'simple' 或 'complex'。"
    )
    try:
        res = await llm.ainvoke(prompt, config=config)
        task_type = res.content.strip().lower()
        if "complex" in task_type:
            task_type = "complex"
        else:
            task_type = "simple"
    except Exception as e:
        logging.warning(f"Classify failed, fallback to complex: {e}")
        task_type = "complex"
        
    return {"task_type": task_type}

def route_after_classify(state: AgentState) -> str:
    return "react_agent" if state.get("task_type") == "simple" else "planner"

async def react_agent_node(state: AgentState, config: RunnableConfig) -> dict:
    loki = LokiClient(settings.loki_base_url, settings.loki_tenant_id, settings.request_timeout_s)
    tools = build_tools(loki)
    llm = get_llm(state["model_name"])
    
    # 构建一个虚拟的 Memory 对象来传递 chat_history
    from langchain.memory import ConversationBufferMemory
    memory = None
    if state.get("chat_history"):
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        memory.chat_memory.messages = state["chat_history"]

    executor = build_executor(llm, memory)
    
    await _emit_thought(config, "开始执行单轮查询，优先使用工具收集可验证证据。")
    res = await executor.ainvoke(
        {
            "input": (
                f"{state['input']}\n\n"
                "要求：如果请求涉及系统状态、日志、指标、链路或故障原因，必须先调用至少一个工具，"
                "不要直接凭经验作答。"
            )
        },
        config=config,
    )
    return {"response": res.get("output", "")}

async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    llm = get_llm(state["model_name"])
    await _emit_thought(config, "正在生成排查计划，随后会按步骤调用工具收集证据。")
    
    if state.get("past_steps"):
        context = "\n".join([f"步骤: {s}\n结果: {r}" for s, r in state["past_steps"]])
        prompt = (
            "你是一个高级运维专家。之前的排查计划在执行中遇到失败，请根据已有进展，重新生成后续的排查计划。\n"
            "要求：\n"
            "1. 每行一个步骤，不要有额外内容或编号前缀。\n"
            "2. 步骤要具体、可执行。\n"
            f"初始请求：{state['input']}\n\n"
            f"已执行的步骤和结果：\n{context}\n\n"
            "请给出下一步及之后的排查计划："
        )
    else:
        prompt = (
            "你是一个高级运维专家。请为以下运维请求生成一个分步执行的排查计划。\n"
            "要求：\n"
            "1. 每行一个步骤，不要有额外内容或编号前缀（如 1. 2. 等，只需文字描述）。\n"
            "2. 步骤要具体、可执行。\n"
            f"请求：{state['input']}"
        )
        
    res = await llm.ainvoke(prompt, config=config)
    plan = [line.strip().lstrip("0123456789.-* ") for line in res.content.split("\n") if line.strip()]
    if plan:
        await _emit_thought(config, f"已生成 {len(plan)} 个排查步骤，开始依次执行。")
    
    # 如果是飞书会话，主动发送一条消息告知计划，但不中断执行
    chat_id = state.get("session_id", "")
    if chat_id.startswith("ou_") or chat_id.startswith("oc_"):
        try:
            from app.interface.feishu_client import feishu_client
            import asyncio
            plan_str = "\n".join([f"- {p}" for p in plan])
            msg = f"已为您生成排查计划，正在自动执行中...\n\n计划内容：\n{plan_str}"
            asyncio.create_task(feishu_client.send_text_message(chat_id=chat_id, text=msg))
        except Exception as e:
            logging.error(f"Failed to send plan to feishu: {e}")

    return {"plan": plan, "current_step_index": 0, "pending_confirmation": ""}

def route_after_planner(state: AgentState) -> str:
    # 直接进入执行阶段，不再中断等待计划确认
    return "execute_step"

async def execute_step_node(state: AgentState, config: RunnableConfig) -> dict:
    if state["current_step_index"] >= len(state["plan"]):
        return {"user_feedback": "", "pending_confirmation": ""}

    step = state["plan"][state["current_step_index"]]
    await _emit_thought(config, f"开始执行步骤：{step}")
    
    # If user provided feedback
    if state.get("user_feedback"):
        feedback = state["user_feedback"].strip().lower()
        logging.info(f"User feedback received: {feedback}")
        
        if state.get("pending_confirmation") == "plan":
            if "不" in feedback or "no" in feedback or "停止" in feedback or "取消" in feedback:
                return {
                    "user_feedback": "",
                    "pending_confirmation": "",
                    "current_step_index": len(state["plan"]) # Skip all steps
                }
            else:
                # Plan confirmed, clear feedback, but continue to evaluate step
                state["user_feedback"] = ""
                state["pending_confirmation"] = ""
        elif state.get("pending_confirmation") == "step":
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

    loki = LokiClient(settings.loki_base_url, settings.loki_tenant_id, settings.request_timeout_s)
    tools = build_tools(loki)
    llm = get_llm(state["model_name"])
    executor = build_executor(llm, None)
    
    context = "\n".join([f"步骤: {s}\n结果: {r}" for s, r in state.get("past_steps", [])])
    prompt = (
        f"初始请求: {state['input']}\n\n"
        f"之前执行的步骤和结果:\n{context}\n\n"
        f"当前需执行的步骤: {step}\n"
        "要求：\n"
        "1. 必须调用至少一个最相关的工具来收集证据，不允许直接凭空回答。\n"
        "2. 若一个工具不够，请继续调用后再总结结果。\n"
        "3. 返回内容应基于工具结果，简洁说明执行结果和证据。\n"
        "请执行该步骤，并返回执行结果。"
    )
    
    try:
        res = await executor.ainvoke({"input": prompt}, config=config)
        result = res.get("output", "")
    except Exception as e:
        result = f"执行失败: {e}"
        
    return {
        "past_steps": [(step, result)],
        "current_step_index": state["current_step_index"] + 1,
        "pending_confirmation": "",
        "user_feedback": ""
    }

def route_after_execute(state: AgentState) -> str:
    if state.get("pending_confirmation") == "step":
        return "wait_for_confirmation"
        
    # Check if last step failed, if so, replan
    if state.get("past_steps"):
        last_step, last_result = state["past_steps"][-1]
        if "执行失败" in last_result or "失败" in last_result:
            # simple fallback: go back to planner to replan
            # In a real scenario we might have a dedicated 'replanner' node
            return "planner"

    if state["current_step_index"] >= len(state["plan"]):
        return "generate_report"
    return "execute_step"

async def generate_report_node(state: AgentState, config: RunnableConfig) -> dict:
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
