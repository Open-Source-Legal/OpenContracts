import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authToken } from "../../graphql/cache";
import { UPLOAD } from "../../assets/configurations/constants";
import {
  importCorpusExportMultipart,
  importDocumentMultipart,
  importDocumentsZipMultipart,
  importZipToCorpusMultipart,
} from "../importHttp";

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

// Centralise the unsafe ``globalThis`` accessor on one bag so each test's
// before/afterEach can read/write the global ``fetch`` slot without
// reintroducing ``as any`` casts. ``unknown`` keeps consumers honest at
// the call sites (we only read with the right shape) without growing the
// project-wide ``any`` count.
const fetchSlot = globalThis as unknown as Record<string, unknown>;

function setMockFetch(impl: ReturnType<typeof vi.fn>): void {
  fetchSlot[FETCH_KEY] = impl;
}

function clearMockFetch(): void {
  delete fetchSlot[FETCH_KEY];
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

describe("importHttp.importDocumentMultipart", () => {
  beforeEach(() => {
    authToken("test-token-123");
  });

  afterEach(() => {
    authToken("");
    clearMockFetch();
  });

  it("posts FormData to /api/imports/documents/ with bearer auth", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse({ ok: true, document_id: 7, status: "created" })
      );
    setMockFetch(fetchMock);

    const file = new File(["hello"], "hello.pdf", {
      type: "application/pdf",
    });
    const result = await importDocumentMultipart({
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
    expect(String(url)).toContain("/api/imports/documents/");
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
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeJsonResponse({ ok: true, document_id: 1 }));
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    await importDocumentMultipart({ file, title: "T" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).toEqual({});
  });

  it("does not append blank-string optional fields", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeJsonResponse({ ok: true, document_id: 1 }));
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    await importDocumentMultipart({
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
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse(
          { ok: false, error: "Corpus not found" },
          { status: 400 }
        )
      );
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    const result = await importDocumentMultipart({ file, title: "T" });

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
    const result = await importDocumentMultipart({ file, title: "T" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status_code).toBe(500);
      expect(result.error).toMatch(/HTTP 500/);
    }
  });

  it("surfaces DRF field validation errors from the response body", async () => {
    // Django REST framework wraps field-validation failures as
    // ``{ field_name: ["...message..."] }``; parseErrorMessage walks the
    // first array-of-string entry it finds.
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse(
          { title: ["This field is required."] },
          { status: 400 }
        )
      );
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    const result = await importDocumentMultipart({ file, title: "" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBe("This field is required.");
    }
  });

  it("appends custom_meta as JSON when non-empty", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeJsonResponse({ ok: true, document_id: 1 }));
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    await importDocumentMultipart({
      file,
      title: "T",
      customMeta: { source: "manual" },
    });

    const fd = fetchMock.mock.calls[0][1].body as FormData;
    expect(fd.get("custom_meta")).toBe(JSON.stringify({ source: "manual" }));
  });

  it("returns ok:false when a 2xx body advertises ok:false", async () => {
    // 200 response, but the server's JSON payload says the import failed.
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse({ ok: false, error: "logical fail", document_id: 0 })
      );
    setMockFetch(fetchMock);

    const file = new File(["x"], "x.pdf", { type: "application/pdf" });
    const result = await importDocumentMultipart({ file, title: "T" });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBe("logical fail");
    }
  });
});

describe("importHttp.importDocumentsZipMultipart", () => {
  beforeEach(() => {
    authToken("zip-token");
  });
  afterEach(() => {
    authToken("");
    clearMockFetch();
  });

  it("posts FormData to /api/imports/documents-zip/ and surfaces job_id", async () => {
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
    const result = await importDocumentsZipMultipart({
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
    expect(String(url)).toContain("/api/imports/documents-zip/");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("returns ok:false when the server reports a logical failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse(
          { ok: false, error: "Corpus not found" },
          { status: 400 }
        )
      );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "bundle.zip", {
      type: "application/zip",
    });
    const result = await importDocumentsZipMultipart({
      file,
      makePublic: false,
    });

    expect(result).toEqual({
      ok: false,
      error: "Corpus not found",
      status_code: 400,
    });
  });

  it("treats a 200 response missing a job_id as a failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeJsonResponse({ ok: true }));
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "bundle.zip", {
      type: "application/zip",
    });
    const result = await importDocumentsZipMultipart({
      file,
      makePublic: false,
    });
    expect(result.ok).toBe(false);
  });

  it("appends custom_meta on the zip path when non-empty", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeJsonResponse({ ok: true, job_id: "j1" }));
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "bundle.zip", {
      type: "application/zip",
    });
    await importDocumentsZipMultipart({
      file,
      makePublic: false,
      customMeta: { source: "bulk-tool" },
    });

    const fd = fetchMock.mock.calls[0][1].body as FormData;
    expect(fd.get("custom_meta")).toBe(JSON.stringify({ source: "bulk-tool" }));
  });
});

