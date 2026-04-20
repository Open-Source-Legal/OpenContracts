import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { routingLogger } from "../routingLogger";

describe("routingLogger", () => {
  let debugSpy: ReturnType<typeof vi.spyOn>;
  let logSpy: ReturnType<typeof vi.spyOn>;
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    window.DEBUG_ROUTING = false;
  });

  afterEach(() => {
    debugSpy.mockRestore();
    logSpy.mockRestore();
    warnSpy.mockRestore();
    errorSpy.mockRestore();
    window.DEBUG_ROUTING = false;
  });

  it("swallows debug logs when DEBUG_ROUTING is disabled", () => {
    routingLogger.debug("invisible", { k: "v" });
    expect(debugSpy).not.toHaveBeenCalled();
  });

  it("emits debug logs when DEBUG_ROUTING is enabled", () => {
    routingLogger.enableDebug();
    routingLogger.debug("visible", "arg");
    expect(debugSpy).toHaveBeenCalledWith("visible", "arg");
  });

  it("always emits info/warn/error", () => {
    routingLogger.info("i");
    routingLogger.warn("w");
    routingLogger.error("e");
    expect(logSpy).toHaveBeenCalledWith("i");
    expect(warnSpy).toHaveBeenCalledWith("w");
    expect(errorSpy).toHaveBeenCalledWith("e");
  });

  it("reports status via getStatus", () => {
    routingLogger.disableDebug();
    expect(routingLogger.getStatus()).toEqual({ debugEnabled: false });
    routingLogger.enableDebug();
    expect(routingLogger.getStatus()).toEqual({ debugEnabled: true });
  });

  it("exposes itself on window", () => {
    expect((window as any).routingLogger).toBe(routingLogger);
  });
});
