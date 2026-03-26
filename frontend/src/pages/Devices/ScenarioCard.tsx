import { PlayCircleOutlined, StopOutlined } from "@ant-design/icons";
import { Badge, Button, Card, List, Progress, Select, Space, Typography, message } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { scenarioApi } from "../../services/scenarioApi";
import type { ScenarioExecutionStatus, ScenarioSummary } from "../../types/scenario";

const ANOMALY_BADGE_COLORS: Record<string, string> = {
  spike: "orange",
  drift: "blue",
  flatline: "default",
  out_of_range: "red",
  data_loss: "purple",
};

interface ScenarioCardProps {
  deviceId: string;
  templateId: string;
  deviceStatus: string;
}

export function ScenarioCard({ deviceId, templateId, deviceStatus }: ScenarioCardProps) {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<ScenarioExecutionStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    scenarioApi.list(templateId).then((resp) => {
      setScenarios(resp.data ?? []);
    });
  }, [templateId]);

  const pollStatus = useCallback(() => {
    scenarioApi.getExecutionStatus(deviceId).then((resp) => {
      const data = resp.data;
      if (data) {
        setStatus(data);
        if (data.status === "running" && !pollRef.current) {
          pollRef.current = setInterval(pollStatus, 1000);
        }
        if (data.status === "completed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    }).catch(() => {
      setStatus(null);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    });
  }, [deviceId]);

  useEffect(() => {
    // Check if scenario is already running on mount
    pollStatus();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollStatus]);

  const handleStart = async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      await scenarioApi.startExecution(deviceId, selectedId);
      message.success("Scenario started");
      // Start polling
      pollRef.current = setInterval(pollStatus, 1000);
      pollStatus();
    } catch {
      message.error("Failed to start scenario");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await scenarioApi.stopExecution(deviceId);
      message.success("Scenario stopped");
      setStatus(null);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    } catch {
      message.error("Failed to stop scenario");
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status?.status === "running";
  const isCompleted = status?.status === "completed";
  const percent = status
    ? Math.round((status.elapsed_seconds / status.total_duration_seconds) * 100)
    : 0;

  return (
    <Card
      title={
        <Space>
          <span>Scenario</span>
          {isRunning && <Badge status="processing" text="Running" />}
          {isCompleted && <Badge status="success" text="Completed" />}
        </Space>
      }
      style={{ marginTop: 16 }}
    >
      {isRunning && status ? (
        <div>
          <Typography.Text strong>{status.scenario_name}</Typography.Text>
          <Progress
            percent={percent}
            format={() => `${status.elapsed_seconds}s / ${status.total_duration_seconds}s`}
            style={{ marginTop: 8, marginBottom: 12 }}
          />
          {status.active_steps.length > 0 && (
            <List
              size="small"
              header={<Typography.Text type="secondary">Active Steps</Typography.Text>}
              dataSource={status.active_steps}
              renderItem={(item) => (
                <List.Item>
                  <span>{item.register_name}</span>
                  <Badge color={ANOMALY_BADGE_COLORS[item.anomaly_type] ?? "default"} text={item.anomaly_type} />
                  <Typography.Text type="secondary">{item.remaining_seconds}s remaining</Typography.Text>
                </List.Item>
              )}
              style={{ marginBottom: 12 }}
            />
          )}
          <Button danger type="primary" icon={<StopOutlined />} onClick={handleStop} loading={loading}>
            Stop Scenario
          </Button>
        </div>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          {isCompleted && (
            <Typography.Text type="success">Scenario completed successfully</Typography.Text>
          )}
          <Select
            placeholder="Select a scenario"
            style={{ width: "100%" }}
            value={selectedId}
            onChange={setSelectedId}
            options={scenarios.map((s) => ({
              value: s.id,
              label: `${s.name} (${s.total_duration_seconds}s)`,
            }))}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleStart}
            loading={loading}
            disabled={!selectedId || deviceStatus !== "running"}
            style={{ backgroundColor: "#52c41a", borderColor: "#52c41a" }}
          >
            {isCompleted ? "Run Again" : "Run Scenario"}
          </Button>
          {deviceStatus !== "running" && (
            <Typography.Text type="secondary">Start the device to run scenarios</Typography.Text>
          )}
        </Space>
      )}
    </Card>
  );
}
