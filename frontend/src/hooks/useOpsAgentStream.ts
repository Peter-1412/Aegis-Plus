import { useCallback, useState } from 'react';
import type { AgentRootCause, AgentStep } from '../types';

export interface StreamAgentMessage {
  id: string;
  role: 'AGENT';
  content: string;
  createdAt: string;
  summary?: string;
  ranked_root_causes: AgentRootCause[];
  next_actions: string[];
  steps: AgentStep[];
}

function createDraftMessage(id: string): StreamAgentMessage {
  return {
    id,
    role: 'AGENT',
    content: '',
    createdAt: new Date().toISOString(),
    ranked_root_causes: [],
    next_actions: [],
    steps: [],
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
              case 'agent_thought':
                ensureDraft((draft) => ({
                  ...draft,
                  steps: [
                    ...draft.steps,
                    {
                      id: data.step_id || crypto.randomUUID(),
                      type: 'thought',
                      content: data.thought || '',
                      status: 'success',
                    },
                  ],
                }));
                break;

              case 'tool_start':
                ensureDraft((draft) => {
                  const stepId = data.step_id || crypto.randomUUID();
                  if (draft.steps.some((step) => step.id === stepId)) {
                    return draft;
                  }
                  return {
                    ...draft,
                    steps: [
                      ...draft.steps,
                      {
                        id: stepId,
                        type: 'tool',
                        content: data.tool || '',
                        toolInput: data.tool_input || '',
                        status: 'pending',
                      },
                    ],
                  };
                });
                break;

              case 'tool_end':
                ensureDraft((draft) => ({
                  ...draft,
                  steps: draft.steps.map((step) =>
                    step.id === data.step_id
                      ? { ...step, toolOutput: data.observation || '', status: 'success' }
                      : step,
                  ),
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
                  steps: Array.isArray(data.steps) ? data.steps : draft.steps,
                }));
                break;

              case 'error':
                if (data.step_id) {
                  ensureDraft((draft) => ({
                    ...draft,
                    steps: draft.steps.map((step) =>
                      step.id === data.step_id
                        ? {
                            ...step,
                            status: 'error',
                            toolOutput: data.error_message || data.message || '执行失败',
                          }
                        : step,
                    ),
                  }));
                } else {
                  setError(data.message || data.error_message || '分析失败');
                }
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