describe("importHttp.importZipToCorpusMultipart", () => {
  beforeEach(() => {
    authToken("ztc-token");
  });
  afterEach(() => {
    authToken("");
    clearMockFetch();
  });

  it("posts FormData to /api/imports/zip-to-corpus/ with the corpus id and bearer auth", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse(
        {
          ok: true,
          job_id: "job-ztc-1",
          message: "Import started. Job ID: job-ztc-1",
        },
        { status: 202 }
      )
    );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1, 2, 3])], "structured.zip", {
      type: "application/zip",
    });
    const result = await importZipToCorpusMultipart({
      file,
      corpusId: "42",
      targetFolderId: "7",
      titlePrefix: "Inv-",
      description: "Q4 invoices",
      makePublic: true,
    });

    expect(result).toEqual({
      ok: true,
      job_id: "job-ztc-1",
      message: "Import started. Job ID: job-ztc-1",
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/imports/zip-to-corpus/");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({
      Authorization: "Bearer ztc-token",
    });
    expect(init.body).toBeInstanceOf(FormData);
    const fd = init.body as FormData;
    expect(fd.get("file")).toBeInstanceOf(File);
    expect(fd.get("corpus_id")).toBe("42");
    expect(fd.get("target_folder_id")).toBe("7");
    expect(fd.get("title_prefix")).toBe("Inv-");
    expect(fd.get("description")).toBe("Q4 invoices");
    expect(fd.get("make_public")).toBe("true");
  });

  it("omits blank-string optional fields", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeJsonResponse({ ok: true, job_id: "j2" }));
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "x.zip", {
      type: "application/zip",
    });
    await importZipToCorpusMultipart({
      file,
      corpusId: "1",
      targetFolderId: null,
      titlePrefix: "",
      description: "",
      makePublic: false,
    });

    const fd = fetchMock.mock.calls[0][1].body as FormData;
    expect(fd.has("target_folder_id")).toBe(false);
    expect(fd.has("title_prefix")).toBe(false);
    expect(fd.has("description")).toBe(false);
  });

  it("returns a structured error on HTTP failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse(
          { ok: false, error: "Corpus not found" },
          { status: 400 }
        )
      );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "x.zip", {
      type: "application/zip",
    });
    const result = await importZipToCorpusMultipart({
      file,
      corpusId: "999",
      makePublic: false,
    });
    expect(result).toEqual({
      ok: false,
      error: "Corpus not found",
      status_code: 400,
    });
  });

  it("treats a 200 response missing a job_id as a failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(makeJsonResponse({ ok: true }));
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "x.zip", {
      type: "application/zip",
    });
    const result = await importZipToCorpusMultipart({
      file,
      corpusId: "1",
      makePublic: false,
    });
    expect(result.ok).toBe(false);
  });
});

