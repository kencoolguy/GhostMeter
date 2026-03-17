import { UploadOutlined } from "@ant-design/icons";
import { Button, Upload } from "antd";
import type { UploadProps } from "antd";
import { templateApi } from "../../services/templateApi";
import { useTemplateStore } from "../../stores/templateStore";

export function ImportExportButtons() {
  const { fetchTemplates } = useTemplateStore();

  const handleImport: UploadProps["customRequest"] = async (options) => {
    const file = options.file as File;
    try {
      await templateApi.importTemplate(file);
      await fetchTemplates();
      options.onSuccess?.(null);
    } catch (error) {
      options.onError?.(error as Error);
    }
  };

  return (
    <Upload
      accept=".json"
      showUploadList={false}
      customRequest={handleImport}
    >
      <Button icon={<UploadOutlined />}>Import</Button>
    </Upload>
  );
}

export async function handleExport(templateId: string, templateName: string) {
  const blob = await templateApi.exportTemplate(templateId);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${templateName.replace(/\s+/g, "_").toLowerCase()}.json`;
  a.click();
  window.URL.revokeObjectURL(url);
}
