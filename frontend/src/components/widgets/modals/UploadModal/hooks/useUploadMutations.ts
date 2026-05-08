import { useCallback, useState } from "react";
import { useApolloClient } from "@apollo/client";
import { toast } from "react-toastify";
import {
  GET_DOCUMENTS,
  GET_DOCUMENTS_FOR_LIST,
} from "../../../../../graphql/queries";
import { GET_CORPUS_FOLDERS } from "../../../../../graphql/queries/folders";
import {
  importDocumentMultipart,
  importDocumentsZipMultipart,
} from "../../../../../utils/importHttp";
import { FileUploadPackage, UploadStatus } from "./useUploadState";

interface UseUploadMutationsProps {
  corpusId?: string | null;
  folderId?: string | null;
  /** Whether uploaded documents should be public (default: false) */
  makePublic?: boolean;
  onFileStatusChange: (index: number, status: UploadStatus) => void;
  onComplete?: () => void;
}

interface UseUploadMutationsReturn {
  uploadSingleFile: (
    file: File,
    formData: FileUploadPackage["formData"],
    index: number
  ) => Promise<boolean>;
  uploadFiles: (
    files: FileUploadPackage[],
    selectedCorpusId?: string | null
  ) => Promise<void>;
  uploadZipFile: (
    zipFile: File,
    targetCorpusId?: string | null
  ) => Promise<boolean>;
  isUploading: boolean;
}

/**
 * Wraps the multipart REST upload endpoints for single documents and
 * bulk ZIP archives. Files are streamed via FormData rather than
 * base64-encoded into a GraphQL variable, which avoids Apollo's
 * "Payload allocation size overflow" invariant for large files.
 */
export function useUploadMutations({
  corpusId,
  folderId,
  makePublic = false,
  onFileStatusChange,
  onComplete,
}: UseUploadMutationsProps): UseUploadMutationsReturn {
  const client = useApolloClient();

  const [singleInFlight, setSingleInFlight] = useState(false);
  const [zipInFlight, setZipInFlight] = useState(false);
  const isUploading = singleInFlight || zipInFlight;

  /**
   * Upload a single file with its metadata.
   * Returns true on success, false on failure.
   */
  const uploadSingleFile = useCallback(
    async (
      file: File,
      formData: FileUploadPackage["formData"],
      index: number
    ): Promise<boolean> => {
      onFileStatusChange(index, "uploading");
      setSingleInFlight(true);
      try {
        const result = await importDocumentMultipart({
          file,
          title: formData.title || file.name,
          description: formData.description || "",
          slug: formData.slug || undefined,
          filename: file.name,
          addToCorpusId: corpusId ?? null,
          addToFolderId: folderId ?? null,
          makePublic,
        });

        if (result.ok) {
          onFileStatusChange(index, "success");
          return true;
        }
        console.error("[UPLOAD] Upload failed:", result.error);
        onFileStatusChange(index, "failed");
        toast.error(result.error || "Upload failed");
        return false;
      } catch (error: unknown) {
        console.error("[UPLOAD] Upload error:", error);
        onFileStatusChange(index, "failed");
        const message =
          error instanceof Error ? error.message : "Upload failed";
        toast.error(message);
        return false;
      } finally {
        setSingleInFlight(false);
      }
    },
    [corpusId, folderId, makePublic, onFileStatusChange]
  );

  /**
   * Upload multiple files sequentially.
   * Uses provided corpusId or falls back to prop corpusId.
   */
  const uploadFiles = useCallback(
    async (
      files: FileUploadPackage[],
      selectedCorpusId?: string | null
    ): Promise<void> => {
      toast.info("Starting upload...");

      const effectiveCorpusId = selectedCorpusId || corpusId;
      setSingleInFlight(true);
      try {
        for (const [index, pkg] of files.entries()) {
          onFileStatusChange(index, "uploading");
          try {
            const result = await importDocumentMultipart({
              file: pkg.file,
              title: pkg.formData?.title || pkg.file.name,
              description: pkg.formData?.description || "",
              slug: pkg.formData?.slug || undefined,
              filename: pkg.file.name,
              addToCorpusId: effectiveCorpusId ?? null,
              addToFolderId: folderId ?? null,
              makePublic,
            });

            if (result.ok) {
              onFileStatusChange(index, "success");
            } else {
              console.error("[UPLOAD] Upload failed:", result.error);
              onFileStatusChange(index, "failed");
              toast.error(result.error || "Upload failed");
            }
          } catch (error: unknown) {
            console.error("[UPLOAD] Upload error:", error);
            onFileStatusChange(index, "failed");
            const message =
              error instanceof Error ? error.message : "Upload failed";
            toast.error(message);
          }
        }
      } finally {
        setSingleInFlight(false);
      }

      // Refetch documents and folders after all uploads. Both the heavy
      // ``GET_DOCUMENTS`` (used by corpus tabs, modals, relationship UI) and
      // the slim ``GET_DOCUMENTS_FOR_LIST`` (used by the top-level Documents
      // view) need to refresh — Apollo's ``refetchQueries`` only refetches
      // queries that are currently active on the client, so listing both is
      // a no-op when the corresponding observable isn't mounted.
      await client.refetchQueries({
        include: [GET_DOCUMENTS, GET_DOCUMENTS_FOR_LIST, GET_CORPUS_FOLDERS],
      });

      onComplete?.();
    },
    [corpusId, folderId, makePublic, client, onFileStatusChange, onComplete]
  );

  /**
   * Upload a ZIP file containing multiple documents.
   * Uploads are processed sequentially on the backend via a Celery job.
   * Returns true on success, false on failure.
   */
  const uploadZipFile = useCallback(
    async (zipFile: File, targetCorpusId?: string | null): Promise<boolean> => {
      setZipInFlight(true);
      try {
        const result = await importDocumentsZipMultipart({
          file: zipFile,
          addToCorpusId: targetCorpusId ?? null,
          makePublic,
        });

        if (result.ok) {
          toast.success(`Upload job started! Job ID: ${result.job_id}`);
          return true;
        }
        const errorMessage = result.error || "Upload failed";
        toast.error(`Upload failed: ${errorMessage}`);
        return false;
      } catch (error: unknown) {
        console.error("[UPLOAD] ZIP upload error:", error);
        const errorMessage =
          error instanceof Error
            ? error.message
            : "An unexpected error occurred";
        toast.error(`Upload failed: ${errorMessage}`);
        return false;
      } finally {
        setZipInFlight(false);
      }
    },
    [makePublic]
  );

  return {
    uploadSingleFile,
    uploadFiles,
    uploadZipFile,
    isUploading,
  };
}

export default useUploadMutations;
