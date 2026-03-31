import { useLocation, useNavigate } from "react-router-dom";
import type { User } from "../types/index";
import { Layout as AntLayout, Menu, Button, Dropdown, Avatar, theme, message as antMessage } from "antd";
import {
  LogoutOutlined,
  HomeOutlined,
  ToolOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  UserOutlined
} from "@ant-design/icons";

const { Header, Content } = AntLayout;

type LayoutProps = {
  children: React.ReactNode;
  user: User | null;
  setUser: (user: User | null) => void;
  isAgentThinking?: boolean;
};

export function Layout({ children, user, setUser, isAgentThinking = false }: LayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    token: { colorBgContainer, colorTextLightSolid },
  } = theme.useToken();

  const handleNavigate = (path: string) => {
    if (isAgentThinking) {
      antMessage.warning('机器人正在思考中，请等待回答完毕后再切换页面');
      return;
    }
    navigate(path);
  };

  async function handleLogout() {
    if (isAgentThinking) {
      antMessage.warning('机器人正在思考中，请等待回答完毕后再退出');
      return;
    }
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
      });
      setUser(null);
      navigate("/login");
    } catch {
      // ignore
    }
  }

  const menuItems = [
    {
      key: "/",
      icon: <HomeOutlined />,
      label: "总览",
      onClick: () => handleNavigate("/"),
    },
    {
      key: "/tools",
      icon: <ToolOutlined />,
      label: "工具",
      onClick: () => handleNavigate("/tools"),
    },
    {
      key: "/agent",
      icon: <RobotOutlined />,
      label: "智能助手",
      onClick: () => handleNavigate("/agent"),
    },
    ...(user?.role === "ADMIN"
      ? [
          {
            key: "/admin",
            icon: <SafetyCertificateOutlined />,
            label: "管理",
            onClick: () => handleNavigate("/admin"),
          },
        ]
      : []),
  ];

  const userMenu = {
    items: [
      {
        key: "profile",
        icon: <UserOutlined />,
        label: "个人中心",
        onClick: () => handleNavigate("/profile"),
      },
      {
        key: "logout",
        icon: <LogoutOutlined />,
        label: "退出登录",
        onClick: handleLogout,
      },
    ],
  };

  const currentPath = (() => {
    const path = location.pathname;
    if (path.startsWith("/tools")) return "/tools";
    if (path.startsWith("/agent")) return "/agent";
    if (path.startsWith("/admin")) return "/admin";
    return "/";
  })();

  if (!user) {
    return (
      <AntLayout className="min-h-screen">
        <Header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "#001529",
            padding: "0 24px",
          }}
        >
          <div className="demo-logo" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ color: '#fff', fontSize: 20, fontWeight: 'bold' }}>OpsPilot</div>
            <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>智能运维平台</div>
          </div>
        </Header>
        <Content style={{ padding: 24, minHeight: 380 }}>{children}</Content>
      </AntLayout>
    );
  }

  return (
    <AntLayout style={{ minHeight: "100vh", background: colorBgContainer }}>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          background: "#001529",
          padding: "0 24px",
        }}
      >
        <div 
          className="demo-logo" 
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 12, 
            marginRight: 48,
            cursor: 'pointer' 
          }}
          onClick={() => handleNavigate('/')}
        >
          <div style={{ color: '#fff', fontSize: 20, fontWeight: 'bold' }}>OpsPilot</div>
          <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12 }}>智能运维平台</div>
        </div>
        
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[currentPath]}
          items={menuItems}
          style={{ flex: 1, minWidth: 0 }}
        />

        <div style={{ marginLeft: "auto" }}>
          <Dropdown menu={userMenu}>
            <Button type="text" style={{ color: colorTextLightSolid }}>
              <Avatar size="small" icon={<UserOutlined />} style={{ marginRight: 8 }} />
              {user.username} · {user.role}
            </Button>
          </Dropdown>
        </div>
      </Header>
      <Content style={{ flex: 1, display: 'flex', flexDirection: 'column', background: colorBgContainer }}>
        <div style={{ flex: 1, padding: 24 }}>
          {children}
        </div>
      </Content>
    </AntLayout>
  );
}
