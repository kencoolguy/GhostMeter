import { useEffect } from "react";
import type { MonitorEvent } from "../../types";

interface EventToastProps {
  event: MonitorEvent | null;
  onDismiss: () => void;
  onOpenDrawer: () => void;
  autoDismissMs?: number;
}

const TYPE_PALETTE: Record<string, { border: string; color: string; label: string }> = {
  anomaly_inject: { border: "#fbbf24", color: "#fbbf24", label: "⚠ Anomaly" },
  fault_set:      { border: "#fb7185", color: "#fb7185", label: "⚠ Fault" },
  device_start:   { border: "#34d399", color: "#34d399", label: "▶ Start" },
  device_stop:    { border: "#9aa5b8", color: "#9aa5b8", label: "■ Stop" },
};

export function EventToast({ event, onDismiss, onOpenDrawer, autoDismissMs = 3000 }: EventToastProps) {
  useEffect(() => {
    if (!event) return;
    const t = setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(t);
  }, [event, onDismiss, autoDismissMs]);

  if (!event) return null;

  const palette = TYPE_PALETTE[event.event_type] ?? {
    border: "#22d3ee",
    color: "#22d3ee",
    label: event.event_type,
  };

  return (
    <div
      key={`${event.timestamp}-${event.device_id}-${event.event_type}`}
      className="gm-mon-toast"
      onClick={onOpenDrawer}
      style={{
        position: "fixed",
        top: 80,
        right: 24,
        width: 260,
        background: "#1a2030",
        border: `1px solid ${palette.border}`,
        borderRadius: 8,
        padding: "10px 12px",
        boxShadow: `0 0 24px ${palette.border}40`,
        cursor: "pointer",
        zIndex: 1000,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: palette.color, marginBottom: 4 }}>
        <span>{palette.label}</span>
        <span style={{ color: "#5f6b80" }}>just now</span>
      </div>
      <div style={{ color: "#e6edf5", fontSize: 12 }}>
        <b>{event.device_name}</b> — {event.detail}
      </div>
    </div>
  );
}
