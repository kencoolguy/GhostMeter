import { describe, it, expect, vi, beforeEach } from "vitest";
import { deviceApi } from "../services/deviceApi";
import { useDeviceStore } from "./deviceStore";

vi.mock("../services/deviceApi", () => ({
  deviceApi: {
    list: vi.fn(), get: vi.fn(), create: vi.fn(), delete: vi.fn(),
    start: vi.fn(), stop: vi.fn(),
  },
}));
vi.mock("antd", () => ({ message: { success: vi.fn(), error: vi.fn() } }));

const mockApi = deviceApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const initialState = useDeviceStore.getState();

beforeEach(() => {
  vi.clearAllMocks();
  useDeviceStore.setState(initialState, true);
});

describe("deviceStore", () => {
  it("fetchDevices populates devices and clears loading", async () => {
    mockApi.list.mockResolvedValue({ data: [{ id: "d1" }], message: "", success: true });
    await useDeviceStore.getState().fetchDevices();
    const s = useDeviceStore.getState();
    expect(s.devices).toEqual([{ id: "d1" }]);
    expect(s.loading).toBe(false);
  });

  it("fetchDevices defaults to [] when response data is null", async () => {
    mockApi.list.mockResolvedValue({ data: null, message: "", success: true });
    await useDeviceStore.getState().fetchDevices();
    expect(useDeviceStore.getState().devices).toEqual([]);
  });

  it("createDevice returns the created device on success", async () => {
    mockApi.create.mockResolvedValue({ data: { id: "d2" }, message: "", success: true });
    const res = await useDeviceStore.getState().createDevice({} as never);
    expect(res).toEqual({ id: "d2" });
  });

  it("createDevice returns null and clears loading when the API rejects", async () => {
    mockApi.create.mockRejectedValue(new Error("400"));
    const res = await useDeviceStore.getState().createDevice({} as never);
    expect(res).toBeNull();
    expect(useDeviceStore.getState().loading).toBe(false);
  });

  it("startDevice returns true on success and false on failure", async () => {
    mockApi.start.mockResolvedValue({ data: {}, message: "", success: true });
    expect(await useDeviceStore.getState().startDevice("d1")).toBe(true);
    mockApi.start.mockRejectedValue(new Error("x"));
    expect(await useDeviceStore.getState().startDevice("d1")).toBe(false);
  });

  it("clearCurrentDevice resets currentDevice", () => {
    useDeviceStore.setState({ currentDevice: { id: "d1" } as never });
    useDeviceStore.getState().clearCurrentDevice();
    expect(useDeviceStore.getState().currentDevice).toBeNull();
  });
});
