import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentRootCause, AgentTimelineItem } from '../types';

export interface StreamAgentMessage {
  id: string;
  role: 'AGENT';
  content: string;
  createdAt: string;
  summary?: string;
  ranked_root_causes: AgentRootCause[];
  next_actions: string[];
  timeline: AgentTimelineItem[];
  statusText?: string;
  isTyping?: boolean;
}

function createDraftMessage(id: string): StreamAgentMessage {
  return {
    id,
    role: 'AGENT',
    content: '',
    createdAt: new Date().toISOString(),
    ranked_root_causes: [],
    next_actions: [],
    timeline: [],
    statusText: '正在准备分析...',
    isTyping: false,
  };
}

function takePlaybackChunk(buffer: string) {
  if (!buffer) return '';
  const sentenceLikeChunk = buffer.match(/^[^\n。！？；，,]{1,3}[。！？；，,\n]?/);
  if (sentenceLikeChunk) return sentenceLikeChunk[0];
  return buffer.slice(0, 2);
}

function appendPreviewStatus(existing: string | undefined, incoming: string) {
  const next = incoming.trim();
  if (!next) return (existing || '').trim();
  const current = (existing || '').trim();
  if (!current || current === '正在生成回答...') return next;
  const lines = current.split('\n').map((line) => line.trim()).filter(Boolean);
  if (lines[lines.length - 1] === next) return current;
  return `${current}\n${next}`;
}

