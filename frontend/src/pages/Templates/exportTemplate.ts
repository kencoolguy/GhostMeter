import { templateApi } from "../../services/templateApi";

export async function exportTemplate(templateId: string, templateName: string) {
  const blob = await templateApi.exportTemplate(templateId);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${templateName.replace(/\s+/g, "_").toLowerCase()}.json`;
  a.click();
  window.URL.revokeObjectURL(url);
}
