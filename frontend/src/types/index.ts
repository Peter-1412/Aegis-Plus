export type User = {
  id: number;
  username: string;
  role: "ADMIN" | "DEVELOPER" | "READONLY";
  isActive: boolean;
  createdAt?: string;
  lastLoginAt?: string | null;
};

export const ROLE_MAP: Record<User["role"], string> = {
  ADMIN: "管理员",
  DEVELOPER: "开发者",
  READONLY: "只读用户",
};

export type OpsTool = {
  id: number;
  name: string;
  type: string;
  environment: string;
  url: string;
  healthCheckUrl?: string;
  description?: string;
  isPinned: boolean;
  isSystem?: boolean;
};

export type AdminConfig = {
  env: Record<string, string | null>;
  note: string;
};

export type AgentSession = {
  id: number;
  title: string;
  userId: number;
  createdAt: string;
  updatedAt: string;
  isPinned?: boolean;
  messages?: AgentMessage[];
};

export type AgentMessage = {
  id: number;
  role: "USER" | "AGENT";
  content: string;
  metadata?: string | null;
  createdAt: string;
};

export type AgentLinkMeta = {
  artifacts?: AgentArtifact[];
  path?: string;
  lineStart?: number;
  lineEnd?: number;
  terminalId?: string;
  commandId?: string;
  previewUrl?: string;
  url?: string;
};

export type AgentArtifact =
  | {
      type: "url" | "preview";
      label: string;
      url: string;
    }
  | {
      type: "file_ref";
      label: string;
      path: string;
      lineStart?: number;
      lineEnd?: number;
    }
  | {
      type: "command_ref";
      label: string;
      commandId: string;
      terminalId?: string;
    };

export type AgentTimelineItem =
  | {
      id: string;
      kind: "thought_summary";
      title?: string;
      content: string;
      phase?: string;
      status: "completed";
    }
  | {
      id: string;
      kind: "tool_call";
      toolName: string;
      status: "started" | "running" | "completed" | "failed";
      inputText?: string;
      outputText?: string;
      resultState?: "ok" | "connectivity_blocked" | "no_data" | "runtime_error";
      resultSummary?: string;
      meta?: AgentLinkMeta;
    }
  | {
      id: string;
      kind: "node_failure";
      title: string;
      message: string;
      detail?: string;
      status: "failed";
    };

export type AgentRootCause = {
  rank: number;
  description: string;
  probability?: number;
  service?: string;
};

export type AgentStructuredMessage = {
  version?: number;
  content?: string;
  summary?: string;
  ranked_root_causes?: AgentRootCause[];
  next_actions?: string[];
  timeline?: AgentTimelineItem[];
};

export type DashboardOverview = {
  clusters: {
    prodStatus: string;
    testStatus: string;
    azCount: number;
  };
  resources: {
    cpuUsage: number;
    memoryUsage: number;
    nodeCount: number;
    podRunning: number;
  };
  alerts: {
    critical: number;
    warning: number;
    info: number;
  };
  ci: {
    lastBuildStatus: string;
    todayBuilds: number;
    failureRate: number;
  };
  summary: {
    userCount: number;
    activeUserCount: number;
    toolCount: number;
    sessionCount: number;
  };
};
