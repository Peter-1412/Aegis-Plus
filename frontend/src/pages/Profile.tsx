import { useEffect, useState } from "react";
import type { User } from "../types/index";
import { ROLE_MAP } from "../types/index";
import {
  Card,
  Typography,
  Tag,
  Form,
  Input,
  Button,
  Modal,
  Space,
  message as antMessage,
} from "antd";

const { Title, Text } = Typography;

type ProfilePageProps = {
  user: User;
  setUser: (user: User | null) => void;
};

export default function ProfilePage({ user, setUser }: ProfilePageProps) {
  const [me, setMe] = useState<User>(user);
  const [loading, setLoading] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [form] = Form.useForm();
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);

  useEffect(() => {
    async function refreshMe() {
      setLoading(true);
      try {
        const res = await fetch("/api/auth/me", { credentials: "include" });
        const data = await res.json();
        if (res.ok && data.user) {
          setMe(data.user);
          setUser(data.user);
        }
      } catch {
        antMessage.error("获取账号信息失败");
      } finally {
        setLoading(false);
      }
    }

    refreshMe();
  }, [setUser]);

  async function handleChangePassword(values: {
    currentPassword: string;
    newPassword: string;
    confirmPassword: string;
  }) {
    if (values.newPassword !== values.confirmPassword) {
      antMessage.error("两次输入的新密码不一致");
      return;
    }

    setSavingPassword(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          currentPassword: values.currentPassword,
          newPassword: values.newPassword,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        antMessage.error(data.error || "修改密码失败");
        return;
      }
      antMessage.success("密码已更新");
      form.resetFields();
      setPasswordModalOpen(false);
    } catch {
      antMessage.error("修改密码失败");
    } finally {
      setSavingPassword(false);
    }
  }

  const labelStyle: React.CSSProperties = {
    width: 160,
    color: "rgba(0,0,0,0.65)",
  };

  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "14px 0",
    borderBottom: "1px solid #f0f0f0",
  };

  const valueStyle: React.CSSProperties = {
    flex: 1,
    fontWeight: 500,
    color: "rgba(0,0,0,0.88)",
  };

  function renderRow(
    label: string,
    value: React.ReactNode,
    action?: React.ReactNode
  ) {
    return (
      <div style={rowStyle}>
        <div style={labelStyle}>{label}</div>
        <div style={valueStyle}>{value}</div>
        {action ? <div>{action}</div> : null}
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 980 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          个人中心
        </Title>
        {me.role === "ADMIN" && (
          <Button type="link" href="/admin">
            前往管理
          </Button>
        )}
      </div>
      <Text type="secondary">账号信息与安全设置。</Text>

      <Card style={{ marginTop: 16 }} loading={loading} bodyStyle={{ paddingTop: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Space>
            <Title level={4} style={{ margin: 0 }}>
              账号信息
            </Title>
          </Space>
        </div>

        <div style={{ marginTop: 8 }}>
          {renderRow("账号名", me.username)}
          {renderRow(
            "角色",
            <Tag color={me.role === "ADMIN" ? "gold" : "blue"}>{ROLE_MAP[me.role]}</Tag>
          )}
          {renderRow(
            "状态",
            me.isActive ? <Tag color="success">已激活</Tag> : <Tag>未激活</Tag>
          )}
          <div style={{ borderBottom: "1px solid #f0f0f0" }} />
        </div>
      </Card>

      <Card style={{ marginTop: 16 }} bodyStyle={{ paddingTop: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Space>
            <Title level={4} style={{ margin: 0 }}>
              安全与登录
            </Title>
          </Space>
        </div>

        <div style={{ marginTop: 8 }}>
          {renderRow(
            "注册时间",
            me.createdAt ? new Date(me.createdAt).toLocaleString() : "-"
          )}
          {renderRow(
            "最后登录时间",
            me.lastLoginAt ? new Date(me.lastLoginAt).toLocaleString() : "从未登录"
          )}
          {renderRow(
            "密码",
            "••••••••••",
            <Button type="link" onClick={() => setPasswordModalOpen(true)}>
              修改
            </Button>
          )}
          <div style={{ borderBottom: "1px solid #f0f0f0" }} />
        </div>
      </Card>

      <Modal
        title="修改密码"
        open={passwordModalOpen}
        onCancel={() => {
          setPasswordModalOpen(false);
          form.resetFields();
        }}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleChangePassword}>
          <Form.Item
            name="currentPassword"
            label="当前密码"
            rules={[{ required: true, message: "请输入当前密码" }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="newPassword"
            label="新密码"
            rules={[{ required: true, message: "请输入新密码" }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label="确认新密码"
            rules={[{ required: true, message: "请再次输入新密码" }]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={savingPassword} block>
            保存
          </Button>
        </Form>
      </Modal>
    </div>
  );
}
