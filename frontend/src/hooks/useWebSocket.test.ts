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
