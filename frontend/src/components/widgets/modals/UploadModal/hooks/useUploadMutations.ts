import { useCallback } from "react";
import { useMutation, useApolloClient } from "@apollo/client";
import { gql } from "@apollo/client";
import { toast } from "react-toastify";
import {
  UPLOAD_DOCUMENT,
  UploadDocumentInputProps,
  UploadDocumentOutputProps,
} from "../../../../../graphql/mutations";
import { GET_DOCUMENTS } from "../../../../../graphql/queries";
import { GET_CORPUS_FOLDERS } from "../../../../../graphql/queries/folders";
import { toBase64 } from "../../../../../utils/files";
import { FileUploadPackage, UploadStatus } from "./useUploadState";

// Bulk upload mutation
const UPLOAD_DOCUMENTS_ZIP = gql`
  mutation UploadDocumentsZip(
    $base64FileString: String!
    $makePublic: Boolean!
    $addToCorpusId: ID
    $titlePrefix: String
    $description: String
  ) {
    uploadDocumentsZip(
      base64FileString: $base64FileString
      makePublic: $makePublic
      addToCorpusId: $addToCorpusId
      titlePrefix: $titlePrefix
      description: $description
    ) {
      ok
      message
      jobId
    }
  }
`;

interface UploadDocumentsZipVars {
  base64FileString: string;
  makePublic: boolean;
  addToCorpusId?: string | null;
  titlePrefix?: string;
  description?: string;
}

interface UploadDocumentsZipOutput {
  uploadDocumentsZip: {
    ok: boolean;
    message: string;
    jobId?: string;
  };
}

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
 * Hook that wraps upload mutations for single documents and ZIP files.
 * Handles file conversion, mutation execution, and error handling.
 */
