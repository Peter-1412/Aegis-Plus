import { useEffect, useState } from "react";
import type { User } from "../types/index";
import { ROLE_MAP } from "../types/index";
import {
  Table,
  Tag,
  Button,
  Popconfirm,
  Select,
  Typography,
  Space,
  message as antMessage,
} from "antd";
import { CheckOutlined, StopOutlined } from "@ant-design/icons";

const { Title } = Typography;
const { Option } = Select;

type AdminPageProps = {
  user: User;
};

export default function AdminPage({ user }: AdminPageProps) {
  const [users, setUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, []);

  async function fetchUsers() {
    setLoadingUsers(true);
    try {
      const res = await fetch("/api/admin/users", { credentials: "include" });
      const data = await res.json();
      if (data.users) {
        // Also ensure frontend sorting as a fallback/guarantee
        const sortedUsers = [...data.users].sort((a, b) => {
          if (a.role === 'ADMIN' && b.role !== 'ADMIN') return -1;
          if (a.role !== 'ADMIN' && b.role === 'ADMIN') return 1;
          return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
        });
        setUsers(sortedUsers);
      }
    } catch {
      antMessage.error("获取用户列表失败");
    } finally {
      setLoadingUsers(false);
    }
  }

  async function handleApprove(id: number) {
    await updateUser(id, { isActive: true });
    antMessage.success("已通过审批");
  }

  async function handleDisable(id: number) {
    await updateUser(id, { isActive: false });
    antMessage.success("已禁用用户");
  }

  async function handleRoleChange(id: number, role: User["role"]) {
    await updateUser(id, { role });
    antMessage.success("角色已更新");
  }

  async function updateUser(id: number, data: Partial<User>) {
    try {
      await fetch("/api/admin/users", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ id, ...data }),
      });
      fetchUsers();
    } catch {
      antMessage.error("操作失败");
    }
  }

  const userColumns = [
    {
      title: "ID",
      dataIndex: "id",
      key: "id",
      width: 80,
    },
    {
      title: "用户名",
      dataIndex: "username",
      key: "username",
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      render: (role: User["role"], record: User) => (
        <Select
          defaultValue={role}
          style={{ width: 120 }}
          onChange={(value: User["role"]) => handleRoleChange(record.id, value)}
          disabled={record.id === user.id}
        >
          <Option value="ADMIN">{ROLE_MAP["ADMIN"]}</Option>
          <Option value="DEVELOPER">{ROLE_MAP["DEVELOPER"]}</Option>
          <Option value="READONLY">{ROLE_MAP["READONLY"]}</Option>
        </Select>
      ),
    },
    {
      title: "状态",
      dataIndex: "isActive",
      key: "isActive",
      render: (isActive: boolean) =>
        isActive ? (
          <Tag color="success">已激活</Tag>
        ) : (
          <Tag color="warning">待审批</Tag>
        ),
    },
    {
      title: "注册时间",
      dataIndex: "createdAt",
      key: "createdAt",
      render: (value: string | undefined) =>
        value ? new Date(value).toLocaleString() : "-",
    },
    {
      title: "最后登录时间",
      dataIndex: "lastLoginAt",
      key: "lastLoginAt",
      render: (value: string | null | undefined) =>
        value ? new Date(value).toLocaleString() : "从未登录",
    },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: User) => (
        <Space size="middle">
          {!record.isActive && (
            <Button
              type="link"
              icon={<CheckOutlined />}
              onClick={() => handleApprove(record.id)}
            >
              通过审批
            </Button>
          )}
          {record.isActive && record.id !== user.id && (
            <Popconfirm
              title="确定禁用该用户？"
              onConfirm={() => handleDisable(record.id)}
            >
              <Button type="link" danger icon={<StopOutlined />}>
                禁用账号
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  if (user.role !== "ADMIN") {
    return <div style={{ textAlign: "center", marginTop: 100 }}>无权访问</div>;
  }

  return (
    <div>
      <Title level={2} style={{ marginBottom: 24 }}>
        管理后台
      </Title>
      <Table
        columns={userColumns}
        dataSource={users}
        rowKey="id"
        loading={loadingUsers}
        pagination={{ pageSize: 10 }}
      />
    </div>
  );
}
