import { Input, Select, Space, Typography } from "antd";
import { useMemo } from "react";
import type { DeviceSummary } from "../../types";
import {
  AGGREGATE_OPS,
  ON_MISSING_MODES,
  buildSourceOptions,
  normalizeSourcesToIds,
  parseAggregateParams,
  serializeAggregateParams,
  type AggregateParams,
} from "../../utils/aggregateParams";

const OP_OPTIONS = AGGREGATE_OPS.map((op) => ({ value: op, label: op }));
const ON_MISSING_OPTIONS = ON_MISSING_MODES.map((m) => ({ value: m, label: m }));

interface AggregateParamsEditorProps {
  /** Current mode_params as the row's JSON string. */
  value: string;
  /** Name of the register being aggregated (default source register). */
  registerName: string;
  /** The aggregating device — excluded from the source list. */
  deviceId: string;
  devices: DeviceSummary[];
  onChange: (json: string) => void;
}

/**
 * Structured editor for `data_mode = "aggregate"` params. Reads/writes the same
 * JSON string the raw-params textarea uses, so the save path is unchanged.
 * Sources are always written as device ids; name references found in an
 * existing config are mapped to ids on load so the Select can display them.
 */
export function AggregateParamsEditor({
  value,
  registerName,
  deviceId,
  devices,
  onChange,
}: AggregateParamsEditorProps) {
  const params = useMemo(() => {
    const parsed = parseAggregateParams(value);
    return { ...parsed, sources: normalizeSourcesToIds(parsed.sources, devices) };
  }, [value, devices]);
  const sourceOptions = useMemo(
    () => buildSourceOptions(devices, deviceId),
    [devices, deviceId],
  );

  const update = (patch: Partial<AggregateParams>) => {
    onChange(serializeAggregateParams({ ...params, ...patch }));
  };

  return (
    <Space direction="vertical" size={4} style={{ width: "100%" }}>
      <Select
        mode="multiple"
        placeholder="Source devices"
        value={params.sources}
        options={sourceOptions}
        style={{ width: "100%" }}
        onChange={(sources: string[]) => update({ sources })}
        showSearch
        optionFilterProp="label"
      />
      <Space.Compact style={{ width: "100%" }}>
        <Select
          value={params.op}
          options={OP_OPTIONS}
          style={{ width: 130 }}
          onChange={(op) => update({ op })}
        />
        <Input
          placeholder={`register (default: ${registerName})`}
          value={params.register ?? ""}
          onChange={(e) => update({ register: e.target.value || undefined })}
        />
        {params.op === "weighted_avg" && (
          <Input
            placeholder="weight_register"
            value={params.weight_register ?? ""}
            status={params.weight_register ? undefined : "error"}
            onChange={(e) => update({ weight_register: e.target.value || undefined })}
          />
        )}
        <Select
          value={params.on_missing}
          options={ON_MISSING_OPTIONS}
          style={{ width: 130 }}
          onChange={(on_missing) => update({ on_missing })}
        />
      </Space.Compact>
      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
        Energy / power / current: <code>sum</code>. Voltage / frequency: <code>avg</code>{" "}
        (not sum). Power factor: <code>weighted_avg</code> by a power register. Values lag
        sources by up to one update interval.
      </Typography.Text>
    </Space>
  );
}
