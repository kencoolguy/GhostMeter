import { describe, expect, it } from "vitest";
import type { DeviceSummary } from "../types";
import {
  buildSourceOptions,
  DEFAULT_AGGREGATE_PARAMS,
  parseAggregateParams,
  serializeAggregateParams,
} from "./aggregateParams";

function device(partial: Partial<DeviceSummary> & { id: string; name: string }): DeviceSummary {
  return {
    template_id: "t",
    template_name: "Meter",
    slave_id: 1,
    status: "stopped",
    port: 502,
    description: null,
    mqtt_publishing: false,
    created_at: "",
    updated_at: "",
    ...partial,
  };
}

describe("parseAggregateParams", () => {
  it("returns defaults for invalid JSON", () => {
    expect(parseAggregateParams("{oops")).toEqual(DEFAULT_AGGREGATE_PARAMS);
  });

  it("returns defaults for a non-object", () => {
    expect(parseAggregateParams("[1,2]")).toEqual(DEFAULT_AGGREGATE_PARAMS);
  });

  it("keeps valid fields and drops unknown values", () => {
    const parsed = parseAggregateParams(
      JSON.stringify({
        op: "weighted_avg",
        sources: ["PM-01", 42, ""],
        register: "power_factor_total",
        weight_register: "total_power",
        on_missing: "bogus",
        value: 230,
      }),
    );
    expect(parsed).toEqual({
      op: "weighted_avg",
      sources: ["PM-01"],
      register: "power_factor_total",
      weight_register: "total_power",
      on_missing: "last_known",
    });
  });

  it("falls back to defaults for a foreign-mode blob", () => {
    expect(parseAggregateParams('{"value": 230}')).toEqual(DEFAULT_AGGREGATE_PARAMS);
  });
});

describe("serializeAggregateParams", () => {
  it("omits empty optionals", () => {
    const json = serializeAggregateParams({
      op: "sum",
      sources: ["PM-01"],
      register: "  ",
      on_missing: "zero",
    });
    expect(JSON.parse(json)).toEqual({ op: "sum", sources: ["PM-01"], on_missing: "zero" });
  });

  it("drops weight_register unless op is weighted_avg", () => {
    const sum = serializeAggregateParams({
      op: "sum",
      sources: ["PM-01"],
      weight_register: "total_power",
      on_missing: "last_known",
    });
    expect(JSON.parse(sum)).not.toHaveProperty("weight_register");

    const weighted = serializeAggregateParams({
      op: "weighted_avg",
      sources: ["PM-01"],
      weight_register: "total_power",
      on_missing: "last_known",
    });
    expect(JSON.parse(weighted).weight_register).toBe("total_power");
  });

  it("round-trips through parse", () => {
    const params = {
      op: "avg" as const,
      sources: ["PM-01", "PM-02"],
      register: "voltage_l1",
      on_missing: "skip" as const,
    };
    expect(parseAggregateParams(serializeAggregateParams(params))).toEqual(params);
  });
});

describe("buildSourceOptions", () => {
  it("excludes the device itself and uses names for unique devices", () => {
    const options = buildSourceOptions(
      [device({ id: "a", name: "MVCB" }), device({ id: "b", name: "PM-01" })],
      "a",
    );
    expect(options).toEqual([{ value: "PM-01", label: "PM-01 (Meter)" }]);
  });

  it("falls back to ids for duplicate names", () => {
    const options = buildSourceOptions(
      [
        device({ id: "11111111-aaaa", name: "PM" }),
        device({ id: "22222222-bbbb", name: "PM" }),
      ],
      "self",
    );
    expect(options.map((o) => o.value)).toEqual(["11111111-aaaa", "22222222-bbbb"]);
    expect(options[0].label).toContain("11111111");
  });

  it("sorts by label", () => {
    const options = buildSourceOptions(
      [device({ id: "1", name: "PM-02" }), device({ id: "2", name: "PM-01" })],
      "self",
    );
    expect(options.map((o) => o.value)).toEqual(["PM-01", "PM-02"]);
  });
});
