import { Typography } from "antd";
import { DeviceList } from "./DeviceList";

export default function DevicesPage() {
  return (
    <div>
      <Typography.Title level={2}>Device Instances</Typography.Title>
      <DeviceList />
    </div>
  );
}
