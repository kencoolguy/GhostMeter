import { Button, Drawer, Empty, List, Tag, Typography } from "antd";
import type { MonitorEvent } from "../../types";

const { Text } = Typography;

const EVENT_COLORS: Record<string, string> = {
  device_start: "green",
  device_stop: "default",
  anomaly_inject: "orange",
  anomaly_clear: "blue",
  fault_set: "red",
  fault_clear: "blue",
};

interface EventDrawerProps {
  open: boolean;
  events: MonitorEvent[];
  onClose: () => void;
  onClear: () => void;
}

export function EventDrawer({ open, events, onClose, onClear }: EventDrawerProps) {
  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={360}
      title="Event Log"
      extra={
        <Button size="small" onClick={onClear} disabled={events.length === 0}>
          Clear
        </Button>
      }
    >
      {events.length === 0 ? (
        <Empty description="No events yet" />
      ) : (
        <List
          size="small"
          dataSource={events}
          renderItem={(e) => {
            const time = new Date(e.timestamp).toLocaleTimeString();
            return (
              <List.Item style={{ padding: "6px 0", display: "block" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{time}</Text>
                  <Tag color={EVENT_COLORS[e.event_type] ?? "default"} style={{ fontSize: 10 }}>
                    {e.event_type}
                  </Tag>
                  <Text strong style={{ fontSize: 12 }}>{e.device_name}</Text>
                </div>
                <Text style={{ fontSize: 12 }}>{e.detail}</Text>
              </List.Item>
            );
          }}
        />
      )}
    </Drawer>
  );
}
