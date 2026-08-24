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
