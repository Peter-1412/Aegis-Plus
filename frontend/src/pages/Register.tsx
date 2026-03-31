import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Form, Input, Card, Typography, Alert, message as antMessage } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";

const { Title, Text } = Typography;

export default function RegisterPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onFinish(values: {
    username: string;
    password: string;
    confirmPassword: string;
  }) {
    if (values.password !== values.confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }
    
    // Simple frontend validation for Chinese characters
    if (!/^[\u4e00-\u9fa5]+$/.test(values.username)) {
      setError("姓名必须为纯中文字符");
      return;
    }

    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          username: values.username,
          password: values.password,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "注册失败");
      } else {
        antMessage.success(data.message || "注册成功");
        setTimeout(() => navigate("/login"), 1500);
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
            注册账号
          </Title>
          <Text style={{ color: "rgba(255, 255, 255, 0.6)" }}>
            首位注册用户将自动成为管理员
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
          name="register"
          onFinish={onFinish}
          layout="vertical"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[
              { required: true, message: "请输入您的真实姓名" },
              { min: 2, message: "姓名至少 2 个字" },
              { pattern: /^[\u4e00-\u9fa5]+$/, message: "只能包含中文字符" }
            ]}
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
            rules={[
              { required: true, message: "请输入密码" },
              { min: 10, message: "密码至少 10 位" },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: "rgba(255,255,255,0.5)" }} />}
              placeholder="设置密码"
              style={{
                background: "rgba(0, 0, 0, 0.2)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "#fff",
              }}
              className="custom-input"
            />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            rules={[{ required: true, message: "请确认密码" }]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: "rgba(255,255,255,0.5)" }} />}
              placeholder="确认密码"
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
              注 册
            </Button>
          </Form.Item>

          <div style={{ textAlign: "center" }}>
            <Button
              type="link"
              onClick={() => navigate("/login")}
              style={{ color: "rgba(255, 255, 255, 0.6)" }}
            >
              已有账号？立即登录
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  );
}
