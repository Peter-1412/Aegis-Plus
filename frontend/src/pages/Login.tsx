import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { User } from "../types/index";
import { Button, Form, Input, Card, Typography, Alert, message as antMessage } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";

const { Title, Text } = Typography;

type LoginProps = {
  setUser: (user: User) => void;
};

export default function LoginPage({ setUser }: LoginProps) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onFinish(values: { username: string; password: string }) {
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(values),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "登录失败");
      } else {
        antMessage.success("登录成功");
        setUser(data.user);
        navigate("/");
      }
    } catch {
      setError("网络异常，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        height: "100vh",
        background: "radial-gradient(circle at 50% 50%, #1a2a6c, #b21f1f, #fdbb2d)", 
        backgroundImage: "linear-gradient(to right, #0f0c29, #302b63, #24243e)",
      }}
    >
      <div style={{ marginBottom: 40, textAlign: "center" }}>
        <h1
          style={{
            fontSize: "3rem",
            fontWeight: 800,
            color: "#fff",
            margin: 0,
            textShadow: "0 0 20px rgba(0, 255, 255, 0.6)",
            fontFamily: "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
          }}
        >
          智能运维平台
        </h1>
        <Text style={{ color: "rgba(255, 255, 255, 0.6)", fontSize: "1.2rem", letterSpacing: "2px" }}>
          AEGIS INTELLIGENT OPS PLATFORM
        </Text>
      </div>

      <Card
        style={{
          width: 420,
          background: "rgba(255, 255, 255, 0.05)",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          boxShadow: "0 8px 32px 0 rgba(0, 0, 0, 0.37)",
          borderRadius: "16px",
        }}
        bordered={false}
      >
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <Title level={3} style={{ color: "#fff", marginBottom: 8 }}>
            欢迎回来
          </Title>
          <Text style={{ color: "rgba(255, 255, 255, 0.6)" }}>
            请使用您的真实姓名登录
          </Text>
        </div>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            style={{ marginBottom: 24, background: "rgba(255, 77, 79, 0.1)", border: "1px solid #ff4d4f", color: "#ff4d4f" }}
          />
        )}

        <Form
          name="login"
          initialValues={{ remember: true }}
          onFinish={onFinish}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: "请输入您的真实姓名" }]}
          >
            <Input
              prefix={<UserOutlined style={{ color: "rgba(255,255,255,0.5)" }} />}
              placeholder="请输入您的真实姓名 (中文)"
              style={{
                background: "rgba(0, 0, 0, 0.2)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "#fff",
              }}
              className="custom-input"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: "rgba(255,255,255,0.5)" }} />}
              placeholder="请输入密码"
              style={{
                background: "rgba(0, 0, 0, 0.2)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "#fff",
              }}
              className="custom-input"
            />
          </Form.Item>

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              style={{
                height: 48,
                fontSize: 16,
                fontWeight: 600,
                background: "linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%)",
                border: "none",
                boxShadow: "0 4px 15px rgba(0, 210, 255, 0.3)",
              }}
            >
              登 录
            </Button>
          </Form.Item>

          <div style={{ textAlign: "center" }}>
            <Button
              type="link"
              onClick={() => navigate("/register")}
              style={{ color: "rgba(255, 255, 255, 0.6)" }}
            >
              没有账号？立即注册
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  );
}
