/**
 * Multipart/form-data helpers for the document import REST endpoints
 * (``POST /api/imports/documents/`` and ``/api/imports/documents-zip/``).
 *
 * Used instead of the legacy base64-over-GraphQL path to avoid Apollo's
 * "Payload allocation size overflow" invariant — base64 inflates the file
 * by ~33% and Apollo serialises the entire string into the JSON request
 * body before any network I/O, which V8 cannot allocate for large files.
 *
 * These helpers stream the file via FormData; the browser handles
 * boundaries and the byte stream goes straight to the server.
 */
import { authToken } from "../graphql/cache";
import { UPLOAD } from "../assets/configurations/constants";
import { getRuntimeEnv } from "./env";

/**
 * Default to "" so requests are issued same-origin (the Vite dev server
 * proxies ``/api/*`` to Django, and same-origin production deployments
 * serve frontend + backend off the same host). Cross-origin deployments
 * must set ``REACT_APP_API_ROOT_URL`` explicitly.
 */
const DEFAULT_API_ROOT = "";

function getApiRoot(): string {
  return getRuntimeEnv().REACT_APP_API_ROOT_URL || DEFAULT_API_ROOT;
}

function buildAuthHeaders(): Record<string, string> {
  const token = authToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface ImportDocumentRestInput {
  file: File;
  title: string;
  description?: string;
  filename?: string;
  slug?: string;
  addToCorpusId?: string | null;
  addToFolderId?: string | null;
  makePublic?: boolean;
  customMeta?: Record<string, unknown>;
  /** Optional progress callback (fraction in ``[0, 1]``) for large uploads. */
  onProgress?: UploadProgressCallback;
}

export interface ImportDocumentRestSuccess {
  ok: true;
  document_id: number;
  status?: string | null;
}

export interface ImportDocumentRestFailure {
  ok: false;
  error: string;
  status_code: number;
}

export type ImportDocumentRestResult =
  | ImportDocumentRestSuccess
  | ImportDocumentRestFailure;

export interface ImportZipRestInput {
  file: File;
  titlePrefix?: string;
  description?: string;
  addToCorpusId?: string | null;
  makePublic?: boolean;
  customMeta?: Record<string, unknown>;
  /** Optional progress callback (fraction in ``[0, 1]``) for large uploads. */
  onProgress?: UploadProgressCallback;
}

export interface ImportZipRestSuccess {
  ok: true;
  job_id: string;
  message?: string;
}

export interface ImportZipRestFailure {
  ok: false;
  error: string;
  status_code: number;
}

export type ImportZipRestResult = ImportZipRestSuccess | ImportZipRestFailure;

export interface ImportZipToCorpusRestInput {
  file: File;
  corpusId: string;
  targetFolderId?: string | null;
  titlePrefix?: string;
  description?: string;
  makePublic?: boolean;
  customMeta?: Record<string, unknown>;
  /** Optional progress callback (fraction in ``[0, 1]``) for large uploads. */
  onProgress?: UploadProgressCallback;
}

export interface ImportCorpusExportRestInput {
  file: File;
  /** Optional progress callback (fraction in ``[0, 1]``) for large uploads. */
  onProgress?: UploadProgressCallback;
}

export interface ImportCorpusExportRestSuccess {
  ok: true;
  corpus_id: number;
  message?: string;
}

export interface ImportCorpusExportRestFailure {
  ok: false;
  error: string;
  status_code: number;
}

export type ImportCorpusExportRestResult =
  | ImportCorpusExportRestSuccess
  | ImportCorpusExportRestFailure;

function appendIfDefined(
  fd: FormData,
  key: string,
  value: string | null | undefined
): void {
  if (value === undefined || value === null || value === "") return;
  fd.append(key, value);
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data === "string") return data;
    if (data && typeof data === "object") {
      if (typeof data.error === "string") return data.error;
      if (typeof data.detail === "string") return data.detail;
      const firstFieldErr = Object.values(data).find(
        (v) => Array.isArray(v) && typeof v[0] === "string"
      ) as string[] | undefined;
      if (firstFieldErr) return firstFieldErr[0];
    }
  } catch {
    // fall through to generic message
  }
  return `Import failed (HTTP ${response.status})`;
}

