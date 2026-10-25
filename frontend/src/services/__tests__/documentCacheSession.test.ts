import "fake-indexeddb/auto";
import { IDBFactory as FDBFactory } from "fake-indexeddb";
import axios, { AxiosHeaders } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { documentCacheManager } from "../documentCacheManager";
import {
  docxBytesCache,
  getDocumentCacheGeneration,
  invalidateDocumentCacheSession,
} from "../documentCacheState";
import {
  beginAuthSession,
  clearAuthSession,
  authSessionCleanupPendingVar,
} from "../../utils/authSession";
import {
  getDocumentRawText,
  getPawlsLayer,
  getCachedPDFUrl,
  getDocxBytes,
} from "../../components/annotator/api/cachedRest";
import * as rest from "../../components/annotator/api/rest";

vi.mock("../../components/annotator/api/rest", () => ({
  getDocumentRawText: vi.fn(),
  getPawlsLayer: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("document cache isolation at authentication changes", () => {
  beforeEach(() => vi.stubGlobal("FDBFactory", FDBFactory));

  afterEach(async () => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    clearAuthSession();
    await vi.waitFor(() => expect(authSessionCleanupPendingVar()).toBe(false));
    await documentCacheManager.clearCache();
  });

  const cacheFormats = [
    {
      format: "text",
      write: () =>
        documentCacheManager.cacheText("private-doc", "PRIVATE", "hash"),
      read: () => documentCacheManager.getCachedText("private-doc", "hash"),
      empty: null,
    },
    {
      format: "pdf",
      write: () =>
        documentCacheManager.cachePDF(
          "private-doc",
          "hash",
          new Blob(["%PDF synthetic"], { type: "application/pdf" })
        ),
      read: () => documentCacheManager.getCachedPDF("private-doc", "hash"),
      empty: null,
    },
    {
      format: "pawls",
      write: () => documentCacheManager.cachePawlsData("private-doc", []),
      read: () => documentCacheManager.getCachedPawlsData("private-doc"),
      empty: null,
    },
  ];
  const cacheReads = [
    ...cacheFormats,
    {
      format: "metadata",
      write: cacheFormats[0].write,
      read: () =>
        documentCacheManager.validateCache("private-doc", "text", "hash"),
      empty: false,
    },
  ];

  it.each(cacheReads)(
    "discards $format reads when the session changes while opening storage",
    async ({ write, read, empty }) => {
      await write();
      expect(await read()).not.toBe(empty);
      const pending = read();
      invalidateDocumentCacheSession();
      expect(await pending).toBe(empty);
    }
  );

  it.each(cacheReads)(
    "discards $format reads when the session changes before storage responds",
    async ({ write, read, empty }) => {
      await write();
      const get = IDBObjectStore.prototype.get;
      vi.spyOn(IDBObjectStore.prototype, "get").mockImplementationOnce(
        function (this: IDBObjectStore, key: IDBValidKey | IDBKeyRange) {
          const request = get.call(this, key);
          // The request still reads the old entry from real fake-indexeddb storage.
          // Only the authentication session changes before its callback runs.
          invalidateDocumentCacheSession();
          return request;
        }
      );
      expect(await read()).toBe(empty);
    }
  );

  it.each(cacheFormats)(
    "discards $format writes when the session changes while opening storage",
    async ({ write }) => {
      const pending = write();
      invalidateDocumentCacheSession();
      await pending;
      expect((await documentCacheManager.getCacheStats()).count).toBe(0);
    }
  );

  it.each(cacheFormats)(
    "discards $format writes when the session changes while checking capacity",
    async ({ write }) => {
      const openCursor = IDBObjectStore.prototype.openCursor;
      vi.spyOn(IDBObjectStore.prototype, "openCursor").mockImplementationOnce(
        function (
          this: IDBObjectStore,
          ...args: Parameters<IDBObjectStore["openCursor"]>
        ) {
          const request = openCursor.apply(this, args);
          invalidateDocumentCacheSession();
          return request;
        }
      );
      await write();
      expect((await documentCacheManager.getCacheStats()).count).toBe(0);
    }
  );

  it("invalidates memory caches even when IndexedDB is unavailable", async () => {
    const generation = getDocumentCacheGeneration();
    docxBytesCache.set("private.docx", new Uint8Array([1, 2]));
    vi.stubGlobal("indexedDB", undefined);
    await documentCacheManager.clearCache();
    expect(getDocumentCacheGeneration()).toBe(generation + 1);
    expect(docxBytesCache.size).toBe(0);
  });

  it("clears stored content and DOCX bytes on logout/account replacement", async () => {
    beginAuthSession("synthetic-owner-token");
    await documentCacheManager.cacheText("private-doc", "OWNER_PRIVATE_TEXT");
    expect(await documentCacheManager.getCachedText("private-doc")).toBe(
      "OWNER_PRIVATE_TEXT"
    );
    docxBytesCache.set("private.docx", new Uint8Array([1, 2]));
    clearAuthSession(undefined, "logout");
    expect(docxBytesCache.size).toBe(0);
    expect(await documentCacheManager.getCachedText("private-doc")).toBeNull();
    await vi.waitFor(() => expect(authSessionCleanupPendingVar()).toBe(false));
    beginAuthSession("synthetic-stranger-token");
    expect(await documentCacheManager.getCachedText("private-doc")).toBeNull();
  });

  it("isolates old storage even when deletion fails", async () => {
    await documentCacheManager.cacheText("private-doc", "OWNER_PRIVATE_TEXT");
    // Changing the namespace is synchronous; safety never depends on IDB deletion.
    invalidateDocumentCacheSession();
    expect(await documentCacheManager.getCachedText("private-doc")).toBeNull();
  });

  it.each(["text", "pawls", "pdf", "docx"])(
    "rejects late %s responses after logout",
    async (format) => {
      const network = deferred<void>();
      let pending: Promise<unknown>;
      if (format === "text") {
        vi.mocked(rest.getDocumentRawText).mockReturnValueOnce(
          network.promise.then(() => "PRIVATE")
        );
        pending = getDocumentRawText("private.txt", "private-doc");
        await vi.waitFor(() =>
          expect(rest.getDocumentRawText).toHaveBeenCalled()
        );
      } else if (format === "pawls") {
        vi.mocked(rest.getPawlsLayer).mockReturnValueOnce(
          network.promise.then(() => [])
        );
        pending = getPawlsLayer("private.json", "private-doc");
        await vi.waitFor(() => expect(rest.getPawlsLayer).toHaveBeenCalled());
      } else {
        vi.spyOn(axios, "get").mockReturnValueOnce(
          network.promise.then(() => ({
            data: new Uint8Array([1, 2]).buffer,
            status: 200,
            statusText: "OK",
            headers: {},
            config: { headers: new AxiosHeaders() },
          }))
        );
        pending =
          format === "pdf"
            ? getCachedPDFUrl("private.pdf", "private-doc", "hash")
            : getDocxBytes("private.docx");
        await vi.waitFor(() => expect(axios.get).toHaveBeenCalled());
      }
      const rejected = expect(pending).rejects.toThrow(
        "Document session changed"
      );
      clearAuthSession(undefined, "logout");
      network.resolve();
      await rejected;
      expect(
        await documentCacheManager.getCachedText("private-doc")
      ).toBeNull();
      expect(docxBytesCache.size).toBe(0);
    }
  );
});
