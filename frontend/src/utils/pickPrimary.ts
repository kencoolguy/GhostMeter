import type { DeviceMonitorData, RegisterData } from "../types";

const PREFERRED = ["total_power", "ac_power", "total_energy"];

export function pickPrimaryName(device: DeviceMonitorData): string | null {
  const names = device.registers.map((r) => r.name);
  return PREFERRED.find((n) => names.includes(n)) ?? names[0] ?? null;
}

export function pickPrimaryAndSecondary(device: DeviceMonitorData): {
  primary: RegisterData | null;
  secondary: RegisterData | null;
} {
  const primaryName = pickPrimaryName(device);
  const names = device.registers.map((r) => r.name);
  const secondaryName =
    PREFERRED.find((n) => names.includes(n) && n !== primaryName) ??
    names.find((n) => n !== primaryName) ??
    null;
  return {
    primary: primaryName ? device.registers.find((r) => r.name === primaryName) ?? null : null,
    secondary: secondaryName ? device.registers.find((r) => r.name === secondaryName) ?? null : null,
  };
}
