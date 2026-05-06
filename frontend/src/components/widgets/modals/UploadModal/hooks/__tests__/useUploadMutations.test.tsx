/**
 * Tests for useUploadMutations.
 *
 * Focuses on the orchestration the hook owns: status callbacks fire in the
 * right order, the multipart helpers are called with the right arguments,
 * and refetch+onComplete fire only after every file in a sequential batch.
 *
 * The wire-level transport (FormData, fetch URL, headers) is covered by
 * importHttp.test.ts; here we mock the helpers so the assertions stay
 * tightly scoped to the hook.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react-hooks";
import { ApolloClient, InMemoryCache, ApolloProvider } from "@apollo/client";
import React from "react";

vi.mock("react-toastify", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("../../../../../../utils/importHttp", () => ({
  importDocumentMultipart: vi.fn(),
  importDocumentsZipMultipart: vi.fn(),
}));

import { useUploadMutations } from "../useUploadMutations";
import type { FileUploadPackage } from "../useUploadState";
import {
  importDocumentMultipart,
  importDocumentsZipMultipart,
} from "../../../../../../utils/importHttp";

const mockedUploadDoc = vi.mocked(importDocumentMultipart);
const mockedUploadZip = vi.mocked(importDocumentsZipMultipart);

function makeClient() {
  const client = new ApolloClient({ cache: new InMemoryCache() });
  vi.spyOn(client, "refetchQueries").mockResolvedValue([]);
  return client;
}

function makeWrapper(client: ApolloClient<any>) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <ApolloProvider client={client}>{children}</ApolloProvider>;
  };
}

function makeFile(name = "doc.pdf", type = "application/pdf"): File {
  return new File(["content"], name, { type });
}

function makePkg(file: File, title = "T"): FileUploadPackage {
  return {
    file,
    formData: { title, slug: "", description: "D" },
    status: "pending",
  };
}

describe("useUploadMutations.uploadSingleFile", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("calls the multipart helper and reports success status", async () => {
    const onFileStatusChange = vi.fn();
    const client = makeClient();
    mockedUploadDoc.mockResolvedValue({
      ok: true,
      document_id: 1,
      status: "created",
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: "corpus-1",
          folderId: "folder-1",
          onFileStatusChange,
        }),
      { wrapper: makeWrapper(client) }
    );

    const ok = await result.current.uploadSingleFile(
      makeFile(),
      { title: "Hello", description: "world", slug: "" },
      0
    );

    expect(ok).toBe(true);
    expect(mockedUploadDoc).toHaveBeenCalledTimes(1);
    expect(mockedUploadDoc.mock.calls[0][0]).toMatchObject({
      title: "Hello",
      description: "world",
      addToCorpusId: "corpus-1",
      addToFolderId: "folder-1",
      makePublic: false,
    });
    expect(onFileStatusChange.mock.calls).toEqual([
      [0, "uploading"],
      [0, "success"],
    ]);
  });

  it("reports failure status when the helper returns ok:false", async () => {
    const onFileStatusChange = vi.fn();
    const client = makeClient();
    mockedUploadDoc.mockResolvedValue({
      ok: false,
      error: "Corpus not found",
      status_code: 400,
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange,
        }),
      { wrapper: makeWrapper(client) }
    );

    const ok = await result.current.uploadSingleFile(
      makeFile(),
      { title: "T", description: "", slug: "" },
      3
    );

    expect(ok).toBe(false);
    expect(onFileStatusChange.mock.calls).toEqual([
      [3, "uploading"],
      [3, "failed"],
    ]);
  });

  it("reports failure when the helper throws", async () => {
    const onFileStatusChange = vi.fn();
    const client = makeClient();
    mockedUploadDoc.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange,
        }),
      { wrapper: makeWrapper(client) }
    );

    const ok = await result.current.uploadSingleFile(
      makeFile(),
      { title: "T", description: "", slug: "" },
      0
    );
    expect(ok).toBe(false);
    expect(onFileStatusChange).toHaveBeenLastCalledWith(0, "failed");
  });
});

describe("useUploadMutations.uploadFiles", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("uploads each file sequentially, then refetches and calls onComplete", async () => {
    const order: string[] = [];
    const client = makeClient();
    const onFileStatusChange = vi.fn((index: number, status: string) =>
      order.push(`${index}:${status}`)
    );
    const onComplete = vi.fn(() => order.push("complete"));

    let inFlight = 0;
    let maxParallel = 0;
    mockedUploadDoc.mockImplementation(async () => {
      inFlight += 1;
      maxParallel = Math.max(maxParallel, inFlight);
      await Promise.resolve();
      inFlight -= 1;
      return { ok: true, document_id: 1, status: "created" };
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange,
          onComplete,
        }),
      { wrapper: makeWrapper(client) }
    );

    const files = [
      makePkg(makeFile("a.pdf")),
      makePkg(makeFile("b.pdf")),
      makePkg(makeFile("c.pdf")),
    ];

    await result.current.uploadFiles(files, "selected-corpus");

    expect(mockedUploadDoc).toHaveBeenCalledTimes(3);
    // Sequential: never more than 1 upload in flight at a time
    expect(maxParallel).toBe(1);
    // Selected corpus passed through to every call
    for (const call of mockedUploadDoc.mock.calls) {
      expect(call[0].addToCorpusId).toBe("selected-corpus");
    }
    // Status sequence: each file goes uploading -> success in order
    expect(order).toEqual([
      "0:uploading",
      "0:success",
      "1:uploading",
      "1:success",
      "2:uploading",
      "2:success",
      "complete",
    ]);
    // Refetch fires once at the end
    expect(client.refetchQueries).toHaveBeenCalledTimes(1);
  });

  it("continues uploading remaining files after one fails", async () => {
    const onFileStatusChange = vi.fn();
    const client = makeClient();
    const onComplete = vi.fn();
    let call = 0;
    mockedUploadDoc.mockImplementation(async () => {
      call += 1;
      if (call === 2) {
        return { ok: false, error: "boom", status_code: 400 };
      }
      return { ok: true, document_id: call, status: "created" };
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange,
          onComplete,
        }),
      { wrapper: makeWrapper(client) }
    );

    await result.current.uploadFiles([
      makePkg(makeFile("a.pdf")),
      makePkg(makeFile("b.pdf")),
      makePkg(makeFile("c.pdf")),
    ]);

    // file 1: success, file 2: failed, file 3: success
    expect(onFileStatusChange).toHaveBeenCalledWith(0, "success");
    expect(onFileStatusChange).toHaveBeenCalledWith(1, "failed");
    expect(onFileStatusChange).toHaveBeenCalledWith(2, "success");
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("continues after a thrown error inside the upload loop", async () => {
    // Distinct from the ok:false branch above — exercises the catch
    // block (network failure mid-batch must not abort remaining files).
    const onFileStatusChange = vi.fn();
    const client = makeClient();
    let call = 0;
    mockedUploadDoc.mockImplementation(async () => {
      call += 1;
      if (call === 2) {
        throw new Error("network down");
      }
      return { ok: true, document_id: call, status: "created" };
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange,
        }),
      { wrapper: makeWrapper(client) }
    );

    await result.current.uploadFiles([
      makePkg(makeFile("a.pdf")),
      makePkg(makeFile("b.pdf")),
      makePkg(makeFile("c.pdf")),
    ]);

    expect(onFileStatusChange).toHaveBeenCalledWith(0, "success");
    expect(onFileStatusChange).toHaveBeenCalledWith(1, "failed");
    expect(onFileStatusChange).toHaveBeenCalledWith(2, "success");
  });

  it("falls back to a generic toast message when the thrown error is not an Error", async () => {
    const onFileStatusChange = vi.fn();
    const client = makeClient();
    mockedUploadDoc.mockImplementation(async () => {
      // Non-Error thrown — exercises the ``error instanceof Error`` ternary's
      // false branch in the catch handler.
      throw "string-not-error"; // eslint-disable-line no-throw-literal
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange,
        }),
      { wrapper: makeWrapper(client) }
    );

    await result.current.uploadFiles([makePkg(makeFile("a.pdf"))]);

    expect(onFileStatusChange).toHaveBeenCalledWith(0, "failed");
  });
});

describe("useUploadMutations.uploadZipFile", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  it("calls the zip helper with the target corpus and returns true on success", async () => {
    const client = makeClient();
    mockedUploadZip.mockResolvedValue({
      ok: true,
      job_id: "j-1",
      message: "ok",
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange: vi.fn(),
        }),
      { wrapper: makeWrapper(client) }
    );

    const file = new File([new Uint8Array([1])], "z.zip", {
      type: "application/zip",
    });
    const ok = await result.current.uploadZipFile(file, "corpus-99");
    expect(ok).toBe(true);
    expect(mockedUploadZip).toHaveBeenCalledWith({
      file,
      addToCorpusId: "corpus-99",
      makePublic: false,
    });
  });

  it("returns false when the helper returns ok:false", async () => {
    const client = makeClient();
    mockedUploadZip.mockResolvedValue({
      ok: false,
      error: "no perms",
      status_code: 400,
    });

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange: vi.fn(),
        }),
      { wrapper: makeWrapper(client) }
    );

    const file = new File([new Uint8Array([1])], "z.zip", {
      type: "application/zip",
    });
    const ok = await result.current.uploadZipFile(file);
    expect(ok).toBe(false);
  });

  it("returns false when the helper throws", async () => {
    const client = makeClient();
    mockedUploadZip.mockRejectedValue(new Error("offline"));

    const { result } = renderHook(
      () =>
        useUploadMutations({
          corpusId: null,
          folderId: null,
          onFileStatusChange: vi.fn(),
        }),
      { wrapper: makeWrapper(client) }
    );

    const file = new File([new Uint8Array([1])], "z.zip", {
      type: "application/zip",
    });
    const ok = await result.current.uploadZipFile(file);
    expect(ok).toBe(false);
  });
});