describe("importHttp.importCorpusExportMultipart", () => {
  beforeEach(() => {
    authToken("cex-token");
  });
  afterEach(() => {
    authToken("");
    clearMockFetch();
  });

  it("posts FormData to /api/imports/corpus/ and surfaces corpus_id", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        makeJsonResponse(
          { ok: true, corpus_id: 17, message: "Import started." },
          { status: 202 }
        )
      );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1, 2])], "corpus-export.zip", {
      type: "application/zip",
    });
    const result = await importCorpusExportMultipart({ file });

    expect(result).toEqual({
      ok: true,
      corpus_id: 17,
      message: "Import started.",
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/imports/corpus/");
    expect(init.body).toBeInstanceOf(FormData);
    const fd = init.body as FormData;
    expect(fd.get("file")).toBeInstanceOf(File);
  });

  it("returns a structured error on HTTP failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      makeJsonResponse(
        {
          ok: false,
          error: "You are not authorized to perform this import.",
        },
        { status: 403 }
      )
    );
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "x.zip", {
      type: "application/zip",
    });
    const result = await importCorpusExportMultipart({ file });
    expect(result).toEqual({
      ok: false,
      error: "You are not authorized to perform this import.",
      status_code: 403,
    });
  });

  it("treats a 200 response missing a corpus_id as a failure", async () => {
    // Empty body must not be interpreted as success — the helper requires
    // ``corpus_id`` to be defined.
    const fetchMock = vi.fn().mockResolvedValue(makeJsonResponse({ ok: true }));
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1])], "x.zip", {
      type: "application/zip",
    });
    const result = await importCorpusExportMultipart({ file });
    expect(result.ok).toBe(false);
  });
});

/**
 * Cloudflare caps a single proxied request body at 100MB. Files above
 * ``CHUNK_THRESHOLD_BYTES`` must therefore be uploaded over the
 * ``/api/imports/chunked/*`` protocol (start -> parts -> complete) rather than
 * a single request, while small files keep the single-shot path. The chunked
 * ``complete`` body shape is identical to the single-request body, so callers
 * get the same typed result either way.
 */
