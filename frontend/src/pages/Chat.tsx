import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentLinkMeta,
  AgentMessage,
  AgentRootCause,
  AgentSession,
  AgentStructuredMessage,
  AgentTimelineItem,
  User,
} from "../types/index";
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
import {
  useOpsAgentStream,
  type StreamAgentMessage,
} from "../hooks/useOpsAgentStream";

const { Text } = Typography;

type ChatPageProps = {
  user: User;
  setIsAgentThinking?: (isThinking: boolean) => void;
};

type AgentRenderContent = {
  content: string;
  timeline: AgentTimelineItem[];
};

const MetaLinks: React.FC<{ meta?: AgentLinkMeta }> = ({ meta }) => {
  if (!meta) return null;
  const chips: string[] = [];
  if (meta.path) {
    chips.push(meta.lineStart ? `${meta.path}:${meta.lineStart}${meta.lineEnd ? `-${meta.lineEnd}` : ""}` : meta.path);
  }
  if (meta.terminalId) chips.push(`terminal ${meta.terminalId}`);
  if (meta.commandId) chips.push(`command ${meta.commandId}`);
  if (meta.previewUrl) chips.push(meta.previewUrl);
  if (meta.url) chips.push(meta.url);
  if (!chips.length) return null;
  return <div style={{ fontSize: "12px", color: "#8c8c8c", marginTop: 8 }}>{chips.join(" | ")}</div>;
};

const TimelineBlock: React.FC<{ item: AgentTimelineItem }> = ({ item }) => {
  const [expanded, setExpanded] = useState(false);

  if (item.kind === "thought_summary") {
    return (
      <div
        style={{
          color: "#8c8c8c",
          fontSize: "13px",
          marginBottom: 8,
          paddingLeft: 12,
          borderLeft: "2px solid #91d5ff",
        }}
      >
        🤔 {item.title || "思路摘要"}: {item.content}
      </div>
    );
  }

  return (
    <div
      style={{
        backgroundColor: "#fafafa",
        borderRadius: 6,
        marginBottom: 8,
        border: "1px solid #f0f0f0",
        overflow: "hidden",
        fontSize: "13px",
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
          backgroundColor: "#f5f5f5",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <span style={{ fontFamily: "monospace", color: "#595959" }}>
          <ToolOutlined style={{ marginRight: 6 }} /> 调用工具: <span style={{ fontWeight: 'bold', color: '#1890ff' }}>{item.toolName}</span>
        </span>
        <span style={{ fontSize: "12px", color: "#8c8c8c" }}>
          {item.status === "started" ? (
            <>
              <Spin size="small" style={{ marginRight: 4 }} /> 已创建
            </>
          ) : item.status === "running" ? (
            <>
              <Spin size="small" style={{ marginRight: 4 }} /> 运行中...
            </>
          ) : item.status === "completed" ? (
            <>
              <CheckCircleOutlined style={{ color: "#52c41a" }} /> 完成
            </>
          ) : (
            <>
              <CloseCircleOutlined style={{ color: "#ff4d4f" }} /> 失败
            </>
          )}
        </span>
      </div>

      {expanded && (
        <div style={{ padding: 12, borderTop: "1px solid #f0f0f0" }}>
          {item.resultSummary ? (
            <div
              style={{
                marginBottom: 8,
                fontSize: "12px",
                color: item.resultState === "connectivity_blocked" || item.resultState === "runtime_error" ? "#cf1322" : "#8c8c8c",
              }}
            >
              结果判定: {item.resultSummary}
            </div>
          ) : null}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: "12px", color: "#8c8c8c", marginBottom: 4 }}>
              输入参数:
            </div>
            <pre
              style={{
                backgroundColor: "#2b2b2b",
                color: "#a6e22e",
                padding: 8,
                borderRadius: 4,
                whiteSpace: "pre-wrap",
                margin: 0,
              }}
            >
              {item.inputText || "无"}
            </pre>
          </div>
          {item.outputText && (
            <div>
              <div style={{ fontSize: "12px", color: "#8c8c8c", marginBottom: 4 }}>
                返回结果:
              </div>
              <pre
                style={{
                  backgroundColor: "#2b2b2b",
                  color: "#d4d4d4",
                  padding: 8,
                  borderRadius: 4,
                  whiteSpace: "pre-wrap",
                  maxHeight: 200,
                  overflowY: "auto",
                  margin: 0,
                }}
              >
                {item.outputText}
              </pre>
            </div>
          )}
          <MetaLinks meta={item.meta} />
        </div>
      )}
    </div>
  );
};

function buildRenderedContent(
  summary?: string,
  rankedRootCauses?: AgentRootCause[],
  nextActions?: string[],
) {
  const sections: string[] = [];
  if (summary?.trim()) {
    sections.push("分析结论");
    sections.push(summary.trim());
  }
  if (rankedRootCauses?.length) {
    sections.push("");
    sections.push("根因排查候选");
    rankedRootCauses.forEach((cause, index) => {
      const confidence =
        typeof cause.probability === "number"
          ? ` (置信度 ${(cause.probability * 100).toFixed(0)}%)`
          : "";
      const service = cause.service ? ` [${cause.service}]` : "";
      sections.push(`${index + 1}. ${cause.description}${service}${confidence}`);
    });
  }
  if (nextActions?.length) {
    sections.push("");
    sections.push("后续建议");
    nextActions.forEach((action) => sections.push(`- ${action}`));
  }
  return sections.join("\n").trim();
}

