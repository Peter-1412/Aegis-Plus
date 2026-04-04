from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional
import logging
import time
import os

import ollama
from openai import OpenAI, AsyncOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from config.config import settings


class OllamaChat(BaseChatModel):
    model: str
    host: str
    streaming: bool = False
    disable_thinking: bool = True

    @property
    def _llm_type(self) -> str:
        return "ollama-chat"

    def _build_messages(self, messages: List[BaseMessage]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for m in messages:
            role = getattr(m, "type", "") or getattr(m, "role", "")
            content = str(getattr(m, "content", "") or "")
            if not content:
                continue
            if role == "system":
                items.append({"role": "system", "content": content})
            elif role in ("human", "user"):
                items.append({"role": "user", "content": content})
            elif role in ("ai", "assistant"):
                items.append({"role": "assistant", "content": content})
            else:
                items.append({"role": "user", "content": content})
        return items

    def _strip_think_block(self, text: str) -> str:
        start = text.find("<think>")
        end = text.find("</think>")
        if start != -1 and end != -1 and end > start:
            head = text[:start]
            tail = text[end + len("</think>") :]
            return (head + tail).strip()
        return text

    def _apply_stop(self, text: str, stop: Optional[List[str]]) -> str:
        if not stop:
            return text
        earliest: int | None = None
        for token in stop:
            if not token:
                continue
            idx = text.find(token)
            if idx == -1:
                continue
            if earliest is None or idx < earliest:
                earliest = idx
        if earliest is None:
            return text
        return text[:earliest].rstrip()

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        t0 = time.monotonic()
        payload_messages = self._build_messages(messages)
        logging.info(
            "llm generate start, model=%s, msg_count=%s, streaming=%s",
            self.model,
            len(payload_messages),
            self.streaming,
        )
        options: dict[str, Any] = {
            "num_predict": settings.ollama_num_predict,
            "temperature": settings.ollama_temperature,
            "top_p": settings.ollama_top_p,
        }
        client = ollama.Client(host=self.host)
        res = client.chat(
            model=self.model,
            messages=payload_messages,
            stream=False,
            options=options,
        )
        content = ""
        try:
            message = res.get("message") or {}
            content = str(message.get("content") or "")
        except Exception:
            content = ""
        content = self._strip_think_block(content)
        content = self._apply_stop(content, stop)
        generation = ChatGeneration(message=AIMessage(content=content))
        dt = time.monotonic() - t0
        logging.info(
            "llm generate done, model=%s, duration_s=%.3f, output_len=%s, content=%s",
            self.model,
            dt,
            len(content),
            content[:500].replace("\n", "\\n") + ("..." if len(content) > 500 else ""),
        )
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        t0 = time.monotonic()
        payload_messages = self._build_messages(messages)
        logging.info(
            "llm agenerate start, model=%s, msg_count=%s, streaming=%s",
            self.model,
            len(payload_messages),
            self.streaming,
        )
        options: dict[str, Any] = {
            "num_predict": settings.ollama_num_predict,
            "temperature": settings.ollama_temperature,
            "top_p": settings.ollama_top_p,
        }
        client = ollama.AsyncClient(host=self.host)
        res = await client.chat(
            model=self.model,
            messages=payload_messages,
            stream=False,
            options=options,
        )
        content = ""
        try:
            message = res.get("message") or {}
            content = str(message.get("content") or "")
        except Exception:
            content = ""
        content = self._strip_think_block(content)
        content = self._apply_stop(content, stop)
        generation = ChatGeneration(message=AIMessage(content=content))
        dt = time.monotonic() - t0
        logging.info(
            "llm agenerate done, model=%s, duration_s=%.3f, output_len=%s, content=%s",
            self.model,
            dt,
            len(content),
            content[:500].replace("\n", "\\n") + ("..." if len(content) > 500 else ""),
        )
        return ChatResult(generations=[generation])


class DoubaoChat(BaseChatModel):
    model: str
    base_url: str
    api_key: str | None
    streaming: bool = False
    thinking_enabled: bool = True
    thinking_effort: str = "high"

    @property
    def _llm_type(self) -> str:
        return "doubao-chat"

    def _build_messages(self, messages: List[BaseMessage]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for m in messages:
            role = getattr(m, "type", "") or getattr(m, "role", "")
            content = str(getattr(m, "content", "") or "")
            if not content:
                continue
            if role == "system":
                items.append({"role": "system", "content": content})
            elif role in ("human", "user"):
                items.append({"role": "user", "content": content})
            elif role in ("ai", "assistant"):
                items.append({"role": "assistant", "content": content})
            else:
                items.append({"role": "user", "content": content})
        return items

    def _format_prompt(self, messages: List[BaseMessage]) -> str:
        items = self._build_messages(messages)
        parts: list[str] = []
        for item in items:
            role = item.get("role") or "user"
            content = item.get("content") or ""
            parts.append(f"{role}: {content}")
        return "\n\n".join(parts).strip()

    def _apply_stop(self, text: str, stop: Optional[List[str]]) -> str:
        if not stop:
            return text
        earliest: int | None = None
        for token in stop:
            if not token:
                continue
            idx = text.find(token)
            if idx == -1:
                continue
            if earliest is None or idx < earliest:
                earliest = idx
        if earliest is None:
            return text
        return text[:earliest].rstrip()

    def _build_extra_body(self) -> dict[str, Any]:
        if self.thinking_enabled:
            return {"thinking": {"type": "enabled"}}
        return {"thinking": {"type": "disabled"}}

    def _extract_content(self, response: Any) -> str:
        content = ""
        try:
            content = str(getattr(response, "output_text", "") or "")
            if content:
                return content
            output = getattr(response, "output", None) or []
            for item in output:
                parts = getattr(item, "content", None) or []
                for part in parts:
                    text = getattr(part, "text", None)
                    if text:
                        content += str(text)
        except Exception:
            content = ""
        if content.strip():
            return content.strip()
        dump = None
        try:
            if hasattr(response, "model_dump"):
                dump = response.model_dump()
            elif hasattr(response, "dict"):
                dump = response.dict()
            elif isinstance(response, dict):
                dump = response
        except Exception:
            dump = None
        if isinstance(dump, dict):
            output_text = dump.get("output_text")
            if output_text:
                return str(output_text).strip()
            text_field = dump.get("text")
            if isinstance(text_field, str) and text_field.strip():
                return text_field.strip()
            if isinstance(text_field, list):
                collected_text = []
                for part in text_field:
                    if isinstance(part, dict):
                        tval = part.get("text") or part.get("content")
                    else:
                        tval = str(part)
                    if tval:
                        collected_text.append(str(tval))
                if collected_text:
                    return "".join(collected_text).strip()
            output = dump.get("output") or []
            collected = []
            for item in output:
                content_parts = None
                if isinstance(item, dict):
                    content_parts = item.get("content") or []
                else:
                    content_parts = getattr(item, "content", None) or []
                for part in content_parts:
                    if isinstance(part, dict):
                        text = part.get("text") or part.get("output_text")
                    else:
                        text = getattr(part, "text", None)
                    if text:
                        collected.append(str(text))
            if collected:
                return "".join(collected).strip()
            choices = dump.get("choices") or []
            for choice in choices:
                if isinstance(choice, dict):
                    message = choice.get("message") or {}
                    text = message.get("content") or ""
                else:
                    message = getattr(choice, "message", None) or {}
                    text = getattr(message, "content", None) or ""
                if text:
                    return str(text).strip()
            keys = list(dump.keys())
            logging.warning(
                "doubao empty output, response_keys=%s, output_items=%s",
                keys,
                len(output) if isinstance(output, list) else 0,
            )
        return ""

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        t0 = time.monotonic()
        if not self.api_key:
            raise RuntimeError("doubao api_key 未配置")
        prompt = self._format_prompt(messages)
        logging.info(
            "llm generate start, model=%s, msg_len=%s, streaming=%s",
            self.model,
            len(prompt),
            self.streaming,
        )
        client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        res = client.responses.create(
            model=self.model,
            input=prompt,
            temperature=settings.doubao_temperature,
            max_output_tokens=settings.doubao_max_tokens,
            extra_body=self._build_extra_body(),
        )
        content = self._extract_content(res)
        content = self._apply_stop(content, stop)
        generation = ChatGeneration(message=AIMessage(content=content))
        dt = time.monotonic() - t0
        logging.info(
            "llm generate done, model=%s, duration_s=%.3f, output_len=%s, content=%s",
            self.model,
            dt,
            len(content),
            content[:500].replace("\n", "\\n") + ("..." if len(content) > 500 else ""),
        )
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        t0 = time.monotonic()
        if not self.api_key:
            raise RuntimeError("doubao api_key 未配置")
        prompt = self._format_prompt(messages)
        logging.info(
            "llm agenerate start, model=%s, msg_len=%s, streaming=%s",
            self.model,
            len(prompt),
            self.streaming,
        )
        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        res = await client.responses.create(
            model=self.model,
            input=prompt,
            temperature=settings.doubao_temperature,
            max_output_tokens=settings.doubao_max_tokens,
            extra_body=self._build_extra_body(),
        )
        content = self._extract_content(res)
        content = self._apply_stop(content, stop)
        generation = ChatGeneration(message=AIMessage(content=content))
        dt = time.monotonic() - t0
        logging.info(
            "llm agenerate done, model=%s, duration_s=%.3f, output_len=%s, content=%s",
            self.model,
            dt,
            len(content),
            content[:500].replace("\n", "\\n") + ("..." if len(content) > 500 else ""),
        )
        return ChatResult(generations=[generation])


def _normalize_model_name(name: str | None) -> str:
    if not name:
        return settings.default_model
    lowered = name.strip().lower()
    if lowered in {"qwen", "glm", "deepseek", "doubao"}:
        return lowered
    return settings.default_model


def get_llm(model_name: str | None = None, streaming: bool = False, allow_thinking: bool = False) -> BaseChatModel:
    selected = _normalize_model_name(model_name)
    if selected == "doubao":
        api_key = settings.doubao_api_key or os.getenv("ARK_API_KEY")
        logging.info(
            "llm init, model=%s, base_url=%s, streaming=%s",
            settings.doubao_model,
            settings.doubao_base_url,
            streaming,
        )
        return DoubaoChat(
            model=settings.doubao_model,
            base_url=settings.doubao_base_url,
            api_key=api_key,
            streaming=streaming,
            thinking_enabled=settings.doubao_thinking_enabled,
            thinking_effort=settings.doubao_thinking_effort,
        )
    if selected == "glm":
        model = settings.ollama_glm_model
    elif selected == "deepseek":
        model = settings.ollama_deepseek_model
    else:
        model = settings.ollama_qwen_model
    logging.info(
        "llm init, model=%s, base_url=%s, streaming=%s",
        model,
        settings.ollama_base_url,
        streaming,
    )
    return OllamaChat(
        model=model,
        host=settings.ollama_base_url,
        streaming=streaming,
        disable_thinking=settings.ollama_disable_thinking and not allow_thinking,
    )


async def stream_rendered_answer(
    model_name: str | None,
    prompt: str,
    on_token: Callable[[str], Awaitable[None]],
    allow_thinking: bool = False,
) -> str:
    selected = _normalize_model_name(model_name)
    collected_parts: list[str] = []

    async def emit_token(token: str):
        if not token:
            return
        collected_parts.append(token)
        await on_token(token)

    if selected == "doubao":
        api_key = settings.doubao_api_key or os.getenv("ARK_API_KEY")
        if not api_key:
            raise RuntimeError("doubao api_key 未配置")
        client = AsyncOpenAI(base_url=settings.doubao_base_url, api_key=api_key)
        extra_body = {"thinking": {"type": "enabled" if allow_thinking and settings.doubao_thinking_enabled else "disabled"}}
        stream = await client.responses.create(
            model=settings.doubao_model,
            input=prompt,
            temperature=settings.doubao_temperature,
            max_output_tokens=settings.doubao_max_tokens,
            extra_body=extra_body,
            stream=True,
        )
        async with stream as events:
            async for event in events:
                if getattr(event, "type", "") == "response.output_text.delta":
                    await emit_token(getattr(event, "delta", "") or "")
        return "".join(collected_parts).strip()

    if selected == "glm":
        model = settings.ollama_glm_model
    elif selected == "deepseek":
        model = settings.ollama_deepseek_model
    else:
        model = settings.ollama_qwen_model

    options: dict[str, Any] = {
        "num_predict": settings.ollama_num_predict,
        "temperature": settings.ollama_temperature,
        "top_p": settings.ollama_top_p,
    }
    client = ollama.AsyncClient(host=settings.ollama_base_url)
    stream = await client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        think=False if settings.ollama_disable_thinking and not allow_thinking else None,
        options=options,
    )
    async for chunk in stream:
        message = getattr(chunk, "message", None) or {}
        token = ""
        if isinstance(message, dict):
            token = str(message.get("content") or "")
        else:
            token = str(getattr(message, "content", "") or "")
        await emit_token(token)
    return "".join(collected_parts).strip()
