import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "./api";
import { writeEventApi } from "./writeEventApi";

vi.mock("./api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

describe("writeEventApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("list() GETs the device's write-events", async () => {
    mockApi.get.mockResolvedValue({ data: { data: [], message: "", success: true } });
    await writeEventApi.list("d1");
    expect(mockApi.get).toHaveBeenCalledWith("/devices/d1/write-events");
  });

  it("ack() POSTs to the ack endpoint and unwraps the body", async () => {
    mockApi.post.mockResolvedValue({ data: { data: { unread: 0 }, message: "", success: true } });
    const res = await writeEventApi.ack("d1");
    expect(mockApi.post).toHaveBeenCalledWith("/devices/d1/write-events/ack");
    expect(res.data).toEqual({ unread: 0 });
  });
});
