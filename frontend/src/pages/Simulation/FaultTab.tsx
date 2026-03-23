import { Button, Card, Descriptions, Input, Select, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useSimulationStore } from "../../stores/simulationStore";
import type { FaultType } from "../../types";

const FAULT_TYPE_OPTIONS: { value: FaultType; label: string }[] = [
  { value: "delay", label: "Delay" },
  { value: "timeout", label: "Timeout" },
  { value: "exception", label: "Exception" },
  { value: "intermittent", label: "Intermittent" },
];

export function FaultTab({ deviceId }: { deviceId: string }) {
  const { currentFault, loading, fetchFault, setFault, clearFault } =
    useSimulationStore();

  const [faultType, setFaultType] = useState<FaultType>("delay");
  const [paramsJson, setParamsJson] = useState("{}");

  useEffect(() => {
    fetchFault(deviceId);
  }, [deviceId, fetchFault]);

  const handleSetFault = async () => {
    let parsedParams: Record<string, unknown>;
    try {
      parsedParams = JSON.parse(paramsJson);
    } catch {
      message.error("Invalid JSON in fault params");
      return;
    }
    await setFault(deviceId, {
      fault_type: faultType,
      params: parsedParams,
    });
  };

  const handleClearFault = async () => {
    await clearFault(deviceId);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card title="Set Fault" size="small">
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Typography.Text strong>Fault Type</Typography.Text>
            <Select
              value={faultType}
              options={FAULT_TYPE_OPTIONS}
              style={{ width: "100%", marginTop: 4 }}
              onChange={setFaultType}
            />
          </div>
          <div>
            <Typography.Text strong>Parameters (JSON)</Typography.Text>
            <Input.TextArea
              value={paramsJson}
              rows={4}
              style={{ fontFamily: "monospace", fontSize: 12, marginTop: 4 }}
              placeholder='{"delay_ms": 500}'
              onChange={(e) => setParamsJson(e.target.value)}
            />
          </div>
          <Button type="primary" onClick={handleSetFault} loading={loading}>
            Set Fault
          </Button>
        </Space>
      </Card>

      <Card title="Current Fault" size="small">
        {currentFault ? (
          <div>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Fault Type">
                {currentFault.fault_type}
              </Descriptions.Item>
              <Descriptions.Item label="Parameters">
                <code style={{ fontSize: 12 }}>
                  {JSON.stringify(currentFault.params, null, 2)}
                </code>
              </Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
              <Button danger onClick={handleClearFault} loading={loading}>
                Clear Fault
              </Button>
            </div>
          </div>
        ) : (
          <Typography.Text type="secondary">No active fault</Typography.Text>
        )}
      </Card>
    </div>
  );
}
