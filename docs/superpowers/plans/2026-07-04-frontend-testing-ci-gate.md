# Frontend Testing Harness + CI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a vitest unit-test harness on the frontend and add eslint + coverage-thresholded test gates to CI, establishing a ratchet coverage baseline on the highest-ROI pure-logic modules.

**Architecture:** vitest (Vite 8 native) with a jsdom environment, config merged into the existing `frontend/vite.config.ts`. Tests colocated next to source (`foo.test.ts`). Coverage scoped to `src/{utils,stores,services,hooks}` with a ratchet threshold set from the measured baseline. CI's `frontend` job gains a `lint` step and a `test:coverage` step.

**Tech Stack:** vitest, @vitest/coverage-v8, jsdom, @testing-library/react, @testing-library/jest-dom, existing eslint (flat config, PR #73).

## Global Constraints

- Branch: `feature/claude-frontend-testing-ci-gate-20260704` (already created from `dev`). Never commit to `dev`/`main`.
- All frontend commands run from `frontend/` working directory.
- Test files use **explicit vitest imports** (`import { describe, it, expect, vi } from "vitest"`) — vitest `globals` stays OFF, so no eslint globals override is needed.
- **No `any`** in test code — typescript-eslint `recommended` sets `@typescript-eslint/no-explicit-any` to error, and the new lint gate will catch it. Use `unknown` casts.
- Commit message format: `test:` / `feat:` / `ci:` / `docs:` per conventional commits. End each commit body with the Co-Authored-By trailer.
- `ApiResponse<T>` body shape is `{ data: T; message: string; success: boolean }`. Services return the whole body (`r.data`); stores read `response.data`.
- Coverage threshold is **ratchet**: set from the measured baseline (Task 5), only raised later, never an aspirational guess.

---

### Task 1: Vitest harness + utils tests

Stands up the runner (deps, config, setup, scripts) and proves it with the two pure `utils` modules.

**Files:**
- Modify: `frontend/package.json` (devDeps + scripts)
- Modify: `frontend/vite.config.ts` (add `test` block, switch import to `vitest/config`)
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/utils/pickPrimary.test.ts`
- Create: `frontend/src/utils/download.test.ts`

**Interfaces:**
- Consumes: `pickPrimaryName`, `pickPrimaryAndSecondary` from `src/utils/pickPrimary.ts`; `downloadBlob`, `downloadJson` from `src/utils/download.ts`.
- Produces: a working `npm run test:run` command that later tasks extend; `src/test/setup.ts` registering jest-dom matchers.

- [ ] **Step 1: Install test dependencies**

```bash
cd frontend
npm install -D vitest@^4 @vitest/coverage-v8@^4 jsdom@^25 @testing-library/react@^16 @testing-library/jest-dom@^6
```

> **Version note:** vitest **4** is required — the entire vitest 3.x line caps
> its Vite dependency at `^7`, which nests a second `vite@7` whose types clash
> with the repo's `vite@8` (`@vitejs/plugin-react`) and breaks `tsc`. vitest 4
> uses the top-level Vite 8.

- [ ] **Step 2: Add the setup file**

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { Blob } from "node:buffer";

// jsdom's Blob does not implement .text()/.arrayBuffer(); Node's does, and
// download.ts only needs Blob for the download path, so restoring the Node
// implementation globally is safe here.
globalThis.Blob = Blob as unknown as typeof globalThis.Blob;
```

> **tsconfig routing:** `setup.ts` imports `node:buffer`, which needs Node
> types, but `tsconfig.app.json` restricts `types` to `["vite/client"]`. Add
> `setup.ts` to `tsconfig.node.json`'s `include` and exclude it from
> `tsconfig.app.json` (`"exclude": ["src/test/setup.ts"]`) so `tsc -b` resolves
> the Node types. The test files themselves stay under `tsconfig.app.json`.

- [ ] **Step 3: Merge the vitest config into `vite.config.ts`**

Change the import to `vitest/config` and add a `test` block. Do **not** add a
`/// <reference types="vitest/config" />` triple-slash directive — eslint's
`@typescript-eslint/triple-slash-reference` forbids it and the `vitest/config`
import already provides the `test` field types. The file becomes:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: false,
    // Scope to unit tests under src/; the Playwright e2e specs in e2e/ use
    // @playwright/test and must not be collected by vitest.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: [
        "src/utils/**",
        "src/stores/**",
        "src/services/**",
        "src/hooks/**",
      ],
      reporter: ["text", "text-summary"],
    },
  },
});
```

- [ ] **Step 4: Add test scripts to `package.json`**

In the `"scripts"` block add:

```json
"test": "vitest",
"test:run": "vitest run",
"test:coverage": "vitest run --coverage"
```

- [ ] **Step 5: Write `src/utils/pickPrimary.test.ts`**

```ts
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
```

- [ ] **Step 6: Write `src/utils/download.test.ts`**

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { downloadBlob, downloadJson } from "./download";

describe("download", () => {
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    globalThis.URL.createObjectURL = vi.fn(() => "blob:mock");
    globalThis.URL.revokeObjectURL = vi.fn();
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates an object URL, clicks an anchor, and revokes the URL", () => {
    const blob = new Blob(["x"], { type: "text/plain" });
    downloadBlob(blob, "f.txt");
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
  });

  it("serializes data as a pretty-printed JSON blob", async () => {
    const createSpy = globalThis.URL.createObjectURL as ReturnType<typeof vi.fn>;
    downloadJson({ a: 1 }, "d.json");
    const blob = createSpy.mock.calls[0][0] as Blob;
    expect(blob.type).toBe("application/json");
    expect(await blob.text()).toBe('{\n  "a": 1\n}');
  });
});
```

