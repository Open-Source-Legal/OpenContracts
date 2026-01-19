// frontend/src/components/widgets/modals/BulkUploadModal.tsx
import React, { useState, useRef } from "react";
import { useMutation, useReactiveVar } from "@apollo/client";
import { Button, Form, Message, FormField } from "semantic-ui-react";
import { toast } from "react-toastify";
import { gql } from "@apollo/client";
import {
  FileArchive,
  AlertCircle,
  ArrowLeftRight,
  CloudUpload,
  FolderOpen,
  Loader2,
} from "lucide-react";

import { showBulkUploadModal } from "../../../graphql/cache";
import { CorpusType } from "../../../types/graphql-api";
import { CorpusDropdown } from "../selectors/CorpusDropdown";
import {
  StyledUploadModal,
  ModalHeader,
  ModalHeaderContent,
  DropZone,
  DropZoneIcon,
  DropZoneText,
  DropZoneButton,
  UploadProgress,
  ActionButton,
  FieldLabel,
  ErrorMessage,
} from "./UploadModalStyles";

// Define the mutation GraphQL string (Renamed back)
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

// Define types for mutation variables and output (These should ideally live in graphql/mutations.ts)
interface UploadDocumentsZipVars {
  base64FileString: string;
  makePublic: boolean; // Assuming default public for simplicity, can add checkbox
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

export const BulkUploadModal = () => {
  const visible = useReactiveVar(showBulkUploadModal);
  // Remove dependency on filterToCorpus
  // const currentCorpus = useReactiveVar(filterToCorpus);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [base64File, setBase64File] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  // Add state for the selected corpus within the modal
  const [targetCorpus, setTargetCorpus] = useState<CorpusType | null>(null);

  const [uploadZipMutation] = useMutation<
    UploadDocumentsZipOutput,
    UploadDocumentsZipVars
  >(UPLOAD_DOCUMENTS_ZIP);

  /**
   * Resets all modal state and closes the modal.
   */
  const handleClose = () => {
    setSelectedFile(null);
    setBase64File(null);
    setLoading(false);
    setError(null);
    setUploadProgress(0);
    setTargetCorpus(null); // Reset target corpus on close
    showBulkUploadModal(false);
  };

  /**
   * Handles the file input change event, validates the file type,
   * and converts the selected file to a base64 string.
   * @param event - The input change event.
   */
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setError(null); // Clear previous errors
    const file = event.target.files?.[0];
    if (file) {
      if (file.type === "application/zip" || file.name.endsWith(".zip")) {
        setSelectedFile(file);
        // Convert file to Base64
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
          const base64 = (reader.result as string).split(",")[1]; // Remove "data:mime/type;base64," part
          setBase64File(base64);
        };
        reader.onerror = (error) => {
          console.error("Error reading file:", error);
          setError("Failed to read the selected file.");
          setSelectedFile(null);
          setBase64File(null);
        };
      } else {
        setError("Invalid file type. Please select a .zip file.");
        setSelectedFile(null);
        setBase64File(null);
        // Reset file input visually
        if (event.target) {
          event.target.value = "";
        }
      }
    } else {
      // Handle case where user cancels file selection
      setSelectedFile(null);
      setBase64File(null);
    }
  };

  /**
   * Handles the form submission, sending the base64 encoded file
   * and selected options to the backend mutation.
   */
  const handleSubmit = async () => {
    if (!base64File) {
      setError("No file selected or file could not be read.");
      return;
    }

    setLoading(true);
    setError(null);
    setUploadProgress(50); // Indicate processing started

    try {
      const result = await uploadZipMutation({
        variables: {
          base64FileString: base64File,
          makePublic: true, // TODO: Consider adding a checkbox for this
          addToCorpusId: targetCorpus?.id ?? null, // Use the locally selected corpus ID
          // titlePrefix: "", // Optional: Add fields if needed
          // description: "", // Optional: Add fields if needed
        },
      });

      setUploadProgress(100); // Indicate near completion

      if (result.data?.uploadDocumentsZip.ok) {
        toast.success(
          `Upload job started successfully! Job ID: ${result.data.uploadDocumentsZip.jobId}`
        );
        handleClose(); // Close modal on success
      } else {
        throw new Error(
          result.data?.uploadDocumentsZip.message || "Upload failed."
        );
      }
    } catch (err: any) {
      console.error("Upload error:", err);
      // Extract GraphQL errors explicitly, falling back to general message
      const errorMessage =
        err.graphQLErrors?.[0]?.message ||
        err.message ||
        "An unexpected error occurred during upload.";
      setError(errorMessage);
      toast.error(`Upload failed: ${errorMessage}`);
      setUploadProgress(0); // Reset progress on error
    } finally {
      setLoading(false);
    }
  };

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDropZoneClick = () => {
    if (!loading && fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <StyledUploadModal open={visible} onClose={handleClose} size="small">
      <StyledUploadModal.Header>
        <ModalHeader>
          <FileArchive size={24} />
          <ModalHeaderContent>
            <span className="title">Bulk Upload Documents</span>
            <span className="subtitle">
              Upload multiple PDFs from a ZIP file
            </span>
          </ModalHeaderContent>
        </ModalHeader>
      </StyledUploadModal.Header>
      <StyledUploadModal.Content>
        <Form loading={loading} error={!!error}>
          {/* Error Message Display */}
          {error && (
            <ErrorMessage>
              <AlertCircle size={24} className="icon" />
              <div className="content">
                <div className="header">Upload Error</div>
                <div className="message">{error}</div>
              </div>
            </ErrorMessage>
          )}

          {/* File Drop Zone */}
          <DropZone
            $hasFiles={!!selectedFile}
            onClick={handleDropZoneClick}
            style={{ marginBottom: "1.5rem" }}
          >
            <input
              id="bulk-upload-file-input"
              ref={fileInputRef}
              type="file"
              accept=".zip,application/zip"
              onChange={handleFileChange}
              disabled={loading}
              aria-label="Select ZIP file for bulk upload"
              style={{ display: "none" }}
            />
            {selectedFile ? (
              <>
                <DropZoneIcon>
                  <FileArchive size={32} />
                </DropZoneIcon>
                <DropZoneText>
                  <div className="primary-text">{selectedFile.name}</div>
                  <div className="secondary-text">
                    {formatFileSize(selectedFile.size)}
                  </div>
                </DropZoneText>
                <DropZoneButton
                  onClick={(e: React.MouseEvent) => {
                    e.stopPropagation();
                    if (!loading && fileInputRef.current) {
                      fileInputRef.current.click();
                    }
                  }}
                >
                  <ArrowLeftRight size={16} /> Change File
                </DropZoneButton>
              </>
            ) : (
              <>
                <DropZoneIcon>
                  <CloudUpload size={32} />
                </DropZoneIcon>
                <DropZoneText>
                  <div className="primary-text">Click to select a ZIP file</div>
                  <div className="secondary-text">
                    The ZIP should contain PDF documents
                  </div>
                </DropZoneText>
                <DropZoneButton>
                  <FolderOpen size={16} /> Browse Files
                </DropZoneButton>
              </>
            )}
          </DropZone>

          {/* Corpus Selection Field */}
          <FormField>
            <FieldLabel>
              Add to Corpus{" "}
              <span style={{ color: "#868e96", fontWeight: 400 }}>
                (Optional)
              </span>
            </FieldLabel>
            <CorpusDropdown
              value={targetCorpus?.id ?? null}
              onChange={setTargetCorpus}
              clearable={true}
              placeholder="Select a corpus..."
            />
          </FormField>

          {/* Loading Progress */}
          {loading && uploadProgress > 0 && (
            <UploadProgress
              percent={uploadProgress}
              indicating={uploadProgress < 100}
              success={uploadProgress === 100}
              progress
            />
          )}
        </Form>
      </StyledUploadModal.Content>
      <StyledUploadModal.Actions>
        <ActionButton
          $variant="secondary"
          onClick={handleClose}
          disabled={loading}
        >
          Cancel
        </ActionButton>
        <ActionButton
          $variant="primary"
          onClick={handleSubmit}
          disabled={!selectedFile || !base64File || loading}
        >
          {loading && uploadProgress < 100 ? (
            <>
              <Loader2 size={16} className="animate-spin" /> Uploading...
            </>
          ) : (
            <>
              <CloudUpload size={16} /> Upload ZIP
            </>
          )}
        </ActionButton>
      </StyledUploadModal.Actions>
    </StyledUploadModal>
  );
};
