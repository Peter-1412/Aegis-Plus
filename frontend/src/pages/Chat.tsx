import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentMessage, AgentSession, User } from "../types/index";
import {
  Button,
  Input,
  List,
  Typography,
  Card,
  Spin,
  Empty,
  Avatar,
  Space,
  message as antMessage,
  Dropdown,
  Modal,
} from "antd";
import {
  SendOutlined,
  PlusOutlined,
  RobotOutlined,
  UserOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ToolOutlined,
  PushpinOutlined,
  EditOutlined,
  DeleteOutlined,
  MoreOutlined,
} from "@ant-design/icons";
import { useOpsAgentStream, type ThinkStep } from "../hooks/useOpsAgentStream";

const { Text } = Typography;

type ChatPageProps = {
  user: User;
  setIsAgentThinking?: (isThinking: boolean) => void;
};

// 渲染单个思考/工具调用节点的子组件
const StepBlock: React.FC<{ step: ThinkStep }> = ({ step }) => {
  const [expanded, setExpanded] = useState(false);

  if (step.type === 'thought') {
    return (
      <div style={{ color: '#8c8c8c', fontSize: '13px', marginBottom: 8, paddingLeft: 12, borderLeft: '2px solid #91d5ff' }}>
        🤔 思考中: {step.content}
      </div>
    );
  }

  return (
    <div style={{ backgroundColor: '#fafafa', borderRadius: 6, marginBottom: 8, border: '1px solid #f0f0f0', overflow: 'hidden', fontSize: '13px' }}>
      <div 
        style={{ padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', backgroundColor: '#f5f5f5' }}
        onClick={() => setExpanded(!expanded)}
      >
        <span style={{ fontFamily: 'monospace', color: '#595959' }}>
          <ToolOutlined style={{ marginRight: 6 }} /> 调用工具: <span style={{ fontWeight: 'bold', color: '#1890ff' }}>{step.content}</span>
        </span>
        <span style={{ fontSize: '12px', color: '#8c8c8c' }}>
          {step.status === 'pending' ? <><Spin size="small" style={{ marginRight: 4 }} /> 运行中...</> : step.status === 'success' ? <><CheckCircleOutlined style={{ color: '#52c41a' }} /> 完成</> : <><CloseCircleOutlined style={{ color: '#ff4d4f' }} /> 失败</>}
        </span>
      </div>
      
      {expanded && (
        <div style={{ padding: 12, borderTop: '1px solid #f0f0f0' }}>
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: 4 }}>输入参数:</div>
            <pre style={{ backgroundColor: '#2b2b2b', color: '#a6e22e', padding: 8, borderRadius: 4, whiteSpace: 'pre-wrap', margin: 0 }}>
              {step.toolInput || '无'}
            </pre>
          </div>
          {step.toolOutput && (
            <div>
              <div style={{ fontSize: '12px', color: '#8c8c8c', marginBottom: 4 }}>返回结果:</div>
              <pre style={{ backgroundColor: '#2b2b2b', color: '#d4d4d4', padding: 8, borderRadius: 4, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto', margin: 0 }}>
                {step.toolOutput}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default function ChatPage({ user, setIsAgentThinking }: ChatPageProps) {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSession, setActiveSession] = useState<AgentSession | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  
  const { analyze, isLoading, steps, finalResult, error, currentSessionId, clear } = useOpsAgentStream();

  useEffect(() => {
    if (setIsAgentThinking) {
      setIsAgentThinking(isLoading);
    }
  }, [isLoading, setIsAgentThinking]);

  useEffect(() => {
    if (activeSession) {
      // Don't clear messages when switching sessions if we are already fetching them 
      // just let fetchMessages replace them to avoid flickering and disappearing issues
      fetchMessages(activeSession.id);
    } else {
      setMessages([]);
    }
  }, [activeSession]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, steps, finalResult, isLoading]);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/agent/sessions", {
        credentials: "include",
      });
      const data = await res.json();
      if (data.sessions) {
        setSessions(data.sessions);
        
        setActiveSession((prev) => {
          if (prev) {
            const updated = data.sessions.find((s: AgentSession) => s.id === prev.id);
            if (updated) {
               // 只有当标题或置顶状态发生变化时才更新引用，避免无限循环
               if (updated.title !== prev.title || updated.isPinned !== prev.isPinned) {
                 return updated;
               }
               return prev;
            }
          } else if (data.sessions?.length > 0) {
            return data.sessions[0];
          }
          return prev;
        });
        
        return data.sessions;
      }
    } catch {
      // ignore
    }
    return [];
  }, []);

  useEffect(() => {
     if (currentSessionId && activeSession?.id !== currentSessionId) {
        fetchSessions().then((sessionsList) => {
           if (sessionsList && sessionsList.length > 0) {
              const target = sessionsList.find((s: AgentSession) => s.id === currentSessionId);
              if (target) {
                 setActiveSession(target);
              }
           }
           fetchMessages(currentSessionId);
        })
     }
  }, [currentSessionId, activeSession?.id, fetchSessions]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  async function fetchMessages(sessionId: number) {
    try {
      const res = await fetch(`/api/agent/sessions/${sessionId}`, {
        credentials: "include",
      });
      const data = await res.json();
      if (data.session?.messages) setMessages(data.session.messages);
    } catch {
      // ignore
    }
  }

  async function handleSend() {
    if (!input.trim() || isLoading) return;

    const userMsg = input;
    setInput("");

    const tempId = Date.now();

    setMessages((prev) => {
      let newMessages = [...prev];
      
      // 不再手动将 finalResult 合并进消息，因为分析完成后会调用 fetchMessages 从后端拉取最新记录
      
      // 2. 然后再把这一轮的新问题加入进去
      newMessages.push({
        id: tempId,
        role: "USER",
        content: userMsg,
        createdAt: new Date().toISOString(),
      });
      
      return newMessages;
    });

    // 3. 调用分析流（这会清空当前的 steps 和 finalResult）
    const returnedSessionId = await analyze(userMsg, activeSession?.id);
    
    // 4. 分析完成后，触发全局的 fetchSessions 以确保拿到最新的 currentSessionId 引用
    fetchSessions();

    // 5. 强制拉取最新消息（包含了后端刚刚保存的这一轮对话），然后清空流状态，避免页面上出现两次相同的结果
    const sessionIdToFetch = returnedSessionId || activeSession?.id || currentSessionId;
    if (sessionIdToFetch) {
      await fetchMessages(sessionIdToFetch);
    }
    clear();
  }

  async function handleNewSession() {
    try {
      const res = await fetch("/api/agent/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ title: "新建对话" }),
      });
      const data = await res.json();
      if (!res.ok) {
        antMessage.error(data.error || "新建对话失败");
        return;
      }
      if (data.session) {
        setSessions((prev) => [data.session, ...prev]);
        setActiveSession(data.session);
        setMessages([]);
      }
    } catch {
      antMessage.error("新建对话失败");
    }
  }

  async function handleSessionAction(action: string, session: AgentSession) {
    if (isLoading) {
      antMessage.warning('机器人正在思考中，请稍后操作');
      return;
    }
    if (action === 'delete') {
      Modal.confirm({
        title: '确认删除',
        content: '删除后无法恢复，确定要删除这个对话吗？',
        okText: '确认',
        cancelText: '取消',
        onOk: async () => {
          try {
            await fetch(`/api/agent/sessions/${session.id}`, { method: 'DELETE', credentials: 'include' });
            antMessage.success('已删除');
            if (activeSession?.id === session.id) {
              setActiveSession(null);
            }
            fetchSessions();
          } catch {
            antMessage.error('删除失败');
          }
        }
      });
    } else if (action === 'rename') {
      let newTitle = session.title;
      Modal.confirm({
        title: '重命名对话',
        content: (
          <Input 
            defaultValue={session.title} 
            onChange={e => newTitle = e.target.value}
            autoFocus
          />
        ),
        okText: '确认',
        cancelText: '取消',
        onOk: async () => {
          if (!newTitle.trim()) return;
          try {
            await fetch(`/api/agent/sessions/${session.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({ title: newTitle.trim() })
            });
            fetchSessions();
          } catch {
            antMessage.error('重命名失败');
          }
        }
      });
    } else if (action === 'pin' || action === 'unpin') {
       try {
         await fetch(`/api/agent/sessions/${session.id}`, {
           method: 'PUT',
           headers: { 'Content-Type': 'application/json' },
           credentials: 'include',
           body: JSON.stringify({ isPinned: action === 'pin' })
         });
         fetchSessions();
       } catch {
         antMessage.error('操作失败');
       }
    }
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 112px)", gap: 16 }}>
      {/* Sidebar */}
      <Card
        style={{
          width: 300,
          display: "flex",
          flexDirection: "column",
          padding: 0,
          pointerEvents: isLoading ? 'none' : 'auto',
          opacity: isLoading ? 0.6 : 1,
        }}
        bodyStyle={{
          padding: 12,
          display: "flex",
          flexDirection: "column",
          height: "100%",
        }}
      >
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleNewSession}
          block
          disabled={isLoading}
          style={{ marginBottom: 12 }}
        >
          新建对话
        </Button>
        <div style={{ flex: 1, overflowY: "auto" }}>
          <List
            dataSource={sessions}
            renderItem={(item) => (
              <List.Item
                onClick={() => {
                  if (isLoading) {
                    antMessage.warning('机器人正在思考中，请等待回答完毕后再切换对话');
                    return;
                  }
                  setActiveSession(item);
                }}
                style={{
                  cursor: isLoading ? "not-allowed" : "pointer",
                  padding: "12px 16px",
                  borderRadius: 6,
                  backgroundColor:
                    activeSession?.id === item.id ? "#e6f7ff" : "transparent",
                  borderBottom: "1px solid #f0f0f0",
                  position: "relative",
                }}
                className="session-list-item"
              >
                <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                   <div style={{ display: 'flex', alignItems: 'center', flex: 1, overflow: 'hidden' }}>
                      {item.isPinned && <PushpinOutlined style={{ marginRight: 6, color: '#8c8c8c', transform: 'rotate(-45deg)' }} />}
                      <Text ellipsis style={{ flex: 1, fontWeight: item.isPinned ? 500 : 400 }}>{item.title}</Text>
                   </div>
                   
                   <div 
                      className="session-actions"
                      style={{ 
                         display: 'flex',
                         visibility: activeSession?.id === item.id ? 'visible' : 'hidden', 
                         gap: 8, 
                         marginLeft: 8 
                      }}
                   >
                     <Dropdown
                       menu={{
                         items: [
                           { key: item.isPinned ? 'unpin' : 'pin', icon: <PushpinOutlined />, label: item.isPinned ? '取消置顶' : '置顶' },
                           { key: 'rename', icon: <EditOutlined />, label: '重命名' },
                           { type: 'divider' },
                           { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true },
                         ],
                         onClick: (e) => {
                           e.domEvent.stopPropagation();
                           handleSessionAction(e.key, item);
                         }
                       }}
                       trigger={['click']}
                     >
                        <Button 
                           type="text" 
                           size="small" 
                           icon={<MoreOutlined />} 
                           onClick={e => e.stopPropagation()} 
                           style={{ color: '#8c8c8c' }}
                        />
                     </Dropdown>
                   </div>
                </div>
              </List.Item>
            )}
          />
          <style>
            {`
              .session-list-item:hover .session-actions {
                 visibility: visible !important;
              }
            `}
          </style>
        </div>
      </Card>

      {/* Chat Area */}
      <Card
        style={{ flex: 1, display: "flex", flexDirection: "column" }}
        bodyStyle={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          padding: 0,
          overflow: "hidden",
        }}
      >
        <div
          ref={scrollRef}
          style={{ flex: 1, overflowY: "auto", padding: 24 }}
        >
          {messages.length === 0 && !isLoading && steps.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={`你好，${user.username}。你可以问我关于 K8s、告警或系统状态的问题。`}
              style={{ marginTop: 100 }}
            />
          ) : (
            messages.map((m) => {
              // 尝试解析结构化数据
              let parsedContent: any = null;
              if (m.role === 'AGENT') {
                // 如果有 metadata，优先使用 metadata（这是后端最新加的字段）
                if ((m as any).metadata) {
                  try {
                    parsedContent = JSON.parse((m as any).metadata);
                  } catch (e) {
                    parsedContent = null;
                  }
                } else {
                  // 兼容旧的将 JSON 存在 content 里的逻辑
                  try {
                    parsedContent = JSON.parse(m.content);
                    if (!parsedContent.summary) {
                      parsedContent = null;
                    }
                  } catch (e) {
                    parsedContent = null;
                  }
                }
              }

              // Transform backend steps to frontend steps format if they exist
              let historySteps: ThinkStep[] = [];
              if (parsedContent && parsedContent.steps) {
                 const stepMap = new Map<string, ThinkStep>();
                 parsedContent.steps.forEach((data: any) => {
                    if (data.event === 'agent_thought') {
                       historySteps.push({
                          id: data.step_id || Math.random().toString(),
                          type: 'thought',
                          content: data.thought,
                          status: 'success'
                       });
                    } else if (data.event === 'agent_action' || data.event === 'tool_start') {
                       stepMap.set(data.step_id, {
                          id: data.step_id,
                          type: 'tool',
                          content: data.tool,
                          toolInput: data.tool_input,
                          status: 'pending'
                       });
                    } else if (data.event === 'tool_end' || data.event === 'agent_observation') {
                       const existing = stepMap.get(data.step_id);
                       if (existing) {
                          existing.status = 'success';
                          existing.toolOutput = data.observation;
                       }
                    } else if (data.event === 'error') {
                       const existing = stepMap.get(data.step_id);
                       if (existing) {
                          existing.status = 'error';
                          existing.toolOutput = data.error_message;
                       }
                    }
                 });
                 // Merge tool steps in order
                 stepMap.forEach(step => historySteps.push(step));
              }

              return (
                <div
                  key={m.id}
                  style={{
                    display: "flex",
                    justifyContent: m.role === "USER" ? "flex-end" : "flex-start",
                    marginBottom: 16,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: m.role === "USER" ? "row-reverse" : "row",
                      gap: 12,
                      maxWidth: "80%",
                    }}
                  >
                    <Avatar
                      icon={m.role === "USER" ? <UserOutlined /> : <RobotOutlined />}
                      style={{ backgroundColor: m.role === "USER" ? "#1890ff" : "#52c41a" }}
                    />
                    
                    {/* 用户消息或普通的纯文本回复 */}
                    {!parsedContent ? (
                      <div
                        style={{
                          padding: "12px 16px",
                          borderRadius: 8,
                          backgroundColor: m.role === "USER" ? "#e6f7ff" : "#f5f5f5",
                          border: m.role === "USER" ? "1px solid #91d5ff" : "1px solid #d9d9d9",
                        }}
                      >
                        <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
                      </div>
                    ) : (
                      /* 渲染历史的结构化消息 */
                      <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%" }}>
                        {historySteps.length > 0 && (
                          <div style={{ opacity: 0.8 }}>
                            {historySteps.map((step: any) => (
                              <StepBlock key={step.id} step={step} />
                            ))}
                          </div>
                        )}
                        <div style={{ backgroundColor: '#fff', padding: 16, borderRadius: 8, border: '1px solid #bae0ff', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                          <h3 style={{ fontSize: '16px', fontWeight: 'bold', color: '#262626', margin: '0 0 12px 0' }}>🎯 分析结论</h3>
                          <p style={{ color: '#595959', whiteSpace: 'pre-wrap', marginBottom: 16 }}>{parsedContent.summary}</p>
                          
                          {parsedContent.ranked_root_causes?.length > 0 && (
                            <div style={{ marginBottom: 16 }}>
                              <h4 style={{ fontWeight: 600, color: '#262626', margin: '0 0 8px 0' }}>🔍 根因排查候选</h4>
                              <ul style={{ paddingLeft: 20, margin: 0, color: '#595959', fontSize: '14px' }}>
                                {parsedContent.ranked_root_causes.map((cause: any) => (
                                  <li key={cause.rank} style={{ marginBottom: 8 }}>
                                    <span style={{ fontWeight: 500, color: '#262626' }}>{cause.description}</span>
                                    {cause.probability && <span style={{ marginLeft: 8, color: '#1890ff', backgroundColor: '#e6f7ff', padding: '2px 6px', borderRadius: 4, fontSize: '12px' }}>置信度: {(cause.probability * 100).toFixed(0)}%</span>}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {parsedContent.next_actions?.length > 0 && (
                            <div>
                              <h4 style={{ fontWeight: 600, color: '#262626', margin: '0 0 8px 0' }}>💡 后续建议</h4>
                              <ul style={{ paddingLeft: 20, margin: 0, color: '#595959', fontSize: '14px' }}>
                                {parsedContent.next_actions.map((action: any, idx: number) => (
                                  <li key={idx} style={{ marginBottom: 4 }}>{action}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* Render Stream Process */}
          {(steps.length > 0 || isLoading || error || finalResult) && (
             <div style={{ display: "flex", gap: 12, marginBottom: 16, justifyContent: "flex-start" }}>
                <Avatar
                    icon={<RobotOutlined />}
                    style={{ backgroundColor: "#52c41a" }}
                  />
                  <div style={{ maxWidth: "80%", display: "flex", flexDirection: "column", gap: 8 }}>
                     {steps.map((step) => (
                       <StepBlock key={step.id} step={step} />
                     ))}

                     {error && (
                        <div style={{ color: '#ff4d4f', backgroundColor: '#fff2f0', padding: '8px 12px', borderRadius: 6, border: '1px solid #ffccc7', fontSize: '13px' }}>
                          ❌ 发生错误: {error}
                        </div>
                     )}

                     {finalResult && (
                        <div style={{ backgroundColor: '#fff', padding: 16, borderRadius: 8, border: '1px solid #bae0ff', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                          <h3 style={{ fontSize: '16px', fontWeight: 'bold', color: '#262626', margin: '0 0 12px 0' }}>🎯 分析结论</h3>
                          <p style={{ color: '#595959', whiteSpace: 'pre-wrap', marginBottom: 16 }}>{finalResult.summary}</p>
                          
                          {finalResult.ranked_root_causes?.length > 0 && (
                            <div style={{ marginBottom: 16 }}>
                              <h4 style={{ fontWeight: 600, color: '#262626', margin: '0 0 8px 0' }}>🔍 根因排查候选</h4>
                              <ul style={{ paddingLeft: 20, margin: 0, color: '#595959', fontSize: '14px' }}>
                                {finalResult.ranked_root_causes.map(cause => (
                                  <li key={cause.rank} style={{ marginBottom: 8 }}>
                                    <span style={{ fontWeight: 500, color: '#262626' }}>{cause.description}</span>
                                    {cause.probability && <span style={{ marginLeft: 8, color: '#1890ff', backgroundColor: '#e6f7ff', padding: '2px 6px', borderRadius: 4, fontSize: '12px' }}>置信度: {(cause.probability * 100).toFixed(0)}%</span>}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {finalResult.next_actions?.length > 0 && (
                            <div>
                              <h4 style={{ fontWeight: 600, color: '#262626', margin: '0 0 8px 0' }}>💡 后续建议</h4>
                              <ul style={{ paddingLeft: 20, margin: 0, color: '#595959', fontSize: '14px' }}>
                                {finalResult.next_actions.map((action, idx) => (
                                  <li key={idx} style={{ marginBottom: 4 }}>{action}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                     )}

                     {isLoading && !finalResult && (
                        <div style={{ color: '#bfbfbf', fontSize: '13px', display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px' }}>
                           <Spin size="small" /> Agent 正在分析集群数据中，请稍候...
                        </div>
                     )}
                  </div>
             </div>
          )}
        </div>

        <div
          style={{
            padding: 16,
            borderTop: "1px solid #f0f0f0",
            backgroundColor: "#fff",
          }}
        >
          <Space.Compact style={{ width: "100%" }}>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={handleSend}
              placeholder="输入你的问题..."
              size="large"
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              size="large"
            >
              发送
            </Button>
          </Space.Compact>
        </div>
      </Card>
    </div>
  );
}
