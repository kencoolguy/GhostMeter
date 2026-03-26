import {
  AppstoreOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  HddOutlined,
  MenuFoldOutlined,
  ThunderboltOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, theme } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAppStore } from "../stores/appStore";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/templates", icon: <AppstoreOutlined />, label: "Templates" },
  { key: "/devices", icon: <HddOutlined />, label: "Devices" },
  { key: "/simulation", icon: <ExperimentOutlined />, label: "Simulation" },
  { key: "/scenarios", icon: <ThunderboltOutlined />, label: "Scenarios" },
  { key: "/monitor", icon: <DashboardOutlined />, label: "Monitor" },
  { key: "/settings", icon: <SettingOutlined />, label: "Settings" },
];

export function MainLayout() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={sidebarCollapsed}
        breakpoint="lg"
        onBreakpoint={(broken) => {
          if (broken && !sidebarCollapsed) {
            toggleSidebar();
          }
        }}
      >
        <div
          style={{
            height: 32,
            margin: 16,
            color: "white",
            fontWeight: "bold",
            fontSize: sidebarCollapsed ? 14 : 18,
            textAlign: "center",
            lineHeight: "32px",
          }}
        >
          {sidebarCollapsed ? "GM" : "GhostMeter"}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 16px",
            background: colorBgContainer,
            display: "flex",
            alignItems: "center",
          }}
        >
          <Button
            type="text"
            icon={
              sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />
            }
            onClick={toggleSidebar}
          />
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            minHeight: 280,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
