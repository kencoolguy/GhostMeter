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
import { Button, Layout, Menu } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAppStore } from "../stores/appStore";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/monitor", icon: <DashboardOutlined />, label: "Monitor" },
  { key: "/devices", icon: <HddOutlined />, label: "Devices" },
  { key: "/templates", icon: <AppstoreOutlined />, label: "Templates" },
  { key: "/simulation", icon: <ExperimentOutlined />, label: "Simulation" },
  { key: "/scenarios", icon: <ThunderboltOutlined />, label: "Scenarios" },
  { key: "/settings", icon: <SettingOutlined />, label: "Settings" },
];

export function MainLayout() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const navigate = useNavigate();
  const location = useLocation();

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
        width={220}
        className="gm-sider"
      >
        <div className={`gm-brand ${sidebarCollapsed ? "gm-brand-collapsed" : ""}`}>
          <div className="gm-brand-logo">GM</div>
          {!sidebarCollapsed && (
            <div className="gm-brand-text">
              <span className="gm-brand-name">GhostMeter</span>
              <span className="gm-brand-tag">DEVICE SIMULATOR</span>
            </div>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ background: "transparent", border: "none" }}
        />
      </Sider>
      <Layout>
        <Header className="gm-header">
          <Button
            type="text"
            icon={
              sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />
            }
            onClick={toggleSidebar}
          />
          <span className="gm-header-live">
            <span className="gm-header-live-dot" />
            <span>Live</span>
          </span>
        </Header>
        <Content className="gm-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
