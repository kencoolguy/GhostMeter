import type { DeviceSummary } from "../types";

/** Mirrors backend `app/simulation/aggregate.py` (AGGREGATE_OPS / ON_MISSING_MODES). */
export const AGGREGATE_OPS = ["sum", "avg", "weighted_avg", "max", "min"] as const;
export type AggregateOp = (typeof AGGREGATE_OPS)[number];

export const ON_MISSING_MODES = ["last_known", "zero", "skip"] as const;
export type OnMissing = (typeof ON_MISSING_MODES)[number];

export interface AggregateParams {
  op: AggregateOp;
  sources: string[];
  register?: string;
  weight_register?: string;
  on_missing: OnMissing;
}

export const DEFAULT_AGGREGATE_PARAMS: AggregateParams = {
  op: "sum",
  sources: [],
  on_missing: "last_known",
};

function isOp(v: unknown): v is AggregateOp {
  return typeof v === "string" && (AGGREGATE_OPS as readonly string[]).includes(v);
}

function isOnMissing(v: unknown): v is OnMissing {
  return typeof v === "string" && (ON_MISSING_MODES as readonly string[]).includes(v);
}

/**
 * Parse the row's JSON params into a well-formed AggregateParams, tolerating
 * a half-edited / foreign-mode blob (e.g. `{"value": 230}` left over from
 * static mode) by falling back to defaults field by field.
 */
export function parseAggregateParams(json: string): AggregateParams {
  let raw: unknown;
  try {
    raw = JSON.parse(json);
  } catch {
    return { ...DEFAULT_AGGREGATE_PARAMS };
  }
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { ...DEFAULT_AGGREGATE_PARAMS };
  }
  const obj = raw as Record<string, unknown>;
  const sources = Array.isArray(obj.sources)
    ? obj.sources.filter((s): s is string => typeof s === "string" && s.length > 0)
    : [];
  const params: AggregateParams = {
    op: isOp(obj.op) ? obj.op : DEFAULT_AGGREGATE_PARAMS.op,
    sources,
    on_missing: isOnMissing(obj.on_missing)
      ? obj.on_missing
      : DEFAULT_AGGREGATE_PARAMS.on_missing,
  };
  if (typeof obj.register === "string" && obj.register.trim()) {
    params.register = obj.register;
  }
  if (typeof obj.weight_register === "string" && obj.weight_register.trim()) {
    params.weight_register = obj.weight_register;
  }
  return params;
}

/** Serialize for the row's JSON field, dropping empty optionals and an
 * unused weight_register (the backend rejects it outside weighted_avg). */
export function serializeAggregateParams(params: AggregateParams): string {
  const out: Record<string, unknown> = {
    op: params.op,
    sources: params.sources,
  };
  if (params.register?.trim()) out.register = params.register.trim();
  if (params.op === "weighted_avg" && params.weight_register?.trim()) {
    out.weight_register = params.weight_register.trim();
  }
  out.on_missing = params.on_missing;
  return JSON.stringify(out, null, 2);
}

export interface SourceOption {
  value: string;
  label: string;
}

/**
 * Selectable source devices for an aggregating device.
 *
 * The backend accepts a device name or id; the UI always sends the **id** so a
 * later rename or a second device with the same name can never change what a
 * saved config points at. The label carries the human-readable name (and the
 * first id characters when several devices share a name). The aggregating
 * device itself is excluded (self-reference is rejected server-side).
 */
export function buildSourceOptions(
  devices: DeviceSummary[],
  selfDeviceId: string,
): SourceOption[] {
  const nameCount = new Map<string, number>();
  for (const d of devices) {
    nameCount.set(d.name, (nameCount.get(d.name) ?? 0) + 1);
  }
  return devices
    .filter((d) => d.id !== selfDeviceId)
    .map((d) => ({
      value: d.id,
      label:
        (nameCount.get(d.name) ?? 0) > 1
          ? `${d.name} (${d.template_name}, ${d.id.slice(0, 8)})`
          : `${d.name} (${d.template_name})`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Map stored source references to device ids so they match the option values.
 *
 * Configs written through the API (or imported) may reference devices by
 * name; a name that resolves to exactly one device becomes that device's id.
 * Ambiguous or unknown references are kept verbatim so the Select shows them
 * as plain tags and the backend can report the problem on save.
 */
export function normalizeSourcesToIds(
  sources: string[],
  devices: DeviceSummary[],
): string[] {
  const ids = new Set(devices.map((d) => d.id));
  const byName = new Map<string, string[]>();
  for (const d of devices) {
    byName.set(d.name, [...(byName.get(d.name) ?? []), d.id]);
  }
  return sources.map((ref) => {
    if (ids.has(ref)) return ref;
    const matches = byName.get(ref);
    return matches?.length === 1 ? matches[0] : ref;
  });
}
