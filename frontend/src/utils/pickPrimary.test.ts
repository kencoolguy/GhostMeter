import { describe, it, expect } from "vitest";
import { pickPrimaryName, pickPrimaryAndSecondary } from "./pickPrimary";
import type { DeviceMonitorData, RegisterData } from "../types";

const reg = (name: string): RegisterData => ({ name, value: 1, unit: "" });

function device(registers: RegisterData[]): DeviceMonitorData {
  return {
    device_id: "d1", name: "D1", template_name: null, slave_id: 1, port: 502,
    status: "running", registers, active_anomalies: [], active_fault: null,
    stats: { request_count: 0, success_count: 0, error_count: 0, avg_response_ms: 0 },
    mqtt_stats: null, write_events: { unread: 0, latest: null },
  };
}

describe("pickPrimaryName", () => {
  it("prefers total_power over a non-preferred register", () => {
    expect(pickPrimaryName(device([reg("voltage"), reg("total_power")]))).toBe("total_power");
  });
  it("follows PREFERRED order (ac_power beats a non-preferred first register)", () => {
    expect(pickPrimaryName(device([reg("current"), reg("ac_power")]))).toBe("ac_power");
  });
  it("falls back to the first register when none are preferred", () => {
    expect(pickPrimaryName(device([reg("voltage"), reg("current")]))).toBe("voltage");
  });
  it("returns null when there are no registers", () => {
    expect(pickPrimaryName(device([]))).toBeNull();
  });
});

describe("pickPrimaryAndSecondary", () => {
  it("returns two distinct registers, primary preferred", () => {
    const { primary, secondary } = pickPrimaryAndSecondary(
      device([reg("total_power"), reg("total_energy"), reg("voltage")]),
    );
    expect(primary?.name).toBe("total_power");
    expect(secondary?.name).toBe("total_energy");
  });
  it("secondary falls back to first non-primary when no second preferred exists", () => {
    const { primary, secondary } = pickPrimaryAndSecondary(
      device([reg("total_power"), reg("voltage")]),
    );
    expect(primary?.name).toBe("total_power");
    expect(secondary?.name).toBe("voltage");
  });
  it("secondary is null when only one register exists", () => {
    const { secondary } = pickPrimaryAndSecondary(device([reg("total_power")]));
    expect(secondary).toBeNull();
  });
});
