import { useMemo } from "react";
import type { DeviceMonitorData } from "../../types";

interface KpiPanelProps {
  devices: DeviceMonitorData[];
  mqttBrokerConnected: boolean;
  pushFreqHz?: number;
}

interface KpiTileProps {
  label: string;
  value: number | string;
  tone?: "default" | "ok" | "err";
  sub?: string;
}

function KpiTile({ label, value, tone = "default", sub }: KpiTileProps) {
  const valueColor =
    tone === "ok" ? "#34d399" : tone === "err" ? "#fb7185" : "#e6edf5";
  return (
    <div
      style={{
        background: "#121826",
        border: "1px solid rgba(148,163,184,0.08)",
        borderRadius: 8,
        padding: "12px 14px",
      }}
    >
      <div
        style={{
          fontSize: 10,
          color: "#5f6b80",
          textTransform: "uppercase",
          letterSpacing: 0.5,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 24,
          color: valueColor,
          fontFamily: "'JetBrains Mono', monospace",
          fontWeight: 600,
          marginTop: 2,
        }}
      >
        {value}
      </div>
      {sub && <div style={{ fontSize: 9, color: "#5f6b80", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

interface PillProps {
  text: string;
  tone: "warn" | "danger" | "ok" | "muted";
}

function Pill({ text, tone }: PillProps) {
  const palette = {
    warn: { border: "rgba(251,191,36,0.4)", color: "#fbbf24", dot: "#fbbf24" },
    danger: { border: "rgba(251,113,133,0.4)", color: "#fb7185", dot: "#fb7185" },
    ok: { border: "rgba(52,211,153,0.4)", color: "#34d399", dot: "#34d399" },
    muted: { border: "rgba(148,163,184,0.25)", color: "#9aa5b8", dot: "#5f6b80" },
  }[tone];
  return (
    <span
      style={{
        background: "#121826",
        border: `1px solid ${palette.border}`,
        borderRadius: 14,
        padding: "4px 10px",
        fontSize: 10,
        color: palette.color,
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
      }}
    >
      <span
        style={{
          display: "inline-block",
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: palette.dot,
        }}
      />
      {text}
    </span>
  );
}

export function KpiPanel({ devices, mqttBrokerConnected, pushFreqHz = 1 }: KpiPanelProps) {
  const stats = useMemo(() => {
    const running = devices.filter((d) => d.status === "running");
    const stopped = devices.filter((d) => d.status === "stopped").length;
    const errors = devices.filter((d) => d.status === "error").length;
    const dps = running.reduce((sum, d) => sum + d.registers.length, 0) * pushFreqHz;
    const activeAnomalies = devices.reduce(
      (sum, d) => sum + d.active_anomalies.length,
      0,
    );
    const activeFaults = devices.filter((d) => d.active_fault !== null).length;
    return {
      running: running.length,
      stopped,
      errors,
      dps,
      activeAnomalies,
      activeFaults,
    };
  }, [devices, pushFreqHz]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
        <KpiTile label="Running" value={stats.running} tone="ok" sub="活躍中設備" />
        <KpiTile label="Stopped" value={stats.stopped} sub="已停止" />
        <KpiTile label="Errors" value={stats.errors} tone={stats.errors > 0 ? "err" : "default"} sub="異常設備" />
        <KpiTile label="Data Points / sec" value={stats.dps} sub="即時資料速率" />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {stats.activeAnomalies > 0 && (
          <Pill tone="warn" text={`${stats.activeAnomalies} active anomal${stats.activeAnomalies === 1 ? "y" : "ies"}`} />
        )}
        {stats.activeFaults > 0 && (
          <Pill tone="danger" text={`${stats.activeFaults} active fault${stats.activeFaults === 1 ? "" : "s"}`} />
        )}
        <Pill
          tone={mqttBrokerConnected ? "ok" : "muted"}
          text={mqttBrokerConnected ? "MQTT broker connected" : "MQTT broker not connected"}
        />
      </div>
    </div>
  );
}