- [ ] **Step 7: Run the tests**

Run: `npm run test:run`
Expected: PASS — 2 test files, 9 tests passing (pickPrimary 7, download 2). (First run also proves the harness is wired.)

- [ ] **Step 8: Verify typecheck + lint still pass**

Run: `npx tsc -b && npm run lint`
Expected: no errors. (Confirms the new test/config files don't break the build or lint gate.)

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts \
  frontend/src/test/setup.ts frontend/src/utils/pickPrimary.test.ts frontend/src/utils/download.test.ts
git commit -m "test: vitest harness + utils unit tests (#62)"
```

---

### Task 2: Service-layer tests

Covers the axios error interceptor and two representative API clients.

**Files:**
- Create: `frontend/src/services/api.test.ts`
- Create: `frontend/src/services/deviceApi.test.ts`
- Create: `frontend/src/services/writeEventApi.test.ts`

**Interfaces:**
- Consumes: `api` from `src/services/api.ts`; `deviceApi` from `src/services/deviceApi.ts`; `writeEventApi` from `src/services/writeEventApi.ts`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write `src/services/api.test.ts`**

```ts
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
```

- [ ] **Step 2: Write `src/services/deviceApi.test.ts`**

```ts
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
```

- [ ] **Step 3: Write `src/services/writeEventApi.test.ts`**

```ts
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
```

- [ ] **Step 4: Run the tests**

Run: `npm run test:run`
Expected: PASS — service tests green (api: 3, deviceApi: 4, writeEventApi: 2), plus Task 1's tests.

- [ ] **Step 5: Verify lint**

Run: `npm run lint`
Expected: no errors (confirms no `any` / unused slipped in).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.test.ts frontend/src/services/deviceApi.test.ts frontend/src/services/writeEventApi.test.ts
git commit -m "test: service-layer unit tests (api interceptor + clients) (#62)"
```

---

### Task 3: useWebSocket hook test

Covers the reconnect/backoff logic (rewritten in PR #73, highest regression risk).

**Files:**
- Create: `frontend/src/hooks/useWebSocket.test.ts`

**Interfaces:**
- Consumes: `useWebSocket` from `src/hooks/useWebSocket.ts`.
- Produces: nothing consumed later.

- [ ] **Step 1: Write `src/hooks/useWebSocket.test.ts`**

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "./useWebSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  close = vi.fn(() => {
    this.onclose?.();
  });
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
}

