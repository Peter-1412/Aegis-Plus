import { useCallback, useState } from 'react';
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
  };
}

export function useOpsAgentStream() {
  const [isLoading, setIsLoading] = useState(false);
  const [draftMessage, setDraftMessage] = useState<StreamAgentMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);

  const analyze = useCallback(async (description: string, sessionId?: number) => {
    const initialDraftId = `draft-${Date.now()}`;
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
                }));
                break;

              case 'tool_call_started':
                ensureDraft((draft) => {
                  const stepId = data.step_id || crypto.randomUUID();
                  return upsertTimeline(draft, {
                    id: stepId,
                    kind: 'tool_call',
                    toolName: data.tool || '',
                    inputText: data.tool_input || '',
                    outputText: '',
                    meta: data.meta || {},
                    resultState: data.result_state,
                    resultSummary: data.result_summary,
                    status: data.status || 'started',
                  });
                });
                break;

              case 'tool_call_running':
                ensureDraft((draft) => {
                  const stepId = data.step_id || crypto.randomUUID();
                  return upsertTimeline(draft, {
                    id: stepId,
                    kind: 'tool_call',
                    toolName: data.tool || '',
                    inputText: data.tool_input || '',
                    meta: data.meta || {},
                    resultState: data.result_state,
                    resultSummary: data.result_summary,
                    status: 'running',
                  });
                });
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
                }));
                break;

              case 'assistant_message_start':
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                }));
                break;

              case 'assistant_message_delta':
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                  content: `${draft.content}${data.delta || ''}`,
                }));
                break;

              case 'assistant_message_end':
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                  content: data.content || draft.content,
                }));
                break;

              case 'final':
                ensureDraft((draft) => ({
                  ...draft,
                  id: data.message_id || draft.id,
                  content: data.content || draft.content,
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
                }));
                setError(data.message || data.error_message || '分析失败');
                break;
            }
          } catch (parseError) {
            console.error('解析 NDJSON 失败:', line, parseError);
          }
        }
      }

      return newSessionId;
    } catch (err) {
      const message = err instanceof Error ? err.message : '网络请求异常';
      setError(message);
      return sessionId;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    setDraftMessage(null);
    setError(null);
  }, []);

  return { analyze, isLoading, draftMessage, error, currentSessionId, clear };
}