// ---------------------------------------------------------------------------
// Chunked (resumable) uploads
// ---------------------------------------------------------------------------
//
// Upstream proxies (Cloudflare) cap a single proxied request body at 100MB.
// To upload anything larger we slice the file into < CHUNK_SIZE_BYTES parts and
// drive the server's ``/api/imports/chunked/*`` protocol: ``start`` (declare
// size + part count) -> PUT each part -> ``complete`` (reassemble + import).
// ``complete`` returns the exact same JSON body as the matching single-request
// endpoint, so the public helpers below map it through the same result
// builders regardless of which transport was used.

type ChunkedKind =
  | "document"
  | "documents_zip"
  | "zip_to_corpus"
  | "corpus_export";

interface ChunkedTransportResult {
  ok: boolean;
  status_code: number;
  /** Parsed ``complete`` response body (only on success). */
  body?: unknown;
  error?: string;
}

/**
 * Progress callback invoked after each successful part upload (and once at
 * ``1`` for the single-shot path), reporting a fraction in ``[0, 1]`` of the
 * file transferred. Lets callers drive a progress bar for large uploads.
 */
export type UploadProgressCallback = (fraction: number) => void;

/** Whether a file is large enough to require the chunked endpoints. */
function shouldChunkFile(file: File): boolean {
  return file.size > UPLOAD.CHUNK_THRESHOLD_BYTES;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface PartUploadOutcome {
  ok: boolean;
  status_code: number;
  error?: string;
}

/**
 * PUT a single part with exponential-backoff retry. The backend persists
 * parts and accepts idempotent re-upload (overwriting the same index), so a
 * transient failure can be safely retried. Non-retryable client errors
 * (4xx other than 408/429) fail fast — retrying a 4xx just wastes attempts.
 */
async function putPartWithRetry(params: {
  root: string;
  uploadId: string;
  index: number;
  filename: string;
  blob: Blob;
}): Promise<PartUploadOutcome> {
  const url = `${params.root}/api/imports/chunked/${params.uploadId}/parts/${params.index}/`;
  let lastStatus = 0;
  let lastError = "Upload failed";

  for (let attempt = 1; attempt <= UPLOAD.CHUNK_MAX_ATTEMPTS; attempt++) {
    if (attempt > 1) {
      await delay(UPLOAD.CHUNK_RETRY_BASE_DELAY_MS * 2 ** (attempt - 2));
    }
    // Build FormData fresh each attempt — a consumed body cannot be re-sent.
    const fd = new FormData();
    fd.append("file", params.blob, `${params.filename}.part${params.index}`);
    try {
      const partRes = await fetch(url, {
        method: "PUT",
        headers: buildAuthHeaders(),
        body: fd,
      });
      if (partRes.ok) {
        return { ok: true, status_code: partRes.status };
      }
      const retryable =
        partRes.status >= 500 ||
        partRes.status === 408 ||
        partRes.status === 429;
      if (!retryable) {
        return {
          ok: false,
          status_code: partRes.status,
          error: await parseErrorMessage(partRes),
        };
      }
      lastStatus = partRes.status;
      lastError = await parseErrorMessage(partRes);
    } catch (e) {
      // Network-level failure (offline, DNS, reset) — retryable.
      lastStatus = 0;
      lastError = e instanceof Error ? e.message : "Network error";
    }
  }
  return { ok: false, status_code: lastStatus, error: lastError };
}

async function uploadFileInChunks(params: {
  kind: ChunkedKind;
  file: File;
  filename: string;
  metadata: Record<string, unknown>;
  onProgress?: UploadProgressCallback;
}): Promise<ChunkedTransportResult> {
  const root = getApiRoot();
  const chunkSize = UPLOAD.CHUNK_SIZE_BYTES;
  const totalSize = params.file.size;
  const totalChunks = Math.max(1, Math.ceil(totalSize / chunkSize));

  // 1. Open the session.
  const startRes = await fetch(`${root}/api/imports/chunked/start/`, {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: params.kind,
      filename: params.filename,
      total_size: totalSize,
      chunk_size: chunkSize,
      total_chunks: totalChunks,
      metadata: params.metadata,
    }),
  });
  if (!startRes.ok) {
    return {
      ok: false,
      status_code: startRes.status,
      error: await parseErrorMessage(startRes),
    };
  }
  const startBody = (await startRes.json()) as { upload_id?: string };
  const uploadId = startBody.upload_id;
  if (!uploadId) {
    return {
      ok: false,
      status_code: startRes.status,
      error: "Failed to start chunked upload",
    };
  }

  // 2. Upload the slices with bounded concurrency. ``File.slice`` returns a
  //    lazy Blob, so at most ``CHUNK_CONCURRENCY`` parts are materialised at
  //    once — even a multi-GB file never sits in memory all at once. A worker
  //    pool of fixed size drains a shared index counter; the first hard part
  //    failure (after retries) aborts the remaining workers.
  let nextIndex = 0;
  let completed = 0;
  let failure: ChunkedTransportResult | null = null;

  const worker = async (): Promise<void> => {
    while (failure === null) {
      const i = nextIndex;
      if (i >= totalChunks) return;
      nextIndex += 1;

      const begin = i * chunkSize;
      const end = Math.min(begin + chunkSize, totalSize);
      const outcome = await putPartWithRetry({
        root,
        uploadId,
        index: i,
        filename: params.filename,
        blob: params.file.slice(begin, end),
      });
      if (!outcome.ok) {
        failure = {
          ok: false,
          status_code: outcome.status_code,
          error: outcome.error,
        };
        return;
      }
      completed += 1;
      params.onProgress?.(completed / totalChunks);
    }
  };

  const workerCount = Math.min(UPLOAD.CHUNK_CONCURRENCY, totalChunks);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  if (failure !== null) {
    return failure;
  }

  // 3. Reassemble + import.
  const completeRes = await fetch(
    `${root}/api/imports/chunked/${uploadId}/complete/`,
    { method: "POST", headers: buildAuthHeaders() }
  );
  if (!completeRes.ok) {
    return {
      ok: false,
      status_code: completeRes.status,
      error: await parseErrorMessage(completeRes),
    };
  }
  return {
    ok: true,
    status_code: completeRes.status,
    body: await completeRes.json(),
  };
}

