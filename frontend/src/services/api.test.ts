import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.mock is hoisted above imports; vi.hoisted keeps errorMock available
// to the (also-hoisted) factory without a "used before initialization" error.
const { errorMock } = vi.hoisted(() => ({ errorMock: vi.fn() }));
vi.mock("antd", () => ({ message: { error: errorMock } }));

import { api } from "./api";

interface RejectedHandler {
  rejected: (e: unknown) => Promise<never>;
}

function rejectedHandler(): (e: unknown) => Promise<never> {
  const interceptors = api.interceptors.response as unknown as {
    handlers: RejectedHandler[];
  };
  return interceptors.handlers[0].rejected;
}

describe("api instance", () => {
  it("targets the v1 API with a 10s timeout", () => {
    expect(api.defaults.baseURL).toBe("/api/v1");
    expect(api.defaults.timeout).toBe(10000);
  });
});

describe("api error interceptor", () => {
  beforeEach(() => errorMock.mockClear());

  it("surfaces the backend detail via antd message", async () => {
    await expect(
      rejectedHandler()({ response: { data: { detail: "boom", error_code: "X" } } }),
    ).rejects.toBeDefined();
    expect(errorMock).toHaveBeenCalledWith("boom");
  });

  it("falls back to error.message when there is no response body", async () => {
    await expect(rejectedHandler()({ message: "network down" })).rejects.toBeDefined();
    expect(errorMock).toHaveBeenCalledWith("network down");
  });
});
