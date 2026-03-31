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
  createdAt: string;
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
