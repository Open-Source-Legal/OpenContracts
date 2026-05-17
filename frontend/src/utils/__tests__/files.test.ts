import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  isTextFileType,
  isPdfFileType,
  isDocxFileType,
  isSpanBasedFileType,
  getDocumentTypeBadge,
  downloadFile,
  formatFileSize,
} from "../files";
import { DOCX_MIME_TYPE } from "../../assets/configurations/constants";

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

// ---------------------------------------------------------------------------
// Helpers extracted out of Documents.tsx in PR #1677
// ---------------------------------------------------------------------------

describe("getDocumentTypeBadge", () => {
  it("returns 'PDF' for the canonical pdf fileType (any case)", () => {
    expect(getDocumentTypeBadge("pdf", "doc.pdf")).toBe("PDF");
    expect(getDocumentTypeBadge("PDF", "doc.PDF")).toBe("PDF");
  });

  it("returns 'DOCX' for both docx and legacy doc fileTypes", () => {
    expect(getDocumentTypeBadge("docx", "doc.docx")).toBe("DOCX");
    expect(getDocumentTypeBadge("doc", "doc.doc")).toBe("DOCX");
  });

  it("returns 'TXT' for the txt fileType", () => {
    expect(getDocumentTypeBadge("txt", "notes.txt")).toBe("TXT");
  });

  it("uppercases any other fileType the system might surface", () => {
    expect(getDocumentTypeBadge("html", "page.html")).toBe("HTML");
    expect(getDocumentTypeBadge("md", "doc.md")).toBe("MD");
  });

  it("falls back to the title extension when fileType is missing", () => {
    expect(getDocumentTypeBadge(null, "untitled.pdf")).toBe("PDF");
    expect(getDocumentTypeBadge(undefined, "memo.docx")).toBe("DOCX");
    expect(getDocumentTypeBadge(null, "memo.doc")).toBe("DOCX");
    expect(getDocumentTypeBadge(null, "memo.txt")).toBe("TXT");
    // An unusual extension still upper-cases rather than crashing.
    expect(getDocumentTypeBadge(null, "x.rtf")).toBe("RTF");
  });

  it("falls back to 'PDF' when neither fileType nor an extension can be derived", () => {
    expect(getDocumentTypeBadge(null, null)).toBe("PDF");
    expect(getDocumentTypeBadge(null, "")).toBe("PDF");
    expect(getDocumentTypeBadge(null, "no-extension")).toBe("PDF");
  });

  // Live backend payload — Django's Document.file_type stores full MIME
  // types, not bare extensions. The badge has to recognise those too or
  // the UI lights up with "APPLICATION/PDF" / DOCX_MIME_TYPE-uppercased.
  it("returns 'PDF' for the application/pdf MIME type", () => {
    expect(getDocumentTypeBadge("application/pdf", null)).toBe("PDF");
  });

  it("returns 'DOCX' for the DOCX MIME type", () => {
    expect(getDocumentTypeBadge(DOCX_MIME_TYPE, null)).toBe("DOCX");
  });

  it("returns 'TXT' for text/plain and the legacy application/txt", () => {
    expect(getDocumentTypeBadge("text/plain", null)).toBe("TXT");
    expect(getDocumentTypeBadge("application/txt", null)).toBe("TXT");
  });

  it("strips the MIME prefix for unknown application/* and text/* types", () => {
    expect(getDocumentTypeBadge("application/json", null)).toBe("JSON");
    expect(getDocumentTypeBadge("image/png", null)).toBe("PNG");
  });
});

describe("isDocxFileType", () => {
  it("matches the DOCX MIME exactly", () => {
    expect(isDocxFileType(DOCX_MIME_TYPE)).toBe(true);
  });

  it("rejects the bare 'docx' string and nullish input", () => {
    expect(isDocxFileType("docx")).toBe(false);
    expect(isDocxFileType(null)).toBe(false);
    expect(isDocxFileType(undefined)).toBe(false);
  });
});

describe("isSpanBasedFileType", () => {
  it("is true for text MIMEs (text/* and the legacy application/txt)", () => {
    expect(isSpanBasedFileType("text/plain")).toBe(true);
    expect(isSpanBasedFileType("text/html")).toBe(true);
    expect(isSpanBasedFileType("application/txt")).toBe(true);
  });

  it("is true for DOCX MIMEs", () => {
    expect(isSpanBasedFileType(DOCX_MIME_TYPE)).toBe(true);
  });

  it("is false for PDF (token-based annotations)", () => {
    expect(isSpanBasedFileType("application/pdf")).toBe(false);
  });

  it("is false for unrelated types and nullish input", () => {
    expect(isSpanBasedFileType("image/png")).toBe(false);
    expect(isSpanBasedFileType(null)).toBe(false);
    expect(isSpanBasedFileType(undefined)).toBe(false);
  });
});

describe("formatFileSize (utils/files.ts)", () => {
  // utils/files.ts has its own ``formatFileSize`` with output formatting
  // distinct from the formatter in ``utils/formatters.ts`` — pin the
  // contract here too.
  it("returns the canonical zero-bytes string when given 0", () => {
    expect(formatFileSize(0)).toBe("0 Bytes");
  });

  it("formats bytes below 1 KB without unit conversion", () => {
    expect(formatFileSize(512)).toBe("512 Bytes");
    expect(formatFileSize(1023)).toBe("1023 Bytes");
  });

  it("formats kilobyte, megabyte, and gigabyte boundaries", () => {
    expect(formatFileSize(1024)).toBe("1 KB");
    expect(formatFileSize(1024 * 1024)).toBe("1 MB");
    expect(formatFileSize(1024 * 1024 * 1024)).toBe("1 GB");
  });

  it("formats fractional sizes with two decimals where present", () => {
    expect(formatFileSize(1536)).toBe("1.5 KB");
    expect(formatFileSize(1024 * 1024 * 2.5)).toBe("2.5 MB");
  });
});
