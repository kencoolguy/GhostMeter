import { List, Tag, Typography } from "antd";
import type { MonitorEvent } from "../../types";

const { Text } = Typography;

interface EventLogProps {
  events: MonitorEvent[];
}

const EVENT_COLORS: Record<string, string> = {
  device_start: "green",
  device_stop: "default",
  anomaly_inject: "orange",
  anomaly_clear: "blue",
  fault_set: "red",
  fault_clear: "blue",
};

export function EventLog({ events }: EventLogProps) {
  if (events.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 20, color: "#999" }}>
        No events yet
      </div>
    );
  }

  return (
    <List
      size="small"
      dataSource={events}
      style={{ maxHeight: 300, overflow: "auto" }}
      renderItem={(event) => {
        const time = new Date(event.timestamp).toLocaleTimeString();
        return (
          <List.Item style={{ padding: "4px 0" }}>
            <Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
              {time}
            </Text>
            <Tag color={EVENT_COLORS[event.event_type] ?? "default"} style={{ fontSize: 11 }}>
              {event.event_type}
            </Tag>
            <Text style={{ fontSize: 13 }}>
              <Text strong style={{ fontSize: 13 }}>{event.device_name}</Text>
              {" — "}
              {event.detail}
            </Text>
          </List.Item>
        );
      }}
    />
  );
}
