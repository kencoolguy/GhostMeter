import { Drawer, Empty, List, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { writeEventApi } from "../../services/writeEventApi";
import type { WriteEventSummary } from "../../types";

const { Text } = Typography;

interface WriteEventsDrawerProps {
  deviceId: string;
  deviceName: string;
  open: boolean;
  onClose: () => void;
}

export function WriteEventsDrawer({
  deviceId,
  deviceName,
  open,
  onClose,
}: WriteEventsDrawerProps) {
  const [events, setEvents] = useState<WriteEventSummary[]>([]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      const res = await writeEventApi.list(deviceId);
      if (cancelled) return;
      setEvents(res.data ?? []);
      // Mark read once the list has been viewed (resets the unread badge).
      await writeEventApi.ack(deviceId);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, deviceId]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={360}
      title={`Write Events — ${deviceName}`}
    >
      {events.length === 0 ? (
        <Empty description="No writes received yet" />
      ) : (
        <List
          size="small"
          dataSource={events}
          renderItem={(e) => {
            const time = new Date(e.timestamp).toLocaleTimeString();
            return (
              <List.Item style={{ padding: "6px 0", display: "block" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {time}
                  </Text>
                  <Tag color="geekblue" style={{ fontSize: 10 }}>
                    {e.operation}
                  </Tag>
                </div>
                <Text style={{ fontSize: 12 }}>
                  {e.register_name ?? `@${e.address}`} = [{e.values.join(", ")}]
                </Text>
              </List.Item>
            );
          }}
        />
      )}
    </Drawer>
  );
}
