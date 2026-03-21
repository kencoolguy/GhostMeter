import { UploadOutlined } from "@ant-design/icons";
import { Button, Modal, Upload, message } from "antd";
import type { UploadProps } from "antd";
import { templateApi } from "../../services/templateApi";
import { useTemplateStore } from "../../stores/templateStore";

const SAMPLE_JSON = `{
  "name": "My Device Template",
  "protocol": "modbus_tcp",
  "description": "Optional description",
  "registers": [
    {
      "name": "voltage",
      "address": 0,
      "function_code": 4,
      "data_type": "float32",
      "byte_order": "big_endian",
      "scale_factor": 1.0,
      "unit": "V",
      "description": "Line-to-neutral voltage",
      "sort_order": 0
    }
  ]
}`;

function showFormatHelp(errorMsg: string) {
  Modal.error({
    title: "Import Failed",
    width: 640,
    content: (
      <div>
        <p>{errorMsg}</p>
        <details>
          <summary style={{ cursor: "pointer", color: "#1677ff", marginTop: 12 }}>
            View expected JSON format
          </summary>
          <pre
            style={{
              marginTop: 8,
              padding: 12,
              backgroundColor: "#f5f5f5",
              borderRadius: 6,
              fontSize: 12,
              overflow: "auto",
              maxHeight: 360,
            }}
          >
            {SAMPLE_JSON}
          </pre>
          <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
            <p style={{ margin: "4px 0" }}><b>Required fields:</b> name, registers (at least one)</p>
            <p style={{ margin: "4px 0" }}><b>data_type:</b> int16 | uint16 | int32 | uint32 | float32 | float64</p>
            <p style={{ margin: "4px 0" }}><b>byte_order:</b> big_endian | little_endian | big_endian_word_swap | little_endian_word_swap</p>
            <p style={{ margin: "4px 0" }}><b>function_code:</b> 3 (Holding) | 4 (Input)</p>
          </div>
        </details>
      </div>
    ),
  });
}

export function ImportExportButtons() {
  const { fetchTemplates } = useTemplateStore();

  const handleImport: UploadProps["customRequest"] = async (options) => {
    const file = options.file as File;
    try {
      await templateApi.importTemplate(file);
      await fetchTemplates();
      options.onSuccess?.(null);
      message.success("Template imported successfully");
    } catch (error: unknown) {
      options.onError?.(error as Error);

      let errorMsg = "Unknown error occurred.";
      if (error && typeof error === "object" && "response" in error) {
        const resp = (error as { response?: { data?: { detail?: unknown } } }).response;
        const detail = resp?.data?.detail;
        if (typeof detail === "string") {
          errorMsg = detail;
        } else if (Array.isArray(detail)) {
          errorMsg = detail
            .map((d: { loc?: string[]; msg?: string }) => {
              const field = d.loc?.slice(1).join(".") ?? "";
              return field ? `${field}: ${d.msg}` : (d.msg ?? "");
            })
            .join("\n");
        }
      } else if (error instanceof Error) {
        errorMsg = error.message;
      }

      showFormatHelp(errorMsg);
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
