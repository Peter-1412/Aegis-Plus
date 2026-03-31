import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Row, Col, Typography, Statistic, Divider, Spin, Tag } from "antd";
import {
  ToolOutlined,
  RobotOutlined,
  WarningOutlined,
  DeploymentUnitOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

import type { DashboardOverview, OpsTool } from "../types/index";

const { Title, Text, Paragraph } = Typography;

export default function Dashboard() {
  const navigate = useNavigate();
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [pinnedTools, setPinnedTools] = useState<OpsTool[]>([]);

  useEffect(() => {
    async function fetchData() {
      try {
        const [overviewRes, toolsRes] = await Promise.all([
          fetch("/api/dashboard/overview", {
            credentials: "include",
          }),
          fetch("/api/tools", {
            credentials: "include",
          }),
        ]);

        const overviewData = await overviewRes.json();
        const toolsData = await toolsRes.json();

        if (overviewRes.ok) {
          setOverview(overviewData);
        }
        if (toolsRes.ok && Array.isArray(toolsData.tools)) {
          setPinnedTools(
            toolsData.tools.filter((t: OpsTool) => t.isPinned)
          );
        }
      } catch {
        setOverview(null);
        setPinnedTools([]);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading || !overview) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
        <Spin tip="加载总览数据中..." />
      </div>
    );
  }

  const hasPinnedTools = pinnedTools.length > 0;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={2} style={{ marginBottom: 8 }}>
          总览
        </Title>
        <Text type="secondary">
          当前环境：生产 / 测试。核心数据已通过后端 API 聚合，后续可接入真实监控与告警服务。
        </Text>
      </div>

      {hasPinnedTools && (
        <>
          <Title level={4} style={{ marginBottom: 12 }}>
            首页置顶运维工具
          </Title>
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            {pinnedTools.map((tool) => (
              <Col xs={24} md={12} lg={8} key={tool.id}>
                <Card
                  hoverable
                  onClick={() => window.open(tool.url, "_blank", "noreferrer")}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 8,
                    }}
                  >
                    <span style={{ fontWeight: 500 }}>{tool.name}</span>
                    <Tag color={tool.environment === "PROD" ? "red" : tool.environment === "TEST" ? "blue" : "default"}>
                      {tool.environment}
                    </Tag>
                  </div>
                  <Paragraph type="secondary" style={{ marginBottom: 4 }}>
                    {tool.type}
                  </Paragraph>
                  <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>
                    {tool.description || tool.url}
                  </Paragraph>
                </Card>
              </Col>
            ))}
          </Row>
        </>
      )}

      <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card>
            <Title level={4} style={{ marginBottom: 12 }}>
              环境总体状态
            </Title>
            <Paragraph type="secondary" style={{ marginBottom: 16 }}>
              生产环境和测试环境整体健康，核心服务运行正常。后续可对接 Prometheus /
              Grafana 展示真实指标。
            </Paragraph>
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="生产集群" value={overview.clusters.prodStatus} />
              </Col>
              <Col span={8}>
                <Statistic title="测试集群" value={overview.clusters.testStatus} />
              </Col>
              <Col span={8}>
                <Statistic
                  title="可用区"
                  value={overview.clusters.azCount}
                  suffix="AZ"
                />
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card>
            <Title level={4} style={{ marginBottom: 12 }}>
              核心资源概览（示意）
            </Title>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic
                  title="CPU 使用率"
                  value={overview.resources.cpuUsage}
                  suffix="%"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="内存使用率"
                  value={overview.resources.memoryUsage}
                  suffix="%"
                />
              </Col>
              <Col span={6}>
                <Statistic title="节点数" value={overview.resources.nodeCount} />
              </Col>
              <Col span={6}>
                <Statistic title="Pod 运行中" value={overview.resources.podRunning} />
              </Col>
            </Row>
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              指标为示意数据，真实环境可通过 Prometheus / K8s API 获取。
            </Paragraph>
          </Card>
        </Col>
      </Row>

      <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card>
            <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
              <WarningOutlined style={{ fontSize: 22, color: "#faad14", marginRight: 8 }} />
              <Title level={4} style={{ margin: 0 }}>
                告警摘要（示意）
              </Title>
            </div>
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="严重告警" value={overview.alerts.critical} />
              </Col>
              <Col span={8}>
                <Statistic title="一般告警" value={overview.alerts.warning} />
              </Col>
              <Col span={8}>
                <Statistic title="信息告警" value={overview.alerts.info} />
              </Col>
            </Row>
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              后续可通过 Alertmanager 聚合不同严重级别和服务维度的告警。
            </Paragraph>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card>
            <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
              <DeploymentUnitOutlined
                style={{ fontSize: 22, color: "#1890ff", marginRight: 8 }}
              />
              <Title level={4} style={{ margin: 0 }}>
                CI/CD 概览（示意）
              </Title>
            </div>
            <Row gutter={16}>
              <Col span={8}>
                <Statistic
                  title="最近构建"
                  value={overview.ci.lastBuildStatus}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="今日构建数"
                  value={overview.ci.todayBuilds}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="失败率"
                  value={overview.ci.failureRate}
                  suffix="%"
                />
              </Col>
            </Row>
            <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              可对接 Jenkins / GitLab CI，将真实 pipeline 状态聚合到这里展示。
            </Paragraph>
          </Card>
        </Col>
      </Row>

      <Divider />

      <Row gutter={[24, 24]}>
        <Col xs={24} md={8}>
          <Card
            hoverable
            onClick={() => navigate("/tools")}
            style={{ height: "100%" }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                marginBottom: 16,
              }}
            >
              <ToolOutlined
                style={{ fontSize: 24, color: "#1890ff", marginRight: 12 }}
              />
              <Title level={4} style={{ margin: 0 }}>
                运维工具
              </Title>
            </div>
            <div style={{ marginBottom: 8, fontSize: 16, fontWeight: 500 }}>
              统一入口导航
            </div>
            <Paragraph type="secondary" style={{ margin: 0 }}>
              Rancher / Jenkins / MinIO / Harbor / Grafana 等系统入口。
            </Paragraph>
          </Card>
        </Col>

        <Col xs={24} md={8}>
          <Card
            hoverable
            onClick={() => navigate("/agent")}
            style={{ height: "100%" }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                marginBottom: 16,
              }}
            >
              <RobotOutlined
                style={{ fontSize: 24, color: "#1890ff", marginRight: 12 }}
              />
              <Title level={4} style={{ margin: 0 }}>
                智能运维助手
              </Title>
            </div>
            <div style={{ marginBottom: 8, fontSize: 16, fontWeight: 500 }}>
              LangChain Agent
            </div>
            <Paragraph type="secondary" style={{ margin: 0 }}>
              通过自然语言查询 K8s 节点、资源使用情况与告警信息。
            </Paragraph>
          </Card>
        </Col>

        <Col xs={24} md={8}>
          <Card
            hoverable
            onClick={() => navigate("/admin")}
            style={{ height: "100%" }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                marginBottom: 16,
              }}
            >
              <ThunderboltOutlined
                style={{ fontSize: 24, color: "#722ed1", marginRight: 12 }}
              />
              <Title level={4} style={{ margin: 0 }}>
                管理与配置
              </Title>
            </div>
            <div style={{ marginBottom: 8, fontSize: 16, fontWeight: 500 }}>
              用户审批与工具配置
            </div>
            <Paragraph type="secondary" style={{ margin: 0 }}>
              管理员可审批新用户、调整角色，并维护运维工具列表。
            </Paragraph>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
