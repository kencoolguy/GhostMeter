import { App, Tag } from "antd";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deviceApi } from "../../services/deviceApi";
import type { DeviceMonitorData, RegisterHistoryPoint } from "../../types";
import { Sparkline } from "./Sparkline";

interface DeviceCardProps {
  device: DeviceMonitorData;
  history: RegisterHistoryPoint[];
}

const PREFERRED = ["total_power", "ac_power", "total_energy"];

function pickPrimaryAndSecondary(device: DeviceMonitorData) {
  const names = device.registers.map((r) => r.name);
  const primary =
    PREFERRED.find((n) => names.includes(n)) ?? names[0] ?? null;
  const secondary =
    PREFERRED.find((n) => names.includes(n) && n !== primary) ??
    names.find((n) => n !== primary) ??
    null;
  return {
    primary: primary ? device.registers.find((r) => r.name === primary) ?? null : null,
    secondary: secondary ? device.registers.find((r) => r.name === secondary) ?? null : null,
  };
}

export function DeviceCard({ device, history }: DeviceCardProps) {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const { primary, secondary } = pickPrimaryAndSecondary(device);

  // Value-flash detection
  const lastPrimaryValueRef = useRef<number | null>(null);
  const [flashKey, setFlashKey] = useState(0);
  useEffect(() => {
    if (!primary) return;
    if (
      lastPrimaryValueRef.current !== null &&
      lastPrimaryValueRef.current !== primary.value
    ) {
      setFlashKey((k) => k + 1);
    }
    lastPrimaryValueRef.current = primary.value;
  }, [primary]);

  const isStopped = device.status === "stopped";
  const isError = device.status === "error";

  const dotClass =
    "gm-mon-dot " +
    (device.status === "running"
      ? "gm-mon-dot-running"
      : isError
      ? "gm-mon-dot-error"
      : "gm-mon-dot-stopped");

  const cardStyle: React.CSSProperties = {
    background: "#121826",
    border: `1px solid ${isError ? "rgba(251,113,133,0.3)" : "rgba(148,163,184,0.12)"}`,
    borderRadius: 10,
    padding: 14,
    cursor: "pointer",
    position: "relative",
    opacity: isStopped ? 0.45 : 1,
  };

  const onCardClick = () => {
    navigate(`/devices/${device.device_id}`);
  };

  const onStartClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deviceApi.start(device.device_id);
      message.success(`Started ${device.name}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      message.error(`Start failed: ${msg}`);
    }
  };

  const valueDisplay = (v: number | undefined) =>
    typeof v === "number" ? v.toFixed(1) : "—";

  return (
    <div className="gm-mon-card" style={cardStyle} onClick={onCardClick}>
      <span style={{ position: "absolute", top: 12, right: 12, color: "#5f6b80", fontSize: 14 }}>
        →
      </span>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ display: "flex", alignItems: "center", color: "#e6edf5", fontWeight: 600, fontSize: 14 }}>
          <span className={dotClass} />
          {device.name}
        </span>
        <span style={{ color: "#5f6b80", fontSize: 10 }}>slv {device.slave_id}</span>
      </div>
      {device.template_name && (
        <div style={{ color: "#5f6b80", fontSize: 10, marginTop: 2 }}>
          {device.template_name}
        </div>
      )}

      {primary ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 10 }}>
            <span style={{ color: "#9aa5b8", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.3 }}>
              {primary.name}
            </span>
            <span
              key={flashKey}
              className={flashKey > 0 ? "gm-mon-value-flash" : undefined}
              style={{
                color: isError ? "#fb7185" : "#22d3ee",
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 18,
                fontWeight: 600,
              }}
            >
              {valueDisplay(primary.value)}
              <span style={{ color: "#9aa5b8", fontSize: 11, marginLeft: 3, fontFamily: "Inter, sans-serif", fontWeight: 400 }}>
                {primary.unit}
              </span>
            </span>
          </div>
          <Sparkline data={history} />
          {secondary && (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              <span style={{ color: "#5f6b80", fontSize: 10 }}>{secondary.name}</span>
              <span style={{ color: "#9aa5b8", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
                {valueDisplay(secondary.value)} {secondary.unit}
              </span>
            </div>
          )}
        </>
      ) : (
        <div style={{ color: "#5f6b80", fontSize: 11, marginTop: 10 }}>No registers</div>
      )}

      <div style={{ display: "flex", gap: 5, marginTop: 10, flexWrap: "wrap" }}>
        {device.mqtt_stats && (
          <Tag color={device.mqtt_stats.error_count > 0 ? "orange" : "cyan"} style={{ fontSize: 10 }}>
            {device.mqtt_stats.error_count > 0 ? "MQTT err" : "MQTT"}
          </Tag>
        )}
        {device.active_anomalies.map((a) => (
          <Tag key={a} color="orange" style={{ fontSize: 10 }}>
            {a}
          </Tag>
        ))}
        {device.active_fault && (
          <Tag color="red" style={{ fontSize: 10 }}>
            {device.active_fault.fault_type}
          </Tag>
        )}
      </div>

      {isStopped && (
        <span
          onClick={onStartClick}
          style={{
            display: "inline-block",
            marginTop: 10,
            padding: "4px 10px",
            borderRadius: 4,
            background: "rgba(52,211,153,0.12)",
            color: "#34d399",
            fontSize: 11,
            border: "1px solid rgba(52,211,153,0.3)",
            cursor: "pointer",
          }}
        >
          ▶ Start
        </span>
      )}
    </div>
  );
}