function normalizeTimeline(rawTimeline: unknown): AgentTimelineItem[] {
  if (Array.isArray(rawTimeline)) {
    return rawTimeline as AgentTimelineItem[];
  }
  return [];
}

function parseStructuredMessage(raw: string | null | undefined) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AgentStructuredMessage;
    if (
      parsed &&
      (parsed.content ||
        parsed.summary ||
        parsed.ranked_root_causes?.length ||
        parsed.next_actions?.length ||
        parsed.timeline?.length)
    ) {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}

function getAgentRenderContent(message: AgentMessage | StreamAgentMessage): AgentRenderContent {
  if ("timeline" in message && "ranked_root_causes" in message) {
    const content =
      message.content ||
      buildRenderedContent(
        message.summary,
        message.ranked_root_causes,
        message.next_actions,
      );
    return { content, timeline: message.timeline };
  }

  const structured =
    parseStructuredMessage(message.metadata) || parseStructuredMessage(message.content);
  if (!structured) {
    return { content: message.content, timeline: [] };
  }

  const content =
    structured.content ||
    buildRenderedContent(
      structured.summary,
      structured.ranked_root_causes,
      structured.next_actions,
    ) ||
    message.content;

  return {
    content,
    timeline: normalizeTimeline(structured.timeline),
  };
}

export default function ChatPage({ user, setIsAgentThinking }: ChatPageProps) {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSession, setActiveSession] = useState<AgentSession | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const { analyze, isLoading, draftMessage, error, currentSessionId, clear } =
    useOpsAgentStream();

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
  }, [messages, draftMessage, isLoading]);

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
      
      newMessages.push({
        id: tempId,
        role: "USER",
        content: userMsg,
        createdAt: new Date().toISOString(),
      });
      
      return newMessages;
    });

    const returnedSessionId = await analyze(userMsg, activeSession?.id);

    fetchSessions();

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

  const renderedDraft = useMemo(
    () => (draftMessage ? getAgentRenderContent(draftMessage) : null),
    [draftMessage],
  );

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
          {messages.length === 0 && !isLoading && !draftMessage ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={`你好，${user.username}。你可以问我关于 K8s、告警或系统状态的问题。`}
              style={{ marginTop: 100 }}
            />
          ) : (
            messages.map((m) => {
              const agentRenderContent =
                m.role === "AGENT" ? getAgentRenderContent(m) : null;

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

                    {m.role === "USER" ? (
                      <div
                        style={{
                          padding: "12px 16px",
                          borderRadius: 8,
                          backgroundColor: "#e6f7ff",
                          border: "1px solid #91d5ff",
                        }}
                      >
                        <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
                      </div>
                    ) : (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 8,
                          width: "100%",
                        }}
                      >
                        {agentRenderContent?.timeline.length ? (
                          <div style={{ opacity: 0.9 }}>
                            {agentRenderContent.timeline.map((item) => (
                              <TimelineBlock key={item.id} item={item} />
                            ))}
                          </div>
                        ) : null}
                        <div
                          style={{
                            padding: "12px 16px",
                            borderRadius: 8,
                            backgroundColor: "#f5f5f5",
                            border: "1px solid #d9d9d9",
                          }}
                        >
                          <div style={{ whiteSpace: "pre-wrap" }}>
                            {agentRenderContent?.content || m.content}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
          {draftMessage && (
            <div
              style={{
                display: "flex",
                gap: 12,
                marginBottom: 16,
                justifyContent: "flex-start",
              }}
            >
              <Avatar
                icon={<RobotOutlined />}
                style={{ backgroundColor: "#52c41a" }}
              />
              <div style={{ maxWidth: "80%", display: "flex", flexDirection: "column", gap: 8 }}>
                {renderedDraft?.timeline.length ? (
                  <div style={{ opacity: 0.9 }}>
                    {renderedDraft.timeline.map((item) => (
                      <TimelineBlock key={item.id} item={item} />
                    ))}
                  </div>
                ) : null}
                <div
                  style={{
                    padding: "12px 16px",
                    borderRadius: 8,
                    backgroundColor: "#f5f5f5",
                    border: "1px solid #d9d9d9",
                  }}
                >
                  <div style={{ whiteSpace: "pre-wrap" }}>
                    {renderedDraft?.content || "正在分析，请稍候..."}
                  </div>
                </div>
                {isLoading && !renderedDraft?.content ? (
                  <div
                    style={{
                      color: "#bfbfbf",
                      fontSize: "13px",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "4px 8px",
                    }}
                  >
                    <Spin size="small" /> Agent 正在分析集群数据中，请稍候...
                  </div>
                ) : null}
              </div>
            </div>
          )}
          {error && (
            <div
              style={{
                color: "#ff4d4f",
                backgroundColor: "#fff2f0",
                padding: "8px 12px",
                borderRadius: 6,
                border: "1px solid #ffccc7",
                fontSize: "13px",
                marginBottom: 16,
              }}
            >
              ❌ 发生错误: {error}
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