export function useOpsAgentStream() {
  const [isLoading, setIsLoading] = useState(false);
  const [draftMessage, setDraftMessage] = useState<StreamAgentMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);
  const pendingContentRef = useRef('');
  const playbackTimerRef = useRef<number | null>(null);
  const streamEndedRef = useRef(false);
  const finalContentRef = useRef('');
  const activeDraftIdRef = useRef('');
  const hasAssistantStreamRef = useRef(false);
  const playbackSettledResolverRef = useRef<(() => void) | null>(null);

  const resolvePlaybackSettled = useCallback(() => {
    if (playbackSettledResolverRef.current) {
      playbackSettledResolverRef.current();
      playbackSettledResolverRef.current = null;
    }
  }, []);

  const stopPlayback = useCallback(() => {
    if (playbackTimerRef.current !== null) {
      window.clearTimeout(playbackTimerRef.current);
      playbackTimerRef.current = null;
    }
  }, []);

  const drainPlayback = useCallback(() => {
    if (playbackTimerRef.current !== null) return;

    const step = () => {
      const chunk = takePlaybackChunk(pendingContentRef.current);
      if (!chunk) {
        playbackTimerRef.current = null;
        if (streamEndedRef.current) {
          setDraftMessage((prev) =>
            prev && prev.id === activeDraftIdRef.current
              ? {
                  ...prev,
                  content: finalContentRef.current || prev.content,
                  statusText: '',
                  isTyping: false,
                }
              : prev,
          );
          resolvePlaybackSettled();
        }
        return;
      }

      pendingContentRef.current = pendingContentRef.current.slice(chunk.length);
      setDraftMessage((prev) =>
        prev && prev.id === activeDraftIdRef.current
          ? {
              ...prev,
              content: `${prev.content}${chunk}`,
              isTyping: true,
            }
          : prev,
      );

      playbackTimerRef.current = window.setTimeout(step, chunk.length <= 1 ? 22 : 30);
    };

    playbackTimerRef.current = window.setTimeout(step, 16);
  }, [resolvePlaybackSettled]);

  useEffect(() => {
    return () => {
      stopPlayback();
    };
  }, [stopPlayback]);

  const analyze = useCallback(async (description: string, sessionId?: number) => {
    const initialDraftId = `draft-${Date.now()}`;
    activeDraftIdRef.current = initialDraftId;
    pendingContentRef.current = '';
    streamEndedRef.current = false;
    finalContentRef.current = '';
    hasAssistantStreamRef.current = false;
    stopPlayback();
    setIsLoading(true);
    setDraftMessage(createDraftMessage(initialDraftId));
    setError(null);
    setCurrentSessionId(null);

    try {
      const response = await fetch('/api/agent/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message: description, sessionId }),
      });

      if (!response.ok) {
        throw new Error(`请求失败: ${response.status}`);
      }
      if (!response.body) {
        throw new Error('当前浏览器不支持 ReadableStream');
      }

      const returnedSessionId = response.headers.get('X-Session-ID');
      let newSessionId = sessionId;
      if (returnedSessionId) {
        newSessionId = parseInt(returnedSessionId, 10);
        setCurrentSessionId(newSessionId);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      const playbackSettledPromise = new Promise<void>((resolve) => {
        playbackSettledResolverRef.current = resolve;
      });

      const ensureDraft = (updater: (draft: StreamAgentMessage) => StreamAgentMessage) => {
        setDraftMessage((prev) => updater(prev ?? createDraftMessage(initialDraftId)));
      };

      const upsertTimeline = (
        draft: StreamAgentMessage,
        item: AgentTimelineItem,
      ): StreamAgentMessage => {
        const existingIndex = draft.timeline.findIndex((timelineItem) => timelineItem.id === item.id);
        if (existingIndex === -1) {
          return { ...draft, timeline: [...draft.timeline, item] };
        }
        const nextTimeline = [...draft.timeline];
        nextTimeline[existingIndex] = { ...nextTimeline[existingIndex], ...item } as AgentTimelineItem;
        return { ...draft, timeline: nextTimeline };
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const data = JSON.parse(line);

            switch (data.event) {
              case 'thought_summary':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.step_id || crypto.randomUUID(),
                    kind: 'thought_summary',
                    title: data.title || '思路摘要',
                    content: data.thought || '',
                    phase: data.workflow_stage || 'planning',
                    status: 'completed',
                  }),
                  statusText: draft.content ? draft.statusText : data.thought || draft.statusText,
                }));
                break;

              case 'tool_call_started':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.step_id || crypto.randomUUID(),
                    kind: 'tool_call',
                    toolName: data.tool || '',
                    inputText: data.tool_input || '',
                    outputText: '',
                    meta: data.meta || {},
                    resultState: data.result_state,
                    resultSummary: data.result_summary,
                    status: data.status || 'started',
                  }),
                  statusText: draft.content ? draft.statusText : (data.tool ? `正在准备调用工具：${data.tool}` : draft.statusText),
                }));
                break;

              case 'tool_call_running':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.step_id || crypto.randomUUID(),
                    kind: 'tool_call',
                    toolName: data.tool || '',
                    inputText: data.tool_input || '',
                    meta: data.meta || {},
                    resultState: data.result_state,
                    resultSummary: data.result_summary,
                    status: 'running',
                  }),
                  statusText: draft.content ? draft.statusText : (data.tool ? `正在调用工具：${data.tool}` : draft.statusText),
                }));
                break;

              case 'tool_call_completed':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.step_id || crypto.randomUUID(),
                    kind: 'tool_call',
                    toolName: data.tool || '',
                    outputText: data.observation || '',
                    resultState: data.result_state || 'ok',
                    resultSummary: data.result_summary,
                    status: 'completed',
                  }),
                  statusText: draft.content ? draft.statusText : (data.tool ? `已完成工具调用：${data.tool}` : draft.statusText),
                }));
                break;

              case 'tool_call_failed':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.step_id || crypto.randomUUID(),
                    kind: 'tool_call',
                    toolName: data.tool || '',
                    outputText: data.error_message || data.message || '执行失败',
                    resultState: data.result_state || 'runtime_error',
                    resultSummary: data.result_summary,
                    status: 'failed',
                  }),
                  statusText: data.tool ? `工具调用失败：${data.tool}` : '工具调用失败',
                }));
                break;

              case 'node_failure':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.node_id || data.step_id || crypto.randomUUID(),
                    kind: 'node_failure',
                    title: data.title || '当前节点失败',
                    message: data.message || '当前节点已停止。',
                    detail: data.detail || '',
                    status: 'failed',
                  }),
                  statusText: data.message || '当前节点已停止。',
                  isTyping: false,
                }));
                break;

              case 'assistant_message_start':
                hasAssistantStreamRef.current = true;
                pendingContentRef.current = '';
                streamEndedRef.current = false;
                finalContentRef.current = '';
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                  content: draft.content,
                  statusText: draft.statusText || '正在生成回答...',
                  isTyping: true,
                }));
                break;

              case 'assistant_message_preview':
                ensureDraft((draft) => {
                  const previewDelta = String(data.delta || '').trim();
                  if (!previewDelta || draft.content) {
                    return {
                      ...draft,
                      id: data.message_id || draft.id,
                      isTyping: true,
                    };
                  }
                  return {
                    ...draft,
                    id: data.message_id || draft.id,
                    statusText: appendPreviewStatus(draft.statusText, previewDelta),
                    isTyping: true,
                  };
                });
                break;

              case 'assistant_message_delta':
                pendingContentRef.current += data.delta || '';
                drainPlayback();
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                  statusText: '',
                  isTyping: true,
                }));
                break;

              case 'assistant_message_end':
                streamEndedRef.current = true;
                finalContentRef.current = data.content || '';
                if (!pendingContentRef.current) {
                  ensureDraft((draft) => ({
                    ...draft,
                    id: data.message_id || draft.id,
                    content: data.content || draft.content,
                    statusText: '',
                    isTyping: false,
                  }));
                  resolvePlaybackSettled();
                } else {
                  drainPlayback();
                }
                break;

              case 'final':
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                  content: draft.content,
                  summary: data.summary || '',
                  ranked_root_causes: data.ranked_root_causes || [],
                  next_actions: data.next_actions || [],
                  timeline: Array.isArray(data.timeline) ? data.timeline : draft.timeline,
                }));
                break;

              case 'error':
                ensureDraft((draft) => ({
                  ...upsertTimeline(draft, {
                    id: data.step_id || `node-error-${Date.now()}`,
                    kind: 'node_failure',
                    title: '当前节点失败',
                    message: data.message || data.error_message || '分析失败',
                    detail: data.error_message || data.message || '',
                    status: 'failed',
                  }),
                  statusText: data.message || data.error_message || '分析失败',
                  isTyping: false,
                }));
                pendingContentRef.current = '';
                streamEndedRef.current = true;
                finalContentRef.current = '';
                stopPlayback();
                resolvePlaybackSettled();
                setError(data.message || data.error_message || '分析失败');
                break;
            }
          } catch (parseError) {
            console.error('解析 NDJSON 失败:', line, parseError);
          }
        }
      }

      if (hasAssistantStreamRef.current) {
        await playbackSettledPromise;
      } else {
        resolvePlaybackSettled();
      }

      return newSessionId;
    } catch (err) {
      resolvePlaybackSettled();
      const message = err instanceof Error ? err.message : '网络请求异常';
      setError(message);
      return sessionId;
    } finally {
      setIsLoading(false);
    }
  }, [drainPlayback, stopPlayback]);

  const clear = useCallback(() => {
    stopPlayback();
    pendingContentRef.current = '';
    streamEndedRef.current = false;
    finalContentRef.current = '';
    hasAssistantStreamRef.current = false;
    resolvePlaybackSettled();
    setDraftMessage(null);
    setError(null);
  }, [resolvePlaybackSettled, stopPlayback]);

  return { analyze, isLoading, draftMessage, error, currentSessionId, clear };
}