// --- Response-body -> typed-result mappers (shared by both transports) ------

function toDocumentResult(
  body: unknown,
  statusCode: number
): ImportDocumentRestResult {
  const data = body as {
    ok?: boolean;
    document_id?: number;
    status?: string;
    error?: string;
  };
  if (!data || data.ok !== true || typeof data.document_id !== "number") {
    return {
      ok: false,
      status_code: statusCode,
      error: data?.error || "Import failed",
    };
  }
  return { ok: true, document_id: data.document_id, status: data.status };
}

function toZipResult(body: unknown, statusCode: number): ImportZipRestResult {
  const data = body as {
    ok?: boolean;
    job_id?: string;
    message?: string;
    error?: string;
  };
  if (!data || data.ok !== true || !data.job_id) {
    return {
      ok: false,
      status_code: statusCode,
      error: data?.error || "Import failed",
    };
  }
  return { ok: true, job_id: data.job_id, message: data.message };
}

function toCorpusResult(
  body: unknown,
  statusCode: number
): ImportCorpusExportRestResult {
  const data = body as {
    ok?: boolean;
    corpus_id?: number;
    message?: string;
    error?: string;
  };
  if (!data || data.ok !== true || data.corpus_id === undefined) {
    return {
      ok: false,
      status_code: statusCode,
      error: data?.error || "Import failed",
    };
  }
  return { ok: true, corpus_id: data.corpus_id, message: data.message };
}