export function useUploadMutations({
  corpusId,
  folderId,
  makePublic = false,
  onFileStatusChange,
  onComplete,
}: UseUploadMutationsProps): UseUploadMutationsReturn {
  const client = useApolloClient();

  const [uploadDocumentMutation, { loading: uploadingDocument }] =
    useMutation<UploadDocumentOutputProps>(UPLOAD_DOCUMENT);

  const [uploadZipMutation, { loading: uploadingZip }] = useMutation<
    UploadDocumentsZipOutput,
    UploadDocumentsZipVars
  >(UPLOAD_DOCUMENTS_ZIP);

  const isUploading = uploadingDocument || uploadingZip;

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

      try {
        const base64String = await toBase64(file);

        if (typeof base64String !== "string") {
          throw new Error("Failed to convert file to base64");
        }

        const variables: UploadDocumentInputProps = {
          base64FileString: base64String.split(",")[1],
          filename: file.name,
          customMeta: {},
          description: formData.description || "",
          title: formData.title || file.name,
          slug: formData.slug || undefined,
          addToCorpusId: corpusId || undefined,
          addToFolderId: folderId || undefined,
          makePublic,
        };

        const result = await uploadDocumentMutation({ variables });

        if (result.data?.uploadDocument?.ok) {
          onFileStatusChange(index, "success");
          return true;
        } else {
          console.error(
            "[UPLOAD] Upload failed:",
            result.data?.uploadDocument?.message
          );
          onFileStatusChange(index, "failed");
          toast.error(result.data?.uploadDocument?.message || "Upload failed");
          return false;
        }
      } catch (error: unknown) {
        console.error("[UPLOAD] Upload error:", error);
        onFileStatusChange(index, "failed");
        const message =
          error instanceof Error ? error.message : "Upload failed";
        toast.error(message);
        return false;
      }
    },
    [corpusId, folderId, makePublic, uploadDocumentMutation, onFileStatusChange]
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

      // Upload files sequentially to avoid overwhelming the server
      for (const [index, pkg] of files.entries()) {
        onFileStatusChange(index, "uploading");

        try {
          const base64String = await toBase64(pkg.file);

          if (typeof base64String !== "string") {
            throw new Error("Failed to convert file to base64");
          }

          const variables: UploadDocumentInputProps = {
            base64FileString: base64String.split(",")[1],
            filename: pkg.file.name,
            customMeta: {},
            description: pkg.formData?.description || "",
            title: pkg.formData?.title || pkg.file.name,
            slug: pkg.formData?.slug || undefined,
            addToCorpusId: effectiveCorpusId || undefined,
            addToFolderId: folderId || undefined,
            makePublic,
          };

          const result = await uploadDocumentMutation({ variables });

          if (result.data?.uploadDocument?.ok) {
            onFileStatusChange(index, "success");
          } else {
            console.error(
              "[UPLOAD] Upload failed:",
              result.data?.uploadDocument?.message
            );
            onFileStatusChange(index, "failed");
            toast.error(
              result.data?.uploadDocument?.message || "Upload failed"
            );
          }
        } catch (error: unknown) {
          console.error("[UPLOAD] Upload error:", error);
          onFileStatusChange(index, "failed");
          const message =
            error instanceof Error ? error.message : "Upload failed";
          toast.error(message);
        }
      }

      // Refetch documents and folders after all uploads
      await client.refetchQueries({
        include: [GET_DOCUMENTS, GET_CORPUS_FOLDERS],
      });

      onComplete?.();
    },
    [
      corpusId,
      folderId,
      makePublic,
      uploadDocumentMutation,
      client,
      onFileStatusChange,
      onComplete,
    ]
  );

  /**
   * Upload a ZIP file containing multiple documents.
   * Uploads are processed sequentially on the backend via a Celery job.
   * Returns true on success, false on failure.
   */
  const uploadZipFile = useCallback(
    async (zipFile: File, targetCorpusId?: string | null): Promise<boolean> => {
      try {
        // Convert to base64 using shared utility for consistency
        const base64Result = await toBase64(zipFile);

        if (typeof base64Result !== "string") {
          throw new Error("Failed to convert file to base64");
        }

        // Remove data:mime/type;base64, prefix
        const base64String = base64Result.split(",")[1];

        const result = await uploadZipMutation({
          variables: {
            base64FileString: base64String,
            makePublic,
            addToCorpusId: targetCorpusId || null,
          },
        });

        if (result.data?.uploadDocumentsZip.ok) {
          toast.success(
            `Upload job started! Job ID: ${result.data.uploadDocumentsZip.jobId}`
          );
          return true;
        } else {
          throw new Error(
            result.data?.uploadDocumentsZip.message || "Upload failed"
          );
        }
      } catch (error: unknown) {
        console.error("[UPLOAD] ZIP upload error:", error);
        // Handle GraphQL errors and standard errors
        let errorMessage = "An unexpected error occurred";
        if (error instanceof Error) {
          // Check for Apollo GraphQL error structure
          const apolloError = error as Error & {
            graphQLErrors?: Array<{ message: string }>;
            networkError?: Error & { bodyText?: string; statusCode?: number };
          };
          // A truncated/non-JSON HTTP response surfaces as a JSON.parse
          // failure on the network error. The base64-encoded zip can exceed
          // proxy/server body limits, causing the upstream response to be
          // returned as HTML or chopped mid-stream. Translate that into an
          // actionable message so users aren't stuck on Apollo's dev-link
          // "Unable to fetch error code" page.
          const networkMessage = apolloError.networkError?.message ?? "";
          const isJsonParseFailure =
            /JSON\.parse|Unexpected token|Unexpected end of JSON/i.test(
              networkMessage
            ) ||
            /JSON\.parse|Unexpected token|Unexpected end of JSON/i.test(
              error.message
            );
          if (isJsonParseFailure) {
            errorMessage =
              "Server returned an invalid response. The ZIP may be too " +
              "large or the server is unavailable. Try a smaller archive " +
              "or retry shortly.";
          } else {
            errorMessage =
              apolloError.graphQLErrors?.[0]?.message ||
              error.message ||
              errorMessage;
          }
        }
        toast.error(`Upload failed: ${errorMessage}`);
        return false;
      }
    },
    [makePublic, uploadZipMutation]
  );

  return {
    uploadSingleFile,
    uploadFiles,
    uploadZipFile,
    isUploading,
  };
}

export default useUploadMutations;
