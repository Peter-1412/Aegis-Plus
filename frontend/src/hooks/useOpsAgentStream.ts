import { useState, useCallback } from 'react';

// 接口类型定义
export interface OpsRootCause {
  rank: number;
  description: string;
  probability?: number;
  service?: string;
  evidence_metrics?: string[];
  evidence_logs?: string[];
}

export interface OpsFinalResult {
  summary: string;
  ranked_root_causes: OpsRootCause[];
  next_actions: string[];
}

export interface ThinkStep {
  id: string;
  type: 'thought' | 'tool';
  content: string; // 思考的内容 或 调用的工具名
  toolInput?: string; // 工具的入参
  toolOutput?: string; // 工具的返回结果
  status: 'pending' | 'success' | 'error';
}

export function useOpsAgentStream() {
  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState<ThinkStep[]>([]);
  const [finalResult, setFinalResult] = useState<OpsFinalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);

  const analyze = useCallback(async (description: string, sessionId?: number) => {
    setIsLoading(true);
    setSteps([]);
    setFinalResult(null);
    setError(null);
    setCurrentSessionId(null);

    try {
      const response = await fetch(`/api/agent/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: "include",
        body: JSON.stringify({ message: description, sessionId: sessionId }), 
      });

      if (!response.body) throw new Error('当前浏览器不支持 ReadableStream');

      const returnedSessionId = response.headers.get("X-Session-ID");
      let newSessionId = sessionId;
      if (returnedSessionId) {
        newSessionId = parseInt(returnedSessionId, 10);
        setCurrentSessionId(newSessionId);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        // 将新读取的 chunk 拼接到 buffer 中
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // 最后一行可能是不完整的 JSON，保留在 buffer 中等待下一次拼接
        buffer = lines.pop() || ''; 

        for (const line of lines) {
          if (!line.trim()) continue;
          
          try {
            const data = JSON.parse(line);
            
            // 根据后端返回的 event 类型组装前台状态
            switch (data.event) {
              case 'agent_thought':
                setSteps(prev => [...prev, {
                  id: data.step_id || Math.random().toString(),
                  type: 'thought',
                  content: data.thought,
                  status: 'success'
                }]);
                break;
                
              case 'agent_action':
              case 'tool_start':
                setSteps(prev => {
                  // 避免重复添加同一个工具调用
                  if (prev.find(s => s.id === data.step_id && s.type === 'tool')) return prev;
                  return [...prev, {
                    id: data.step_id || Math.random().toString(),
                    type: 'tool',
                    content: data.tool,
                    toolInput: data.tool_input,
                    status: 'pending'
                  }];
                });
                break;
                
              case 'tool_end':
              case 'agent_observation':
                setSteps(prev => prev.map(step => 
                  step.id === data.step_id 
                    ? { ...step, toolOutput: data.observation, status: 'success' } 
                    : step
                ));
                break;
                
              case 'error':
                if (data.step_id) {
                  setSteps(prev => prev.map(step => 
                    step.id === data.step_id ? { ...step, status: 'error', toolOutput: data.error_message } : step
                  ));
                } else {
                  setError(data.message || data.error_message);
                }
                break;
                
              case 'final':
                setFinalResult({
                  summary: data.summary,
                  ranked_root_causes: data.ranked_root_causes,
                  next_actions: data.next_actions
                });
                break;
            }
          } catch (e) {
            console.error('解析 NDJSON 失败:', line, e);
          }
        }
      }
      return newSessionId;
    } catch (err: any) {
      setError(err.message || '网络请求异常');
      return sessionId;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    setSteps([]);
    setFinalResult(null);
    setError(null);
  }, []);

  return { analyze, isLoading, steps, finalResult, error, currentSessionId, clear };
}