describe("importHttp chunked transport", () => {
  beforeEach(() => {
    authToken("test-token-123");
  });

  afterEach(() => {
    authToken("");
    clearMockFetch();
  });

  /** A File that reports ``sizeBytes`` regardless of its real (tiny) content. */
  function makeLargeFile(
    name: string,
    sizeBytes: number,
    type = "application/pdf"
  ): File {
    const file = new File([new Uint8Array(8)], name, { type });
    Object.defineProperty(file, "size", { value: sizeBytes });
    return file;
  }

  /** Route the three chunked verbs to canned responses by URL. */
  function makeRoutedFetch(routes: {
    start: () => Response;
    part: () => Response;
    complete: () => Response;
  }): ReturnType<typeof vi.fn> {
    return vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.includes("/chunked/start/")) return routes.start();
      if (u.includes("/parts/")) return routes.part();
      if (u.includes("/complete/")) return routes.complete();
      throw new Error(`unexpected url ${u}`);
    });
  }

  it("splits a large document into start, parts, and complete requests", async () => {
    const sizeBytes =
      UPLOAD.CHUNK_THRESHOLD_BYTES + UPLOAD.CHUNK_SIZE_BYTES * 2;
    const expectedParts = Math.ceil(sizeBytes / UPLOAD.CHUNK_SIZE_BYTES);

    const fetchMock = makeRoutedFetch({
      start: () =>
        makeJsonResponse({ ok: true, upload_id: "u-1" }, { status: 201 }),
      part: () => makeJsonResponse({ ok: true }, { status: 200 }),
      complete: () =>
        makeJsonResponse(
          { ok: true, document_id: 99, status: "created" },
          { status: 201 }
        ),
    });
    setMockFetch(fetchMock);

    const file = makeLargeFile("big.pdf", sizeBytes);
    const result = await importDocumentMultipart({
      file,
      title: "Big",
      addToCorpusId: "7",
    });

    expect(result).toEqual({ ok: true, document_id: 99, status: "created" });

    // 1 start + N parts + 1 complete.
    expect(fetchMock).toHaveBeenCalledTimes(2 + expectedParts);

    const calls = fetchMock.mock.calls;
    const [startUrl, startInit] = calls[0];
    expect(String(startUrl)).toContain("/api/imports/chunked/start/");
    expect(startInit.method).toBe("POST");
    expect(startInit.headers).toMatchObject({
      Authorization: "Bearer test-token-123",
    });
    const startPayload = JSON.parse(startInit.body as string);
    expect(startPayload.kind).toBe("document");
    expect(startPayload.total_size).toBe(sizeBytes);
    expect(startPayload.total_chunks).toBe(expectedParts);
    expect(startPayload.metadata.title).toBe("Big");
    expect(startPayload.metadata.add_to_corpus_id).toBe("7");

    // Every part is a PUT of FormData carrying a Blob.
    const partCall = calls[1];
    expect(String(partCall[0])).toContain("/api/imports/chunked/u-1/parts/0/");
    expect(partCall[1].method).toBe("PUT");
    expect(partCall[1].body).toBeInstanceOf(FormData);

    const completeCall = calls[calls.length - 1];
    expect(String(completeCall[0])).toContain(
      "/api/imports/chunked/u-1/complete/"
    );
    expect(completeCall[1].method).toBe("POST");
  });

  it("keeps small files on the single-request endpoint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(makeJsonResponse({ ok: true, document_id: 3 }));
    setMockFetch(fetchMock);

    const file = new File([new Uint8Array([1, 2, 3])], "small.pdf", {
      type: "application/pdf",
    });
    const result = await importDocumentMultipart({ file, title: "Small" });

    expect(result).toEqual({ ok: true, document_id: 3, status: undefined });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/api/imports/documents/"
    );
  });

  it("aborts and surfaces the error when start is rejected", async () => {
    const fetchMock = makeRoutedFetch({
      start: () =>
        makeJsonResponse(
          { ok: false, error: "File too large.", max_bytes: 10 },
          { status: 413 }
        ),
      part: () => makeJsonResponse({ ok: true }),
      complete: () => makeJsonResponse({ ok: true }),
    });
    setMockFetch(fetchMock);

    const file = makeLargeFile("huge.pdf", UPLOAD.CHUNK_THRESHOLD_BYTES + 1);
    const result = await importDocumentMultipart({ file, title: "T" });

    expect(result).toEqual({
      ok: false,
      status_code: 413,
      error: "File too large.",
    });
    // No parts attempted once start fails.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("chunks a large ZIP via the documents_zip kind", async () => {
    const fetchMock = makeRoutedFetch({
      start: () =>
        makeJsonResponse({ ok: true, upload_id: "z-1" }, { status: 201 }),
      part: () => makeJsonResponse({ ok: true }),
      complete: () =>
        makeJsonResponse(
          { ok: true, job_id: "job-42", message: "Import started." },
          { status: 202 }
        ),
    });
    setMockFetch(fetchMock);

    const file = makeLargeFile(
      "bundle.zip",
      UPLOAD.CHUNK_THRESHOLD_BYTES + 1,
      "application/zip"
    );
    const result = await importDocumentsZipMultipart({
      file,
      addToCorpusId: "5",
    });

    expect(result).toEqual({
      ok: true,
      job_id: "job-42",
      message: "Import started.",
    });
    const startPayload = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(startPayload.kind).toBe("documents_zip");
    expect(startPayload.metadata.add_to_corpus_id).toBe("5");
  });

  it("retries a transiently-failing part and then completes", async () => {
    // Part index 0 fails once with a 503 (retryable) then succeeds; the whole
    // upload must still complete rather than abort on the blip.
    let part0Attempts = 0;
    const fetchMock = vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.includes("/chunked/start/"))
        return makeJsonResponse(
          { ok: true, upload_id: "u-1" },
          { status: 201 }
        );
      if (u.includes("/complete/"))
        return makeJsonResponse(
          { ok: true, document_id: 7, status: "created" },
          { status: 201 }
        );
      if (u.includes("/parts/0/")) {
        part0Attempts += 1;
        if (part0Attempts === 1) {
          return makeJsonResponse({ error: "try again" }, { status: 503 });
        }
      }
      return makeJsonResponse({ ok: true }, { status: 200 });
    });
    setMockFetch(fetchMock);

    const sizeBytes = UPLOAD.CHUNK_SIZE_BYTES * 2;
    const file = makeLargeFile("retry.pdf", sizeBytes);

    vi.useFakeTimers();
    const promise = importDocumentMultipart({ file, title: "T" });
    await vi.runAllTimersAsync();
    const result = await promise;
    vi.useRealTimers();

    expect(result).toEqual({ ok: true, document_id: 7, status: "created" });
    // Part 0 was attempted twice (initial 503 + successful retry).
    expect(part0Attempts).toBe(2);
  });

  it("aborts after exhausting retries on a persistently-failing part", async () => {
    const fetchMock = makeRoutedFetch({
      start: () =>
        makeJsonResponse({ ok: true, upload_id: "u-1" }, { status: 201 }),
      part: () => makeJsonResponse({ error: "boom" }, { status: 500 }),
      complete: () => makeJsonResponse({ ok: true }, { status: 201 }),
    });
    setMockFetch(fetchMock);

    const file = makeLargeFile("fail.pdf", UPLOAD.CHUNK_SIZE_BYTES * 2);

    vi.useFakeTimers();
    const promise = importDocumentMultipart({ file, title: "T" });
    await vi.runAllTimersAsync();
    const result = await promise;
    vi.useRealTimers();

    expect(result).toEqual({
      ok: false,
      status_code: 500,
      error: "boom",
    });
    // ``complete`` is never reached once a part fails.
    const completeCalls = fetchMock.mock.calls.filter((c) =>
      String(c[0]).includes("/complete/")
    );
    expect(completeCalls).toHaveLength(0);
  });

  it("does not retry a 4xx client error on a part", async () => {
    let partCalls = 0;
    const fetchMock = vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.includes("/chunked/start/"))
        return makeJsonResponse(
          { ok: true, upload_id: "u-1" },
          { status: 201 }
        );
      if (u.includes("/complete/")) return makeJsonResponse({ ok: true });
      partCalls += 1;
      return makeJsonResponse({ error: "bad part" }, { status: 400 });
    });
    setMockFetch(fetchMock);

    const file = makeLargeFile("bad.pdf", UPLOAD.CHUNK_SIZE_BYTES * 2);
    const result = await importDocumentMultipart({ file, title: "T" });

    expect(result).toEqual({
      ok: false,
      status_code: 400,
      error: "bad part",
    });
    // A 4xx is non-retryable: each worker's part fails on its first attempt.
    // With 2 parts and 2 workers, both may fire once before the abort flips —
    // but no part is attempted more than once.
    expect(partCalls).toBeLessThanOrEqual(2);
  });

  it("reports upload progress ending at 1", async () => {
    const fetchMock = makeRoutedFetch({
      start: () =>
        makeJsonResponse({ ok: true, upload_id: "u-1" }, { status: 201 }),
      part: () => makeJsonResponse({ ok: true }, { status: 200 }),
      complete: () =>
        makeJsonResponse(
          { ok: true, document_id: 1, status: "created" },
          { status: 201 }
        ),
    });
    setMockFetch(fetchMock);

    const sizeBytes = UPLOAD.CHUNK_SIZE_BYTES * 3;
    const expectedParts = Math.ceil(sizeBytes / UPLOAD.CHUNK_SIZE_BYTES);
    const file = makeLargeFile("progress.pdf", sizeBytes);

    const fractions: number[] = [];
    const result = await importDocumentMultipart({
      file,
      title: "T",
      onProgress: (f) => fractions.push(f),
    });

    expect(result.ok).toBe(true);
    expect(fractions).toHaveLength(expectedParts);
    expect(fractions[fractions.length - 1]).toBeCloseTo(1);
    // Monotonic non-decreasing.
    for (let i = 1; i < fractions.length; i++) {
      expect(fractions[i]).toBeGreaterThanOrEqual(fractions[i - 1]);
    }
  });

  it("uploads parts with bounded concurrency", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const fetchMock = vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.includes("/chunked/start/"))
        return makeJsonResponse(
          { ok: true, upload_id: "u-1" },
          { status: 201 }
        );
      if (u.includes("/complete/"))
        return makeJsonResponse(
          { ok: true, document_id: 1, status: "created" },
          { status: 201 }
        );
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await Promise.resolve();
      inFlight -= 1;
      return makeJsonResponse({ ok: true }, { status: 200 });
    });
    setMockFetch(fetchMock);

    // 6 parts with a concurrency cap of 4 → peak in-flight should be 4.
    const sizeBytes = UPLOAD.CHUNK_SIZE_BYTES * 6;
    const file = makeLargeFile("concurrent.pdf", sizeBytes);
    const result = await importDocumentMultipart({ file, title: "T" });

    expect(result.ok).toBe(true);
    expect(maxInFlight).toBe(UPLOAD.CHUNK_CONCURRENCY);
  });
});
