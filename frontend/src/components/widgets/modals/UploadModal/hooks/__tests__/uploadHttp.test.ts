import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authToken } from "../../../../../../graphql/cache";
import {
  uploadDocumentMultipart,
  uploadZipMultipart,
} from "../uploadHttp";

/**
 * The frontend bulk-upload bug was specifically a result of the GraphQL
 * path stuffing the entire base64-encoded file into a JSON request body —
 * Apollo couldn't allocate the resulting string and the request never
 * fired. The replacement transport must:
 *
 *   1. Issue a real `fetch` (not a GraphQL mutation), so large files
 *      stream through the browser without a giant string allocation.
 *   2. Encode the file as multipart/form-data (so the browser hands the
 *      binary stream directly to the network layer).
 *   3. Attach the JWT bearer token from the Apollo reactive var.
 *   4. Translate non-2xx responses into a structured error object so
 *      callers can surface a useful toast message without throwing.
 */

const FETCH_KEY = "fetch";

function setMockFetch(impl: ReturnType<typeof vi.fn>): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any)[FETCH_KEY] = impl;
}

function makeJsonResponse(
  body: unknown,
  init: { status?: number; ok?: boolean } = {}
): Response {
  const status = init.status ?? 200;
  return {
    ok: init.ok ?? (status >= 200 && status < 300),
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("uploadHttp.uploadDocumentMultipart", () => {
  beforeEach(() => {
    authToken("test-token-123");
  });

  afterEach(() => {
    authToken("");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis as any)[FETCH_KEY];
  });

  it("posts FormData to /api/uploads/documents/ with bearer auth", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse({ ok: true, document_id: 7, status: "created" })
    );
    setMockFetch(fetchMock);

    const file = new File(["hello"], "hello.pdf", {
      type: "application/pdf",
    });
    const result = await uploadDocumentMultipart({
      file,
      title: "T",
      description: "D",
      addToCorpusId: "42",
      makePublic: true,
    });

    expect(result).toEqual({
      ok: true,
      document_id: 7,
      status: "created",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/uploads/documents/");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({
      Authorization: "Bearer test-token-123",
    });
    // The body must be FormData (NOT a JSON string) — that's the whole
    // point of the new transport.
    expect(init.body).toBeInstanceOf(FormData);
    const fd = init.body as FormData;
    expect(fd.get("title")).toBe("T");
    expect(fd.get("description")).toBe("D");
    expect(fd.get("add_to_corpus_id")).toBe("42");
    expect(fd.get("make_public")).toBe("true");
    expect(fd.get("file")).toBeInstanceOf(File);
  });

  it("omits Authorization header when no token is set", async () => {
    authToken("");
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse({ ok: true, document_id: 1 })
    );
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    await uploadDocumentMultipart({ file, title: "T" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).toEqual({});
  });

  it("does not append blank-string optional fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse({ ok: true, document_id: 1 })
    );
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    await uploadDocumentMultipart({
      file,
      title: "T",
      description: "",
      slug: "",
      addToCorpusId: null,
    });

    const fd = fetchMock.mock.calls[0][1].body as FormData;
    expect(fd.has("description")).toBe(false);
    expect(fd.has("slug")).toBe(false);
    expect(fd.has("add_to_corpus_id")).toBe(false);
  });

  it("returns a structured error on HTTP failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse(
        { ok: false, error: "Corpus not found" },
        { status: 400 }
      )
    );
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    const result = await uploadDocumentMultipart({ file, title: "T" });

    expect(result).toEqual({
      ok: false,
      error: "Corpus not found",
      status_code: 400,
    });
  });

  it("falls back to a generic message if the error body is not parseable", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response);
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    const result = await uploadDocumentMultipart({ file, title: "T" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status_code).toBe(500);
      expect(result.error).toMatch(/HTTP 500/);
    }
  });
});

describe("uploadHttp.uploadZipMultipart", () => {
  beforeEach(() => {
    authToken("zip-token");
  });
  afterEach(() => {
    authToken("");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis as any)[FETCH_KEY];
  });

  it("posts FormData to /api/uploads/documents-zip/ and surfaces job_id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse(
        {
          ok: true,
          job_id: "abc-123",
          message: "Upload started. Job ID: abc-123",
        },
        { status: 202 }
      )
    );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1, 2, 3])], "bundle.zip", {
      type: "application/zip",
    });
    const result = await uploadZipMultipart({
      file,
      addToCorpusId: "9",
      makePublic: false,
    });

    expect(result).toEqual({
      ok: true,
      job_id: "abc-123",
      message: "Upload started. Job ID: abc-123",
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/uploads/documents-zip/");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("returns ok:false when the server reports a logical failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse(
        { ok: false, error: "Corpus not found" },
        { status: 400 }
      )
    );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "bundle.zip", {
      type: "application/zip",
    });
    const result = await uploadZipMultipart({ file, makePublic: false });

    expect(result).toEqual({
      ok: false,
      error: "Corpus not found",
      status_code: 400,
    });
  });

  it("treats a 200 response missing a job_id as a failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse({ ok: true })
    );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "bundle.zip", {
      type: "application/zip",
    });
    const result = await uploadZipMultipart({ file, makePublic: false });
    expect(result.ok).toBe(false);
  });
});
