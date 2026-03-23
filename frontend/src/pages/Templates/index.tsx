import { Typography } from "antd";
import { TemplateList } from "./TemplateList";

export default function TemplatesPage() {
  return (
    <div>
      <Typography.Title level={2}>Device Templates</Typography.Title>
      <TemplateList />
    </div>
  );
}
