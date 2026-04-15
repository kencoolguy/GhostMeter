import { theme, type ThemeConfig } from "antd";

/** GhostMeter visual language — dark slate base + electric cyan accent. */
export const ghostMeterTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    // Brand
    colorPrimary: "#22d3ee",
    colorInfo: "#22d3ee",
    colorSuccess: "#34d399",
    colorWarning: "#fbbf24",
    colorError: "#fb7185",

    // Surface
    colorBgBase: "#0b0f17",
    colorBgLayout: "#0b0f17",
    colorBgContainer: "#121826",
    colorBgElevated: "#1a2030",

    // Border / text
    colorBorder: "rgba(148, 163, 184, 0.12)",
    colorBorderSecondary: "rgba(148, 163, 184, 0.08)",
    colorText: "#e6edf5",
    colorTextSecondary: "#9aa5b8",
    colorTextTertiary: "#5f6b80",
    colorTextQuaternary: "#475569",

    // Typography
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
    fontFamilyCode:
      "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace",
    fontSize: 14,

    // Shape
    borderRadius: 8,
    borderRadiusLG: 10,
    borderRadiusSM: 6,

    // Motion
    motionDurationMid: "0.18s",
  },
  components: {
    Layout: {
      headerBg: "#0b0f17",
      headerHeight: 56,
      siderBg: "#0b0f17",
      bodyBg: "#0b0f17",
    },
    Menu: {
      darkItemBg: "#0b0f17",
      darkSubMenuItemBg: "#0b0f17",
      darkItemSelectedBg: "rgba(34, 211, 238, 0.12)",
      darkItemSelectedColor: "#22d3ee",
      darkItemHoverBg: "rgba(148, 163, 184, 0.06)",
      darkItemHoverColor: "#e6edf5",
      itemBorderRadius: 6,
      itemMarginInline: 8,
    },
    Button: {
      controlHeight: 34,
      fontWeight: 500,
      primaryShadow: "0 0 16px rgba(34, 211, 238, 0.25)",
    },
    Card: {
      colorBgContainer: "#121826",
      headerBg: "transparent",
      borderRadiusLG: 10,
    },
    Table: {
      headerBg: "#0f1420",
      headerColor: "#9aa5b8",
      headerSplitColor: "rgba(148, 163, 184, 0.12)",
      borderColor: "rgba(148, 163, 184, 0.08)",
      rowHoverBg: "rgba(34, 211, 238, 0.04)",
    },
    Tag: {
      borderRadiusSM: 4,
    },
    Badge: {
      dotSize: 8,
    },
    Modal: {
      contentBg: "#121826",
      headerBg: "#121826",
    },
    Input: {
      colorBgContainer: "#0f1420",
      activeBorderColor: "#22d3ee",
      hoverBorderColor: "rgba(34, 211, 238, 0.5)",
    },
    Select: {
      colorBgContainer: "#0f1420",
    },
    Tabs: {
      itemSelectedColor: "#22d3ee",
      inkBarColor: "#22d3ee",
    },
  },
};
