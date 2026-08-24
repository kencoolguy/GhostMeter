import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "./api";
import { deviceApi } from "./deviceApi";

vi.mock("./api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe("deviceApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("list() GETs /devices and unwraps the response body", async () => {
    mockApi.get.mockResolvedValue({ data: { data: [{ id: "d1" }], message: "", success: true } });
    const res = await deviceApi.list();
    expect(mockApi.get).toHaveBeenCalledWith("/devices");
    expect(res.data).toEqual([{ id: "d1" }]);
  });

  it("start() POSTs to /devices/:id/start", async () => {
    mockApi.post.mockResolvedValue({ data: { data: { id: "d1" }, message: "", success: true } });
    await deviceApi.start("d1");
    expect(mockApi.post).toHaveBeenCalledWith("/devices/d1/start");
  });

  it("batchStart() POSTs a device_ids payload", async () => {
    mockApi.post.mockResolvedValue({
      data: { data: { success_count: 2, skipped_count: 0 }, message: "", success: true },
    });
    await deviceApi.batchStart(["a", "b"]);
    expect(mockApi.post).toHaveBeenCalledWith("/devices/batch/start", { device_ids: ["a", "b"] });
  });

  it("delete() DELETEs /devices/:id", async () => {
    mockApi.delete.mockResolvedValue({ data: { data: null, message: "", success: true } });
    await deviceApi.delete("d1");
    expect(mockApi.delete).toHaveBeenCalledWith("/devices/d1");
  });
});
