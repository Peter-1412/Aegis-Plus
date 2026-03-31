import { useEffect, useRef, useState } from "react";
import type { OpsTool, User } from "../types/index";
import {
  Button,
  Card,
  Row,
  Col,
  Typography,
  Tag,
  Modal,
  Form,
  Input,
  Popconfirm,
  Checkbox,
  Divider,
  Badge,
  message as antMessage,
} from "antd";
import { PlusOutlined, PushpinFilled } from "@ant-design/icons";

const { Title, Paragraph } = Typography;

type ToolsPageProps = {
  user: User;
};

export default function ToolsPage({ user }: ToolsPageProps) {
  const [tools, setTools] = useState<OpsTool[]>([]);
  const [health, setHealth] = useState<Record<number, "UP" | "DOWN" | "UNKNOWN">>({});
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [deleteOpenId, setDeleteOpenId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const suppressOpenRef = useRef(0);

  async function fetchTools() {
    try {
      const res = await fetch("/api/tools", { credentials: "include" });
      const data = await res.json();
      if (data.tools) setTools(data.tools);
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    fetchTools();
  }, []);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const res = await fetch("/api/tools/health", { credentials: "include" });
        const data = await res.json();
        if (res.ok && Array.isArray(data.statuses)) {
          const map: Record<number, "UP" | "DOWN" | "UNKNOWN"> = {};
          for (const item of data.statuses) {
            map[item.id] = item.status;
          }
          setHealth(map);
        }
      } catch {
        // ignore
      }
    }

    if (tools.length > 0) {
      fetchHealth();
      const id = setInterval(fetchHealth, 30000);
      return () => clearInterval(id);
    }
  }, [tools.length]);

  async function handleAdd(values: {
    name: string;
    url: string;
    description?: string;
    isPinned?: boolean;
    type: string;
    environment: string;
  }) {
    setLoading(true);
    try {
      await fetch("/api/tools", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(values),
      });
      antMessage.success("添加成功");
      setIsModalVisible(false);
      form.resetFields();
      fetchTools();
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await fetch("/api/tools", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ id }),
      });
      antMessage.success("删除成功");
      fetchTools();
    } catch {
      // ignore
    }
  }

  const grouped = tools.reduce<Record<string, OpsTool[]>>((acc, tool) => {
    const env = tool.environment || "OTHER";
    if (!acc[env]) acc[env] = [];
    acc[env].push(tool);
    return acc;
  }, {});

  const orderedEnvs = ["PROD", "TEST", "DEV", ...Object.keys(grouped).filter((e) => !["PROD", "TEST", "DEV"].includes(e))];

  function openTool(url: string) {
    if (deleteOpenId !== null) return;
    if (Date.now() - suppressOpenRef.current < 400) return;
    window.open(url, "_blank", "noreferrer");
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <Title level={2} style={{ margin: 0 }}>
          运维工具
        </Title>
        {user.role === "ADMIN" && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setIsModalVisible(true)}
          >
            添加工具
          </Button>
        )}
      </div>

      <Card style={{ marginBottom: 24 }}>
        <Title level={4} style={{ marginBottom: 12 }}>
          工具说明（点击卡片直接打开）
        </Title>
        <Row gutter={[16, 16]}>
          {[
            {
              type: "Prometheus",
              title: "Prometheus — 指标监控",
              desc: "用来采集 CPU、内存、请求量等指标，相当于“健康体检仪”。出问题时可以看到哪个服务指标异常。",
              url: "http://192.169.223.108:30090"
            },
            {
              type: "Grafana",
              title: "Grafana — 可视化看板",
              desc: "把 Prometheus 等数据画成图表，看趋势用的“监控大屏”，适合业务方一眼看整体情况。",
              url: "http://192.169.223.108:30030/?orgId=1&from=now-6h&to=now&timezone=browser"
            },
            {
              type: "Harbor",
              title: "Harbor — 镜像仓库",
              desc: "存放应用镜像和制品的“仓库”，类似代码的 Git 仓库，但存的是镜像包。",
              url: "https://192.169.223.141/harbor/projects"
            },
            {
              type: "Jenkins",
              title: "Jenkins — CI/CD 流水线",
              desc: "代码提交后自动构建、测试、发布的“流水线”，可以看到每次构建是否成功。",
              url: "http://192.169.223.141:8080/"
            },
            {
              type: "K8s Dashboard",
              title: "Rancher — 集群控制台",
              desc: "可视化查看 Kubernetes 集群里有哪些服务、Pod 是否正常，相当于图形化的 k8s 命令。",
              url: "https://192.169.223.141:8444/dashboard/auth/login?timed-out"
            },
            {
              type: "VirtualMachine",
              title: "VirtualMachine — 虚拟机管理",
              desc: "基础设施虚拟机生命周期管理平台。",
              url: "https://192.169.223.141:9090/machines"
            },
            {
              type: "MinIO",
              title: "MinIO — 对象存储",
              desc: "高性能分布式对象存储服务，兼容 Amazon S3 API。",
              url: "http://192.169.223.141:9001"
            },
            {
              type: "Jaeger",
              title: "Jaeger — 链路追踪",
              desc: "端到端分布式链路追踪系统，用于监控和排查微服务延迟问题。",
              url: "http://192.169.223.108:30686/search"
            }
          ].map((guide) => {
            const toolForType = tools.find(
              (t) => t.type.toLowerCase() === guide.type.toLowerCase()
            );
            const url = toolForType?.url || guide.url;
            return (
              <Col xs={24} md={12} lg={8} key={guide.type}>
                <Card
                  hoverable
                  onClick={() => openTool(url)}
                  style={{
                    height: "100%",
                    borderRadius: 8,
                    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
                  }}
                >
                  <Paragraph strong style={{ marginBottom: 8 }}>
                    {guide.title}
                  </Paragraph>
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    {guide.desc}
                  </Paragraph>
                </Card>
              </Col>
            );
          })}
        </Row>
      </Card>

      {orderedEnvs.map((env) => {
        const list = grouped[env];
        if (!list || list.length === 0) return null;
        return (
          <div key={env} style={{ marginBottom: 24 }}>
            <Divider>
              {env === "PROD" ? "生产环境" : env === "TEST" ? "测试环境" : env === "DEV" ? "开发环境" : env}
            </Divider>
            <Row gutter={[24, 24]}>
              {list.map((tool) => (
                <Col xs={24} md={12} lg={8} key={tool.id}>
                  <Card
                    hoverable
                    onClick={() => openTool(tool.url)}
                    style={{
                      height: "100%",
                      borderRadius: 8,
                      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: 8,
                      }}
                    >
                      <Paragraph strong style={{ marginBottom: 0 }}>
                        {tool.name}
                      </Paragraph>
                      <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        {tool.isPinned && (
                          <Tag color="gold">
                            <PushpinFilled style={{ marginRight: 4 }} />
                            首页置顶
                          </Tag>
                        )}
                        {tool.environment && (
                          <Tag
                            color={
                              tool.environment === "PROD"
                                ? "red"
                                : tool.environment === "TEST"
                                ? "blue"
                                : "default"
                            }
                          >
                            {tool.environment}
                          </Tag>
                        )}
                      </span>
                    </div>
                    <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                      {tool.description || tool.url}
                    </Paragraph>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span>
                        <Badge
                          status={
                            health[tool.id] === "UP"
                              ? "success"
                              : health[tool.id] === "DOWN"
                              ? "error"
                              : "default"
                          }
                          text={
                            health[tool.id] === "UP"
                              ? "健康"
                              : health[tool.id] === "DOWN"
                              ? "异常"
                              : "未知"
                          }
                        />
                      </span>
                      {user.role === "ADMIN" && !tool.isSystem && (
                        <Popconfirm
                          title="确定删除该工具？"
                          open={deleteOpenId === tool.id}
                          onOpenChange={(open) => {
                            if (open) {
                              setDeleteOpenId(tool.id);
                            } else {
                              setDeleteOpenId(null);
                              suppressOpenRef.current = Date.now();
                            }
                          }}
                          onConfirm={() => {
                            setDeleteOpenId(null);
                            suppressOpenRef.current = Date.now();
                            handleDelete(tool.id);
                          }}
                          onCancel={() => {
                            setDeleteOpenId(null);
                            suppressOpenRef.current = Date.now();
                          }}
                        >
                          <Button
                            type="link"
                            danger
                            size="small"
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteOpenId(tool.id);
                            }}
                          >
                            删除
                          </Button>
                        </Popconfirm>
                      )}
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          </div>
        );
      })}

      <Modal
        title="添加运维工具"
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) =>
            handleAdd({
              ...values,
              type: "OTHER",
              environment: "PROD",
            })
          }
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入工具名称" }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            name="url"
            label="URL"
            rules={[{ required: true, message: "请输入工具地址" }]}
          >
            <Input />
          </Form.Item>

          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Form.Item name="isPinned" valuePropName="checked">
            <Checkbox>在首页总览置顶展示</Checkbox>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              保存
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