// --- Per-kind metadata builders (mirror the multipart field set) ------------

function withOptional(
  md: Record<string, unknown>,
  key: string,
  value: string | null | undefined
): void {
  if (value === undefined || value === null || value === "") return;
  md[key] = value;
}

function buildDocumentMetadata(
  input: ImportDocumentRestInput
): Record<string, unknown> {
  const md: Record<string, unknown> = {
    title: input.title,
    filename: input.filename ?? input.file.name,
    make_public: !!input.makePublic,
  };
  withOptional(md, "description", input.description);
  withOptional(md, "slug", input.slug);
  withOptional(md, "add_to_corpus_id", input.addToCorpusId);
  withOptional(md, "add_to_folder_id", input.addToFolderId);
  if (input.customMeta && Object.keys(input.customMeta).length > 0) {
    md.custom_meta = input.customMeta;
  }
  return md;
}

function buildZipMetadata(input: ImportZipRestInput): Record<string, unknown> {
  const md: Record<string, unknown> = { make_public: !!input.makePublic };
  withOptional(md, "title_prefix", input.titlePrefix);
  withOptional(md, "description", input.description);
  withOptional(md, "add_to_corpus_id", input.addToCorpusId);
  if (input.customMeta && Object.keys(input.customMeta).length > 0) {
    md.custom_meta = input.customMeta;
  }
  return md;
}

function buildZipToCorpusMetadata(
  input: ImportZipToCorpusRestInput
): Record<string, unknown> {
  const md: Record<string, unknown> = {
    corpus_id: input.corpusId,
    make_public: !!input.makePublic,
  };
  withOptional(md, "target_folder_id", input.targetFolderId);
  withOptional(md, "title_prefix", input.titlePrefix);
  withOptional(md, "description", input.description);
  if (input.customMeta && Object.keys(input.customMeta).length > 0) {
    md.custom_meta = input.customMeta;
  }
  return md;
}

