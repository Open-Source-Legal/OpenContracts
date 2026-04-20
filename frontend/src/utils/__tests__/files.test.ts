import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  isTextFileType,
  isPdfFileType,
  downloadFile,
  toBase64,
} from "../files";

// --- Shared Axios mock -----------------------------------------------------
// Mock at module scope so downloadFile uses a test-controlled client. We
// re-assign the mock implementation per-test to cover the success and error
// branches without re-importing.
vi.mock("axios", () => ({
  default: {
    get: vi.fn(),
  },
}));

describe("File type utilities", () => {
  describe("isTextFileType", () => {
    it("should return true for text/plain", () => {
      expect(isTextFileType("text/plain")).toBe(true);
    });

    it("should return true for text/* variants", () => {
      expect(isTextFileType("text/html")).toBe(true);
      expect(isTextFileType("text/csv")).toBe(true);
    });

    it("should return true for application/txt (legacy)", () => {
      expect(isTextFileType("application/txt")).toBe(true);
    });

    it("should return false for PDF", () => {
      expect(isTextFileType("application/pdf")).toBe(false);
    });

    it("should return false for other MIME types", () => {
      expect(isTextFileType("application/json")).toBe(false);
      expect(isTextFileType("image/png")).toBe(false);
    });

    it("should handle null/undefined gracefully", () => {
      expect(isTextFileType(null)).toBe(false);
      expect(isTextFileType(undefined)).toBe(false);
    });

    it("should return false for empty string", () => {
      expect(isTextFileType("")).toBe(false);
    });
  });

  describe("isPdfFileType", () => {
    it("should return true for application/pdf", () => {
      expect(isPdfFileType("application/pdf")).toBe(true);
    });

    it("should return false for text types", () => {
      expect(isPdfFileType("text/plain")).toBe(false);
      expect(isPdfFileType("application/txt")).toBe(false);
    });

    it("should handle null/undefined gracefully", () => {
      expect(isPdfFileType(null)).toBe(false);
      expect(isPdfFileType(undefined)).toBe(false);
    });

    it("should return false for empty string", () => {
      expect(isPdfFileType("")).toBe(false);
    });
  });
});

describe("downloadFile", () => {
  let axiosGet: ReturnType<typeof vi.fn>;
  let consoleLogSpy: ReturnType<typeof vi.spyOn>;
  let createObjectURLSpy: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    const Axios = (await import("axios")).default;
    axiosGet = Axios.get as unknown as ReturnType<typeof vi.fn>;
    axiosGet.mockReset();

    consoleLogSpy = vi
      .spyOn(console, "log")
      .mockImplementation(() => undefined);

    // Stub the Blob-URL API (not available in jsdom) so the success path
    // can run without throwing in setup code.
    createObjectURLSpy = vi.fn().mockReturnValue("blob:mock-url");
    Object.defineProperty(window.URL, "createObjectURL", {
      configurable: true,
      value: createObjectURLSpy,
    });
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
  });

  it("downloads successfully and triggers a link click", async () => {
    axiosGet.mockResolvedValue({
      data: new ArrayBuffer(8),
      headers: { "content-type": "application/pdf" },
    });

    // Spy on anchor click so we can verify the download was triggered
    // without actually navigating.
    const clickSpy = vi.fn();
    const originalCreate = document.createElement.bind(document);
    const createSpy = vi
      .spyOn(document, "createElement")
      .mockImplementation((tagName: string) => {
        const el = originalCreate(tagName);
        if (tagName === "a") {
          (el as HTMLAnchorElement).click = clickSpy;
        }
        return el;
      });

    await expect(
      downloadFile("https://example.com/files/report.pdf")
    ).resolves.toBeUndefined();

    expect(axiosGet).toHaveBeenCalledWith(
      "https://example.com/files/report.pdf",
      { responseType: "blob" }
    );
    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalledTimes(1);

    createSpy.mockRestore();
  });

  it("logs and re-throws when axios rejects (catch block)", async () => {
    const networkError = new Error("Network Error");
    axiosGet.mockRejectedValue(networkError);

    await expect(downloadFile("https://example.com/missing.pdf")).rejects.toBe(
      networkError
    );

    // Verify the catch block logged before re-throwing
    const logged = consoleLogSpy.mock.calls.some(
      (call) =>
        typeof call[0] === "string" &&
        (call[0] as string).includes("Downloading file failed")
    );
    expect(logged).toBe(true);
  });
});

describe("toBase64", () => {
  it("resolves with base64 data URL on successful read", async () => {
    const file = new File(["hello"], "hello.txt", { type: "text/plain" });
    const result = await toBase64(file);
    expect(typeof result).toBe("string");
    expect(result as string).toMatch(/^data:/);
  });

  it("rejects when FileReader emits an error", async () => {
    const originalReader = window.FileReader;

    // Replace FileReader with a stub that synchronously invokes onerror
    // after readAsDataURL is called, exercising the reject path in toBase64.
    class StubReader {
      public onload: ((ev: any) => void) | null = null;
      public onerror: ((ev: any) => void) | null = null;
      public result: any = null;
      readAsDataURL() {
        setTimeout(() => this.onerror?.({ target: { error: "nope" } }), 0);
      }
    }
    (window as any).FileReader = StubReader;

    try {
      const file = new File(["x"], "x.txt", { type: "text/plain" });
      await expect(toBase64(file)).rejects.toBeTruthy();
    } finally {
      (window as any).FileReader = originalReader;
    }
  });
});