describe("useWebSocket", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("opens a socket and reports connected on open", () => {
    const { result } = renderHook(() => useWebSocket({ url: "ws://x", onMessage: vi.fn() }));
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      FakeWebSocket.instances[0].onopen?.();
    });
    expect(result.current.connected).toBe(true);
  });

  it("parses JSON messages and forwards them to onMessage", () => {
    const onMessage = vi.fn();
    renderHook(() => useWebSocket({ url: "ws://x", onMessage }));
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({ data: '{"a":1}' });
    });
    expect(onMessage).toHaveBeenCalledWith({ a: 1 });
  });

  it("ignores malformed JSON without throwing", () => {
    const onMessage = vi.fn();
    renderHook(() => useWebSocket({ url: "ws://x", onMessage }));
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({ data: "not json" });
    });
    expect(onMessage).not.toHaveBeenCalled();
  });

  it("reconnects after close once the backoff timer fires", () => {
    renderHook(() => useWebSocket({ url: "ws://x", onMessage: vi.fn(), reconnectInterval: 1000 }));
    act(() => {
      FakeWebSocket.instances[0].onclose?.();
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("does not reconnect after unmount", () => {
    const { unmount } = renderHook(() => useWebSocket({ url: "ws://x", onMessage: vi.fn() }));
    unmount();
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the test**

Run: `npm run test:run src/hooks/useWebSocket.test.ts`
Expected: PASS — 5 tests.

- [ ] **Step 3: Verify lint**

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useWebSocket.test.ts
git commit -m "test: useWebSocket connect/reconnect/cleanup (#62)"
```

---

### Task 4: Store tests

Covers the pure reducer logic in `monitorStore` and the async action flow in `deviceStore`.

**Files:**
- Create: `frontend/src/stores/monitorStore.test.ts`
- Create: `frontend/src/stores/deviceStore.test.ts`

**Interfaces:**
- Consumes: `useMonitorStore` from `src/stores/monitorStore.ts`; `useDeviceStore` from `src/stores/deviceStore.ts`; `deviceApi` (mocked) from `src/services/deviceApi.ts`.
- Produces: nothing consumed later.

- [ ] **Step 1: Write `src/stores/monitorStore.test.ts`**

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { useMonitorStore } from "./monitorStore";
import type { DeviceMonitorData, MonitorEvent, MonitorUpdate } from "../types";

function device(overrides: Partial<DeviceMonitorData> = {}): DeviceMonitorData {
  return {
    device_id: "d1", name: "D1", template_name: null, slave_id: 1, port: 502,
    status: "running",
    registers: [{ name: "total_power", value: 42, unit: "W" }],
    active_anomalies: [], active_fault: null,
    stats: { request_count: 0, success_count: 0, error_count: 0, avg_response_ms: 0 },
    mqtt_stats: null, write_events: { unread: 0, latest: null },
    ...overrides,
  };
}

function update(overrides: Partial<MonitorUpdate> = {}): MonitorUpdate {
  return {
    type: "monitor_update", timestamp: "t", devices: [device()],
    events: [], mqtt_broker_connected: false, ...overrides,
  };
}

const initialState = useMonitorStore.getState();
beforeEach(() => {
  useMonitorStore.setState(initialState, true);
});

describe("monitorStore.handleMonitorUpdate", () => {
  it("stores devices and appends a history point for the primary register", () => {
    useMonitorStore.getState().handleMonitorUpdate(update());
    const s = useMonitorStore.getState();
    expect(s.devices).toHaveLength(1);
    expect(s.registerHistory["d1:total_power"]).toHaveLength(1);
    expect(s.registerHistory["d1:total_power"][0].value).toBe(42);
  });

  it("does not track history for non-running devices", () => {
    useMonitorStore.getState().handleMonitorUpdate(
      update({ devices: [device({ status: "stopped" })] }),
    );
    expect(useMonitorStore.getState().registerHistory).toEqual({});
  });

  it("caps register history at 300 points", () => {
    const store = useMonitorStore.getState();
    for (let i = 0; i < 305; i++) store.handleMonitorUpdate(update());
    expect(useMonitorStore.getState().registerHistory["d1:total_power"]).toHaveLength(300);
  });

  it("raises a toast for a new toast-worthy event", () => {
    const evt: MonitorEvent = {
      timestamp: "2026", device_id: "d1", device_name: "D1",
      event_type: "anomaly_inject", detail: "spike",
    };
    useMonitorStore.getState().handleMonitorUpdate(update({ events: [evt] }));
    expect(useMonitorStore.getState().recentToastEvent?.event_type).toBe("anomaly_inject");
  });

  it("ignores non-toast event types", () => {
    const evt: MonitorEvent = {
      timestamp: "2026", device_id: "d1", device_name: "D1",
      event_type: "register_read", detail: "",
    };
    useMonitorStore.getState().handleMonitorUpdate(update({ events: [evt] }));
    expect(useMonitorStore.getState().recentToastEvent).toBeNull();
  });
});

describe("monitorStore drawer + events", () => {
  it("opens and closes the event drawer", () => {
    useMonitorStore.getState().openEventDrawer();
    expect(useMonitorStore.getState().eventDrawerOpen).toBe(true);
    useMonitorStore.getState().closeEventDrawer();
    expect(useMonitorStore.getState().eventDrawerOpen).toBe(false);
  });

  it("clears events", () => {
    useMonitorStore.setState({
      events: [{ timestamp: "t", device_id: "d1", device_name: "D1", event_type: "x", detail: "" }],
    });
    useMonitorStore.getState().clearEvents();
    expect(useMonitorStore.getState().events).toEqual([]);
  });
});
```

- [ ] **Step 2: Write `src/stores/deviceStore.test.ts`**

```ts
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
```

- [ ] **Step 3: Run the tests**

Run: `npm run test:run`
Expected: PASS — all suites green (monitorStore: 7, deviceStore: 6, plus prior tasks).

- [ ] **Step 4: Verify lint**

Run: `npm run lint`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/monitorStore.test.ts frontend/src/stores/deviceStore.test.ts
git commit -m "test: monitorStore reducer + deviceStore async actions (#62)"
```

---

### Task 5: Lock in the ratchet coverage threshold

Measures the baseline, then sets thresholds just below it so future regressions fail CI.

**Files:**
- Modify: `frontend/vite.config.ts` (add `coverage.thresholds`)
- Modify: `frontend/.gitignore` (ignore `coverage/`)
- Modify: `frontend/eslint.config.ts` (ignore `coverage`)

**Interfaces:**
- Consumes: the full test suite from Tasks 1–4.
- Produces: a `test:coverage` command that fails when coverage drops below the locked baseline.

- [ ] **Step 1: Measure the baseline**

Run: `npm run test:coverage`
Read the `% Coverage report` summary line for the four metrics (Statements / Branches / Functions / Lines).

- [ ] **Step 2: Compute ratchet thresholds**

For each of the four metrics, take the measured percentage and **round down to the nearest 5** to get the threshold (e.g. measured Lines 62.4 → 60; Branches 71.0 → 70; Functions 58.9 → 55; Statements 62.4 → 60). This leaves a small margin so trivial fluctuations don't flake CI, while still failing on any real drop.

- [ ] **Step 3: Add the thresholds to `vite.config.ts`**

Inside `test.coverage`, add a `thresholds` block using the numbers from Step 2. Example shape (substitute your rounded numbers):

```ts
    coverage: {
      provider: "v8",
      include: [
        "src/utils/**",
        "src/stores/**",
        "src/services/**",
        "src/hooks/**",
      ],
      reporter: ["text", "text-summary"],
      thresholds: {
        statements: 60,
        branches: 70,
        functions: 55,
        lines: 60,
      },
    },
```

- [ ] **Step 4: Ignore the coverage output**

Append `coverage` to `frontend/.gitignore` (add the line if not present):

```
coverage
```

In `frontend/eslint.config.ts`, extend the existing ignore so lint never scans coverage reports:

```ts
  globalIgnores(['dist', 'coverage']),
```

- [ ] **Step 5: Verify the gate passes at the locked threshold**

Run: `npm run test:coverage`
Expected: PASS — "coverage threshold" not reported as failing; exit code 0.

- [ ] **Step 6: Verify the gate actually bites (sanity check, then revert)**

Temporarily raise one threshold above the measured value (e.g. `lines: 99`), run `npm run test:coverage`, and confirm it **fails** with a threshold error. Then revert the number back to the Step 2 value.

Expected: the inflated run fails; the reverted run passes.

- [ ] **Step 7: Commit**

```bash
git add frontend/vite.config.ts frontend/.gitignore frontend/eslint.config.ts
git commit -m "test: lock ratchet coverage thresholds for frontend logic modules (#62)"
```

---

### Task 6: CI gates + documentation

Wires `lint` and `test:coverage` into the CI `frontend` job and updates the required docs.

**Files:**
- Modify: `.github/workflows/ci.yml` (frontend job steps)
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`

**Interfaces:**
- Consumes: `npm run lint`, `npm run test:coverage` from prior tasks.
- Produces: a green CI run with four frontend steps.

- [ ] **Step 1: Add lint + test steps to the `frontend` job**

In `.github/workflows/ci.yml`, in the `frontend` job, insert a `Lint` step before `Type check` and a `Test` step after it. The steps block becomes:

```yaml
      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npx tsc -b

      - name: Test with coverage
        run: npm run test:coverage

      - name: Build
        run: npm run build
```

- [ ] **Step 2: Update `CHANGELOG.md`**

Under `## [Unreleased]` (create it above the latest version section if absent), add:

```markdown
### Added
- Frontend unit-test harness (vitest + jsdom + Testing Library) covering utils, services, stores, and the `useWebSocket` hook.
- CI `frontend` job now runs eslint and vitest with a ratchet coverage threshold (issue #62).
```

- [ ] **Step 3: Update `docs/development-log.md`**

Append a dated entry describing: the zero-frontend-tests gap, the vitest+jsdom choice, the pure-logic scope, the ratchet threshold decision (scoped `include` to logic dirs), and the two new CI gates. Note components/pages and Playwright-in-CI are deferred (#62).

- [ ] **Step 4: Update `docs/development-phases.md`**

In the Milestone 8.7 (Consolidation) checklist, add a completed item:

```markdown
- [x] Frontend testing harness + CI gate (#62): vitest + jsdom + Testing Library unit tests over utils/services/stores/useWebSocket; CI gains eslint + ratchet-threshold coverage steps. Component/page tests + Playwright-in-CI deferred.
```

- [ ] **Step 5: Verify the whole gate locally one last time**

Run: `npm run lint && npx tsc -b && npm run test:coverage && npm run build`
Expected: all four succeed with exit code 0.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml CHANGELOG.md docs/development-log.md docs/development-phases.md
git commit -m "ci: add frontend eslint + coverage gates; docs (#62)"
```

- [ ] **Step 7: Push and open the PR to `dev`**

```bash
git push -u origin feature/claude-frontend-testing-ci-gate-20260704
gh pr create --base dev --title "test: frontend vitest harness + CI eslint/coverage gates (#62)" \
  --body "Stands up a vitest unit-test harness (utils/services/stores/useWebSocket) and adds eslint + ratchet-coverage gates to the CI frontend job. Component/page tests and Playwright-in-CI deferred (#62)."
```

Expected: CI runs and the `frontend` job passes all four steps. Wait for human review before merge.

---

## Notes for the implementer

- **Version pins in Step 1 of Task 1** are floors; if `npm install` resolves newer compatible majors, that is fine as long as `npm run test:run` works. vitest 3 pairs with the repo's Vite 8.
- If `npx tsc -b` complains about missing Testing Library or vitest types, confirm the devDeps installed and that `src/test/setup.ts` exists — `tsconfig.app.json` includes `src`, so test files are typechecked (this is intended; they are not bundled by `vite build`).
- Keep every test file free of `any` — the lint gate (Task 6) will reject it, and Task 2's `api.test.ts` deliberately uses an `unknown` cast to reach axios internals without `any`.