export async function importDocumentMultipart(
  input: ImportDocumentRestInput
): Promise<ImportDocumentRestResult> {
  // Large files exceed the 100MB upstream proxy cap; route them through the
  // chunked endpoints, which return the identical ``complete`` body shape.
  if (shouldChunkFile(input.file)) {
    const r = await uploadFileInChunks({
      kind: "document",
      file: input.file,
      filename: input.filename ?? input.file.name,
      metadata: buildDocumentMetadata(input),
      onProgress: input.onProgress,
    });
    if (!r.ok) {
      return {
        ok: false,
        status_code: r.status_code,
        error: r.error || "Import failed",
      };
    }
    return toDocumentResult(r.body, r.status_code);
  }

  const fd = new FormData();
  fd.append("file", input.file);
  fd.append("title", input.title);
  appendIfDefined(fd, "filename", input.filename ?? input.file.name);
  appendIfDefined(fd, "description", input.description);
  appendIfDefined(fd, "slug", input.slug);
  appendIfDefined(fd, "add_to_corpus_id", input.addToCorpusId);
  appendIfDefined(fd, "add_to_folder_id", input.addToFolderId);
  fd.append("make_public", input.makePublic ? "true" : "false");
  if (input.customMeta && Object.keys(input.customMeta).length > 0) {
    fd.append("custom_meta", JSON.stringify(input.customMeta));
  }

  const response = await fetch(`${getApiRoot()}/api/imports/documents/`, {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!response.ok) {
    return {
      ok: false,
      status_code: response.status,
      error: await parseErrorMessage(response),
    };
  }

  return toDocumentResult(await response.json(), response.status);
}

export async function importDocumentsZipMultipart(
  input: ImportZipRestInput
): Promise<ImportZipRestResult> {
  if (shouldChunkFile(input.file)) {
    const r = await uploadFileInChunks({
      kind: "documents_zip",
      file: input.file,
      filename: input.file.name,
      metadata: buildZipMetadata(input),
      onProgress: input.onProgress,
    });
    if (!r.ok) {
      return {
        ok: false,
        status_code: r.status_code,
        error: r.error || "Import failed",
      };
    }
    return toZipResult(r.body, r.status_code);
  }

  const fd = new FormData();
  fd.append("file", input.file);
  appendIfDefined(fd, "title_prefix", input.titlePrefix);
  appendIfDefined(fd, "description", input.description);
  appendIfDefined(fd, "add_to_corpus_id", input.addToCorpusId);
  fd.append("make_public", input.makePublic ? "true" : "false");
  if (input.customMeta && Object.keys(input.customMeta).length > 0) {
    fd.append("custom_meta", JSON.stringify(input.customMeta));
  }

  const response = await fetch(`${getApiRoot()}/api/imports/documents-zip/`, {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!response.ok) {
    return {
      ok: false,
      status_code: response.status,
      error: await parseErrorMessage(response),
    };
  }

  return toZipResult(await response.json(), response.status);
}

/**
 * Bulk-zip import that preserves the zip's folder hierarchy into the
 * specified corpus. Replaces the legacy ``ImportZipToCorpus`` GraphQL
 * mutation that base64-encoded the entire zip into a JSON request body.
 */
export async function importZipToCorpusMultipart(
  input: ImportZipToCorpusRestInput
): Promise<ImportZipRestResult> {
  if (shouldChunkFile(input.file)) {
    const r = await uploadFileInChunks({
      kind: "zip_to_corpus",
      file: input.file,
      filename: input.file.name,
      metadata: buildZipToCorpusMetadata(input),
      onProgress: input.onProgress,
    });
    if (!r.ok) {
      return {
        ok: false,
        status_code: r.status_code,
        error: r.error || "Import failed",
      };
    }
    return toZipResult(r.body, r.status_code);
  }

  const fd = new FormData();
  fd.append("file", input.file);
  fd.append("corpus_id", input.corpusId);
  appendIfDefined(fd, "target_folder_id", input.targetFolderId);
  appendIfDefined(fd, "title_prefix", input.titlePrefix);
  appendIfDefined(fd, "description", input.description);
  fd.append("make_public", input.makePublic ? "true" : "false");
  if (input.customMeta && Object.keys(input.customMeta).length > 0) {
    fd.append("custom_meta", JSON.stringify(input.customMeta));
  }

  const response = await fetch(`${getApiRoot()}/api/imports/zip-to-corpus/`, {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!response.ok) {
    return {
      ok: false,
      status_code: response.status,
      error: await parseErrorMessage(response),
    };
  }

  return toZipResult(await response.json(), response.status);
}

/**
 * OpenContracts corpus-export zip import. Creates a new corpus owned by
 * the requester and queues the export hydration task. Replaces the
 * legacy ``UploadCorpusImportZip`` GraphQL mutation.
 */
export async function importCorpusExportMultipart(
  input: ImportCorpusExportRestInput
): Promise<ImportCorpusExportRestResult> {
  if (shouldChunkFile(input.file)) {
    const r = await uploadFileInChunks({
      kind: "corpus_export",
      file: input.file,
      filename: input.file.name,
      metadata: {},
      onProgress: input.onProgress,
    });
    if (!r.ok) {
      return {
        ok: false,
        status_code: r.status_code,
        error: r.error || "Import failed",
      };
    }
    return toCorpusResult(r.body, r.status_code);
  }

  const fd = new FormData();
  fd.append("file", input.file);

  const response = await fetch(`${getApiRoot()}/api/imports/corpus/`, {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!response.ok) {
    return {
      ok: false,
      status_code: response.status,
      error: await parseErrorMessage(response),
    };
  }

  return toCorpusResult(await response.json(), response.status);
}
