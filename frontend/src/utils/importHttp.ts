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

export async function importDocumentMultipart(
  input: ImportDocumentRestInput
): Promise<ImportDocumentRestResult> {
  const fd = new FormData();
  fd.append("file", input.file);
  fd.append("title", input.title);
  appendIfDefined(fd, "filename", input.filename ?? input.file.name);
  appendIfDefined(fd, "description", input.description);
  appendIfDefined(fd, "slug", input.slug);
  appendIfDefined(fd, "add_to_corpus_id", input.addToCorpusId ?? undefined);
  appendIfDefined(fd, "add_to_folder_id", input.addToFolderId ?? undefined);
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

  const data = (await response.json()) as {
    ok: boolean;
    document_id: number;
    status?: string;
    error?: string;
  };
  if (!data.ok) {
    return {
      ok: false,
      status_code: response.status,
      error: data.error || "Import failed",
    };
  }
  return { ok: true, document_id: data.document_id, status: data.status };
}

export async function importDocumentsZipMultipart(
  input: ImportZipRestInput
): Promise<ImportZipRestResult> {
  const fd = new FormData();
  fd.append("file", input.file);
  appendIfDefined(fd, "title_prefix", input.titlePrefix);
  appendIfDefined(fd, "description", input.description);
  appendIfDefined(fd, "add_to_corpus_id", input.addToCorpusId ?? undefined);
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

  const data = (await response.json()) as {
    ok: boolean;
    job_id?: string;
    message?: string;
    error?: string;
  };
  if (!data.ok || !data.job_id) {
    return {
      ok: false,
      status_code: response.status,
      error: data.error || "Import failed",
    };
  }
  return { ok: true, job_id: data.job_id, message: data.message };
}
