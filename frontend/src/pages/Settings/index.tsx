import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { Button, Card, message, Modal, Space, Typography, Upload } from "antd";
import type { UploadProps } from "antd";
import { useState } from "react";
import { systemApi } from "../../services/systemApi";
import type { ImportResult } from "../../types/system";

export default function SettingsPage() {
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await systemApi.exportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ghostmeter-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      message.success("Configuration exported successfully");
    } catch {
      message.error("Export failed");
    } finally {
      setExporting(false);
    }
  };

  const formatResult = (result: ImportResult): string => {
    const lines: string[] = [];
    if (result.templates_created > 0)
      lines.push(`Templates created: ${result.templates_created}`);
    if (result.templates_updated > 0)
      lines.push(`Templates updated: ${result.templates_updated}`);
    if (result.templates_skipped > 0)
      lines.push(`Templates skipped: ${result.templates_skipped}`);
    if (result.devices_created > 0)
      lines.push(`Devices created: ${result.devices_created}`);
    if (result.devices_updated > 0)
      lines.push(`Devices updated: ${result.devices_updated}`);
    if (result.simulation_configs_set > 0)
      lines.push(`Simulation configs: ${result.simulation_configs_set}`);
    if (result.anomaly_schedules_set > 0)
      lines.push(`Anomaly schedules: ${result.anomaly_schedules_set}`);
    return lines.length > 0 ? lines.join("\n") : "No changes made";
  };

  const uploadProps: UploadProps = {
    accept: ".json",
    showUploadList: false,
    beforeUpload: async (file) => {
      setImporting(true);
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const resp = await systemApi.importConfig(data);
        if (resp.data) {
          Modal.success({
            title: "Import Complete",
            content: formatResult(resp.data),
            style: { whiteSpace: "pre-line" },
          });
        }
      } catch {
        message.error("Import failed — check file format");
      } finally {
        setImporting(false);
      }
      return false;
    },
  };

  return (
    <div>
      <Typography.Title level={2}>Settings</Typography.Title>
      <Card title="Configuration Management" style={{ maxWidth: 600 }}>
        <Typography.Paragraph>
          Export your full system configuration (templates, devices, simulation
          configs, anomaly schedules) as a JSON file. Import to restore or
          migrate to another instance.
        </Typography.Paragraph>
        <Space>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={handleExport}
            loading={exporting}
          >
            Export Config
          </Button>
          <Upload {...uploadProps}>
            <Button icon={<UploadOutlined />} loading={importing}>
              Import Config
            </Button>
          </Upload>
        </Space>
      </Card>
    </div>
  );
}
